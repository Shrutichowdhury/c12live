"""
command_protocol.py
-------------------
Binary command protocol for the SkyDroid C12 over Ethernet.

Frame format (SIYI SDK-compatible — the standard used by Skydroid, SIYI,
and many other Chinese Ethernet gimbal cameras):

  [0x55][0x66][CTRL][LEN_L][LEN_H][SEQ_L][SEQ_H][CMD_ID][DATA…][CRC_L][CRC_H]

  CTRL   : 0x01 = request, 0x02 = response
  LEN    : uint16 little-endian — length of DATA only (not header/CRC)
  SEQ    : uint16 little-endian — sequence number, auto-incremented by caller
  CRC    : CRC-16/IBM (ARC) over bytes [2 … last DATA byte] (excludes STX)

References
----------
  • SIYI SDK protocol spec (public): https://github.com/mzahana/siyi_sdk
  • Community reverse-engineering of Skydroid T-series / C-series cameras.
"""

from __future__ import annotations
import struct
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frame constants
# ---------------------------------------------------------------------------
STX_HIGH  = 0x55
STX_LOW   = 0x66
CTRL_REQ  = 0x01   # outgoing request
CTRL_RSP  = 0x02   # incoming response

# ---------------------------------------------------------------------------
# Command ID catalogue
# ---------------------------------------------------------------------------
class CMD:
    FIRMWARE_VERSION   = 0x01
    HARDWARE_ID        = 0x02
    AUTO_FOCUS         = 0x04
    VIDEO_RECORD       = 0x05   # data: 0x01=start  0x02=stop
    TAKE_PHOTO         = 0x06
    GIMBAL_ATTITUDE    = 0x07   # query — camera replies with roll/pitch/yaw
    FUNC_FEEDBACK      = 0x08
    PHOTO_FUNC         = 0x0C
    CENTER_GIMBAL      = 0x0D   # data: 0x01
    GIMBAL_ROTATE      = 0x0E   # data: [yaw_speed int8, pitch_speed int8]  -100…100
    SET_ZOOM           = 0x0F   # data: [zoom uint8]  1-30
    HYBRID_ZOOM        = 0x12   # same structure on some firmware
    ZOOM_IN_STEP       = 0x14
    ZOOM_OUT_STEP      = 0x15
    MAX_ZOOM           = 0x16
    FOCUS_IN           = 0x18
    FOCUS_OUT          = 0x19
    PALETTE            = 0x20   # data: [palette_id uint8]
    THERMAL_GAIN       = 0x22   # data: [0x00=low 0x01=high 0xFF=auto]
    TEMP_MEASURE       = 0x24   # data: [0x00=off 0x01=on]
    IMAGE_SETTINGS     = 0x30   # data: [brightness, contrast, saturation, sharpness] each uint8 0-100
    LOOK_DOWN          = 0x40   # look straight down (nadir)
    LOOK_FORWARD       = 0x41
    SYSTEM_REBOOT      = 0x80

# ---------------------------------------------------------------------------
# Palette name → ID mapping (SIYI ordering)
# ---------------------------------------------------------------------------
PALETTE_IDS: dict[str, int] = {
    "White Hot":  0,
    "Black Hot":  1,
    "Iron Red":   2,
    "Rainbow":    3,
    "Arctic":     4,
    "Lava":       5,
    "Medical":    6,
    "Fusion":     7,
    "Amber":      8,
    "Red Hot":    9,
    "Green Hot":  10,
}
THERMAL_PALETTES = list(PALETTE_IDS.keys())

# ---------------------------------------------------------------------------
# CRC-16/IBM (ARC) — polynomial 0x8005, init 0x0000, reflected in/out
# ---------------------------------------------------------------------------
_CRC16_TABLE: list[int] = []


def _init_crc16_table() -> None:
    poly = 0x8005
    for i in range(256):
        crc = 0
        c = i
        for _ in range(8):
            if (crc ^ c) & 0x0001:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
            c >>= 1
        _CRC16_TABLE.append(crc)


_init_crc16_table()


def crc16(data: bytes) -> int:
    """CRC-16/IBM (ARC) over *data*."""
    crc = 0x0000
    for byte in data:
        idx = (crc ^ byte) & 0xFF
        crc = ((crc >> 8) ^ _CRC16_TABLE[idx]) & 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Frame builder / parser
# ---------------------------------------------------------------------------

def build_frame(cmd_id: int, data: bytes = b"", seq: int = 0) -> bytes:
    """
    Build a complete SIYI-format request frame.

    Args:
        cmd_id: One of the CMD.* constants.
        data:   Payload bytes (may be empty).
        seq:    Sequence number (uint16, wraps at 65535).

    Returns:
        Ready-to-send bytes.
    """
    length = len(data)
    # Header bytes that are CRC'd (everything except the two STX bytes)
    crc_payload = struct.pack("<BHHB", CTRL_REQ, length, seq & 0xFFFF, cmd_id) + data
    checksum = crc16(crc_payload)
    frame = bytes([STX_HIGH, STX_LOW]) + crc_payload + struct.pack("<H", checksum)
    logger.debug("TX  cmd=0x%02X seq=%d len=%d  %s", cmd_id, seq, length, frame.hex())
    return frame


