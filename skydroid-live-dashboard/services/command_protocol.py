"""
command_protocol.py
-------------------
Human-readable command definitions and packet builder/parser for the SkyDroid C12.

The actual binary protocol details for the C12 over Ethernet are not publicly
documented. All low-level packet functions raise NotImplementedError so that the
rest of the application (API layer + UI) keeps working through MockController.
When you obtain the real protocol spec, fill in build_command() and
parse_response() — nothing else needs to change.
"""

from __future__ import annotations
import struct
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command name catalogue (used as keys everywhere)
# ---------------------------------------------------------------------------
COMMANDS = {
    # Gimbal motion
    "gimbal_pitch_up":      {"description": "Pitch gimbal upward",       "params": ["speed"]},
    "gimbal_pitch_down":    {"description": "Pitch gimbal downward",      "params": ["speed"]},
    "gimbal_yaw_left":      {"description": "Yaw gimbal left",            "params": ["speed"]},
    "gimbal_yaw_right":     {"description": "Yaw gimbal right",           "params": ["speed"]},
    "gimbal_roll_left":     {"description": "Roll gimbal left",           "params": ["speed"]},
    "gimbal_roll_right":    {"description": "Roll gimbal right",          "params": ["speed"]},
    "gimbal_stop":          {"description": "Stop all gimbal motion",     "params": []},
    "gimbal_center":        {"description": "Center all axes",            "params": []},
    "gimbal_center_yaw":    {"description": "Center yaw only",           "params": []},
    "gimbal_look_down":     {"description": "Look straight down",         "params": []},
    "gimbal_look_forward":  {"description": "Look straight forward",      "params": []},
    # Zoom
    "zoom_in":              {"description": "Zoom in one step",           "params": []},
    "zoom_out":             {"description": "Zoom out one step",          "params": []},
    "zoom_set":             {"description": "Set absolute zoom level",    "params": ["level"]},
    # Camera capture
    "camera_photo":         {"description": "Take a photo",               "params": []},
    "camera_rec_start":     {"description": "Start video recording",      "params": []},
    "camera_rec_stop":      {"description": "Stop video recording",       "params": []},
    # Tracking
    "tracking_enable":      {"description": "Enable target tracking",     "params": []},
    "tracking_disable":     {"description": "Disable target tracking",    "params": []},
    # Calibration
    "cal_temperature":      {"description": "Run temperature calibration","params": []},
    "cal_horizontal":       {"description": "Horizontal calibration",     "params": []},
    "cal_vertical":         {"description": "Vertical calibration",       "params": []},
    "cal_fine_adjust":      {"description": "Fine roll/pitch offset",     "params": ["roll_offset", "pitch_offset"]},
    # Working mode
    "mode_hoist":           {"description": "Switch to hoist mode",       "params": []},
    "mode_upside_down":     {"description": "Switch to upside-down mode", "params": []},
    # Speed mode
    "speed_mode":           {"description": "Set speed mode",             "params": ["mode"]},
    # Thermal settings
    "thermal_palette":      {"description": "Set thermal palette",        "params": ["name"]},
    "thermal_gain":         {"description": "Set thermal gain mode",      "params": ["mode"]},
    "thermal_temp_measure": {"description": "Toggle temp measurement",    "params": ["enabled"]},
    # Image settings
    "image_settings":       {"description": "Set brightness/contrast/saturation/sharpness",
                             "params": ["brightness", "contrast", "saturation", "sharpness"]},
    # System
    "system_reboot":        {"description": "Reboot camera",              "params": []},
    "system_firmware":      {"description": "Upgrade firmware",           "params": ["file_path"]},
}

# ---------------------------------------------------------------------------
# Palette catalogue
# ---------------------------------------------------------------------------
THERMAL_PALETTES = [
    "White Hot", "Black Hot", "Iron Red", "Rainbow",
    "Arctic", "Lava", "Medical", "Fusion",
    "Amber", "Red Hot", "Green Hot",
]

# ---------------------------------------------------------------------------
# Packet builder / parser
# ---------------------------------------------------------------------------

def build_command(name: str, params: dict | None = None) -> bytes:
    """
    Build a binary command packet for the C12.

    Replace the body of this function with real framing once the protocol
    spec is available. The current implementation raises NotImplementedError
    so callers know they must use MockController until the spec is known.

    Args:
        name:   One of the keys in COMMANDS.
        params: Optional dict of parameter values (e.g. {"speed": 50}).

    Returns:
        Raw bytes ready to send over the control socket.

    Raises:
        ValueError:          If `name` is not a recognised command.
        NotImplementedError: Always — real packet format is unknown.
    """
    if name not in COMMANDS:
        raise ValueError(f"Unknown command: {name!r}. Valid: {list(COMMANDS)}")

    params = params or {}
    logger.debug("build_command(%s, %s) called — protocol not implemented", name, params)

    # ------------------------------------------------------------------ #
    # TODO: replace with real packet framing when the spec is available.  #
    # Example skeleton (little-endian, 8-byte header):                    #
    #                                                                      #
    #   MAGIC   = 0x5A5A                                                  #
    #   cmd_id  = COMMAND_IDS[name]                                        #
    #   payload = encode_params(params)                                    #
    #   length  = len(payload)                                             #
    #   checksum = crc16(payload)                                          #
    #   packet = struct.pack("<HHH", MAGIC, cmd_id, length) + payload +   #
    #            struct.pack("<H", checksum)                               #
    #   return packet                                                      #
    # ------------------------------------------------------------------ #

    raise NotImplementedError(
        "Real C12 command protocol is not yet implemented. "
        "Use MockController (USE_MOCK_CONTROLLER = True) or fill in "
        "build_command() once the Ethernet spec is known."
    )


def parse_response(data: bytes) -> dict:
    """
    Parse a raw response packet from the C12.

    Same caveat as build_command — fill this in when the spec is known.

    Args:
        data: Raw bytes received from the control socket.

    Returns:
        Dict with at minimum {"success": bool, "raw": <hex string>}.

    Raises:
        NotImplementedError: Always — real response format is unknown.
    """
    logger.debug("parse_response(%d bytes) called — protocol not implemented", len(data))

    raise NotImplementedError(
        "Real C12 response parsing is not yet implemented."
    )
