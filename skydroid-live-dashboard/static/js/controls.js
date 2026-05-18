/**
 * controls.js — SkyDroid C12 Control Dashboard
 *
 * Handles all API calls to gimbal, zoom, camera, thermal, image settings,
 * calibration, mode, and tracking endpoints.
 * Polls /api/status every second to keep the status panel current.
 */

"use strict";

// ─── API helpers ────────────────────────────────────────────────────────────

async function apiPost(path, body = {}) {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.success && data.error) {
      showToast("⚠ " + data.error, "error");
    }
    return data;
  } catch (err) {
    showToast("⚠ Network error: " + err.message, "error");
    return { success: false, error: err.message };
  }
}

async function apiGet(path) {
  try {
    const res = await fetch(path);
    return await res.json();
  } catch (err) {
    return null;
  }
}

// ─── Toast notifications ─────────────────────────────────────────────────────

let _toastTimer = null;

function showToast(msg, type = "info") {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "show " + (type === "error" ? "toast-error" : type === "success" ? "toast-success" : "");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ""; }, 2800);
}

// ─── Status polling ──────────────────────────────────────────────────────────

async function fetchStatus() {
  const data = await apiGet("/api/status");
  if (!data) return;

  // Stream status badges
  setStreamBadge("visible-status",     data.visible_connected);
  setStreamBadge("thermal-status",     data.thermal_connected);
  setStreamBadge("visible-status-cam", data.visible_connected);
  setStreamBadge("thermal-status-cam", data.thermal_connected);

  // FPS
  setText("visible-fps",         (data.visible_fps || 0).toFixed(1) + " fps");
  setText("thermal-fps",         (data.thermal_fps || 0).toFixed(1) + " fps");
  setText("visible-fps-overlay", (data.visible_fps || 0).toFixed(1) + " fps");
  setText("thermal-fps-overlay", (data.thermal_fps || 0).toFixed(1) + " fps");

  // Uptime
  setText("uptime", formatUptime(data.uptime_seconds || 0));

  // Control status panel
  setStatusChip("status-mock",      data.mock_mode,   "Mock Mode",   "Live Mode");
  setStatusChip("status-recording", data.recording,   "REC ●",       "Not Recording");
  setStatusChip("status-tracking",  data.tracking,    "Tracking ON", "Tracking OFF");

  setText("status-palette", data.palette  || "—");
  setText("status-zoom",    (data.zoom || 1.0).toFixed(2) + "×");
  setText("status-cmd",     data.last_command || "—");

  // Zoom slider sync
  const zoomSlider = document.getElementById("zoom-slider");
  if (zoomSlider && document.activeElement !== zoomSlider) {
    zoomSlider.value = data.zoom || 1.0;
    setText("zoom-display", (data.zoom || 1.0).toFixed(2) + "×");
  }

  // Recording indicator
  const recIndicator = document.getElementById("rec-indicator");
  if (recIndicator) {
    recIndicator.classList.toggle("active", !!data.recording);
  }
}

function setStreamBadge(id, online) {
  const el = document.getElementById(id);
  if (!el) return;
  if (online) {
    el.className = "badge badge-online";
    el.innerHTML = '<span class="badge-dot"></span> Online';
  } else {
    el.className = "badge badge-offline";
    el.innerHTML = '<span class="badge-dot"></span> Offline';
  }
}

function setStatusChip(id, active, labelOn, labelOff) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = active ? labelOn : labelOff;
  el.className = "status-chip " + (active ? "chip-active" : "chip-inactive");
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function formatUptime(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return [h > 0 ? h + "h" : null, m > 0 ? m + "m" : null, sec + "s"]
    .filter(Boolean).join(" ");
}

// ─── Hold-to-move helpers ────────────────────────────────────────────────────

const _holdIntervals = new Map();

function startHold(endpoint, intervalMs = 150) {
  if (_holdIntervals.has(endpoint)) return;
  apiPost(endpoint); // immediate first call
  const id = setInterval(() => apiPost(endpoint), intervalMs);
  _holdIntervals.set(endpoint, id);
}

