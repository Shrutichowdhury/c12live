# SkyDroid C12 Control Center

A professional web dashboard for the **SkyDroid C12** gimbal camera.
Streams live visible and thermal video and provides full gimbal/camera
control via a DJI-style dark UI — with Mock Mode so the UI works
without any hardware connected.

---

## Important: must run locally

The camera is at `192.168.144.108` — a private LAN address.
**This server must run on a computer that is on the same network as the camera.**
Cloud-hosted environments (Replit preview, etc.) cannot reach private IP addresses.

---

## Quick start (local)

### Windows
```
Double-click  run_local.bat
```
Opens a terminal, creates a Python virtual environment, installs dependencies,
and starts the server on `http://localhost:5000`.

### macOS / Linux
```bash
chmod +x run_local.sh
./run_local.sh
```

### Manual
```bash
cd skydroid-live-dashboard
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Enabling real gimbal control

1. Start the server locally (see above).
2. Scroll to **Connection Settings** in the dashboard.
3. Click **Test Connection** — green means the control port is reachable.
4. Click **Protocol Probe** — sends two SIYI-format packets and shows
   any raw bytes the camera replies with.
   - If the reply starts with `5566` the protocol is confirmed.
5. Click **Enable Real Control** — commands go directly to the camera.

If the connection test times out, check:
- Your PC is on the same LAN as `192.168.144.108`
- The camera is powered and the Ethernet cable / Wi-Fi bridge is connected
- No firewall is blocking UDP port 37260

---

## Protocol

The C12 uses a **SIYI SDK-compatible binary protocol** over UDP port 37260.

Frame format:
```
[0x55][0x66][CTRL][LEN_L][LEN_H][SEQ_L][SEQ_H][CMD_ID][DATA…][CRC_L][CRC_H]
```
- CRC: CRC-16/IBM (ARC), polynomial 0x8005, reflected in/out
- CTRL: 0x01 = request

All packet builders are in `services/command_protocol.py`.
The controller is in `services/c12_controller.py` (UDP with TCP fallback).

---

## Features

- Live MJPEG streaming — visible light + thermal (RTSP via OpenCV)
- Automatic stream reconnection with offline placeholder
- **Full gimbal control** — pitch, yaw, roll, presets
- **Zoom control** — buttons + slider (1×–30×)
- **Camera capture** — photo, start/stop recording
- **Thermal settings** — 11 palettes, gain mode, temperature measurement
- **Image settings** — brightness, contrast, saturation, sharpness
- **Calibration tools** — temperature, horizontal, vertical, fine adjust
- **Working modes** — Normal, Hoist, Upside-Down
- **Speed modes** — Constant / Variable
- **Target tracking** toggle
- **Keyboard shortcuts** — W A S D Q E + Space + C + Z X (press `?`)
- **Mock Mode** — full UI simulation without any hardware
- **Connection Settings** panel — Test / Probe / enable Real Mode at runtime

---

## Keyboard shortcuts

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

---

## RTSP stream URLs

| Camera  | URL |
|---------|-----|
| Visible | `rtsp://192.168.144.108:554/stream=1` |
| Thermal | `rtsp://192.168.144.108:555/stream=2` |

---

## Folder structure

```
skydroid-live-dashboard/
├── app.py                      # Flask entry point, 40+ REST endpoints
├── requirements.txt
├── run_local.bat               # Windows one-click launcher
├── run_local.sh                # macOS/Linux one-click launcher
├── README.md
├── services/
│   ├── stream_manager.py       # RTSP capture, MJPEG, FPS, reconnect
│   ├── command_protocol.py     # SIYI binary protocol: frame builder, CRC, cmd helpers
│   ├── mock_controller.py      # Full in-memory mock — no camera needed
│   └── c12_controller.py       # Real controller — UDP (TCP fallback), SIYI frames
├── templates/
│   └── index.html              # Dashboard UI
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       ├── controls.js         # All API calls incl. connection settings
│       └── keyboard.js
└── snapshots/
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Not reachable" on Test Connection | Run the server locally, not in Replit cloud |
| Streams show "Offline" | Ensure your PC is on the same LAN as `192.168.144.108` |
| Gimbal moves in Mock Mode but not real | Protocol Probe — check reply bytes; try other UDP ports (14550, 8554) |
| `pip install opencv-python` fails | The `requirements.txt` uses `opencv-python-headless` (no GUI) |
| Port 5000 in use | Change the port in the last line of `app.py` |
