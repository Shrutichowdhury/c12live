/**
 * controls.js — SkyDroid C12 Ground Control Station
 * Full-screen drone GCS — all UI bindings, stream management, status HUD.
 */

"use strict";

// ─── API helpers ─────────────────────────────────────────────────────────────

async function apiPost(path, body = {}) {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.success && data.error) showToast("⚠ " + data.error, "error");
    return data;
  } catch (err) {
    return { success: false, error: err.message };
  }
}

async function apiGet(path) {
  try { return await (await fetch(path)).json(); }
  catch { return null; }
}

// ─── Toast ────────────────────────────────────────────────────────────────────

let _toastTimer = null;
function showToast(msg, type = "info") {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "show" + (type === "error" ? " toast-error" : type === "success" ? " toast-success" : "");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ""; }, 2800);
}

// ─── Stream state ─────────────────────────────────────────────────────────────

let _mainStream = "visible";   // "visible" | "thermal"
let _recording  = false;
let _recSeconds = 0;
let _recInterval = null;

const STREAM_URLS  = { visible: "/video/visible", thermal: "/video/thermal" };
const STREAM_LABEL = { visible: "VISIBLE",        thermal: "THERMAL"       };

function applyStreamLayout() {
  const mainImg = document.getElementById("main-stream");
  const pipImg  = document.getElementById("pip-stream");
  const mainLbl = document.getElementById("main-stream-label");
  const pipLbl  = document.getElementById("pip-label");
  const pip     = document.getElementById("pip-wrap");
  const sec     = _mainStream === "visible" ? "thermal" : "visible";

  if (mainImg) mainImg.src = STREAM_URLS[_mainStream];
  if (pipImg)  pipImg.src  = STREAM_URLS[sec];
  if (mainLbl) mainLbl.textContent = STREAM_LABEL[_mainStream];
  if (pipLbl)  pipLbl.textContent  = STREAM_LABEL[sec];
}

function swapStreams() {
  _mainStream = _mainStream === "visible" ? "thermal" : "visible";
  applyStreamLayout();
  showToast("Switched to " + STREAM_LABEL[_mainStream], "info");
}

function initStreamControls() {
  on("btn-swap-streams", "click", (e) => { e.stopPropagation(); swapStreams(); });
  const pip = document.getElementById("pip-wrap");
  if (pip) pip.addEventListener("click", swapStreams);
  applyStreamLayout();
}

// ─── Fullscreen ───────────────────────────────────────────────────────────────

function initFullscreen() {
  on("btn-fullscreen", "click", () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  });
  document.addEventListener("fullscreenchange", () => {
    const btn = document.getElementById("btn-fullscreen");
    if (!btn) return;
    if (document.fullscreenElement) {
      btn.textContent = "⊡";
      btn.title = "Exit full screen";
    } else {
      btn.textContent = "⛶";
      btn.title = "Full screen";
    }
  });
}

// ─── Status polling ───────────────────────────────────────────────────────────

