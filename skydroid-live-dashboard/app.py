"""
app.py
------
SkyDroid Live Streaming Dashboard — Flask entry point.

Run locally:
    python app.py

Then open http://localhost:5000 in your browser.
NOTE: The camera at 192.168.144.108 must be reachable from this machine.
"""

import time
import logging
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

from services.stream_manager import StreamManager

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RTSP stream URLs
# ---------------------------------------------------------------------------
VISIBLE_RTSP = "rtsp://192.168.144.108:554/stream=1"
THERMAL_RTSP = "rtsp://192.168.144.108:555/stream=2"

# ---------------------------------------------------------------------------
# Flask app setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Stream manager instances
# ---------------------------------------------------------------------------
visible_stream = StreamManager("Visible", VISIBLE_RTSP)
thermal_stream = StreamManager("Thermal", THERMAL_RTSP)

# Track server start time for uptime calculation
_start_time: float = time.time()


# ---------------------------------------------------------------------------
# MJPEG generator helper
# ---------------------------------------------------------------------------
def _mjpeg_generator(stream: StreamManager):
    """
    Yields MJPEG frames from the given StreamManager in multipart format.
    Each frame is preceded by the required multipart boundary headers.
    """
    while True:
        frame = stream.get_frame()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame +
            b"\r\n"
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the dashboard HTML page."""
    return render_template("index.html")


@app.route("/video/visible")
def video_visible():
    """MJPEG stream for the visible-light camera."""
    return Response(
        _mjpeg_generator(visible_stream),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/video/thermal")
def video_thermal():
    """MJPEG stream for the thermal camera."""
    return Response(
        _mjpeg_generator(thermal_stream),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/status")
def api_status():
    """Return JSON status for both streams plus server uptime."""
    uptime = int(time.time() - _start_time)
    return jsonify(
        {
            "visible_connected": visible_stream.connected,
            "thermal_connected": thermal_stream.connected,
            "visible_fps": visible_stream.get_fps(),
            "thermal_fps": thermal_stream.get_fps(),
            "uptime_seconds": uptime,
        }
    )


@app.route("/api/start", methods=["POST"])
def api_start():
    """Start both RTSP streams."""
    visible_stream.start()
    thermal_stream.start()
    logger.info("Streams started via API.")
    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stop both RTSP streams."""
    visible_stream.stop()
    thermal_stream.stop()
    logger.info("Streams stopped via API.")
    return jsonify({"status": "stopped"})


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Auto-start both streams on launch
    logger.info("Starting RTSP streams automatically…")
    visible_stream.start()
    thermal_stream.start()

    try:
        app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
    finally:
        # Graceful shutdown — release OpenCV resources
        logger.info("Shutting down — releasing stream resources.")
        visible_stream.stop()
        thermal_stream.stop()
