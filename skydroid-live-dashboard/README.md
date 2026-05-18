# SkyDroid C12 Control Center

A professional web dashboard for the **SkyDroid C12** gimbal camera.
Streams live visible and thermal video, and provides full gimbal/camera
control via a DJI-style dark UI — including Mock Mode so everything
works immediately without a real camera connected.

---

## Features

- Live MJPEG streaming — visible light + thermal (RTSP via OpenCV)
- Automatic stream reconnection with offline placeholder
- **Full gimbal control** — pitch, yaw, roll, presets (center, look down…)
- **Zoom control** — buttons + slider (1×–4×)
- **Camera capture** — photo, start/stop recording with live indicator
- **Thermal settings** — 11 palettes, gain mode, temperature measurement toggle
- **Image settings** — brightness, contrast, saturation, sharpness sliders
- **Calibration tools** — temperature, horizontal, vertical, fine adjust
- **Working modes** — Normal, Hoist, Upside-Down
- **Speed modes** — Constant / Variable
- **Target tracking** — enable/disable (placeholder for real tracking)
- **Keyboard control** — W A S D Q E + Space + C + Z X (see below)
- **Mock Mode** — fully functional UI without real hardware
- **Real C12 controller** scaffold — ready for protocol implementation
- Dark aerospace theme with glassmorphism cards
- Fully responsive layout

---

## Folder Structure

```
skydroid-live-dashboard/
├── app.py                      # Flask entry point, all API routes
├── requirements.txt
├── README.md
├── services/
│   ├── __init__.py
│   ├── stream_manager.py       # RTSP capture, MJPEG, FPS, reconnect
│   ├── command_protocol.py     # Command definitions & packet builder scaffold
│   ├── mock_controller.py      # Full in-memory mock — works without camera
│   └── c12_controller.py      # Real TCP controller (fill in protocol later)
├── templates/
│   └── index.html              # Dashboard UI
├── static/
│   ├── css/style.css           # DJI-inspired dark theme
│   └── js/
│       ├── app.js              # Stream status polling & stream controls
│       ├── controls.js         # All camera/gimbal/thermal API calls
│       └── keyboard.js         # Keyboard & hold-to-move shortcuts
└── snapshots/                  # Reserved for snapshot saves
```

---

## Installation

> **Requirements:** Python 3.11+, same local network as the C12 camera.

```bash
# 1. Navigate to the project folder
cd skydroid-live-dashboard

# 2. Create and activate a virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Mock Mode (default)

By default `USE_MOCK_CONTROLLER = True` in `app.py`.  
In Mock Mode:

- All gimbal/camera API calls are accepted and logged.
- State is tracked in memory (zoom, palette, recording, etc.).
- The status panel updates in real time.
- No real camera or network connection is needed.
- Keyboard shortcuts and hold-to-move all work normally.

**To switch to real hardware**, set `USE_MOCK_CONTROLLER = False` in `app.py`:

```python
USE_MOCK_CONTROLLER = False   # line ~20 in app.py
```

The app will attempt a TCP connection to `CAMERA_IP:CONTROL_PORT`.
If the connection fails it automatically falls back to MockController
and logs a warning.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `W` / `↑` | Pitch Up |
| `S` / `↓` | Pitch Down |
| `A` / `←` | Yaw Left |
| `D` / `→` | Yaw Right |
| `Q` | Roll Left |
| `E` | Roll Right |
| `Space` | Stop Motion |
| `C` | Center All |
| `Z` | Zoom In |
| `X` | Zoom Out |
| `?` | Toggle shortcut overlay |
| `Esc` | Close overlay |

Hold any directional key for continuous motion. Releasing the last held key
automatically sends a Stop command.

---

## Configuration

Edit these constants near the top of `app.py`:

```python
CAMERA_IP           = "192.168.144.108"
CONTROL_PORT        = 37260       # TCP control port (adjust if different)
USE_MOCK_CONTROLLER = True        # False = real C12 via Ethernet
```

---

## How to Implement the Real Command Protocol

When you obtain the Ethernet protocol documentation for the C12:

1. Open `services/command_protocol.py`.
2. Fill in `build_command(name, params)` with real packet framing
   (header, command ID, payload, checksum).
3. Fill in `parse_response(data)` to decode the camera's reply.
4. Set `USE_MOCK_CONTROLLER = False` in `app.py`.
5. All 40+ API endpoints will immediately use the real hardware.

Everything else — the Flask routes, the UI, the JavaScript — stays
unchanged. The command names in `COMMANDS` map 1:1 to the methods
in both `MockController` and `C12Controller`.

---

## API Endpoints

### Stream
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Dashboard page |
| GET | `/video/visible` | MJPEG — visible camera |
| GET | `/video/thermal` | MJPEG — thermal camera |
| GET | `/api/status` | Combined stream + camera status |
| POST | `/api/start` | Start streams |
| POST | `/api/stop` | Stop streams |

### Gimbal
`POST /api/gimbal/{pitch_up, pitch_down, yaw_left, yaw_right, roll_left, roll_right, stop, center, center_yaw, look_down, look_forward}`

### Zoom
`POST /api/camera/{zoom_in, zoom_out, set_zoom}`  Body: `{"level": 2.0}`

### Camera Capture
`POST /api/camera/{photo, start_recording, stop_recording}`

### Thermal
`POST /api/thermal/{set_palette, set_gain, temperature_measurement}`

### Image
`POST /api/image/settings`  Body: `{"brightness":50, "contrast":50, ...}`

### Calibration
`POST /api/calibration/{temperature, horizontal, vertical, fine_adjust}`

### Mode & Speed
`POST /api/mode/{hoist, upside_down}`  
`POST /api/speed_mode`  Body: `{"mode": "constant"}`

### Tracking
`POST /api/tracking/{enable, disable}`

---

## RTSP URLs

| Camera | URL |
|--------|-----|
| Visible | `rtsp://192.168.144.108:554/stream=1` |
| Thermal | `rtsp://192.168.144.108:555/stream=2` |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Streams show "Offline" | Ensure your PC is on the same network as `192.168.144.108`. Ping it first. |
| `pip install opencv-python` fails | Try `opencv-python-headless` instead. |
| Port 5000 in use | Change `app.run(port=5001, ...)` in `app.py` |
| Low FPS | Check network bandwidth / Wi-Fi signal. |
| Replit Preview shows offline | Expected — Replit can't reach your local camera. Run locally. |
| Controller error in logs | Check `CAMERA_IP` and `CONTROL_PORT` in `app.py`. Mock Mode will activate automatically on failure. |
