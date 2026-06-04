"""
c12_controller.py
-----------------
Real UDP controller for the SkyDroid C12 gimbal camera.

Uses the real ASCII text protocol reverse-engineered from the official SkyDroid APK.
Commands are ASCII strings like "#TPUG2wPTZ01" with a 2-char hex checksum appended.

Transport: UDP to camera IP:37260  (also sends to port 9002 as the app does)
Responses: ASCII strings starting with "#TP" or "AT+"

All public methods match MockController exactly — app.py picks one or the other
based on mock_mode, no other code needs to change.
"""

from __future__ import annotations
import socket
import threading
import logging
import time
from services import command_protocol as proto

logger = logging.getLogger(__name__)

SOCKET_TIMEOUT  = 2.0    # seconds for send/recv
RECV_BUFFER     = 4096
CTRL_PORT       = 37260
ALT_PORT        = 9002   # some firmware also listens here; app sends to both


class C12Controller:
    """
    Real SkyDroid C12 controller using the official ASCII text protocol over UDP.

    The camera lives at 192.168.144.108 (default) on port 37260.
    Commands are UTF-8 encoded ASCII strings with a 1-byte sum CRC appended as 2 hex chars.
    """

    def __init__(self, ip: str, port: int = CTRL_PORT) -> None:
        self.ip   = ip
        self.port = port
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self.connected: bool = False
        self._state: dict = {
            "zoom": 1.0, "recording": False, "tracking": False,
            "gimbal_pitch": 0.0, "gimbal_yaw": 0.0, "gimbal_roll": 0.0,
            "last_command": None, "last_response": None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> dict:
        """
        Open a UDP socket and send a version query as a connectivity probe.
        UDP is connectionless so we consider it "connected" as soon as the socket
        is open and the probe packet doesn't raise an error.  A timeout on the
        probe reply is normal — some firmware replies, some doesn't.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(SOCKET_TIMEOUT)
            # Probe: send a version query
            probe = proto.CMD_QUERY_VERSION()
            s.sendto(probe, (self.ip, self.port))
            logger.info("[C12] UDP probe sent to %s:%d: %s", self.ip, self.port, probe)
            try:
                data, addr = s.recvfrom(RECV_BUFFER)
                parsed = proto.parse_response(data)
                logger.info("[C12] Got reply from %s: %s", addr, parsed.get("raw_text", data.hex()))
                self._state["last_response"] = parsed.get("raw_text")
            except socket.timeout:
                logger.info("[C12] No reply to probe (normal — camera may not respond to VER query)")
            self._sock = s
            self.connected = True
            return {"success": True, "transport": "udp", "ip": self.ip, "port": self.port}
        except OSError as exc:
            logger.error("[C12] UDP connect failed: %s", exc)
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
            "success":    True,
            "connected":  self.connected,
            "mock_mode":  False,
            "transport":  "udp",
            **self._state,
        }

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    def _send(self, frame: bytes, want_reply: bool = False) -> dict:
        """
        Send *frame* over UDP.  If *want_reply* is True, wait for a response.
        Returns a result dict with success/error and optionally parsed response.
        """
        if not self.connected or self._sock is None:
            return {"success": False, "error": "Not connected — call connect() first."}
        try:
            with self._lock:
                self._sock.sendto(frame, (self.ip, self.port))
                logger.debug("[C12] TX %d bytes → %s:%d", len(frame), self.ip, self.port)
                if want_reply:
                    try:
                        raw, addr = self._sock.recvfrom(RECV_BUFFER)
                        parsed = proto.parse_response(raw)
                        self._state["last_response"] = parsed.get("raw_text")
                        logger.debug("[C12] RX from %s: %s", addr, parsed.get("raw_text"))
                        return {"success": True, **parsed}
                    except socket.timeout:
                        return {"success": True, "no_reply": True}
                else:
                    return {"success": True}
        except OSError as exc:
            logger.error("[C12] Send error: %s", exc)
            self.connected = False
            return {"success": False, "error": str(exc)}

    def _cmd(self, frame: bytes, state_update: dict | None = None,
             want_reply: bool = False) -> dict:
        """Send a frame and optionally update internal state cache."""
        result = self._send(frame, want_reply=want_reply)
        if result.get("success") and state_update:
            self._state.update(state_update)
        return result

    # ------------------------------------------------------------------
    # Gimbal direction (discrete D-pad style)
    # ------------------------------------------------------------------

    def pitch_up(self, speed: int = 50) -> dict:
        return self._cmd(proto.CMD_PTZ_UP(), {"last_command": "pitch_up"})

    def pitch_down(self, speed: int = 50) -> dict:
        return self._cmd(proto.CMD_PTZ_DOWN(), {"last_command": "pitch_down"})

    def yaw_left(self, speed: int = 50) -> dict:
        return self._cmd(proto.CMD_PTZ_LEFT(), {"last_command": "yaw_left"})

    def yaw_right(self, speed: int = 50) -> dict:
        return self._cmd(proto.CMD_PTZ_RIGHT(), {"last_command": "yaw_right"})

    def roll_left(self, speed: int = 50) -> dict:
        # No dedicated roll command in protocol — use yaw speed variant
        return self._cmd(proto.cmd_yaw_speed(-50), {"last_command": "roll_left"})

    def roll_right(self, speed: int = 50) -> dict:
        return self._cmd(proto.cmd_yaw_speed(50), {"last_command": "roll_right"})

    def stop_motion(self) -> dict:
        return self._cmd(proto.CMD_PTZ_STOP(), {"last_command": "stop"})

    def center_all(self) -> dict:
        return self._cmd(proto.CMD_PTZ_CENTER(),
                         {"last_command": "center", "gimbal_pitch": 0.0, "gimbal_yaw": 0.0})

    def center_yaw(self) -> dict:
        return self._cmd(proto.cmd_set_yaw_angle(0.0),
                         {"last_command": "center_yaw", "gimbal_yaw": 0.0})

    def look_down(self) -> dict:
        return self._cmd(proto.cmd_set_pitch_angle(-90.0),
                         {"last_command": "look_down", "gimbal_pitch": -90.0})

    def look_forward(self) -> dict:
        return self._cmd(proto.cmd_set_pitch_angle(0.0),
                         {"last_command": "look_forward", "gimbal_pitch": 0.0})

    # ------------------------------------------------------------------
    # Speed-based continuous control (joystick style)
    # ------------------------------------------------------------------

    def gimbal_speed(self, yaw_speed: int, pitch_speed: int) -> dict:
        """
        Send continuous yaw + pitch speed commands.
        Speeds are signed integers -99..99. Send 0,0 to stop.
        The app sends either yaw or pitch (whichever has larger magnitude),
        so we mirror that behaviour.
        """
        ys = max(-99, min(99, int(yaw_speed)))
        ps = max(-99, min(99, int(pitch_speed)))
        if abs(ys) >= abs(ps):
            frame = proto.cmd_yaw_speed(ys)
        else:
            frame = proto.cmd_pitch_speed(-ps)   # app inverts pitch
        return self._cmd(frame, {"last_command": f"speed y={ys} p={ps}"})

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def zoom_in(self) -> dict:
        r = self._cmd(proto.CMD_ZOOM_IN())
        self._state["zoom"] = min(30.0, self._state["zoom"] + 0.5)
        return r

    def zoom_out(self) -> dict:
        r = self._cmd(proto.CMD_ZOOM_OUT())
        self._state["zoom"] = max(1.0, self._state["zoom"] - 0.5)
        return r

    def zoom_stop(self) -> dict:
        return self._cmd(proto.CMD_ZOOM_STOP())

    def set_zoom(self, level: float) -> dict:
        # No direct absolute zoom command in this protocol; use in/out step
        # Best we can do is update state and send a stop
        self._state["zoom"] = float(level)
        return self._cmd(proto.CMD_ZOOM_STOP(), {"zoom": float(level)})

    # ------------------------------------------------------------------
    # Focus
    # ------------------------------------------------------------------

    def focus_in(self) -> dict:
        return self._cmd(proto.CMD_FOCUS_IN(), {"last_command": "focus_in"})

    def focus_out(self) -> dict:
        return self._cmd(proto.CMD_FOCUS_OUT(), {"last_command": "focus_out"})

    def focus_stop(self) -> dict:
        return self._cmd(proto.CMD_FOCUS_STOP(), {"last_command": "focus_stop"})

    # ------------------------------------------------------------------
    # Camera capture
    # ------------------------------------------------------------------

    def take_photo(self) -> dict:
        return self._cmd(proto.CMD_TAKE_PHOTO(), {"last_command": "take_photo"})

    def start_recording(self) -> dict:
        return self._cmd(proto.CMD_REC_START(), {"recording": True, "last_command": "rec_start"})

    def stop_recording(self) -> dict:
        return self._cmd(proto.CMD_REC_STOP(), {"recording": False, "last_command": "rec_stop"})

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
    # Calibration
    # ------------------------------------------------------------------

    def temperature_calibration(self) -> dict:
        return self._cmd(proto.CMD_PTZ_CALIBRATE(), {"last_command": "calibrate"})

    def horizontal_calibration(self) -> dict:
        return self._cmd(proto.CMD_PTZ_H_CAL(), {"last_command": "h_cal"})

    def vertical_calibration(self) -> dict:
        return self._cmd(proto.CMD_PTZ_V_CAL(), {"last_command": "v_cal"})

    def fine_adjust(self, roll_offset: float = 0.0, pitch_offset: float = 0.0) -> dict:
        # Use X/Y trim commands
        results = []
        if roll_offset > 0:
            results.append(self._cmd(proto.CMD_PTZ_X_ADD()))
        elif roll_offset < 0:
            results.append(self._cmd(proto.CMD_PTZ_X_REDUCE()))
        if pitch_offset > 0:
            results.append(self._cmd(proto.CMD_PTZ_Y_ADD()))
        elif pitch_offset < 0:
            results.append(self._cmd(proto.CMD_PTZ_Y_REDUCE()))
        return results[0] if results else {"success": True, "note": "No adjustment needed"}

    def clear_adjustments(self) -> dict:
        return self._cmd(proto.CMD_PTZ_CLEAR_ADJ(), {"last_command": "clear_adj"})

    # ------------------------------------------------------------------
    # Working mode (mount orientation)
    # ------------------------------------------------------------------

    def set_hoist_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_HOIST(), {"last_command": "hoist_mode"})

    def set_upside_down_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_INVERT(), {"last_command": "upside_down_mode"})

    def set_follow_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_FOLLOW(), {"last_command": "follow_mode"})

    def set_lock_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_LOCK(), {"last_command": "lock_mode"})

    # ------------------------------------------------------------------
    # Speed mode (no direct equivalent in this protocol)
    # ------------------------------------------------------------------

    def set_speed_mode(self, mode: str = "constant") -> dict:
        return {"success": True, "note": "Speed mode not configurable in this firmware"}

    # ------------------------------------------------------------------
    # Thermal / image settings (C12 has thermal camera)
    # Note: thermal palette/gain commands are AT-style in this protocol
    # ------------------------------------------------------------------

    def set_palette(self, name: str) -> dict:
        # No palette command in the discovered protocol; store state only
        self._state["palette"] = name
        return {"success": True, "palette": name, "note": "Palette selection not available over control port"}

    def set_thermal_gain(self, mode: str = "auto") -> dict:
        return {"success": True, "note": "Thermal gain not available over control port"}

    def set_temperature_measurement(self, enabled: bool = True) -> dict:
        return {"success": True, "note": "Temperature measurement toggle not available over control port"}

    def set_brightness(self, value: int) -> dict:
        return {"success": True, "note": "Image settings not available in this firmware version"}

    def set_contrast(self, value: int) -> dict:
        return {"success": True, "note": "Image settings not available in this firmware version"}

    def set_saturation(self, value: int) -> dict:
        return {"success": True, "note": "Image settings not available in this firmware version"}

    def set_sharpness(self, value: int) -> dict:
        return {"success": True, "note": "Image settings not available in this firmware version"}

    # ------------------------------------------------------------------
    # LED
    # ------------------------------------------------------------------

    def led_on(self) -> dict:
        return self._cmd(proto.CMD_LED_ON(), {"last_command": "led_on"})

    def led_off(self) -> dict:
        return self._cmd(proto.CMD_LED_OFF(), {"last_command": "led_off"})

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def reboot_camera(self) -> dict:
        return self._cmd(proto.CMD_FACTORY_RESET(), {"last_command": "reboot"})

    def upgrade_firmware(self, file_path: str = "") -> dict:
        return {"success": False, "error": "Firmware upgrade not supported over this interface."}

    # ------------------------------------------------------------------
    # Query commands (read state from camera)
    # ------------------------------------------------------------------

    def query_version(self) -> dict:
        return self._cmd(proto.CMD_QUERY_VERSION(), want_reply=True)

    def query_recording_state(self) -> dict:
        return self._cmd(proto.CMD_QUERY_REC(), want_reply=True)

    def query_video_config(self) -> dict:
        return self._cmd(proto.CMD_QUERY_VOM(), want_reply=True)

    def query_image_quality(self) -> dict:
        return self._cmd(proto.CMD_QUERY_IQE(), want_reply=True)

    # ------------------------------------------------------------------
    # Raw command passthrough (for diagnostics / testing)
    # ------------------------------------------------------------------

    def send_raw_command(self, cmd: str, add_crc: bool = True) -> dict:
        """
        Send an arbitrary command string.
        If add_crc is True, appends the checksum (use for #TP commands).
        If add_crc is False, sends verbatim (use for AT+ commands).
        """
        if add_crc:
            frame = proto.build(cmd)
        else:
            frame = proto.build_raw(cmd)
        return self._send(frame, want_reply=True)
