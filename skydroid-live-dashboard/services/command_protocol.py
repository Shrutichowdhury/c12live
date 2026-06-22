"""
command_protocol.py
-------------------
Real SkyDroid ASCII text protocol for the C12 gimbal camera.

PROTOCOL (confirmed from official SkyDroid SDK AAR v1.9.1 + APK decompile)
============================================================================

Frame format:
  <command_string><CRC>

  command_string : ASCII text, e.g. "#TPUG2wPTZ01"
  CRC            : sum of all bytes in command_string, mod 256, as 2-char UPPERCASE hex
                   e.g. sum("#TPUG2wPTZ01") & 0xFF = 0x6B  →  append "6B"
  Final wire bytes: UTF-8 encode(command_string + crc_hex)

Transport: UDP to camera port 5000 (PayloadManager.getUDPPayload(C12, 5000, ip, 5000))
           Port 9002 is sometimes also used in older firmware.

Responses from camera are ASCII strings starting with "#TP" or "AT+".

Command encoding guide (the digit after "TPUG"/"TPUD"/"TPUM" = hex length of data after 3-char name):
  #TPUG2wPTZ<2>  — PTZ gimbal direction (1 byte → 2 hex chars)
  #TPUG2wGSY<2>  — yaw speed (signed byte → 2 hex chars)
  #TPUG2wGSP<2>  — pitch speed (signed byte → 2 hex chars)
  #TPUG6wGAY<6>  — goto yaw angle (int16×100 → 4 hex, then "10" flag)
  #TPUG6wGAP<6>  — goto pitch angle (same)
  #TPUGCwGAM<C>  — goto yaw+pitch+roll simultaneously (3×int16 = 12 hex)
  #TPUD2wDZM<2>  — set zoom ratio 0-4 (0=original, 1-4=digital zoom)
  #TPUD2wIMG<2>  — set thermal palette (0=WHITE_HOT..9=GLORY_HOT)
  #TPUDFwTIM<15> — sync time (HHmmssddMMyy.00 = 15 chars, F=15 in hex)

PTZ Commands (#TPUG2wPTZ<code>)
  00=STOP  01=UP  02=DOWN  03=LEFT  04=RIGHT  05=CENTER
  06=FOLLOW_MODE  07=LOCK_HEAD  08=FOLLOW_SWITCH  09=CALIBRATION
  0A=HOISTING  0B=INVERSION  0C=H_CAL  0D=V_CAL
  0E=X_ADD  0F=X_REDUCE  10=Y_ADD  11=Y_REDUCE  12=Z_ADD  13=Z_REDUCE
  14=CLEAR_ADJUST

Zoom (#TPUM2wZMC<code>):  00=STOP  01=IN  02=OUT  (continuous)
Focus (#TPUM2wFCC<code>): 00=STOP  01=ADD  02=REDUCE

Video (#TPUD2wREC<code>): 01=START  00=STOP
Photo: #TPUD2wCAP01

Query commands (read, position 6 = "r"):
  #TPUD2rVER00  — firmware version
  #TPUD2rREC00  — recording state
  #TPUD2rVID00  — video resolution
  #TPUD2rVOM00  — video output mode/config
  #TPUD2rIQE00  — image quality/effect config
  #TPUD2rIMG00  — current thermal palette
  #TPUD2rDZM00  — current zoom ratio
  #TPUD2rIPV00  — IP address
  #TPUD2rGTW00  — gateway
  #TPUD2rMOD00  — camera mode
  #TPUD2rSDC01  — SD card capacity

Speed encoding: signed 8-bit integer, big-endian 2-char hex
  +100 → "64"   +30 → "1E"   0 → "00"   -30 → "E2"   -100 → "9C"
  Confirmed from SDK demo: #TPUG2wGSY6469 (yaw=+100), #TPUG2wGSY9C7B (yaw=-100)
                           #TPUG2wGSP6460 (pitch=+100), #TPUG2wGSP9C72 (pitch=-100)

Angle encoding: signed 16-bit big-endian × 100 (units = 0.01°), then "10" suffix
  +30.0° → int 3000 → 0x0BB8 → "0BB8"  → "#TPUG6wGAY0BB810" + CRC
  -90.0° → int -9000 → 0xDC18 → "DC18" → "#TPUG6wGAP DC1810" + CRC
"""

