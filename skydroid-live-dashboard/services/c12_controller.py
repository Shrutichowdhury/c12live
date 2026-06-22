"""
c12_controller.py
-----------------
Real UDP controller for the SkyDroid C12 gimbal camera.

Uses the real ASCII text protocol confirmed from official SkyDroid SDK AAR v1.9.1.
Commands are ASCII strings like "#TPUG2wPTZ01" with a 2-char hex checksum appended.

Transport: UDP to camera port 5000 (SDK: PayloadManager.getUDPPayload(C12, 5000, ip, 5000))
           Port 9002 is a known alternate for some older firmware.
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
CTRL_PORT       = 5000   # SDK: getUDPPayload(C12, 5000, ip, 5000)
ALT_PORT        = 9002   # older firmware fallback


class C12Controller:
    """
    Real SkyDroid C12 controller using the official ASCII text protocol over UDP.

    The camera lives at 192.168.144.108 (default) on port 5000.
    Commands are UTF-8 encoded ASCII strings with a 1-byte sum CRC appended as 2 hex chars.

    Port confirmed from official SDK README:
        c12 = PayloadManager.getUDPPayload(PayloadType.C12, 5000, "192.168.144.108", 5000)
    """

    def __init__(self, ip: str, port: int = CTRL_PORT) -> None:
        self.ip   = ip
        self.port = port
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self.connected: bool = False
        self._state: dict = {
            "zoom": 1.0, "zoom_ratio": 0, "recording": False, "tracking": False,
            "gimbal_pitch": 0.0, "gimbal_yaw": 0.0, "gimbal_roll": 0.0,
            "palette": "White Hot", "palette_index": 0,
            "last_command": None, "last_response": None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> dict:
        """
        Open a UDP socket and send a version query as a connectivity probe.
        UDP is connectionless so we consider it "connected" as soon as the socket
        is open and the probe packet doesn't raise an error.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(SOCKET_TIMEOUT)
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
    # Gimbal direction (discrete D-pad style, PTZ commands)
    # ------------------------------------------------------------------

    def pitch_up(self, speed: int = 50) -> dict:
        """
        Continuous pitch up using speed command (#TPUG2wGSP).
        Using PTZ_UP (#TPUG2wPTZ01) is WRONG — it jumps to the extreme angle instantly.
        Speed commands give smooth incremental motion at the requested rate.
        """
        s = max(1, min(100, int(speed)))
        return self._cmd(proto.cmd_pitch_speed(+s), {"last_command": "pitch_up"})

    def pitch_down(self, speed: int = 50) -> dict:
        """Continuous pitch down. Negative speed = downward."""
        s = max(1, min(100, int(speed)))
        return self._cmd(proto.cmd_pitch_speed(-s), {"last_command": "pitch_down"})

    def yaw_left(self, speed: int = 50) -> dict:
        """Continuous yaw left. Negative speed = leftward."""
        s = max(1, min(100, int(speed)))
        return self._cmd(proto.cmd_yaw_speed(-s), {"last_command": "yaw_left"})

    def yaw_right(self, speed: int = 50) -> dict:
        """Continuous yaw right. Positive speed = rightward."""
        s = max(1, min(100, int(speed)))
        return self._cmd(proto.cmd_yaw_speed(+s), {"last_command": "yaw_right"})

    def roll_left(self, speed: int = 50) -> dict:
        s = max(1, min(100, int(speed)))
        return self._cmd(proto.cmd_yaw_speed(-s), {"last_command": "roll_left"})

    def roll_right(self, speed: int = 50) -> dict:
        s = max(1, min(100, int(speed)))
        return self._cmd(proto.cmd_yaw_speed(+s), {"last_command": "roll_right"})

    def stop_motion(self) -> dict:
        """
        Stop all continuous motion by zeroing both axes.
        cmd_stop_speed() only zeros yaw; we must also zero pitch separately.
        """
        self._cmd(proto.cmd_yaw_speed(0),   {"last_command": "stop_yaw"})
        return self._cmd(proto.cmd_pitch_speed(0), {"last_command": "stop"})

    def center_all(self) -> dict:
        return self._cmd(proto.CMD_PTZ_CENTER(),
                         {"last_command": "center", "gimbal_pitch": 0.0, "gimbal_yaw": 0.0})

    def center_yaw(self) -> dict:
        return self._cmd(proto.cmd_goto_yaw(0.0),
                         {"last_command": "center_yaw", "gimbal_yaw": 0.0})

    def look_down(self) -> dict:
        return self._cmd(proto.cmd_goto_pitch(-90.0),
                         {"last_command": "look_down", "gimbal_pitch": -90.0})

    def look_forward(self) -> dict:
        return self._cmd(proto.cmd_goto_pitch(0.0),
                         {"last_command": "look_forward", "gimbal_pitch": 0.0})

    # ------------------------------------------------------------------
    # Speed-based continuous control (SDK: controlYaw / controlPitch)
    # Speeds: -100..100  (positive=right/up, negative=left/down)
    # SDK float range: -63.5 to +63.5 °/s maps to our -100..100 integer
    # Wire: #TPUG2wGSY<signed-byte-hex>  / #TPUG2wGSP<signed-byte-hex>
    # ------------------------------------------------------------------

    def control_yaw(self, speed: int) -> dict:
        """Continuous yaw speed. +100=full right, -100=full left, 0=stop."""
        return self._cmd(proto.cmd_yaw_speed(speed),
                         {"last_command": f"ctrl_yaw_{speed}"})

    def control_pitch(self, speed: int) -> dict:
        """Continuous pitch speed. +100=full up, -100=full down, 0=stop."""
        return self._cmd(proto.cmd_pitch_speed(speed),
                         {"last_command": f"ctrl_pitch_{speed}"})

    def gimbal_speed(self, yaw_speed: int, pitch_speed: int) -> dict:
        """
        Send continuous yaw + pitch speed commands simultaneously.
        The SDK sends them as separate packets; we send whichever has larger magnitude
        to avoid axis fighting (matching app behaviour).
        """
        ys = max(-100, min(100, int(yaw_speed)))
        ps = max(-100, min(100, int(pitch_speed)))
        if ys == 0 and ps == 0:
            frame = proto.cmd_stop_speed()
        elif abs(ys) >= abs(ps):
            frame = proto.cmd_yaw_speed(ys)
        else:
            frame = proto.cmd_pitch_speed(ps)
        return self._cmd(frame, {"last_command": f"speed y={ys} p={ps}"})

    # ------------------------------------------------------------------
    # Angle control (SDK: gotoYaw / gotoPitch)
    # degrees: -90.0 to +90.0  (positive=right/up)
    # Wire: #TPUG6wGAY/GAP<int16_scaled_hex>10
    # ------------------------------------------------------------------

    def goto_yaw(self, degrees: float) -> dict:
        """Go to absolute yaw angle (-90.0 to +90.0 degrees)."""
        degrees = max(-90.0, min(90.0, float(degrees)))
        return self._cmd(proto.cmd_goto_yaw(degrees),
                         {"last_command": f"goto_yaw_{degrees}", "gimbal_yaw": degrees})

    def goto_pitch(self, degrees: float) -> dict:
        """Go to absolute pitch angle (-90.0 to +90.0 degrees, -90=nadir)."""
        degrees = max(-90.0, min(90.0, float(degrees)))
        return self._cmd(proto.cmd_goto_pitch(degrees),
                         {"last_command": f"goto_pitch_{degrees}", "gimbal_pitch": degrees})

    # ------------------------------------------------------------------
    # Zoom (continuous + discrete ratio 0-4)
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
        self._state["zoom"] = float(level)
        return self._cmd(proto.CMD_ZOOM_STOP(), {"zoom": float(level)})

    def set_zoom_ratio(self, ratio: int) -> dict:
        """
        Set discrete zoom level 0-4 (SDK: setZoomRatios).
        0=original image, 1-4=progressive digital zoom.
        Wire: #TPUD2wDZM0<ratio:X>
        """
        ratio = max(0, min(4, int(ratio)))
        labels = ["1× (original)", "2× digital", "4× digital", "8× digital", "16× digital"]
        return self._cmd(proto.cmd_set_zoom_ratio(ratio),
                         {"zoom_ratio": ratio, "last_command": f"zoom_ratio_{ratio}",
                          "zoom_label": labels[ratio]})

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
    # Thermal palette (SDK: setThermalPalette)
    # Wire: #TPUD2wIMG<index:02X>
    # Palette indices: 0=WHITE_HOT..9=GLORY_HOT
    # ------------------------------------------------------------------

    def set_palette(self, name: str) -> dict:
        """
        Set thermal palette by label name or SDK enum name.
        Sends real #TPUD2wIMG command to camera.
        """
        name_lower = name.strip().lower().replace(" ", "_").replace("-", "_")
        for p in proto.THERMAL_PALETTES:
            if (name_lower == p["label"].lower().replace(" ", "_")
                    or name_lower == p["sdk"].lower()
                    or str(p["index"]) == name.strip()):
                idx = p["index"]
                frame = proto.cmd_set_thermal_palette(idx)
                return self._cmd(frame,
                                 {"palette": p["label"], "palette_index": idx,
                                  "last_command": f"palette_{p['sdk']}"})
        # Try numeric fallback
        try:
            idx = int(name.strip())
            idx = max(0, min(9, idx))
            frame = proto.cmd_set_thermal_palette(idx)
            label = proto.THERMAL_PALETTES[idx]["label"]
            return self._cmd(frame,
                             {"palette": label, "palette_index": idx,
                              "last_command": f"palette_{idx}"})
        except (ValueError, IndexError):
            pass
        return {"success": False, "error": f"Unknown palette: {name}. "
                f"Valid: {[p['label'] for p in proto.THERMAL_PALETTES]}"}

    def set_palette_index(self, index: int) -> dict:
        """Set thermal palette by index (0-9)."""
        index = max(0, min(9, int(index)))
        frame = proto.cmd_set_thermal_palette(index)
        label = proto.THERMAL_PALETTES[index]["label"]
        return self._cmd(frame,
                         {"palette": label, "palette_index": index,
                          "last_command": f"palette_{index}"})

    def set_thermal_gain(self, mode: str = "auto") -> dict:
        return {"success": True, "note": "Thermal gain not available via this interface"}

    def set_temperature_measurement(self, enabled: bool = True) -> dict:
        return {"success": True, "note": "Temperature measurement toggle not available via this interface"}

    def set_brightness(self, value: int) -> dict:
        return {"success": True, "note": "Brightness control not available in this firmware version"}

    def set_contrast(self, value: int) -> dict:
        return {"success": True, "note": "Contrast control not available in this firmware version"}

    def set_saturation(self, value: int) -> dict:
        return {"success": True, "note": "Saturation control not available in this firmware version"}

    def set_sharpness(self, value: int) -> dict:
        return {"success": True, "note": "Sharpness control not available in this firmware version"}

    # ------------------------------------------------------------------
    # Time synchronisation (SDK: setTime — must call after video starts)
    # ------------------------------------------------------------------

    def sync_time(self, timestamp_ms: int | None = None) -> dict:
        """
        Sync camera clock to current UTC time (or provided timestamp_ms).
        Wire: #TPUDFwTIM<HHmmss><ddMMyy>.00 + CRC
        """
        frame = proto.cmd_set_time(timestamp_ms)
        return self._cmd(frame, {"last_command": "sync_time"})

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
    # Mount mode
    # ------------------------------------------------------------------

    def set_hoist_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_HOIST(), {"last_command": "hoist_mode"})

    def set_upside_down_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_INVERT(), {"last_command": "upside_down_mode"})

    def set_follow_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_FOLLOW(), {"last_command": "follow_mode"})

    def set_lock_mode(self) -> dict:
        return self._cmd(proto.CMD_PTZ_LOCK(), {"last_command": "lock_mode"})

    def set_speed_mode(self, mode: str = "constant") -> dict:
        return {"success": True, "note": "Speed mode not configurable in this firmware"}

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
        return self._cmd(proto.CMD_RESET(), {"last_command": "reboot"})

    def upgrade_firmware(self, file_path: str = "") -> dict:
        return {"success": False, "error": "Firmware upgrade not supported over this interface."}

    # ------------------------------------------------------------------
    # Query commands
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
    # Raw command passthrough
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