function stopHold(endpoint) {
  if (_holdIntervals.has(endpoint)) {
    clearInterval(_holdIntervals.get(endpoint));
    _holdIntervals.delete(endpoint);
    apiPost("/api/gimbal/stop");
  }
}

function bindHold(btnId, endpoint) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.addEventListener("mousedown",  (e) => { e.preventDefault(); startHold(endpoint); });
  btn.addEventListener("mouseup",    ()  => stopHold(endpoint));
  btn.addEventListener("mouseleave", ()  => stopHold(endpoint));
  btn.addEventListener("touchstart", (e) => { e.preventDefault(); startHold(endpoint); }, { passive: false });
  btn.addEventListener("touchend",   ()  => stopHold(endpoint));
}

// ─── Gimbal controls ─────────────────────────────────────────────────────────

function initGimbalControls() {
  bindHold("btn-pitch-up",   "/api/gimbal/pitch_up");
  bindHold("btn-pitch-down", "/api/gimbal/pitch_down");
  bindHold("btn-yaw-left",   "/api/gimbal/yaw_left");
  bindHold("btn-yaw-right",  "/api/gimbal/yaw_right");
  bindHold("btn-roll-left",  "/api/gimbal/roll_left");
  bindHold("btn-roll-right", "/api/gimbal/roll_right");

  on("btn-stop",         "click", () => { apiPost("/api/gimbal/stop");        showToast("⬛ Motion stopped"); });
  on("btn-center",       "click", () => { apiPost("/api/gimbal/center");       showToast("✦ Centered all axes"); });
  on("btn-center-yaw",   "click", () => { apiPost("/api/gimbal/center_yaw");   showToast("↔ Yaw centred"); });
  on("btn-look-down",    "click", () => { apiPost("/api/gimbal/look_down");    showToast("↓ Looking down"); });
  on("btn-look-forward", "click", () => { apiPost("/api/gimbal/look_forward"); showToast("→ Looking forward"); });
}

// ─── Zoom controls ───────────────────────────────────────────────────────────

function initZoomControls() {
  on("btn-zoom-in",  "click", async () => {
    const r = await apiPost("/api/camera/zoom_in");
    if (r.zoom) setText("zoom-display", r.zoom.toFixed(2) + "×");
    showToast("🔍 Zoom in");
  });
  on("btn-zoom-out", "click", async () => {
    const r = await apiPost("/api/camera/zoom_out");
    if (r.zoom) setText("zoom-display", r.zoom.toFixed(2) + "×");
    showToast("🔍 Zoom out");
  });

  const slider = document.getElementById("zoom-slider");
  if (slider) {
    slider.addEventListener("input", () => {
      setText("zoom-display", parseFloat(slider.value).toFixed(2) + "×");
    });
    slider.addEventListener("change", async () => {
      const r = await apiPost("/api/camera/set_zoom", { level: parseFloat(slider.value) });
      showToast("🔍 Zoom " + parseFloat(slider.value).toFixed(2) + "×");
    });
  }
}

// ─── Camera capture ──────────────────────────────────────────────────────────

function initCameraControls() {
  on("btn-photo", "click", async () => {
    await apiPost("/api/camera/photo");
    showToast("📷 Photo taken!", "success");
  });
  on("btn-rec-start", "click", async () => {
    await apiPost("/api/camera/start_recording");
    showToast("● Recording started", "success");
  });
  on("btn-rec-stop", "click", async () => {
    await apiPost("/api/camera/stop_recording");
    showToast("■ Recording stopped");
  });
}

// ─── Thermal controls ────────────────────────────────────────────────────────

