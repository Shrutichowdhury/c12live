"""
stream_manager.py
-----------------
Manages an RTSP video stream in a background thread.
Continuously reads frames, calculates FPS, and auto-reconnects on failure.
"""

import threading
import time
import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Target frame dimensions
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# Reconnect delay in seconds when a stream fails
RECONNECT_DELAY = 3.0


class StreamManager:
    """
    Opens an RTSP stream in a background thread, stores the latest JPEG frame,
    tracks FPS, and automatically reconnects when the stream drops.
    """

    def __init__(self, name: str, rtsp_url: str):
        """
        Args:
            name:     Human-readable label (e.g. "Visible", "Thermal").
            rtsp_url: Full RTSP URL for the camera stream.
        """
        self.name = name
        self.rtsp_url = rtsp_url

        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

        # Latest JPEG-encoded frame (bytes)
        self._frame: bytes = self._make_offline_frame()

        # FPS tracking
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._fps_start: float = time.time()

        # Connection state
        self.connected: bool = False

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background capture thread if not already running."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("[%s] Stream thread started → %s", self.name, self.rtsp_url)

    def stop(self) -> None:
        """Signal the capture thread to stop and release the capture device."""
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        self.connected = False
        self._fps = 0.0
        self._frame = self._make_offline_frame()
        logger.info("[%s] Stream stopped.", self.name)

    # ------------------------------------------------------------------
    # Frame / status accessors (thread-safe)
    # ------------------------------------------------------------------

    def get_frame(self) -> bytes:
        """Return the latest JPEG frame as raw bytes."""
        with self._lock:
            return self._frame

    def get_fps(self) -> float:
        """Return the current measured FPS."""
        return round(self._fps, 1)

    # ------------------------------------------------------------------
    # Internal capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Main loop: open stream → read frames → reconnect on error."""
        while self._running:
            self._open_stream()
            if not self.connected:
                # Could not connect — show offline frame and wait before retry
                with self._lock:
                    self._frame = self._make_offline_frame()
                time.sleep(RECONNECT_DELAY)
                continue

            # Reset FPS counters after a fresh connection
            self._frame_count = 0
            self._fps_start = time.time()

            while self._running:
                if self._cap is None or not self._cap.isOpened():
                    break

                ret, frame = self._cap.read()
                if not ret or frame is None:
                    logger.warning("[%s] Frame read failed — reconnecting.", self.name)
                    self.connected = False
                    break

                # Resize to target resolution
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

                # Encode as JPEG
                ret_enc, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if not ret_enc:
                    continue

                with self._lock:
                    self._frame = buffer.tobytes()

                # Update FPS counter
                self._frame_count += 1
                elapsed = time.time() - self._fps_start
                if elapsed >= 1.0:
                    self._fps = self._frame_count / elapsed
                    self._frame_count = 0
                    self._fps_start = time.time()

            # Exited inner loop — stream dropped or stopped
            if self._cap:
                self._cap.release()
                self._cap = None
            self.connected = False

            if self._running:
                logger.info(
                    "[%s] Reconnecting in %.1f s…", self.name, RECONNECT_DELAY
                )
                with self._lock:
                    self._frame = self._make_offline_frame()
                time.sleep(RECONNECT_DELAY)

    def _open_stream(self) -> None:
        """Attempt to open the RTSP URL with OpenCV."""
        logger.info("[%s] Connecting to %s", self.name, self.rtsp_url)
        try:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            if cap.isOpened():
                self._cap = cap
                self.connected = True
                logger.info("[%s] Connected successfully.", self.name)
            else:
                cap.release()
                self.connected = False
                logger.warning("[%s] Could not open stream.", self.name)
        except Exception as exc:
            self.connected = False
            logger.error("[%s] Exception opening stream: %s", self.name, exc)

    # ------------------------------------------------------------------
    # Placeholder frame generator
    # ------------------------------------------------------------------

    def _make_offline_frame(self) -> bytes:
        """
        Generate a dark placeholder JPEG with "Stream Offline" text
        and the RTSP URL, so the browser img tag always shows something.
        """
        img = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)  # dark grey background

        font = cv2.FONT_HERSHEY_SIMPLEX

        # Main "Stream Offline" label
        text_main = "Stream Offline"
        scale_main = 2.0
        thickness_main = 3
        (tw, th), _ = cv2.getTextSize(text_main, font, scale_main, thickness_main)
        cx = (FRAME_WIDTH - tw) // 2
        cy = FRAME_HEIGHT // 2 - 60
        cv2.putText(img, text_main, (cx, cy), font, scale_main, (80, 80, 200), thickness_main, cv2.LINE_AA)

        # Camera name
        text_name = f"[ {self.name} ]"
        scale_name = 1.0
        (tw2, _), _ = cv2.getTextSize(text_name, font, scale_name, 2)
        cv2.putText(img, text_name, ((FRAME_WIDTH - tw2) // 2, cy + 60), font, scale_name, (150, 150, 150), 2, cv2.LINE_AA)

        # RTSP URL
        scale_url = 0.55
        (tw3, _), _ = cv2.getTextSize(self.rtsp_url, font, scale_url, 1)
        cv2.putText(img, self.rtsp_url, ((FRAME_WIDTH - tw3) // 2, cy + 110), font, scale_url, (100, 200, 100), 1, cv2.LINE_AA)

        # Hint
        hint = "Run locally on the same network as 192.168.144.108"
        scale_hint = 0.5
        (tw4, _), _ = cv2.getTextSize(hint, font, scale_hint, 1)
        cv2.putText(img, hint, ((FRAME_WIDTH - tw4) // 2, cy + 155), font, scale_hint, (120, 120, 120), 1, cv2.LINE_AA)

        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