from __future__ import annotations
import logging
import struct
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRC algorithm (from UdpConnect.java getCrc())
#   sum all bytes of the command string, take low byte, format as 2-char hex
# ---------------------------------------------------------------------------

def crc(cmd: str) -> str:
    """Return 2-char uppercase hex checksum for *cmd*."""
    total = sum(cmd.encode("utf-8")) & 0xFF
    return f"{total:02X}"


def build(cmd: str) -> bytes:
    """
    Append CRC to *cmd* and return the full UTF-8 frame ready to send.

    Example:
      build("#TPUG2wPTZ01") -> b"#TPUG2wPTZ016B"
    """
    frame = cmd + crc(cmd)
    logger.debug("TX: %s", frame)
    return frame.encode("utf-8")


def build_raw(data: str) -> bytes:
    """
    Send *data* verbatim (no CRC appended).
    Used for AT+LED and similar commands sent without getCrc().
    """
    logger.debug("TX raw: %s", data)
    return data.encode("utf-8")


# ---------------------------------------------------------------------------
# PTZ gimbal direction
# ---------------------------------------------------------------------------

def ptz(code: str) -> bytes:
    """Build a PTZ control command.  code is 2-char hex like "01"."""
    return build(f"#TPUG2wPTZ{code}")


CMD_PTZ_STOP         = lambda: ptz("00")
CMD_PTZ_UP           = lambda: ptz("01")   # pitch up
CMD_PTZ_DOWN         = lambda: ptz("02")   # pitch down
CMD_PTZ_LEFT         = lambda: ptz("03")   # yaw left
CMD_PTZ_RIGHT        = lambda: ptz("04")   # yaw right
CMD_PTZ_CENTER       = lambda: ptz("05")   # return to center
CMD_PTZ_FOLLOW       = lambda: ptz("06")   # follow mode
CMD_PTZ_LOCK         = lambda: ptz("07")   # lock head mode
CMD_PTZ_FOLLOW_SW    = lambda: ptz("08")   # follow switch
CMD_PTZ_CALIBRATE    = lambda: ptz("09")   # full calibration
CMD_PTZ_HOIST        = lambda: ptz("0A")   # hoisting / upright mount
CMD_PTZ_INVERT       = lambda: ptz("0B")   # inversion / inverted mount
CMD_PTZ_H_CAL        = lambda: ptz("0C")   # horizontal calibration
CMD_PTZ_V_CAL        = lambda: ptz("0D")   # vertical calibration
CMD_PTZ_X_ADD        = lambda: ptz("0E")   # X trim +
CMD_PTZ_X_REDUCE     = lambda: ptz("0F")   # X trim -
CMD_PTZ_Y_ADD        = lambda: ptz("10")   # Y trim +
CMD_PTZ_Y_REDUCE     = lambda: ptz("11")   # Y trim -
CMD_PTZ_Z_ADD        = lambda: ptz("12")   # Z trim +
CMD_PTZ_Z_REDUCE     = lambda: ptz("13")   # Z trim -
CMD_PTZ_CLEAR_ADJ    = lambda: ptz("14")   # clear all adjustments


# ---------------------------------------------------------------------------
# Speed-based gimbal control (continuous, -100..100)
# Encoding: signed byte as 2-char hex (e.g. +100 → "64", -100 → "9C")
# Verified from SDK demo source with real CRC examples.
# ---------------------------------------------------------------------------

def _signed_byte_hex(val: int) -> str:
    """
    Encode a signed integer (clamped -100..100) as 2-char hex.
    Uses signed byte interpretation: +100→"64", 0→"00", -100→"9C".
    """
    val = max(-100, min(100, int(val)))
    return f"{val & 0xFF:02X}"


def cmd_yaw_speed(speed: int) -> bytes:
    """
    #TPUG2wGSY<hex> — continuous yaw at signed speed -100..100.
    Positive = right, negative = left.
    Example: speed=100 → #TPUG2wGSY6469
    """
    return build(f"#TPUG2wGSY{_signed_byte_hex(speed)}")


def cmd_pitch_speed(speed: int) -> bytes:
    """
    #TPUG2wGSP<hex> — continuous pitch at signed speed -100..100.
    Positive = up, negative = down.
    Example: speed=100 → #TPUG2wGSP6460
    """
    return build(f"#TPUG2wGSP{_signed_byte_hex(speed)}")


def cmd_stop_speed() -> bytes:
    """Send zero speed to both axes to stop continuous movement."""
    return build("#TPUG2wGSY00")