function initThermalControls() {
  const paletteSelect = document.getElementById("palette-select");
  if (paletteSelect) {
    paletteSelect.addEventListener("change", async () => {
      await apiPost("/api/thermal/set_palette", { palette: paletteSelect.value });
      showToast("🌡 Palette: " + paletteSelect.value);
    });
  }

  const gainSelect = document.getElementById("gain-select");
  if (gainSelect) {
    gainSelect.addEventListener("change", async () => {
      await apiPost("/api/thermal/set_gain", { mode: gainSelect.value });
      showToast("🌡 Gain: " + gainSelect.value);
    });
  }

  const tempToggle = document.getElementById("temp-measure-toggle");
  if (tempToggle) {
    tempToggle.addEventListener("change", async () => {
      await apiPost("/api/thermal/temperature_measurement", { enabled: tempToggle.checked });
      showToast("🌡 Temp measurement " + (tempToggle.checked ? "ON" : "OFF"));
    });
  }
}

// ─── Image settings ──────────────────────────────────────────────────────────

function initImageSettings() {
  ["brightness", "contrast", "saturation", "sharpness"].forEach((key) => {
    const slider = document.getElementById("slider-" + key);
    const display = document.getElementById("val-" + key);
    if (!slider) return;
    slider.addEventListener("input", () => { if (display) display.textContent = slider.value; });
    slider.addEventListener("change", async () => {
      await apiPost("/api/image/settings", { [key]: parseInt(slider.value, 10) });
      showToast("🎨 " + capitalize(key) + ": " + slider.value);
    });
  });
}

// ─── Calibration ─────────────────────────────────────────────────────────────

function initCalibration() {
  on("btn-cal-temp", "click", async () => {
    await apiPost("/api/calibration/temperature");
    showToast("🌡 Temperature calibration run");
  });
  on("btn-cal-horiz", "click", async () => {
    await apiPost("/api/calibration/horizontal");
    showToast("↔ Horizontal calibration run");
  });
  on("btn-cal-vert", "click", async () => {
    await apiPost("/api/calibration/vertical");
    showToast("↕ Vertical calibration run");
  });
  on("btn-cal-fine", "click", async () => {
    const roll  = parseFloat(document.getElementById("fine-roll")?.value  || 0);
    const pitch = parseFloat(document.getElementById("fine-pitch")?.value || 0);
    await apiPost("/api/calibration/fine_adjust", { roll_offset: roll, pitch_offset: pitch });
    showToast("✦ Fine adjust applied");
  });
}

// ─── Working mode ────────────────────────────────────────────────────────────

function initWorkingMode() {
  on("btn-mode-hoist",       "click", async () => {
    await apiPost("/api/mode/hoist");
    showToast("⬆ Hoist mode active");
    setActiveMode("btn-mode-hoist");
  });
  on("btn-mode-upside-down", "click", async () => {
    await apiPost("/api/mode/upside_down");
    showToast("⬇ Upside-down mode active");
    setActiveMode("btn-mode-upside-down");
  });
}

function setActiveMode(activeId) {
  ["btn-mode-hoist", "btn-mode-upside-down"].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.classList.toggle("btn-active", id === activeId);
  });
}

// ─── Speed mode ──────────────────────────────────────────────────────────────

function initSpeedMode() {
  on("btn-speed-constant", "click", async () => {
    await apiPost("/api/speed_mode", { mode: "constant" });
    showToast("⚡ Constant speed mode");
    setActiveSpeed("btn-speed-constant");
  });
  on("btn-speed-variable", "click", async () => {
    await apiPost("/api/speed_mode", { mode: "variable" });
    showToast("〜 Variable speed mode");
    setActiveSpeed("btn-speed-variable");
  });
}

function setActiveSpeed(activeId) {
  ["btn-speed-constant", "btn-speed-variable"].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.classList.toggle("btn-active", id === activeId);
  });
}

// ─── Tracking ────────────────────────────────────────────────────────────────

function initTracking() {
  on("btn-track-enable",  "click", async () => {
    await apiPost("/api/tracking/enable");
    showToast("🎯 Tracking enabled", "success");
  });
  on("btn-track-disable", "click", async () => {
    await apiPost("/api/tracking/disable");
    showToast("🎯 Tracking disabled");
  });
}

// ─── Stream controls ─────────────────────────────────────────────────────────