async function fetchStatus() {
  const data = await apiGet("/api/status");
  if (!data) return;

  // Live/offline badge
  const live = data.visible_connected || data.thermal_connected;
  const liveBadge = document.getElementById("live-badge");
  if (liveBadge) {
    liveBadge.className = "live-badge" + (live ? "" : " offline");
    liveBadge.innerHTML = live
      ? '<span class="live-dot"></span>LIVE'
      : '<span class="live-dot"></span>OFFLINE';
  }

  // FPS (main stream)
  const fps = _mainStream === "visible"
    ? (data.visible_fps || 0)
    : (data.thermal_fps || 0);
  setText("hud-fps", fps.toFixed(1));

  // Signal bars — derive from FPS
  updateSignalBars(live ? Math.min(4, Math.ceil(fps / 8)) : 0);

  // Mode chip
  const chip = document.getElementById("hud-mode");
  if (chip) {
    chip.textContent = data.mock_mode ? "MOCK" : "LIVE";
    chip.className   = "mode-chip " + (data.mock_mode ? "mode-mock" : "mode-live");
  }

  // Recording badge + timer
  if (data.recording !== _recording) {
    _recording = data.recording;
    if (_recording) {
      _recSeconds = 0;
      clearInterval(_recInterval);
      _recInterval = setInterval(() => {
        _recSeconds++;
        setText("rec-timer", formatRecTime(_recSeconds));
      }, 1000);
    } else {
      clearInterval(_recInterval);
    }
    const recBadge = document.getElementById("rec-badge");
    if (recBadge) recBadge.classList.toggle("hidden", !_recording);
    const recBtn = document.getElementById("btn-rec-toggle");
    if (recBtn) recBtn.classList.toggle("recording", _recording);
    setText("rec-label", _recording ? "STOP" : "REC");
  }

  // Gimbal angle readouts
  const pitch = data.gimbal_pitch ?? 0;
  const yaw   = data.gimbal_yaw   ?? 0;
  updateAngleBar("pitch-bar", pitch, -90, 90);
  updateAngleBar("yaw-bar",   yaw,   -90, 90);
  setText("display-pitch", pitch.toFixed(1) + "°");
  setText("display-yaw",   yaw.toFixed(1)   + "°");

  // Zoom readout
  const zoom = data.zoom ?? 1.0;
  setText("zoom-readout", zoom.toFixed(1) + "×");
  setText("zoom-display", zoom.toFixed(1) + "×");

  // Sync zoom ratio buttons
  if (typeof data.zoom_ratio === "number") syncZoomRatioButtons(data.zoom_ratio);

  // Palette
  if (typeof data.palette_index === "number") {
    document.querySelectorAll(".palette-swatch").forEach(el => {
      el.classList.toggle("active", +el.dataset.index === data.palette_index);
    });
    const p = PALETTES[data.palette_index];
    if (p) setText("palette-current-label", p.short);
  }

  // No-signal overlay
  const noSig = document.getElementById("no-signal");
  if (noSig) noSig.classList.toggle("hidden", live);
}

function updateSignalBars(strength) {  // 0-4
  for (let i = 1; i <= 4; i++) {
    const el = document.querySelector(`.sig-bar.s${i}`);
    if (el) el.classList.toggle("active", i <= strength);
  }
}

function updateAngleBar(barId, value, min, max) {
  const bar = document.getElementById(barId);
  if (!bar) return;
  const pct = Math.min(1, Math.abs(value) / (Math.max(Math.abs(min), Math.abs(max)))) * 50;
  if (value >= 0) {
    bar.style.left  = "50%";
    bar.style.width = pct + "%";
  } else {
    bar.style.width = pct + "%";
    bar.style.left  = (50 - pct) + "%";
  }
}

function formatRecTime(s) {
  const m = Math.floor(s / 60), sec = s % 60;
  return String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
}

// ─── Hold-to-move ─────────────────────────────────────────────────────────────

const _holdIntervals = new Map();

function startHold(endpoint, ms = 140) {
  if (_holdIntervals.has(endpoint)) return;
  apiPost(endpoint);
  const id = setInterval(() => apiPost(endpoint), ms);
  _holdIntervals.set(endpoint, id);
}

// Gimbal hold: fires stop command when finger/mouse lifts
function stopHoldGimbal(endpoint) {
  if (!_holdIntervals.has(endpoint)) return;
  clearInterval(_holdIntervals.get(endpoint));
  _holdIntervals.delete(endpoint);
  if (_holdIntervals.size === 0) apiPost("/api/gimbal/stop");
}

// Action hold (zoom, etc.): just stops the interval — NO gimbal stop
function stopHoldAction(endpoint) {
  if (!_holdIntervals.has(endpoint)) return;
  clearInterval(_holdIntervals.get(endpoint));
  _holdIntervals.delete(endpoint);
}

// Gimbal D-pad buttons
function bindHold(btnId, endpoint) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const start = e => { e.preventDefault(); startHold(endpoint); };
  const stop  = ()  => stopHoldGimbal(endpoint);
  btn.addEventListener("mousedown",  start);
  btn.addEventListener("mouseup",    stop);
  btn.addEventListener("mouseleave", stop);
  btn.addEventListener("touchstart", start, { passive: false });
  btn.addEventListener("touchend",   stop);
}

// Non-gimbal repeating buttons (zoom in/out, etc.)
function bindHoldAction(btnId, endpoint) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const start = e => { e.preventDefault(); startHold(endpoint); };
  const stop  = ()  => stopHoldAction(endpoint);
  btn.addEventListener("mousedown",  start);
  btn.addEventListener("mouseup",    stop);
  btn.addEventListener("mouseleave", stop);
  btn.addEventListener("touchstart", start, { passive: false });
  btn.addEventListener("touchend",   stop);
}

