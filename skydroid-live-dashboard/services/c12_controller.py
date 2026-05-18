"""
c12_controller.py
-----------------
Real Ethernet controller for the SkyDroid C12.

Communicates with the camera at CAMERA_IP:CONTROL_PORT over TCP.
Builds binary packets using command_protocol.build_command() and parses
responses with command_protocol.parse_response().

Currently the low-level packet functions raise NotImplementedError because
the exact Ethernet protocol is not publicly documented. This class is
provided as a clean scaffold — fill in command_protocol.py once the spec
is known and this controller will work automatically.
"""

from __future__ import annotations
import socket
import logging
import time
from services import command_protocol as proto

logger = logging.getLogger(__name__)

# Default timeout for socket operations (seconds)
SOCKET_TIMEOUT = 2.0
# How many bytes to read per response
RECV_BUFFER = 1024


class C12Controller:
    """
    TCP controller for the SkyDroid C12 gimbal/camera system.

    Sends binary command packets over an Ethernet TCP connection and
    returns parsed response dicts.

    Usage:
        ctrl = C12Controller("192.168.144.108", port=37260)
        ctrl.connect()
        ctrl.take_photo()
        ctrl.disconnect()
    """

    def __init__(self, ip: str, port: int = 37260) -> None:
        self.ip = ip
        self.port = port
        self._sock: socket.socket | None = None
        self.connected: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> dict:
        """Open a TCP connection to the camera control port."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self.ip, self.port))
            self._sock = s
            self.connected = True
            logger.info("[C12Controller] Connected to %s:%d", self.ip, self.port)
            return {"success": True, "connected": True}
        except OSError as exc:
            logger.error("[C12Controller] Connection failed: %s", exc)
            self.connected = False
            return {"success": False, "error": str(exc)}

    def disconnect(self) -> dict:
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self.connected = False
        logger.info("[C12Controller] Disconnected.")
        return {"success": True, "connected": False}

    def get_status(self) -> dict:
        return {"success": True, "connected": self.connected, "mock_mode": False}

    # ------------------------------------------------------------------
    # Internal send/receive
    # ------------------------------------------------------------------

    def _send(self, command_name: str, params: dict | None = None) -> dict:
        """
        Build and send a command, then read and parse the response.

        Raises:
            NotImplementedError: Until command_protocol is implemented.
            RuntimeError:        If not connected.
        """
        if not self.connected or self._sock is None:
            raise RuntimeError("Not connected — call connect() first.")

        # This will raise NotImplementedError until the protocol is filled in
        packet = proto.build_command(command_name, params)

        self._sock.sendall(packet)
        raw = self._sock.recv(RECV_BUFFER)
        return proto.parse_response(raw)

    # ------------------------------------------------------------------
    # Gimbal motion
    # ------------------------------------------------------------------

    def pitch_up(self, speed: int = 50) -> dict:
        return self._send("gimbal_pitch_up", {"speed": speed})

    def pitch_down(self, speed: int = 50) -> dict:
        return self._send("gimbal_pitch_down", {"speed": speed})

    def yaw_left(self, speed: int = 50) -> dict:
        return self._send("gimbal_yaw_left", {"speed": speed})

    def yaw_right(self, speed: int = 50) -> dict:
        return self._send("gimbal_yaw_right", {"speed": speed})

    def roll_left(self, speed: int = 50) -> dict:
        return self._send("gimbal_roll_left", {"speed": speed})

    def roll_right(self, speed: int = 50) -> dict:
        return self._send("gimbal_roll_right", {"speed": speed})

    def stop_motion(self) -> dict:
        return self._send("gimbal_stop")

    def center_all(self) -> dict:
        return self._send("gimbal_center")

    def center_yaw(self) -> dict:
        return self._send("gimbal_center_yaw")

    def look_down(self) -> dict:
        return self._send("gimbal_look_down")

    def look_forward(self) -> dict:
        return self._send("gimbal_look_forward")

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def zoom_in(self) -> dict:
        return self._send("zoom_in")

    def zoom_out(self) -> dict:
        return self._send("zoom_out")

    def set_zoom(self, level: float) -> dict:
        return self._send("zoom_set", {"level": level})

    # ------------------------------------------------------------------
    # Camera capture
    # ------------------------------------------------------------------

    def take_photo(self) -> dict:
        return self._send("camera_photo")

    def start_recording(self) -> dict:
        return self._send("camera_rec_start")

    def stop_recording(self) -> dict:
        return self._send("camera_rec_stop")

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def enable_tracking(self) -> dict:
        return self._send("tracking_enable")

    def disable_tracking(self) -> dict:
        return self._send("tracking_disable")

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def temperature_calibration(self) -> dict:
        return self._send("cal_temperature")

    def horizontal_calibration(self) -> dict:
        return self._send("cal_horizontal")

    def vertical_calibration(self) -> dict:
        return self._send("cal_vertical")

    def fine_adjust(self, roll_offset: float = 0.0, pitch_offset: float = 0.0) -> dict:
        return self._send("cal_fine_adjust", {"roll_offset": roll_offset, "pitch_offset": pitch_offset})

    # ------------------------------------------------------------------
    # Working mode
    # ------------------------------------------------------------------

    def set_hoist_mode(self) -> dict:
        return self._send("mode_hoist")

    def set_upside_down_mode(self) -> dict:
        return self._send("mode_upside_down")

    # ------------------------------------------------------------------
    # Speed mode
    # ------------------------------------------------------------------

    def set_speed_mode(self, mode: str = "constant") -> dict:
        return self._send("speed_mode", {"mode": mode})

    # ------------------------------------------------------------------
    # Thermal settings
    # ------------------------------------------------------------------

    def set_palette(self, name: str) -> dict:
        return self._send("thermal_palette", {"name": name})

    def set_thermal_gain(self, mode: str = "auto") -> dict:
        return self._send("thermal_gain", {"mode": mode})

    def set_temperature_measurement(self, enabled: bool = True) -> dict:
        return self._send("thermal_temp_measure", {"enabled": enabled})

    # ------------------------------------------------------------------
    # Image settings
    # ------------------------------------------------------------------

    def set_brightness(self, value: int) -> dict:
        return self._send("image_settings", {"brightness": value})

    def set_contrast(self, value: int) -> dict:
        return self._send("image_settings", {"contrast": value})

    def set_saturation(self, value: int) -> dict:
        return self._send("image_settings", {"saturation": value})

    def set_sharpness(self, value: int) -> dict:
        return self._send("image_settings", {"sharpness": value})

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def reboot_camera(self) -> dict:
        return self._send("system_reboot")

    def upgrade_firmware(self, file_path: str = "") -> dict:
        return self._send("system_firmware", {"file_path": file_path})