def parse_frame(data: bytes) -> dict:
    """
    Parse a raw SIYI-format response frame.

    Returns a dict with keys:
      success, cmd_id, seq, payload, raw_hex

    On parse error sets success=False and adds an 'error' key.
    """
    if len(data) < 10:
        return {"success": False, "error": f"Frame too short ({len(data)} bytes)", "raw_hex": data.hex()}
    if data[0] != STX_HIGH or data[1] != STX_LOW:
        return {"success": False, "error": f"Bad STX: {data[0]:02X} {data[1]:02X}", "raw_hex": data.hex()}
    ctrl, length, seq, cmd_id = struct.unpack_from("<BHHB", data, 2)
    payload_start = 9
    payload_end   = payload_start + length
    if len(data) < payload_end + 2:
        return {"success": False, "error": "Frame truncated", "raw_hex": data.hex()}
    payload  = data[payload_start:payload_end]
    crc_recv = struct.unpack_from("<H", data, payload_end)[0]
    crc_calc = crc16(data[2:payload_end])
    if crc_recv != crc_calc:
        logger.warning("CRC mismatch: recv=0x%04X calc=0x%04X", crc_recv, crc_calc)
    logger.debug("RX  cmd=0x%02X seq=%d len=%d payload=%s", cmd_id, seq, length, payload.hex())
    return {
        "success": True,
        "cmd_id":  cmd_id,
        "seq":     seq,
        "payload": payload,
        "raw_hex": data.hex(),
    }


# ---------------------------------------------------------------------------
# High-level command builders (return ready-to-send bytes)
# ---------------------------------------------------------------------------

def cmd_gimbal_rotate(yaw_speed: int, pitch_speed: int, seq: int = 0) -> bytes:
    """Send continuous gimbal rotation.  Speeds are signed int8 (-100…100)."""
    yaw_speed   = max(-100, min(100, int(yaw_speed)))
    pitch_speed = max(-100, min(100, int(pitch_speed)))
    data = struct.pack("<bb", yaw_speed, pitch_speed)
    return build_frame(CMD.GIMBAL_ROTATE, data, seq)


def cmd_gimbal_stop(seq: int = 0) -> bytes:
    """Stop all gimbal motion (send zero speeds)."""
    return cmd_gimbal_rotate(0, 0, seq)


def cmd_center_gimbal(seq: int = 0) -> bytes:
    return build_frame(CMD.CENTER_GIMBAL, bytes([0x01]), seq)


def cmd_look_down(seq: int = 0) -> bytes:
    return build_frame(CMD.LOOK_DOWN, b"", seq)


def cmd_look_forward(seq: int = 0) -> bytes:
    return build_frame(CMD.LOOK_FORWARD, b"", seq)


def cmd_take_photo(seq: int = 0) -> bytes:
    return build_frame(CMD.TAKE_PHOTO, b"", seq)


def cmd_record_start(seq: int = 0) -> bytes:
    return build_frame(CMD.VIDEO_RECORD, bytes([0x01]), seq)


def cmd_record_stop(seq: int = 0) -> bytes:
    return build_frame(CMD.VIDEO_RECORD, bytes([0x02]), seq)


def cmd_zoom_in(seq: int = 0) -> bytes:
    return build_frame(CMD.ZOOM_IN_STEP, b"", seq)


def cmd_zoom_out(seq: int = 0) -> bytes:
    return build_frame(CMD.ZOOM_OUT_STEP, b"", seq)


def cmd_set_zoom(level: int, seq: int = 0) -> bytes:
    level = max(1, min(30, int(level)))
    return build_frame(CMD.SET_ZOOM, bytes([level]), seq)


def cmd_set_palette(name: str, seq: int = 0) -> bytes:
    pid = PALETTE_IDS.get(name, 0)
    return build_frame(CMD.PALETTE, bytes([pid]), seq)


def cmd_thermal_gain(mode: str, seq: int = 0) -> bytes:
    m = {"low": 0x00, "high": 0x01, "auto": 0xFF}.get(mode.lower(), 0xFF)
    return build_frame(CMD.THERMAL_GAIN, bytes([m]), seq)


def cmd_temp_measure(enabled: bool, seq: int = 0) -> bytes:
    return build_frame(CMD.TEMP_MEASURE, bytes([0x01 if enabled else 0x00]), seq)


def cmd_image_settings(brightness: int = 50, contrast: int = 50,
                       saturation: int = 50, sharpness: int = 50,
                       seq: int = 0) -> bytes:
    def clamp(v): return max(0, min(100, int(v)))
    data = bytes([clamp(brightness), clamp(contrast), clamp(saturation), clamp(sharpness)])
    return build_frame(CMD.IMAGE_SETTINGS, data, seq)


def cmd_query_attitude(seq: int = 0) -> bytes:
    return build_frame(CMD.GIMBAL_ATTITUDE, b"", seq)


def cmd_reboot(seq: int = 0) -> bytes:
    return build_frame(CMD.SYSTEM_REBOOT, b"", seq)


# ---------------------------------------------------------------------------
# Legacy stub kept so existing callers that import build_command still compile
# ---------------------------------------------------------------------------
COMMANDS: dict = {}  # kept for import compatibility


def build_command(name: str, params: dict | None = None) -> bytes:
    """Legacy shim — prefer the cmd_* functions above."""
    raise NotImplementedError(
        "Use the cmd_* helpers (cmd_gimbal_rotate, cmd_center_gimbal, …) directly."
    )