// ─── Gimbal controls ──────────────────────────────────────────────────────────

function initGimbalControls() {
  bindHold("btn-pitch-up",   "/api/gimbal/pitch_up");
  bindHold("btn-pitch-down", "/api/gimbal/pitch_down");
  bindHold("btn-yaw-left",   "/api/gimbal/yaw_left");
  bindHold("btn-yaw-right",  "/api/gimbal/yaw_right");
  bindHold("btn-roll-left",  "/api/gimbal/roll_left");
  bindHold("btn-roll-right", "/api/gimbal/roll_right");

  on("btn-gimbal-stop", "click", () => apiPost("/api/gimbal/stop"));
  on("btn-center",      "click", () => { apiPost("/api/gimbal/center"); showToast("⊕ Centred"); });
}

// ─── Goto angle (settings panel) ─────────────────────────────────────────────

function initGotoAngle() {
  on("btn-goto-angle", "click", async () => {
    const yaw   = parseFloat(document.getElementById("inp-goto-yaw")?.value   || 0);
    const pitch = parseFloat(document.getElementById("inp-goto-pitch")?.value || 0);
    if (isNaN(yaw)   || yaw   < -90 || yaw   > 90) { showToast("Yaw must be -90…+90°", "error"); return; }
    if (isNaN(pitch) || pitch < -90 || pitch > 90) { showToast("Pitch must be -90…+90°", "error"); return; }
    await Promise.all([
      apiPost("/api/gimbal/goto_yaw",   { degrees: yaw }),
      apiPost("/api/gimbal/goto_pitch", { degrees: pitch }),
    ]);
    showToast(`↗ Goto yaw ${yaw}° pitch ${pitch}°`, "success");
  });

  on("btn-look-down",    "click", async () => {
    await apiPost("/api/gimbal/look_down");
    showToast("↓ Nadir", "info");
  });
  on("btn-look-forward", "click", async () => {
    await apiPost("/api/gimbal/look_forward");
    showToast("→ Forward", "info");
  });
}

// ─── Camera controls ──────────────────────────────────────────────────────────

function initCameraControls() {
  on("btn-photo", "click", async () => {
    await apiPost("/api/camera/photo");
    showToast("📷 Photo saved", "success");
  });

  on("btn-rec-toggle", "click", async () => {
    if (_recording) {
      await apiPost("/api/camera/stop_recording");
      showToast("■ Recording stopped");
    } else {
      await apiPost("/api/camera/start_recording");
      showToast("⏺ Recording started", "success");
    }
  });
}

// ─── Zoom ─────────────────────────────────────────────────────────────────────

function initZoomControls() {
  bindHoldAction("btn-zoom-in",  "/api/camera/zoom_in");
  bindHoldAction("btn-zoom-out", "/api/camera/zoom_out");
}

function syncZoomRatioButtons(activeRatio) {
  document.querySelectorAll(".zr-btn").forEach(btn => {
    btn.classList.toggle("active", +btn.dataset.ratio === activeRatio);
  });
}

function initZoomRatioControls() {
  document.querySelectorAll(".zr-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const ratio = +btn.dataset.ratio;
      const r = await apiPost("/api/camera/zoom_ratio", { ratio });
      if (r.success) {
        syncZoomRatioButtons(ratio);
        showToast(`🔍 ${["1×","2×","4×","8×","16×"][ratio]}`, "info");
      }
    });
  });
}

// ─── Thermal palette strip ────────────────────────────────────────────────────

const PALETTES = [
  { index:0, label:"White Hot",  short:"WHT", color:"#e8e8e8" },
  { index:1, label:"Sepia",      short:"SPA", color:"#b87333" },
  { index:2, label:"Iron Bow",   short:"IRN", color:"#c0392b" },
  { index:3, label:"Rainbow",    short:"RBW", color:"#9b59b6" },
  { index:4, label:"Aurora",     short:"AUR", color:"#1abc9c" },
  { index:5, label:"Red Hot",    short:"RED", color:"#e74c3c" },
  { index:6, label:"Jungle",     short:"JNG", color:"#27ae60" },
  { index:7, label:"Medical",    short:"MED", color:"#2980b9" },
  { index:8, label:"Black Hot",  short:"BLK", color:"#555"    },
  { index:9, label:"Glory Hot",  short:"GLR", color:"#f39c12" },
];

