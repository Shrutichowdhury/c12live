"""
mock_controller.py
------------------
MockController — a fully functional in-memory simulation of the C12.

All commands are accepted and logged. State is updated so the UI
reflects realistic feedback without needing a real camera on the network.
Enable by setting mock_mode = True in the config (the default).
"""

from __future__ import annotations
import logging
import time
from services.command_protocol import THERMAL_PALETTES, THERMAL_PALETTE_NAMES

logger = logging.getLogger(__name__)


class MockController:
    """
    Simulates the SkyDroid C12 gimbal/camera controller.

    Every method logs the call, updates internal state, and returns a
    successful result dict so the REST layer behaves identically to a
    real-device scenario.
    """

    def __init__(self) -> None:
        self._state: dict = {
            "connected": True,
            "mock_mode": True,
            "recording": False,
            "tracking": False,
            "zoom": 1.0,
            "zoom_ratio": 0,
            "palette": THERMAL_PALETTES[0]["label"],
            "palette_index": 0,
            "thermal_gain": "auto",
            "temp_measurement": False,
            "brightness": 50,
            "contrast": 50,
            "saturation": 50,
            "sharpness": 50,
            "speed_mode": "constant",
            "working_mode": "normal",
            "gimbal_pitch": 0.0,
            "gimbal_yaw": 0.0,
            "gimbal_roll": 0.0,
            "last_command": None,
            "last_command_time": None,
        }
        logger.info("[MockController] Initialised — all commands will be simulated.")

    def _ok(self, command: str, **extra) -> dict:
        self._state["last_command"] = command
        self._state["last_command_time"] = time.strftime("%H:%M:%S")
        logger.info("[MockController] %-30s %s", command, extra or "")
        return {"success": True, "mock": True, "command": command, **extra}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> dict:
        self._state["connected"] = True
        return self._ok("connect")

    def disconnect(self) -> dict:
        self._state["connected"] = False
        return self._ok("disconnect")

    def get_status(self) -> dict:
        return {**self._state, "success": True, "mock": True}

    # ------------------------------------------------------------------
    # Gimbal direction (D-pad)
    # ------------------------------------------------------------------

    def pitch_up(self, speed: int = 50) -> dict:
        self._state["gimbal_pitch"] = min(90.0, self._state["gimbal_pitch"] + 2)
        return self._ok("pitch_up", speed=speed, pitch=self._state["gimbal_pitch"])

    def pitch_down(self, speed: int = 50) -> dict:
        self._state["gimbal_pitch"] = max(-90.0, self._state["gimbal_pitch"] - 2)
        return self._ok("pitch_down", speed=speed, pitch=self._state["gimbal_pitch"])

    def yaw_left(self, speed: int = 50) -> dict:
        self._state["gimbal_yaw"] = (self._state["gimbal_yaw"] - 2) % 360
        return self._ok("yaw_left", speed=speed, yaw=self._state["gimbal_yaw"])

    def yaw_right(self, speed: int = 50) -> dict:
        self._state["gimbal_yaw"] = (self._state["gimbal_yaw"] + 2) % 360
        return self._ok("yaw_right", speed=speed, yaw=self._state["gimbal_yaw"])

    def roll_left(self, speed: int = 50) -> dict:
        self._state["gimbal_roll"] = max(-30.0, self._state["gimbal_roll"] - 1)
        return self._ok("roll_left", speed=speed, roll=self._state["gimbal_roll"])

    def roll_right(self, speed: int = 50) -> dict:
        self._state["gimbal_roll"] = min(30.0, self._state["gimbal_roll"] + 1)
        return self._ok("roll_right", speed=speed, roll=self._state["gimbal_roll"])

    def stop_motion(self) -> dict:
        return self._ok("stop_motion")

    def center_all(self) -> dict:
        self._state["gimbal_pitch"] = 0.0
        self._state["gimbal_yaw"]   = 0.0
        self._state["gimbal_roll"]  = 0.0
        return self._ok("center_all")

    def center_yaw(self) -> dict:
        self._state["gimbal_yaw"] = 0.0
        return self._ok("center_yaw")

    def look_down(self) -> dict:
        self._state["gimbal_pitch"] = -90.0
        return self._ok("look_down", pitch=-90)

    def look_forward(self) -> dict:
        self._state["gimbal_pitch"] = 0.0
        return self._ok("look_forward", pitch=0)

    # ------------------------------------------------------------------
    # Speed-based continuous control (SDK: controlYaw / controlPitch)
    # ------------------------------------------------------------------

    def control_yaw(self, speed: int) -> dict:
        return self._ok("control_yaw", speed=speed)

    def control_pitch(self, speed: int) -> dict:
        return self._ok("control_pitch", speed=speed)

    def gimbal_speed(self, yaw_speed: int, pitch_speed: int) -> dict:
        return self._ok("gimbal_speed", yaw=yaw_speed, pitch=pitch_speed)

    # ------------------------------------------------------------------
    # Angle goto (SDK: gotoYaw / gotoPitch)
    # ------------------------------------------------------------------

    def goto_yaw(self, degrees: float) -> dict:
        self._state["gimbal_yaw"] = max(-90.0, min(90.0, float(degrees)))
        return self._ok("goto_yaw", degrees=degrees, yaw=self._state["gimbal_yaw"])

    def goto_pitch(self, degrees: float) -> dict:
        self._state["gimbal_pitch"] = max(-90.0, min(90.0, float(degrees)))
        return self._ok("goto_pitch", degrees=degrees, pitch=self._state["gimbal_pitch"])

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def zoom_in(self) -> dict:
        self._state["zoom"] = min(4.0, round(self._state["zoom"] + 0.25, 2))
        return self._ok("zoom_in", zoom=self._state["zoom"])

    def zoom_out(self) -> dict:
        self._state["zoom"] = max(1.0, round(self._state["zoom"] - 0.25, 2))
        return self._ok("zoom_out", zoom=self._state["zoom"])

    def zoom_stop(self) -> dict:
        return self._ok("zoom_stop")

    def set_zoom(self, level: float) -> dict:
        self._state["zoom"] = max(1.0, min(30.0, float(level)))
        return self._ok("set_zoom", zoom=self._state["zoom"])

    def set_zoom_ratio(self, ratio: int) -> dict:
        """Discrete zoom 0-4 (SDK: setZoomRatios). 0=original, 1-4=digital zoom."""
        ratio = max(0, min(4, int(ratio)))
        labels = ["1× (original)", "2× digital", "4× digital", "8× digital", "16× digital"]
        self._state["zoom_ratio"] = ratio
        self._state["zoom"] = [1.0, 2.0, 4.0, 8.0, 16.0][ratio]
        return self._ok("set_zoom_ratio", ratio=ratio, label=labels[ratio])

    # ------------------------------------------------------------------
    # Focus
    # ------------------------------------------------------------------

    def focus_in(self) -> dict:
        return self._ok("focus_in")

    def focus_out(self) -> dict:
        return self._ok("focus_out")

    def focus_stop(self) -> dict:
        return self._ok("focus_stop")

    # ------------------------------------------------------------------
    # Camera capture
    # ------------------------------------------------------------------

    def take_photo(self) -> dict:
        return self._ok("take_photo")

    def start_recording(self) -> dict:
        self._state["recording"] = True
        return self._ok("start_recording")

    def stop_recording(self) -> dict:
        self._state["recording"] = False
        return self._ok("stop_recording")

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def enable_tracking(self) -> dict:
        self._state["tracking"] = True
        return self._ok("enable_tracking")

    def disable_tracking(self) -> dict:
        self._state["tracking"] = False
        return self._ok("disable_tracking")

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def temperature_calibration(self) -> dict:
        return self._ok("temperature_calibration")

    def horizontal_calibration(self) -> dict:
        return self._ok("horizontal_calibration")

    def vertical_calibration(self) -> dict:
        return self._ok("vertical_calibration")

    def fine_adjust(self, roll_offset: float = 0.0, pitch_offset: float = 0.0) -> dict:
        return self._ok("fine_adjust", roll_offset=roll_offset, pitch_offset=pitch_offset)

    def clear_adjustments(self) -> dict:
        return self._ok("clear_adjustments")

    # ------------------------------------------------------------------
    # Working mode
    # ------------------------------------------------------------------

    def set_hoist_mode(self) -> dict:
        self._state["working_mode"] = "hoist"
        return self._ok("set_hoist_mode")

    def set_upside_down_mode(self) -> dict:
        self._state["working_mode"] = "upside_down"
        return self._ok("set_upside_down_mode")

    def set_follow_mode(self) -> dict:
        self._state["working_mode"] = "follow"
        return self._ok("set_follow_mode")

    def set_lock_mode(self) -> dict:
        self._state["working_mode"] = "lock"
        return self._ok("set_lock_mode")

    # ------------------------------------------------------------------
    # Speed mode
    # ------------------------------------------------------------------

    def set_speed_mode(self, mode: str = "constant") -> dict:
        if mode not in ("constant", "variable"):
            mode = "constant"
        self._state["speed_mode"] = mode
        return self._ok("set_speed_mode", mode=mode)

    # ------------------------------------------------------------------
    # Thermal palette (SDK: setThermalPalette)
    # ------------------------------------------------------------------

    def set_palette(self, name: str) -> dict:
        name_lower = name.strip().lower().replace(" ", "_").replace("-", "_")
        for p in THERMAL_PALETTES:
            if (name_lower == p["label"].lower().replace(" ", "_")
                    or name_lower == p["sdk"].lower()
                    or str(p["index"]) == name.strip()):
                self._state["palette"] = p["label"]
                self._state["palette_index"] = p["index"]
                return self._ok("set_palette", palette=p["label"], index=p["index"])
        # Numeric fallback
        try:
            idx = max(0, min(9, int(name.strip())))
            self._state["palette"] = THERMAL_PALETTES[idx]["label"]
            self._state["palette_index"] = idx
            return self._ok("set_palette", palette=THERMAL_PALETTES[idx]["label"], index=idx)
        except (ValueError, IndexError):
            pass
        return {"success": False, "error": f"Unknown palette: {name!r}. "
                f"Valid: {[p['label'] for p in THERMAL_PALETTES]}"}

    def set_palette_index(self, index: int) -> dict:
        index = max(0, min(9, int(index)))
        self._state["palette"] = THERMAL_PALETTES[index]["label"]
        self._state["palette_index"] = index
        return self._ok("set_palette_index", index=index, palette=THERMAL_PALETTES[index]["label"])

    def set_thermal_gain(self, mode: str = "auto") -> dict:
        self._state["thermal_gain"] = mode
        return self._ok("set_thermal_gain", mode=mode)

    def set_temperature_measurement(self, enabled: bool = True) -> dict:
        self._state["temp_measurement"] = bool(enabled)
        return self._ok("set_temperature_measurement", enabled=enabled)

    # ------------------------------------------------------------------
    # Image settings
    # ------------------------------------------------------------------

    def set_brightness(self, value: int) -> dict:
        self._state["brightness"] = max(0, min(100, int(value)))
        return self._ok("set_brightness", value=self._state["brightness"])

    def set_contrast(self, value: int) -> dict:
        self._state["contrast"] = max(0, min(100, int(value)))
        return self._ok("set_contrast", value=self._state["contrast"])

    def set_saturation(self, value: int) -> dict:
        self._state["saturation"] = max(0, min(100, int(value)))
        return self._ok("set_saturation", value=self._state["saturation"])

    def set_sharpness(self, value: int) -> dict:
        self._state["sharpness"] = max(0, min(100, int(value)))
        return self._ok("set_sharpness", value=self._state["sharpness"])

    # ------------------------------------------------------------------
    # Time sync
    # ------------------------------------------------------------------

    def sync_time(self, timestamp_ms: int | None = None) -> dict:
        return self._ok("sync_time", timestamp_ms=timestamp_ms)

    # ------------------------------------------------------------------
    # LED
    # ------------------------------------------------------------------

    def led_on(self) -> dict:
        return self._ok("led_on")

    def led_off(self) -> dict:
        return self._ok("led_off")

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def reboot_camera(self) -> dict:
        return self._ok("reboot_camera")

    def upgrade_firmware(self, file_path: str = "") -> dict:
        return self._ok("upgrade_firmware", file_path=file_path)

    def send_raw_command(self, cmd: str, add_crc: bool = True) -> dict:
        return self._ok("send_raw_command", cmd=cmd, add_crc=add_crc,
                        note="Mock mode — command not sent to camera")
