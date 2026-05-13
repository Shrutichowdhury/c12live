# SkyDroid Live Streaming Dashboard

A professional web dashboard that displays two live RTSP streams from the **SkyDroid C12** camera — visible light and thermal — converted to browser-compatible MJPEG streams via Python and OpenCV.

---

## Features

- Live MJPEG streaming from two RTSP sources (visible + thermal)
- Automatic reconnection if a stream disconnects
- Real-time FPS measurement per stream
- Online / Offline status badges with 1-second polling
- Start / Stop stream controls
- Offline placeholder image when the camera is unreachable
- Dark-themed responsive dashboard (mobile-friendly)
- Modular, commented codebase

---

## Folder Structure

```
skydroid-live-dashboard/
├── app.py                  # Flask entry point, routes, stream init
├── requirements.txt
├── README.md
├── .gitignore
├── services/
│   ├── __init__.py
│   └── stream_manager.py   # RTSP capture thread, FPS, reconnect logic
├── templates/
│   └── index.html          # Dashboard UI
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js          # Status polling, button handlers
└── snapshots/              # (reserved for future snapshot saves)
```

---

## Installation

> **Requirement:** Python 3.11 or later.

### 1. Clone / download the project

Place the `skydroid-live-dashboard/` folder anywhere on your computer.

### 2. Create and activate a virtual environment

```bash
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running Locally

Make sure your computer is on the **same Wi-Fi / network** as the SkyDroid camera (`192.168.144.108`).

```bash
python app.py
```

Then open your browser and go to:

```
http://localhost:5000
```

The two RTSP streams will start automatically.

---

## RTSP Stream URLs

| Camera   | URL                                    |
|----------|----------------------------------------|
| Visible  | `rtsp://192.168.144.108:554/stream=1`  |
| Thermal  | `rtsp://192.168.144.108:555/stream=2`  |

---

## How to Change RTSP URLs

Open `app.py` and edit the two constants near the top:

```python
VISIBLE_RTSP = "rtsp://192.168.144.108:554/stream=1"
THERMAL_RTSP = "rtsp://192.168.144.108:555/stream=2"
```

Replace with your camera's IP, port, and stream path. No other changes are needed.

---

## API Endpoints

| Method | Route             | Description                         |
|--------|-------------------|-------------------------------------|
| GET    | `/`               | Dashboard page                      |
| GET    | `/video/visible`  | MJPEG stream — visible camera       |
| GET    | `/video/thermal`  | MJPEG stream — thermal camera       |
| GET    | `/api/status`     | JSON status (connection, FPS, uptime) |
| POST   | `/api/start`      | Start both streams                  |
| POST   | `/api/stop`       | Stop both streams                   |

`/api/status` response format:

```json
{
  "visible_connected": true,
  "thermal_connected": true,
  "visible_fps": 29.7,
  "thermal_fps": 24.5,
  "uptime_seconds": 1234
}
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Streams show "Offline" / placeholder | Ensure your PC is on the same network as `192.168.144.108`. Ping the camera first. |
| `pip install opencv-python` fails | Try `pip install opencv-python-headless` instead. |
| Port 5000 already in use | Change the port in `app.py`: `app.run(port=5001, ...)` |
| Very low FPS | Check network bandwidth / Wi-Fi signal. RTSP over a congested network causes frame drops. |
| Replit Preview shows offline | Expected — Replit cannot reach your local camera. Run the app locally. |

---

## Notes

- Frames are resized to **1280×720** before streaming.
- JPEG quality is set to **80** for a good speed/quality balance. Adjust `IMWRITE_JPEG_QUALITY` in `stream_manager.py` if needed.
- The app uses **threaded Flask** (`threaded=True`) so both MJPEG streams serve concurrently.
