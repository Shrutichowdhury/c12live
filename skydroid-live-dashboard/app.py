"""
app.py
------
SkyDroid C12 Control Dashboard — Flask entry point.

Run locally:
    python app.py

Then open http://localhost:5000 in your browser.
NOTE: For live video the camera at 192.168.144.108 must be reachable.
      Camera control works immediately via Mock Mode (USE_MOCK_CONTROLLER = True).
"""

import time
import socket
import logging
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

from services.stream_manager import StreamManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime configuration (can be changed via /api/config at runtime)
# ---------------------------------------------------------------------------
_config = {
    "camera_ip":    "192.168.144.108",
    "control_port": 37260,
    "mock_mode":    True,   # Start in mock mode; user can disable from the UI
}

VISIBLE_RTSP = f"rtsp://{_config['camera_ip']}:554/stream=1"
THERMAL_RTSP = f"rtsp://{_config['camera_ip']}:555/stream=2"

# ---------------------------------------------------------------------------
# Controller factory
# ---------------------------------------------------------------------------
from services.mock_controller import MockController
from services.c12_controller   import C12Controller


def _make_controller(mock: bool, ip: str, port: int):
    """Instantiate the appropriate controller and connect if real."""
    if mock:
        c = MockController()
        logger.info("Controller: MOCK MODE — commands are simulated, no data sent to camera.")
        return c, True
    # Try real controller
    c = C12Controller(ip, port)
    res = c.connect()
    if res.get("success"):
        logger.info("Controller: connected to C12 at %s:%d", ip, port)
        return c, False
    # Connection failed — fall back to mock
    logger.warning(
        "Controller: could NOT connect to %s:%d (%s) — falling back to MOCK MODE.",
        ip, port, res.get("error", "unknown error"),
    )
    return MockController(), True


controller, _active_mock = _make_controller(
    _config["mock_mode"], _config["camera_ip"], _config["control_port"]
)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Stream managers
# ---------------------------------------------------------------------------
visible_stream = StreamManager("Visible", VISIBLE_RTSP)
thermal_stream = StreamManager("Thermal", THERMAL_RTSP)

_start_time: float = time.time()


# ---------------------------------------------------------------------------
# MJPEG helper
# ---------------------------------------------------------------------------
def _mjpeg_generator(stream: StreamManager):
    while True:
        frame = stream.get_frame()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame +
            b"\r\n"
        )


