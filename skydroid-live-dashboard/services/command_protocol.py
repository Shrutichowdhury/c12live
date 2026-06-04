"""
command_protocol.py
-------------------
Real SkyDroid ASCII text protocol for the C12 gimbal camera.

PROTOCOL (reversed from official SkyDroid APK — SkydroidControl.java + UdpConnect.java)
========================================================================================

Frame format:
  <command_string><CRC>

  command_string : ASCII text, e.g. "#TPUG2wPTZ01"
  CRC            : sum of all bytes in command_string, mod 256, as 2-char UPPERCASE hex
                   e.g. sum("#TPUG2wPTZ01") & 0xFF = 0x6B  →  append "6B"
  Final wire bytes: UTF-8 encode(command_string + crc_hex)

Transport: UDP to camera port 37260 (also 9002 in some firmware).
           TCP also supported on same port.

Responses from camera are also ASCII strings starting with "#TP" or "AT+".

PTZ Commands (#TPUG2wPTZ<code>)
  00=STOP  01=UP  02=DOWN  03=LEFT  04=RIGHT  05=CENTER
  06=FOLLOW_MODE  07=LOCK_HEAD  08=FOLLOW_SWITCH  09=CALIBRATION
  0A=HOISTING  0B=INVERSION  0C=H_CAL  0D=V_CAL
  0E=X_ADD  0F=X_REDUCE  10=Y_ADD  11=Y_REDUCE  12=Z_ADD  13=Z_REDUCE
  14=CLEAR_ADJUST

Zoom (#TPUM2wZMC<code>):  00=STOP  01=IN  02=OUT
Focus (#TPUM2wFCC<code>): 00=STOP  01=ADD  02=REDUCE

Video (#TPUD2wREC<code>): 01=START  00=STOP  0A=FLIP
Photo: #TPUD2wCAP01

Query commands (read, prefix "r"):
  #TPUD2rVER00  — firmware version
  #TPUD2rREC00  — recording state
  #TPUD2rVOM00  — video config
  #TPUD2rIQE00  — image quality/effect config
"""

from __future__ import annotations
import logging

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
    Used for AT+LED and TempEnum commands which are sent without getCrc().
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
CMD_PTZ_CENTER       = lambda: ptz("05")   # return to center / back-mid
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
# Speed-based gimbal control (continuous, -99..99)
# ---------------------------------------------------------------------------

def int2hex(val: int) -> str:
    """
    Encode a signed integer as a 2-char signed hex string the way the app does.
    Positive: "01".."63"  Zero: "00"  Negative: appended as signed byte hex.
    The app uses int2Hex which formats as signed byte (FF=-1, FE=-2, …).
    """
    if val < -99:
        val = -99
    if val > 99:
        val = 99
    return f"{val & 0xFF:02X}"


def cmd_yaw_speed(speed: int) -> bytes:
    """#TPUG2wGSY<speed_hex> — yaw at signed speed -99..99."""
    return build(f"#TPUG2wGSY{int2hex(speed)}")


def cmd_pitch_speed(speed: int) -> bytes:
    """#TPUG2wGSP<speed_hex> — pitch at signed speed -99..99."""
    return build(f"#TPUG2wGSP{int2hex(speed)}")


# ---------------------------------------------------------------------------
# Angle control (set absolute angle in degrees * 100, encoded as signed short)
# ---------------------------------------------------------------------------

def short2hex(val: int) -> str:
    """Encode signed int as 4-char hex (big-endian signed short, like the app)."""
    val = max(-9000, min(9000, val))
    return f"{val & 0xFFFF:04X}"


def cmd_set_yaw_angle(degrees: float) -> bytes:
    """#TPUG6wGAY<angle_hex>10 — set absolute yaw angle."""
    return build(f"#TPUG6wGAY{short2hex(int(degrees * 100))}10")


def cmd_set_pitch_angle(degrees: float) -> bytes:
    """#TPUG6wGAP<angle_hex>10 — set absolute pitch angle."""
    return build(f"#TPUG6wGAP{short2hex(int(degrees * 100))}10")


def cmd_set_roll_angle(degrees: float) -> bytes:
    """#TPUG6wGAR<angle_hex>10 — set absolute roll angle."""
    return build(f"#TPUG6wGAR{short2hex(int(degrees * 100))}10")


# ---------------------------------------------------------------------------
# Zoom and Focus
# ---------------------------------------------------------------------------

CMD_ZOOM_STOP  = lambda: build("#TPUM2wZMC00")
CMD_ZOOM_IN    = lambda: build("#TPUM2wZMC01")
CMD_ZOOM_OUT   = lambda: build("#TPUM2wZMC02")

CMD_FOCUS_STOP    = lambda: build("#TPUM2wFCC00")
CMD_FOCUS_IN      = lambda: build("#TPUM2wFCC01")   # add / closer
CMD_FOCUS_OUT     = lambda: build("#TPUM2wFCC02")   # reduce / farther

CMD_ZOOM_DEFAULT  = lambda: build("#TPUD2wDZM0A")   # reset zoom to default
CMD_ZOOM_DIRECT   = lambda: build("#TPUD2wDZM0B")   # direct zoom mode


# ---------------------------------------------------------------------------
# Camera capture
# ---------------------------------------------------------------------------

CMD_TAKE_PHOTO     = lambda: build("#TPUD2wCAP01")
CMD_REC_START      = lambda: build("#TPUD2wREC01")
CMD_REC_STOP       = lambda: build("#TPUD2wREC00")
CMD_REC_FLIP       = lambda: build("#TPUD2wREC0A")  # flip recording


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
# System
# ---------------------------------------------------------------------------

CMD_RESET          = lambda: build("#TPUD2wRST00")
CMD_FACTORY_RESET  = lambda: build("#TPUD2wRTF01")

CMD_LED_ON         = lambda: build_raw("AT+LED -e1\r\n")
CMD_LED_OFF        = lambda: build_raw("AT+LED -e0\r\n")


# ---------------------------------------------------------------------------
# Palette list — kept for UI / MockController compatibility
# (The real C12 does not expose palette control over the control port)
# ---------------------------------------------------------------------------

THERMAL_PALETTES: list[str] = [
    "White Hot", "Black Hot", "Iron Red", "Rainbow",
    "Arctic", "Lava", "Medical", "Fusion", "Amber",
    "Red Hot", "Green Hot",
]


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def parse_response(raw: bytes) -> dict:
    """
    Attempt to parse an ASCII response from the camera.

    Camera responses look like: "#TPUD2rVER00<version_string><CRC>"
    or AT-style: "AT+t=<temperature>"

    Returns dict with keys: success, raw_text, data
    """
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return {"success": False, "error": str(e), "raw_hex": raw.hex()}

    logger.debug("RX: %s", text)
    result: dict = {"success": True, "raw_text": text}

    # Strip the trailing 2-char CRC if it looks like a #TP response
    if text.startswith("#TP") and len(text) > 14:
        # Last 2 chars are the CRC
        body = text[:-2]
        recv_crc = text[-2:]
        calc_crc = crc(body)
        result["crc_ok"] = (recv_crc.upper() == calc_crc.upper())
        result["body"] = body
        # Extract the 3-char tag (e.g. "VER", "REC", "VOM")
        if len(body) >= 12:
            result["tag"] = body[9:12]
            result["data"] = body[12:]
    elif text.startswith("AT+"):
        result["body"] = text
        result["tag"] = "AT"
        result["data"] = text

    return result
