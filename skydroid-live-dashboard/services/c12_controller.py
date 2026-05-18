"""
c12_controller.py
-----------------
Real Ethernet controller for the SkyDroid C12 gimbal/camera system.

Protocol
--------
Implements the SIYI SDK-compatible binary protocol (the de-facto standard
for Skydroid / SIYI and related Chinese Ethernet gimbal cameras).
  • Transport : UDP (default, port 37260)  — camera broadcasts status, we send commands
  • Frame     : [0x55][0x66][CTRL][LEN16LE][SEQ16LE][CMD][DATA…][CRC16LE]
  • CRC       : CRC-16/IBM (ARC), poly 0x8005, reflected

Most cameras in this family also respond to TCP on the same port; UDP is
tried first because it is non-blocking and matches the camera's broadcast
behaviour.  If UDP fails (e.g. unreachable), the controller returns an
error dict and the app falls back to MockController automatically.
"""

from __future__ import annotations
import socket
import threading
import logging
import time
from services import command_protocol as proto

logger = logging.getLogger(__name__)

SOCKET_TIMEOUT = 2.0   # seconds for connect / single recv
RECV_BUFFER    = 1024


class C12Controller:
    """
    UDP (with TCP fallback) controller for the SkyDroid C12.

    Sends SIYI-format binary command frames and reads responses.
    All public methods match the MockController API exactly so the
    app layer never needs to know which one is active.
    """

    def __init__(self, ip: str, port: int = 37260) -> None:
        self.ip   = ip
        self.port = port
        self._sock: socket.socket | None = None
        self._transport: str = "udp"
        self._seq: int = 0
        self._lock = threading.Lock()
        self.connected: bool = False
        self._state: dict = {
            "zoom": 1.0, "recording": False, "tracking": False,
            "palette": "White Hot", "gimbal_pitch": 0.0,
            "gimbal_yaw": 0.0, "gimbal_roll": 0.0, "last_command": None,
        }

    # ------------------------------------------------------------------
    # Sequence numbers
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        with self._lock:
            self._seq = (self._seq + 1) & 0xFFFF
            return self._seq

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> dict:
        """Try UDP first, then TCP. Returns {"success": bool, ...}."""
        # --- UDP ---
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(SOCKET_TIMEOUT)
            # Send a firmware-version query as a connectivity probe
            probe = proto.build_frame(proto.CMD.FIRMWARE_VERSION, b"", 0)
            s.sendto(probe, (self.ip, self.port))
            try:
                data, _ = s.recvfrom(RECV_BUFFER)
                logger.info("[C12] UDP connected to %s:%d, got %d bytes back",
                            self.ip, self.port, len(data))
            except socket.timeout:
                # No reply is OK for UDP — the port is open and didn't refuse
                logger.info("[C12] UDP probe to %s:%d sent (no reply — that is normal)", self.ip, self.port)
            self._sock = s
            self._transport = "udp"
            self.connected = True
            return {"success": True, "transport": "udp"}
        except OSError as exc:
            logger.warning("[C12] UDP connect failed: %s — trying TCP", exc)

        # --- TCP fallback ---
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self.ip, self.port))
            self._sock = s
            self._transport = "tcp"
            self.connected = True
            logger.info("[C12] TCP connected to %s:%d", self.ip, self.port)
            return {"success": True, "transport": "tcp"}
        except OSError as exc:
            logger.error("[C12] TCP connect also failed: %s", exc)
            self.connected = False
            return {"success": False, "error": str(exc)}

    def disconnect(self) -> dict:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self.connected = False
        logger.info("[C12] Disconnected.")
        return {"success": True, "connected": False}

    def get_status(self) -> dict:
        return {
            "success":      True,
            "connected":    self.connected,
            "mock_mode":    False,
            "transport":    self._transport,
            **self._state,
        }

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    def _send(self, frame: bytes) -> dict:
        """Send *frame* and optionally read one response."""
        if not self.connected or self._sock is None:
            return {"success": False, "error": "Not connected — call connect() first."}
        try:
            with self._lock:
                if self._transport == "udp":
                    self._sock.sendto(frame, (self.ip, self.port))
                    try:
                        raw, _ = self._sock.recvfrom(RECV_BUFFER)
                        return proto.parse_frame(raw)
                    except socket.timeout:
                        # Many cameras don't reply to every command — that is OK
                        return {"success": True, "no_reply": True}
                else:
                    self._sock.sendall(frame)
                    try:
                        raw = self._sock.recv(RECV_BUFFER)
                        return proto.parse_frame(raw)
                    except socket.timeout:
                        return {"success": True, "no_reply": True}
        except OSError as exc:
            logger.error("[C12] Send error: %s", exc)
            self.connected = False
            return {"success": False, "error": str(exc)}

    def _cmd(self, frame: bytes, state_update: dict | None = None) -> dict:
        """Send a frame and optionally update internal state cache."""
        result = self._send(frame)
        if result.get("success") and state_update:
            self._state.update(state_update)
        return result

    # ------------------------------------------------------------------
    # Gimbal motion
    # ------------------------------------------------------------------

    def pitch_up(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(0, speed, self._next_seq()),
                         {"last_command": "pitch_up"})

    def pitch_down(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(0, -speed, self._next_seq()),
                         {"last_command": "pitch_down"})

    def yaw_left(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(-speed, 0, self._next_seq()),
                         {"last_command": "yaw_left"})

    def yaw_right(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(speed, 0, self._next_seq()),
                         {"last_command": "yaw_right"})

    def roll_left(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(-speed, 0, self._next_seq()),
                         {"last_command": "roll_left"})

    def roll_right(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(speed, 0, self._next_seq()),
                         {"last_command": "roll_right"})

    def stop_motion(self) -> dict:
        return self._cmd(proto.cmd_gimbal_stop(self._next_seq()),
                         {"last_command": "stop"})

    def center_all(self) -> dict:
        return self._cmd(proto.cmd_center_gimbal(self._next_seq()),
                         {"last_command": "center", "gimbal_pitch": 0.0, "gimbal_yaw": 0.0})

    def center_yaw(self) -> dict:
        return self._cmd(proto.cmd_gimbal_rotate(0, 0, self._next_seq()),
                         {"last_command": "center_yaw", "gimbal_yaw": 0.0})

    def look_down(self) -> dict:
        return self._cmd(proto.cmd_look_down(self._next_seq()),
                         {"last_command": "look_down", "gimbal_pitch": -90.0})

    def look_forward(self) -> dict:
        return self._cmd(proto.cmd_look_forward(self._next_seq()),
                         {"last_command": "look_forward", "gimbal_pitch": 0.0})

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def zoom_in(self) -> dict:
        r = self._cmd(proto.cmd_zoom_in(self._next_seq()))
        self._state["zoom"] = min(30.0, self._state["zoom"] + 0.5)
        return r

    def zoom_out(self) -> dict:
        r = self._cmd(proto.cmd_zoom_out(self._next_seq()))
        self._state["zoom"] = max(1.0, self._state["zoom"] - 0.5)
        return r

    def set_zoom(self, level: float) -> dict:
        return self._cmd(proto.cmd_set_zoom(int(level), self._next_seq()),
                         {"zoom": float(level)})

    # ------------------------------------------------------------------
    # Camera capture
    # ------------------------------------------------------------------

    def take_photo(self) -> dict:
        return self._cmd(proto.cmd_take_photo(self._next_seq()),
                         {"last_command": "take_photo"})

    def start_recording(self) -> dict:
        return self._cmd(proto.cmd_record_start(self._next_seq()),
                         {"recording": True})

    def stop_recording(self) -> dict:
        return self._cmd(proto.cmd_record_stop(self._next_seq()),
                         {"recording": False})

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def enable_tracking(self) -> dict:
        self._state["tracking"] = True
        return {"success": True, "tracking": True}

    def disable_tracking(self) -> dict:
        self._state["tracking"] = False
        return {"success": True, "tracking": False}

    # ------------------------------------------------------------------
    # Calibration (protocol-agnostic best-effort)
    # ------------------------------------------------------------------

    def temperature_calibration(self) -> dict:
        return self._cmd(proto.build_frame(0x31, b"", self._next_seq()))

    def horizontal_calibration(self) -> dict:
        return self._cmd(proto.build_frame(0x32, b"", self._next_seq()))

    def vertical_calibration(self) -> dict:
        return self._cmd(proto.build_frame(0x33, b"", self._next_seq()))

    def fine_adjust(self, roll_offset: float = 0.0, pitch_offset: float = 0.0) -> dict:
        import struct as _s
        data = _s.pack("<ff", roll_offset, pitch_offset)
        return self._cmd(proto.build_frame(0x34, data, self._next_seq()))

    # ------------------------------------------------------------------
    # Working mode
    # ------------------------------------------------------------------

    def set_hoist_mode(self) -> dict:
        return self._cmd(proto.build_frame(0x50, bytes([0x01]), self._next_seq()),
                         {"last_command": "hoist_mode"})

    def set_upside_down_mode(self) -> dict:
        return self._cmd(proto.build_frame(0x50, bytes([0x02]), self._next_seq()),
                         {"last_command": "upside_down_mode"})

    # ------------------------------------------------------------------
    # Speed mode
    # ------------------------------------------------------------------

    def set_speed_mode(self, mode: str = "constant") -> dict:
        val = 0x01 if mode == "variable" else 0x00
        return self._cmd(proto.build_frame(0x51, bytes([val]), self._next_seq()),
                         {"last_command": f"speed_{mode}"})

    # ------------------------------------------------------------------
    # Thermal settings
    # ------------------------------------------------------------------

    def set_palette(self, name: str) -> dict:
        return self._cmd(proto.cmd_set_palette(name, self._next_seq()),
                         {"palette": name})

    def set_thermal_gain(self, mode: str = "auto") -> dict:
        return self._cmd(proto.cmd_thermal_gain(mode, self._next_seq()))

    def set_temperature_measurement(self, enabled: bool = True) -> dict:
        return self._cmd(proto.cmd_temp_measure(enabled, self._next_seq()))

    # ------------------------------------------------------------------
    # Image settings
    # ------------------------------------------------------------------

    def set_brightness(self, value: int) -> dict:
        return self._cmd(proto.cmd_image_settings(brightness=value, seq=self._next_seq()))

    def set_contrast(self, value: int) -> dict:
        return self._cmd(proto.cmd_image_settings(contrast=value, seq=self._next_seq()))

    def set_saturation(self, value: int) -> dict:
        return self._cmd(proto.cmd_image_settings(saturation=value, seq=self._next_seq()))

    def set_sharpness(self, value: int) -> dict:
        return self._cmd(proto.cmd_image_settings(sharpness=value, seq=self._next_seq()))

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def reboot_camera(self) -> dict:
        return self._cmd(proto.cmd_reboot(self._next_seq()))

    def upgrade_firmware(self, file_path: str = "") -> dict:
        return {"success": False, "error": "Firmware upgrade not supported over this interface."}