function initPaletteStrip() {
  const drawer = document.getElementById("palette-drawer");
  if (!drawer) return;

  // Populate swatches
  PALETTES.forEach(p => {
    const btn = document.createElement("button");
    btn.className = "palette-swatch" + (p.index === 0 ? " active" : "");
    btn.dataset.index = p.index;
    btn.innerHTML = `<span class="swatch-dot" style="background:${p.color}"></span>${p.label}`;
    btn.addEventListener("click", async () => {
      const r = await apiPost("/api/thermal/palette_index", { index: p.index });
      if (r.success) {
        document.querySelectorAll(".palette-swatch").forEach(s => s.classList.remove("active"));
        btn.classList.add("active");
        setText("palette-current-label", p.short);
        showToast("🌡 " + p.label, "info");
      }
    });
    drawer.appendChild(btn);
  });

  // Toggle drawer
  on("btn-palette-toggle", "click", () => {
    drawer.classList.toggle("open");
  });

  // Close drawer when clicking elsewhere
  document.addEventListener("click", (e) => {
    const strip = document.getElementById("palette-strip");
    if (strip && !strip.contains(e.target)) {
      drawer.classList.remove("open");
    }
  });
}

// ─── Time sync ────────────────────────────────────────────────────────────────

function initTimeSyncControl() {
  on("btn-sync-time", "click", async () => {
    const r = await apiPost("/api/camera/sync_time", { timestamp_ms: Date.now() });
    const el = document.getElementById("sync-result");
    if (r.success) {
      const utc = new Date().toUTCString().replace("GMT", "UTC");
      if (el) { el.textContent = "✓ " + utc; el.classList.remove("hidden"); }
      showToast("⏱ Time synced", "success");
    } else {
      if (el) { el.textContent = "✗ " + (r.error || "Failed"); el.classList.remove("hidden"); }
    }
  });
}

// ─── Settings modal ───────────────────────────────────────────────────────────

function openSettings()  {
  const o = document.getElementById("settings-overlay");
  if (o) o.classList.remove("hidden");
}
function closeSettings() {
  const o = document.getElementById("settings-overlay");
  if (o) o.classList.add("hidden");
}

function applyModeUI(isMock) {
  const txt  = document.getElementById("conn-mode-text");
  const chip = document.getElementById("hud-mode");
  if (txt) {
    txt.textContent = isMock
      ? "⚠ Simulation — commands not sent to camera"
      : "✓ Live — commands sent to camera";
    txt.className = "conn-status-text " + (isMock ? "mock" : "live");
  }
  if (chip) {
    chip.textContent = isMock ? "MOCK" : "LIVE";
    chip.className   = "mode-chip " + (isMock ? "mode-mock" : "mode-live");
  }
}

async function loadConfig() {
  const cfg = await apiGet("/api/config");
  if (!cfg) return;
  const ip   = document.getElementById("inp-camera-ip");
  const port = document.getElementById("inp-control-port");
  if (ip)   ip.value   = cfg.camera_ip    || "192.168.144.108";
  if (port) port.value = cfg.control_port || 5000;
  applyModeUI(cfg.mock_mode !== false);
}