function initStreamControls() {
  on("btn-start", "click", async () => {
    await apiPost("/api/start");
    showToast("▶ Streams started");
  });
  on("btn-stop", "click", async () => {
    await apiPost("/api/stop");
    showToast("■ Streams stopped");
  });
  on("btn-refresh", "click", () => {
    fetchStatus();
    document.querySelectorAll(".video-wrapper img").forEach(img => {
      const src = img.src.split("?")[0];
      img.src = src + "?t=" + Date.now();
    });
    showToast("↻ Refreshed");
  });
}

// ─── Utility ─────────────────────────────────────────────────────────────────

function on(id, event, handler) {
  const el = document.getElementById(id);
  if (el) el.addEventListener(event, handler);
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ─── Connection settings ──────────────────────────────────────────────────────

async function loadConfig() {
  const cfg = await apiGet("/api/config");
  if (!cfg) return;
  const ip   = document.getElementById("inp-camera-ip");
  const port = document.getElementById("inp-control-port");
  if (ip)   ip.value   = cfg.camera_ip    || "192.168.144.108";
  if (port) port.value = cfg.control_port || 37260;
  applyModeUI(cfg.mock_mode);
}

function applyModeUI(isMock) {
  const banner    = document.getElementById("mock-banner");
  const indicator = document.getElementById("conn-mode-indicator");
  const label     = document.getElementById("conn-mode-label");
  const mockBtn   = document.getElementById("btn-enable-mock");
  const realBtn   = document.getElementById("btn-enable-real");

  if (banner) banner.classList.toggle("hidden", !isMock);
  if (indicator) {
    indicator.className = "conn-mode " + (isMock ? "mock" : "real");
  }
  if (label) {
    label.textContent = isMock
      ? "Mock Mode — commands simulated, camera NOT controlled"
      : "Real Mode — commands sent to camera hardware";
  }
  if (mockBtn) mockBtn.classList.toggle("btn-active", isMock);
  if (realBtn) realBtn.classList.toggle("btn-active", !isMock);

  // Update header chip
  const chip = document.getElementById("status-mock");
  if (chip) {
    chip.textContent = isMock ? "Mock Mode" : "Real Mode";
    chip.className   = "status-chip " + (isMock ? "chip-active" : "chip-inactive");
  }
}

function initConnectionSettings() {
  on("btn-enable-mock", "click", async () => {
    const r = await apiPost("/api/config", { mock_mode: true });
    if (r.success) {
      applyModeUI(true);
      showToast("Mock Mode enabled — UI only, no camera commands", "info");
    }
  });

  on("btn-enable-real", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "37260", 10);
    showToast("Connecting to " + ip + ":" + port + " …", "info");
    const r = await apiPost("/api/config", { mock_mode: false, camera_ip: ip, control_port: port });
    if (r.success) {
      applyModeUI(r.mock_mode);
      if (r.mock_mode) {
        showToast("⚠ Could not reach camera — still in Mock Mode", "error");
      } else {
        showToast("✓ Real Mode active — commands go to " + ip, "success");
      }
    }
  });

  on("btn-test-conn", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "37260", 10);
    const result = document.getElementById("conn-test-result");

    if (result) {
      result.textContent = "Testing " + ip + ":" + port + " …";
      result.className = "conn-test-result";
    }

    const r = await apiPost("/api/connection/test", { camera_ip: ip, control_port: port });
    if (!result) return;
    if (r.reachable) {
      result.className = "conn-test-result reachable";
      result.textContent = "✓ Reachable — port " + port + " is open on " + ip
        + ". Click \"Enable Real Control\" to activate.";
    } else {
      result.className = "conn-test-result unreachable";
      result.textContent = "✗ Not reachable — " + (r.error || "connection refused")
        + ". Check the camera IP, port, and network connection.";
    }
  });
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────

function init() {
  initStreamControls();
  initGimbalControls();
  initZoomControls();
  initCameraControls();
  initThermalControls();
  initImageSettings();
  initCalibration();
  initWorkingMode();
  initSpeedMode();
  initTracking();
  initConnectionSettings();
  loadConfig();
  // Polling is started by app.js once this file is loaded.
}

document.addEventListener("DOMContentLoaded", init);