# ---------------------------------------------------------------------------
# Helper: wrap controller calls in try/except
# ---------------------------------------------------------------------------
def _call(fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        return jsonify(result)
    except Exception as exc:
        logger.error("Controller error: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video/visible")
def video_visible():
    return Response(
        _mjpeg_generator(visible_stream),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/video/thermal")
def video_thermal():
    return Response(
        _mjpeg_generator(thermal_stream),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    uptime = int(time.time() - _start_time)
    cam_status = controller.get_status()
    return jsonify({
        "visible_connected": visible_stream.connected,
        "thermal_connected": thermal_stream.connected,
        "visible_fps": visible_stream.get_fps(),
        "thermal_fps": thermal_stream.get_fps(),
        "uptime_seconds": uptime,
        "mock_mode": _active_mock,
        "recording": cam_status.get("recording", False),
        "tracking": cam_status.get("tracking", False),
        "zoom": cam_status.get("zoom", 1.0),
        "palette": cam_status.get("palette", "White Hot"),
        "last_command": cam_status.get("last_command"),
        "gimbal_pitch": cam_status.get("gimbal_pitch", 0.0),
        "gimbal_yaw": cam_status.get("gimbal_yaw", 0.0),
        "gimbal_roll": cam_status.get("gimbal_roll", 0.0),
    })


# ---------------------------------------------------------------------------
# Stream control (existing)
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def api_config_get():
    """Return current runtime configuration."""
    return jsonify({
        "camera_ip":    _config["camera_ip"],
        "control_port": _config["control_port"],
        "mock_mode":    _active_mock,
    })


@app.route("/api/config", methods=["POST"])
def api_config_set():
    """
    Update runtime configuration and reinitialise the controller.
    Body: { "camera_ip": "...", "control_port": 37260, "mock_mode": false }
    """
    global controller, _active_mock, _config
    body = request.json or {}

    if "camera_ip"    in body: _config["camera_ip"]    = str(body["camera_ip"])
    if "control_port" in body: _config["control_port"] = int(body["control_port"])
    if "mock_mode"    in body: _config["mock_mode"]    = bool(body["mock_mode"])

    # Re-instantiate controller with new settings
    controller, _active_mock = _make_controller(
        _config["mock_mode"], _config["camera_ip"], _config["control_port"]
    )
    logger.info("Config updated → %s (mock=%s)", _config, _active_mock)
    return jsonify({
        "success":      True,
        "mock_mode":    _active_mock,
        "camera_ip":    _config["camera_ip"],
        "control_port": _config["control_port"],
    })


@app.route("/api/connection/test", methods=["POST"])
def api_connection_test():
    """
    Try both UDP and TCP to the camera control port (2-second timeout each).
    Returns reachable=True/False plus which transport succeeded.
    """
    ip   = (request.json or {}).get("camera_ip",    _config["camera_ip"])
    port = int((request.json or {}).get("control_port", _config["control_port"]))

    # --- UDP probe first ---
    try:
        import services.command_protocol as proto
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        probe = proto.build_frame(proto.CMD.FIRMWARE_VERSION, b"", 0)
        s.sendto(probe, (ip, port))
        try:
            data, _ = s.recvfrom(1024)
            s.close()
            logger.info("Connection test UDP %s:%d — reachable, got %d bytes", ip, port, len(data))
            return jsonify({"success": True, "reachable": True, "transport": "udp",
                            "reply_hex": data.hex(), "ip": ip, "port": port})
        except socket.timeout:
            # No reply over UDP — port may still be open (fire-and-forget cameras)
            s.close()
            logger.info("Connection test UDP %s:%d — probe sent, no reply (normal for some cameras)", ip, port)
            # Fall through to TCP to confirm reachability
        except OSError:
            s.close()
    except Exception as exc:
        logger.warning("UDP probe exception: %s", exc)

    # --- TCP fallback ---
    try:
        s = socket.create_connection((ip, port), timeout=2)
        s.close()
        logger.info("Connection test TCP %s:%d — reachable", ip, port)
        return jsonify({"success": True, "reachable": True, "transport": "tcp", "ip": ip, "port": port})
    except OSError as exc:
        logger.warning("Connection test %s:%d — NOT reachable: %s", ip, port, exc)
        return jsonify({"success": True, "reachable": False, "ip": ip, "port": port,
                        "error": str(exc)})


@app.route("/api/probe", methods=["POST"])
def api_probe():
    """
    Multi-format protocol scanner.  Tries every known protocol variant used
    by Skydroid / SIYI / Viewpro cameras and returns raw replies.
    Also sends an actual center-gimbal command in each format so you can see
    if the gimbal physically moves.
    """
    ip   = (request.json or {}).get("camera_ip",    _config["camera_ip"])
    port = int((request.json or {}).get("control_port", _config["control_port"]))

    import services.command_protocol as proto
    results = []

    def udp_probe(name: str, pkt: bytes, listen_sec: float = 1.5) -> dict:
        """Send pkt over UDP and wait up to listen_sec for any reply."""
        entry = {"probe": name, "sent_hex": pkt.hex()}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(listen_sec)
            s.sendto(pkt, (ip, port))
            try:
                data, addr = s.recvfrom(4096)
                entry["reply_hex"] = data.hex()
                entry["reply_len"] = len(data)
                entry["reply_from"] = str(addr)
            except socket.timeout:
                entry["reply"] = "no_reply"
            s.close()
        except OSError as exc:
            entry["error"] = str(exc)
        return entry

    # ── 1. SIYI standard — firmware version query ──────────────────────────
    results.append(udp_probe(
        "siyi_v1_firmware",
        proto.build_frame(proto.CMD.FIRMWARE_VERSION, b"", 1),
    ))

    # ── 2. SIYI standard — gimbal attitude query ───────────────────────────
    results.append(udp_probe(
        "siyi_v1_attitude",
        proto.build_frame(proto.CMD.GIMBAL_ATTITUDE, b"", 2),
    ))

    # ── 3. SIYI standard — center gimbal (sends actual movement cmd) ───────
    results.append(udp_probe(
        "siyi_v1_center",
        proto.cmd_center_gimbal(3),
    ))

    # ── 4. SIYI v2 variant — some cameras use 0x6655 instead of 0x5566 ────
    #       frame: [0x66][0x55][0x01][len16LE][seq16LE][cmd][data][crc16LE]
    def siyi_v2_frame(cmd_id: int, data: bytes = b"", seq: int = 0) -> bytes:
        from services.command_protocol import crc16
        inner = bytes([0x01]) + (len(data)).to_bytes(2, "little") + \
                seq.to_bytes(2, "little") + bytes([cmd_id]) + data
        crc = crc16(inner)
        return bytes([0x66, 0x55]) + inner + crc.to_bytes(2, "little")

    results.append(udp_probe("siyi_v2_firmware", siyi_v2_frame(0x01, b"", 1)))
    results.append(udp_probe("siyi_v2_center",   siyi_v2_frame(0x0D, b"\x01", 2)))

    # ── 5. Viewpro / ViewLink protocol — magic 0xEB 0x90 ──────────────────
    #       [0xEB][0x90][addr][cmd][len][data…][checksum]
    def viewpro_frame(cmd: int, data: bytes = b"") -> bytes:
        body = bytes([0x01, cmd, len(data)]) + data
        chk  = sum(body) & 0xFF
        return bytes([0xEB, 0x90]) + body + bytes([chk])

    results.append(udp_probe("viewpro_query",  viewpro_frame(0x01)))
    results.append(udp_probe("viewpro_center", viewpro_frame(0x08, b"\x00\x00\x00")))

    # ── 6. MAVLink heartbeat — some cameras respond to MAVLink ─────────────
    #       HEARTBEAT (msg 0) from GCS (sys 255, comp 190)
    def mavlink_heartbeat() -> bytes:
        #  STX  len  seq  sys   comp  msgid  payload (9 bytes for HEARTBEAT)
        payload = bytes([
            0x00, 0x00, 0x00, 0x00,   # custom_mode
            0x06,                      # type=6 (GCS)
            0x08,                      # autopilot=8 (INVALID/NONE)
            0x00,                      # base_mode
            0x04,                      # system_status=4 (ACTIVE)
            0x03,                      # mavlink_version=3
        ])
        seq, sys_id, comp_id, msg_id = 0, 255, 190, 0
        header = bytes([0xFE, len(payload), seq, sys_id, comp_id, msg_id])
        crc_extra = 50   # HEARTBEAT CRC_EXTRA
        import struct
        crc_data = bytes([len(payload), seq, sys_id, comp_id, msg_id]) + payload + bytes([crc_extra])
        crc_val = 0xFFFF
        for b in crc_data:
            tmp = b ^ (crc_val & 0xFF)
            tmp = (tmp ^ (tmp << 4)) & 0xFF
            crc_val = (crc_val >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
            crc_val &= 0xFFFF
        return header + payload + struct.pack("<H", crc_val)

    results.append(udp_probe("mavlink_heartbeat", mavlink_heartbeat(), 2.0))

    # ── 7. Listen passively for camera broadcasts ──────────────────────────
    #       Many cameras broadcast status on the same port without any query.
    listen_entry = {"probe": "passive_listen_37260", "note": "waiting 3 s for camera broadcasts"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(3)
        s.bind(("0.0.0.0", port))
        broadcasts = []
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                data, addr = s.recvfrom(4096)
                broadcasts.append({"from": str(addr), "hex": data.hex(), "len": len(data)})
                if len(broadcasts) >= 5:
                    break
            except socket.timeout:
                break
        s.close()
        listen_entry["broadcasts"] = broadcasts
        listen_entry["count"] = len(broadcasts)
    except OSError as exc:
        listen_entry["error"] = str(exc)
    results.append(listen_entry)

    # ── 8. HTTP API probe — many cameras expose REST on 8080 / 8888 ───────
    http_results = []
    for http_port in [8080, 8888, 80]:
        for path in ["/", "/api/info", "/cgi-bin/param.cgi", "/Status"]:
            try:
                cs = socket.create_connection((ip, http_port), timeout=1)
                req = f"GET {path} HTTP/1.0\r\nHost: {ip}\r\n\r\n".encode()
                cs.sendall(req)
                cs.settimeout(1)
                raw = b""
                try:
                    while True:
                        chunk = cs.recv(512)
                        if not chunk:
                            break
                        raw += chunk
                        if len(raw) > 2048:
                            break
                except Exception:
                    pass
                cs.close()
                if raw:
                    http_results.append({
                        "port": http_port, "path": path,
                        "response_preview": raw[:300].decode("latin-1", errors="replace"),
                    })
                    break   # found HTTP on this port
            except OSError:
                pass
        if http_results and http_results[-1].get("port") == http_port:
            break

    if http_results:
        results.append({"probe": "http_api", "found": http_results})
    else:
        results.append({"probe": "http_api", "reply": "no HTTP on ports 80/8080/8888"})

    logger.info("Multi-protocol probe to %s:%d complete — %d probes", ip, port, len(results))
    return jsonify({"success": True, "ip": ip, "port": port, "probes": results})


@app.route("/api/probe/listen", methods=["POST"])
def api_probe_listen():
    """
    Bind to UDP on the given port and collect whatever the camera broadcasts
    for up to 5 seconds.  Returns raw hex packets.
    """
    ip   = (request.json or {}).get("camera_ip",    _config["camera_ip"])
    port = int((request.json or {}).get("control_port", _config["control_port"]))
    wait = float((request.json or {}).get("wait_seconds", 5))

    packets = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(wait)
        s.bind(("0.0.0.0", port))
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                data, addr = s.recvfrom(4096)
                packets.append({
                    "from": str(addr),
                    "hex":  data.hex(),
                    "len":  len(data),
                    "ascii": data.decode("latin-1", errors="replace"),
                })
                if len(packets) >= 20:
                    break
            except socket.timeout:
                break
        s.close()
    except OSError as exc:
        return jsonify({"success": False, "error": str(exc)})

    return jsonify({"success": True, "port": port, "packets": packets, "count": len(packets)})


@app.route("/api/start", methods=["POST"])
def api_start():
    visible_stream.start()
    thermal_stream.start()
    logger.info("Streams started via API.")
    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    visible_stream.stop()
    thermal_stream.stop()
    logger.info("Streams stopped via API.")
    return jsonify({"status": "stopped"})


# ---------------------------------------------------------------------------
# Camera status endpoint
# ---------------------------------------------------------------------------

@app.route("/api/camera/status")
def api_camera_status():
    return _call(controller.get_status)


# ---------------------------------------------------------------------------
# Gimbal control
# ---------------------------------------------------------------------------

@app.route("/api/gimbal/pitch_up", methods=["POST"])
def gimbal_pitch_up():
    speed = request.json.get("speed", 50) if request.json else 50
    return _call(controller.pitch_up, speed)


@app.route("/api/gimbal/pitch_down", methods=["POST"])
def gimbal_pitch_down():
    speed = request.json.get("speed", 50) if request.json else 50
    return _call(controller.pitch_down, speed)


@app.route("/api/gimbal/yaw_left", methods=["POST"])
def gimbal_yaw_left():
    speed = request.json.get("speed", 50) if request.json else 50
    return _call(controller.yaw_left, speed)


@app.route("/api/gimbal/yaw_right", methods=["POST"])
def gimbal_yaw_right():
    speed = request.json.get("speed", 50) if request.json else 50
    return _call(controller.yaw_right, speed)


@app.route("/api/gimbal/roll_left", methods=["POST"])
def gimbal_roll_left():
    speed = request.json.get("speed", 50) if request.json else 50
    return _call(controller.roll_left, speed)


@app.route("/api/gimbal/roll_right", methods=["POST"])
def gimbal_roll_right():
    speed = request.json.get("speed", 50) if request.json else 50
    return _call(controller.roll_right, speed)


@app.route("/api/gimbal/stop", methods=["POST"])
def gimbal_stop():
    return _call(controller.stop_motion)


@app.route("/api/gimbal/center", methods=["POST"])
def gimbal_center():
    return _call(controller.center_all)


@app.route("/api/gimbal/center_yaw", methods=["POST"])
def gimbal_center_yaw():
    return _call(controller.center_yaw)


@app.route("/api/gimbal/look_down", methods=["POST"])
def gimbal_look_down():
    return _call(controller.look_down)


@app.route("/api/gimbal/look_forward", methods=["POST"])
def gimbal_look_forward():
    return _call(controller.look_forward)


# ---------------------------------------------------------------------------
# Zoom control
# ---------------------------------------------------------------------------

@app.route("/api/camera/zoom_in", methods=["POST"])
def camera_zoom_in():
    return _call(controller.zoom_in)


@app.route("/api/camera/zoom_out", methods=["POST"])
def camera_zoom_out():
    return _call(controller.zoom_out)


@app.route("/api/camera/set_zoom", methods=["POST"])
def camera_set_zoom():
    level = (request.json or {}).get("level", 1.0)
    return _call(controller.set_zoom, level)


# ---------------------------------------------------------------------------
# Camera capture
# ---------------------------------------------------------------------------

@app.route("/api/camera/photo", methods=["POST"])
def camera_photo():
    return _call(controller.take_photo)


@app.route("/api/camera/start_recording", methods=["POST"])
def camera_start_recording():
    return _call(controller.start_recording)


@app.route("/api/camera/stop_recording", methods=["POST"])
def camera_stop_recording():
    return _call(controller.stop_recording)


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------

@app.route("/api/tracking/enable", methods=["POST"])
def tracking_enable():
    return _call(controller.enable_tracking)


@app.route("/api/tracking/disable", methods=["POST"])
def tracking_disable():
    return _call(controller.disable_tracking)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

@app.route("/api/calibration/temperature", methods=["POST"])
def calibration_temperature():
    return _call(controller.temperature_calibration)


@app.route("/api/calibration/horizontal", methods=["POST"])
def calibration_horizontal():
    return _call(controller.horizontal_calibration)


@app.route("/api/calibration/vertical", methods=["POST"])
def calibration_vertical():
    return _call(controller.vertical_calibration)


@app.route("/api/calibration/fine_adjust", methods=["POST"])
def calibration_fine_adjust():
    body = request.json or {}
    roll_offset  = float(body.get("roll_offset", 0.0))
    pitch_offset = float(body.get("pitch_offset", 0.0))
    return _call(controller.fine_adjust, roll_offset, pitch_offset)


# ---------------------------------------------------------------------------
# Thermal settings
# ---------------------------------------------------------------------------

@app.route("/api/thermal/set_palette", methods=["POST"])
def thermal_set_palette():
    name = (request.json or {}).get("palette", "White Hot")
    return _call(controller.set_palette, name)


@app.route("/api/thermal/set_gain", methods=["POST"])
def thermal_set_gain():
    mode = (request.json or {}).get("mode", "auto")
    return _call(controller.set_thermal_gain, mode)


@app.route("/api/thermal/temperature_measurement", methods=["POST"])
def thermal_temperature_measurement():
    enabled = (request.json or {}).get("enabled", True)
    return _call(controller.set_temperature_measurement, enabled)


# ---------------------------------------------------------------------------
# Image settings
# ---------------------------------------------------------------------------

@app.route("/api/image/settings", methods=["POST"])
def image_settings():
    body = request.json or {}
    results = {}
    if "brightness" in body:
        results["brightness"] = controller.set_brightness(int(body["brightness"]))
    if "contrast" in body:
        results["contrast"] = controller.set_contrast(int(body["contrast"]))
    if "saturation" in body:
        results["saturation"] = controller.set_saturation(int(body["saturation"]))
    if "sharpness" in body:
        results["sharpness"] = controller.set_sharpness(int(body["sharpness"]))
    return jsonify({"success": True, "results": results})


# ---------------------------------------------------------------------------
# Working mode
# ---------------------------------------------------------------------------

@app.route("/api/mode/hoist", methods=["POST"])
def mode_hoist():
    return _call(controller.set_hoist_mode)


@app.route("/api/mode/upside_down", methods=["POST"])
def mode_upside_down():
    return _call(controller.set_upside_down_mode)


# ---------------------------------------------------------------------------
# Speed mode
# ---------------------------------------------------------------------------

@app.route("/api/speed_mode", methods=["POST"])
def speed_mode():
    mode = (request.json or {}).get("mode", "constant")
    return _call(controller.set_speed_mode, mode)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting RTSP streams…")
    visible_stream.start()
    thermal_stream.start()

    try:
        app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
    finally:
        logger.info("Shutting down — releasing stream resources.")
        visible_stream.stop()
        thermal_stream.stop()
        if not USE_MOCK_CONTROLLER:
            controller.disconnect()