# ---------------------------------------------------------------------------
# Angle control (set absolute angle in degrees, encoded as degrees×100 as signed int16)
# Format: #TPUG6wGAY<4-hex-int16><2-hex-mode> + CRC
# The trailing "10" is a movement-mode byte (0x10 = smooth/timed).
# Range: -90.0° to +90.0° (int16 range: -9000 to +9000)
# ---------------------------------------------------------------------------

def _int16_hex(val: int) -> str:
    """Encode signed int as 4-char big-endian hex (signed 16-bit)."""
    val = max(-32768, min(32767, int(val)))
    return f"{val & 0xFFFF:04X}"


def cmd_goto_yaw(degrees: float) -> bytes:
    """
    #TPUG6wGAY<angle_hex>10 — go to absolute yaw angle.
    degrees: -90.0 to +90.0  (positive = right)
    Encodes as degrees × 100 as signed int16 big-endian.
    """
    scaled = int(round(degrees * 100))
    return build(f"#TPUG6wGAY{_int16_hex(scaled)}10")


def cmd_goto_pitch(degrees: float) -> bytes:
    """
    #TPUG6wGAP<angle_hex>10 — go to absolute pitch angle.
    degrees: -90.0 to +90.0  (positive = up, -90 = straight down)
    """
    scaled = int(round(degrees * 100))
    return build(f"#TPUG6wGAP{_int16_hex(scaled)}10")


def cmd_goto_roll(degrees: float) -> bytes:
    """#TPUG6wGAR<angle_hex>10 — go to absolute roll angle."""
    scaled = int(round(degrees * 100))
    return build(f"#TPUG6wGAR{_int16_hex(scaled)}10")


# Keep legacy aliases for existing code
cmd_set_yaw_angle   = cmd_goto_yaw
cmd_set_pitch_angle = cmd_goto_pitch
cmd_set_roll_angle  = cmd_goto_roll


# ---------------------------------------------------------------------------
# Zoom (continuous in/out + discrete ratio 0-4)
# ---------------------------------------------------------------------------

CMD_ZOOM_STOP  = lambda: build("#TPUM2wZMC00")
CMD_ZOOM_IN    = lambda: build("#TPUM2wZMC01")
CMD_ZOOM_OUT   = lambda: build("#TPUM2wZMC02")

CMD_FOCUS_STOP    = lambda: build("#TPUM2wFCC00")
CMD_FOCUS_IN      = lambda: build("#TPUM2wFCC01")   # add / closer
CMD_FOCUS_OUT     = lambda: build("#TPUM2wFCC02")   # reduce / farther


def cmd_set_zoom_ratio(ratio: int) -> bytes:
    """
    #TPUD2wDZM0<ratio_hex> — set discrete zoom level.
    ratio: 0=original image, 1-4=digital zoom levels
    Confirmed from SDK TopCameraCore: setZoomRatios(int)
    """
    ratio = max(0, min(4, int(ratio)))
    return build(f"#TPUD2wDZM0{ratio:X}")


CMD_ZOOM_QUERY = lambda: build("#TPUD2rDZM00")


# ---------------------------------------------------------------------------
# Thermal palette
# SDK ThermalPalette enum (ordinal 0-9, confirmed from AAR class extraction):
#   0=WHITE_HOT  1=SEPIA  2=IRONBOW  3=RAINBOW  4=AURORA
#   5=RED_HOT    6=JUNGLE 7=MEDICAL  8=BLACK_HOT 9=GLORY_HOT
# Command: #TPUD2wIMG<index:02X>  (SDK TopCameraCore.setThermalPalette)
# ---------------------------------------------------------------------------

THERMAL_PALETTES: list[dict] = [
    {"index": 0,  "sdk": "WHITE_HOT",  "label": "White Hot"},
    {"index": 1,  "sdk": "SEPIA",      "label": "Sepia"},
    {"index": 2,  "sdk": "IRONBOW",    "label": "Iron Bow"},
    {"index": 3,  "sdk": "RAINBOW",    "label": "Rainbow"},
    {"index": 4,  "sdk": "AURORA",     "label": "Aurora"},
    {"index": 5,  "sdk": "RED_HOT",    "label": "Red Hot"},
    {"index": 6,  "sdk": "JUNGLE",     "label": "Jungle"},
    {"index": 7,  "sdk": "MEDICAL",    "label": "Medical"},
    {"index": 8,  "sdk": "BLACK_HOT",  "label": "Black Hot"},
    {"index": 9,  "sdk": "GLORY_HOT",  "label": "Glory Hot"},
    {"index": 10, "sdk": "NIGHT",      "label": "Night"},
]