function initSettingsModal() {
  on("btn-settings",       "click", openSettings);
  on("btn-settings-close", "click", closeSettings);
  on("btn-kb-help",        "click", () => {
    const o = document.getElementById("kb-overlay");
    if (o) o.classList.toggle("hidden");
  });

  // Close overlay on backdrop click
  const overlay = document.getElementById("settings-overlay");
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeSettings();
    });
  }

  // Esc closes both modals
  document.addEventListener("keydown", e => {
    if (e.code === "Escape") {
      closeSettings();
      const kb = document.getElementById("kb-overlay");
      if (kb) kb.classList.add("hidden");
    }
  });

  // Go Live / Simulation
  on("btn-enable-real", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    showToast("Connecting to " + ip + "…", "info");
    const r = await apiPost("/api/config", { mock_mode: false, camera_ip: ip, control_port: port });
    if (r.success) {
      applyModeUI(r.mock_mode);
      showToast(r.mock_mode ? "⚠ Could not reach camera" : "✓ Live mode active", r.mock_mode ? "error" : "success");
    }
  });

  on("btn-enable-mock", "click", async () => {
    const r = await apiPost("/api/config", { mock_mode: true });
    if (r.success) { applyModeUI(true); showToast("Simulation mode", "info"); }
  });

  // Test connection
  on("btn-test-conn", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const box  = document.getElementById("conn-result");
    if (box) { box.textContent = "Testing…"; box.className = "sp-result"; }
    const r = await apiPost("/api/connection/test", { camera_ip: ip, control_port: port });
    if (!box) return;
    if (r.reachable) {
      box.className = "sp-result ok";
      box.textContent = "✓ Reachable — port " + port + " open on " + ip
        + (r.reply_hex ? "\nCamera replied: " + r.reply_hex : "");
    } else {
      box.className = "sp-result err";
      box.textContent = "✗ Not reachable — " + (r.error || "no response") + "\nRun locally on same LAN as camera.";
    }
    box.classList.remove("hidden");
  });

  // Protocol scan
  on("btn-probe-conn", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const box  = document.getElementById("conn-result");
    if (box) { box.textContent = "Scanning…(~15s, watch if gimbal moves)"; box.className = "sp-result"; box.classList.remove("hidden"); }
    const r = await apiPost("/api/probe", { camera_ip: ip, control_port: port });
    if (!box) return;
    let out = "Protocol Scan — " + ip + ":" + port + "\n\n";
    let anyReply = false;
    (r.probes || []).forEach(p => {
      out += "• " + p.probe + "\n";
      if (p.reply_text) { anyReply = true; out += "  ✓ " + p.reply_text + "\n"; }
      else if (p.count > 0) { anyReply = true; out += "  ✓ " + p.count + " packets\n"; }
      else out += "  no reply\n";
    });
    out += anyReply ? "\n★ Camera responded! Click Go Live." : "\nNo replies (did the gimbal move?)";
    box.className = "sp-result " + (anyReply ? "ok" : "");
    box.textContent = out;
  });

  // Thermal gain
  const gainSel = document.getElementById("gain-select");
  if (gainSel) gainSel.addEventListener("change", async () => {
    await apiPost("/api/thermal/set_gain", { mode: gainSel.value });
    showToast("Gain: " + gainSel.value);
  });

  // Temp measurement
  const tempTog = document.getElementById("temp-measure-toggle");
  if (tempTog) tempTog.addEventListener("change", async () => {
    await apiPost("/api/thermal/temperature_measurement", { enabled: tempTog.checked });
    showToast("Temp measurement " + (tempTog.checked ? "ON" : "OFF"));
  });

  // Calibration
  on("btn-cal-temp",  "click", async () => { await apiPost("/api/calibration/temperature"); showToast("🌡 Temp calibration"); });
  on("btn-cal-horiz", "click", async () => { await apiPost("/api/calibration/horizontal");  showToast("↔ H-Cal"); });
  on("btn-cal-vert",  "click", async () => { await apiPost("/api/calibration/vertical");    showToast("↕ V-Cal"); });

  // Raw command
  on("btn-raw-send", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const cmd  = document.getElementById("inp-raw-cmd")?.value?.trim() || "";
    const crc  = document.getElementById("chk-raw-crc")?.checked !== false;
    const box  = document.getElementById("raw-result");
    if (!cmd) { showToast("Enter a command", "error"); return; }
    if (box) { box.textContent = "Sending…"; box.className = "sp-result"; box.classList.remove("hidden"); }
    const r = await apiPost("/api/raw_command", { cmd, add_crc: crc, camera_ip: ip, port, wait_reply: true });
    if (!box) return;
    box.textContent = "Sent:  " + (r.sent_ascii || cmd) + "\n"
      + "Hex:   " + (r.sent_hex || "")  + "\n"
      + (r.reply_ascii ? "Reply: " + r.reply_ascii : "Reply: (none)");
    box.className = "sp-result " + (r.reply_ascii ? "ok" : "");
  });
}

// ─── Utility ──────────────────────────────────────────────────────────────────

function on(id, event, handler) {
  const el = document.getElementById(id);
  if (el) el.addEventListener(event, handler);
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initStreamControls();
  initFullscreen();
  initGimbalControls();
  initGotoAngle();
  initCameraControls();
  initZoomControls();
  initZoomRatioControls();
  initPaletteStrip();
  initTimeSyncControl();
  initSettingsModal();
  loadConfig();
  // Status polling started by app.js
});