# Also keep flat list for backward-compat
THERMAL_PALETTE_NAMES: list[str] = [p["label"] for p in THERMAL_PALETTES]


def cmd_set_thermal_palette(index: int) -> bytes:
    """
    #TPUD2wIMG<index:02X> — set thermal camera palette.
    index: 0 (WHITE_HOT) to 9 (GLORY_HOT)
    """
    index = max(0, min(10, int(index)))
    return build(f"#TPUD2wIMG{index:02X}")


CMD_THERMAL_QUERY = lambda: build("#TPUD2rIMG00")


# ---------------------------------------------------------------------------
# Camera capture
# ---------------------------------------------------------------------------

CMD_TAKE_PHOTO     = lambda: build("#TPUD2wCAP01")
CMD_REC_START      = lambda: build("#TPUD2wREC01")
CMD_REC_STOP       = lambda: build("#TPUD2wREC00")
CMD_REC_FLIP       = lambda: build("#TPUD2wREC0A")


# ---------------------------------------------------------------------------
# Query commands (camera replies with ASCII data)
# ---------------------------------------------------------------------------

CMD_QUERY_VERSION   = lambda: build("#TPUD2rVER00")
CMD_QUERY_REC       = lambda: build("#TPUD2rREC00")
CMD_QUERY_VID       = lambda: build("#TPUD2rVID00")
CMD_QUERY_VOM       = lambda: build("#TPUD2rVOM00")
CMD_QUERY_IQE       = lambda: build("#TPUD2rIQE00")
CMD_QUERY_IP        = lambda: build("#TPUD2rIPV00")
CMD_QUERY_GATEWAY   = lambda: build("#TPUD2rGTW00")
CMD_QUERY_MODE      = lambda: build("#TPUD2rMOD00")
CMD_QUERY_SD        = lambda: build("#TPUD2rSDC01")
CMD_QUERY_THERMAL_B = lambda: build("#TPUD2rTIB00")
CMD_QUERY_THERMAL_C = lambda: build("#TPUD2rTIC00")


# ---------------------------------------------------------------------------
# Time synchronisation
# SDK: setTime(timestamp_ms) → #TPUDFwTIM + HHmmss + ddMMyy + .00
# "F" (hex) = 15 = length of time+date+suffix string
# Must be called AFTER video output starts (SDK note).
# ---------------------------------------------------------------------------

def cmd_set_time(timestamp_ms: int | None = None) -> bytes:
    """
    #TPUDFwTIM<HHmmss><ddMMyy>.00 — sync camera clock.
    timestamp_ms: Unix timestamp in milliseconds; defaults to now (UTC).
    """
    if timestamp_ms is None:
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    time_str = dt.strftime("%H%M%S")   # HHmmss
    date_str = dt.strftime("%d%m%y")   # ddMMyy
    return build(f"#TPUDFwTIM{time_str}{date_str}.00")


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

CMD_RESET          = lambda: build("#TPUD2wRST00")
CMD_FACTORY_RESET  = lambda: build("#TPUD2wRTF01")

CMD_LED_ON         = lambda: build_raw("AT+LED -e1\r\n")
CMD_LED_OFF        = lambda: build_raw("AT+LED -e0\r\n")


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def parse_response(raw: bytes) -> dict:
    """
    Attempt to parse an ASCII response from the camera.

    Camera responses look like: "#TPUD2rVER00<version_string><CRC>"
    or AT-style: "AT+INFO ..."

    Returns dict with keys: success, raw_text, tag, data, crc_ok
    """
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return {"success": False, "error": str(e), "raw_hex": raw.hex()}

    logger.debug("RX: %s", text)
    result: dict = {"success": True, "raw_text": text}

    if text.startswith("#TP") and len(text) > 14:
        body = text[:-2]
        recv_crc = text[-2:]
        calc_crc = crc(body)
        result["crc_ok"] = (recv_crc.upper() == calc_crc.upper())
        result["body"] = body
        if len(body) >= 12:
            result["tag"] = body[9:12]
            result["data"] = body[12:]
    elif text.startswith("AT+"):
        result["body"] = text
        result["tag"] = "AT"
        result["data"] = text

    return result
