/**
 * controls.js — SkyDroid C12 Control Dashboard
 *
 * Handles all API calls to gimbal, zoom, camera, thermal, image settings,
 * calibration, mode, and tracking endpoints.
 * Polls /api/status every second to keep the status panel current.
 *
 * SDK-confirmed protocol (AAR v1.9.1):
 *   Port        : 5000 UDP
 *   Speed yaw   : #TPUG2wGSY<signed-byte-hex>  (cmd_yaw_speed)
 *   Speed pitch : #TPUG2wGSP<signed-byte-hex>  (cmd_pitch_speed)
 *   Goto yaw    : #TPUG6wGAY<int16_hex>10      (gotoYaw)
 *   Goto pitch  : #TPUG6wGAP<int16_hex>10      (gotoPitch)
 *   Zoom ratio  : #TPUD2wDZM0<N:X>             (setZoomRatios 0-4)
 *   Palette     : #TPUD2wIMG<index:02X>        (setThermalPalette)
 *   Time sync   : #TPUDFwTIM<HHmmss><ddMMyy>.00 (setTime)
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

  // Zoom ratio button sync
  if (typeof data.zoom_ratio === "number") {
    syncZoomRatioButtons(data.zoom_ratio);
  }

  // Palette select sync
  const paletteSelect = document.getElementById("palette-select");
  if (paletteSelect && typeof data.palette_index === "number"
      && document.activeElement !== paletteSelect) {
    paletteSelect.value = String(data.palette_index);
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
  apiPost(endpoint);
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

  on("btn-gimbal-stop",  "click", () => { apiPost("/api/gimbal/stop");        showToast("⬛ Motion stopped"); });
  on("btn-center",       "click", () => { apiPost("/api/gimbal/center");       showToast("✦ Centered all axes"); });
  on("btn-center-yaw",   "click", () => { apiPost("/api/gimbal/center_yaw");   showToast("↔ Yaw centred"); });
  on("btn-look-down",    "click", () => { apiPost("/api/gimbal/look_down");    showToast("↓ Looking down"); });
  on("btn-look-forward", "click", () => { apiPost("/api/gimbal/look_forward"); showToast("→ Looking forward"); });
}

// ─── Goto angle (SDK: gotoYaw / gotoPitch) ───────────────────────────────────

function initGotoAngle() {
  on("btn-goto-angle", "click", async () => {
    const yaw   = parseFloat(document.getElementById("inp-goto-yaw")?.value   || 0);
    const pitch = parseFloat(document.getElementById("inp-goto-pitch")?.value || 0);

    if (isNaN(yaw) || yaw < -90 || yaw > 90) {
      showToast("⚠ Yaw must be -90 to +90", "error"); return;
    }
    if (isNaN(pitch) || pitch < -90 || pitch > 90) {
      showToast("⚠ Pitch must be -90 to +90", "error"); return;
    }

    const [ry, rp] = await Promise.all([
      apiPost("/api/gimbal/goto_yaw",   { degrees: yaw }),
      apiPost("/api/gimbal/goto_pitch", { degrees: pitch }),
    ]);
    if (ry.success && rp.success) {
      showToast(`↗ Goto yaw ${yaw}° pitch ${pitch}°`, "success");
    }
  });
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
      await apiPost("/api/camera/set_zoom", { level: parseFloat(slider.value) });
      showToast("🔍 Zoom " + parseFloat(slider.value).toFixed(2) + "×");
    });
  }
}

// ─── Discrete zoom ratio 0-4 (SDK: setZoomRatios, #TPUD2wDZM0N) ─────────────

function syncZoomRatioButtons(activeRatio) {
  document.querySelectorAll(".btn-zoom-ratio").forEach(btn => {
    const r = parseInt(btn.dataset.ratio || "0", 10);
    btn.classList.toggle("btn-active", r === activeRatio);
  });
}

function initZoomRatioControls() {
  document.querySelectorAll(".btn-zoom-ratio").forEach(btn => {
    btn.addEventListener("click", async () => {
      const ratio = parseInt(btn.dataset.ratio || "0", 10);
      const labels = ["1× (1:1)", "2× digital", "4× digital", "8× digital", "16× digital"];
      const r = await apiPost("/api/camera/zoom_ratio", { ratio });
      if (r.success) {
        syncZoomRatioButtons(ratio);
        showToast(`🔍 Zoom ratio: ${labels[ratio]}`, "success");
      }
    });
  });
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

// ─── Thermal palette (SDK: setThermalPalette, #TPUD2wIMG<index>) ─────────────

function initThermalControls() {
  const paletteSelect = document.getElementById("palette-select");
  if (paletteSelect) {
    paletteSelect.addEventListener("change", async () => {
      const index = parseInt(paletteSelect.value, 10);
      const label = paletteSelect.options[paletteSelect.selectedIndex]?.text || "";
      const r = await apiPost("/api/thermal/palette_index", { index });
      if (r.success) showToast("🎨 Palette: " + label, "success");
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

// ─── Time sync (SDK: setTime, #TPUDFwTIM<HHmmss><ddMMyy>.00) ────────────────

function initTimeSyncControl() {
  on("btn-sync-time", "click", async () => {
    const ts = Date.now();
    const r = await apiPost("/api/camera/sync_time", { timestamp_ms: ts });
    const resultEl = document.getElementById("sync-time-result");
    if (r.success) {
      const now = new Date(ts);
      const utc = now.toUTCString().replace("GMT", "UTC");
      showToast("⏱ Camera time synced to " + utc, "success");
      if (resultEl) resultEl.textContent = "✓ Synced: " + utc;
    } else {
      if (resultEl) resultEl.textContent = "✗ " + (r.error || "Failed");
    }
  });
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
  if (port) port.value = cfg.control_port || 5000;
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
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
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
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const result = document.getElementById("conn-test-result");

    if (result) {
      result.textContent = "Testing " + ip + ":" + port + " …";
      result.className = "conn-test-result";
    }

    const r = await apiPost("/api/connection/test", { camera_ip: ip, control_port: port });
    if (!result) return;
    if (r.reachable) {
      result.className = "conn-test-result reachable";
      result.textContent = "✓ Reachable via " + (r.transport || "network") + " — port "
        + port + " is open on " + ip + ". Click \"Enable Real Control\" to activate."
        + (r.reply_hex ? "  Camera replied: " + r.reply_hex : "");
    } else {
      result.className = "conn-test-result unreachable";
      result.textContent = "✗ Not reachable — " + (r.error || "connection refused")
        + ".  This server must run locally on the same network as the camera.";
    }
  });

  on("btn-probe-conn", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const box  = document.getElementById("conn-probe-result");
    const listenBox = document.getElementById("conn-listen-result");
    if (listenBox) listenBox.className = "conn-probe-result hidden";

    if (box) {
      box.textContent = "⏳ Scanning protocol formats + HTTP + passive listen on " + ip + ":" + port + " …\n(takes ~15 s, also sends center-gimbal — watch if the gimbal moves!)";
      box.className = "conn-probe-result visible";
    }

    const r = await apiPost("/api/probe", { camera_ip: ip, control_port: port });
    if (!box) return;

    let text = "═══ SkyDroid ASCII Protocol Scan ═══\n" + ip + ":" + port + "\n\n";
    let anyReply = false;

    (r.probes || []).forEach(p => {
      text += "┌─ " + p.probe + "\n";
      if (p.sent_ascii) text += "│  Sent:  " + p.sent_ascii + "\n";
      if (p.reply_text) {
        anyReply = true;
        text += "│  ✓ Reply (" + p.reply_len + "B from " + p.reply_from + "):\n";
        text += "│     ASCII: " + p.reply_text + "\n";
        text += "│     Hex:   " + p.reply_hex + "\n";
        if (p.reply_text.startsWith("#TP")) text += "│  ★ Real Skydroid protocol confirmed!\n";
      } else if (p.reply === "no_reply") {
        text += "│  no reply (normal — camera may not reply to all queries)\n";
      } else if (p.broadcasts !== undefined) {
        if (p.count > 0) {
          anyReply = true;
          text += "│  ✓ Got " + p.count + " broadcast packet(s)!\n";
          p.broadcasts.forEach(b => {
            text += "│    from " + b.from + " (" + b.len + "B):\n";
            text += "│    ASCII: " + (b.ascii || "") + "\n";
            text += "│    Hex:   " + b.hex + "\n";
          });
        } else {
          text += "│  no broadcasts heard\n";
        }
      } else if (p.found) {
        anyReply = true;
        text += "│  ✓ HTTP API found!\n";
        p.found.forEach(h => {
          text += "│    Port " + h.port + " " + h.path + ":\n";
          text += "│    " + (h.response_preview || "").split("\n").slice(0, 3).join("\n│    ") + "\n";
        });
      } else if (p.reply === "no HTTP on ports 80/8080/8888") {
        text += "│  no HTTP API found\n";
      } else if (p.error) {
        text += "│  Error: " + p.error + "\n";
      } else if (p.note) {
        text += "│  " + p.note + "\n";
      }
      text += "└─────────────────────\n\n";
    });

    if (anyReply) {
      text += "★ Camera replied! Real control should work — click \"Enable Real Control\".\n";
      showToast("Camera replied! Real control ready.", "success");
    } else {
      text += "▸ No replies received (this can be normal).\n";
      text += "▸ Commands WERE sent using real Skydroid ASCII protocol (port 5000 UDP).\n";
      text += "▸ Did the gimbal move when PTZ CENTER was sent? If yes → real control works!\n";
      text += "▸ Click \"Enable Real Control\" and try the D-pad buttons.\n";
      showToast("Scan complete — did the gimbal move?", "info");
    }

    box.textContent = text;
  });

  on("btn-listen-conn", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const box  = document.getElementById("conn-listen-result");
    const probeBox = document.getElementById("conn-probe-result");
    if (probeBox) probeBox.className = "conn-probe-result hidden";

    if (box) {
      box.textContent = "📻 Listening on UDP port " + port + " for 5 seconds …\n(camera broadcasts status packets continuously on many models)";
      box.className = "conn-probe-result visible";
    }

    const r = await apiPost("/api/probe/listen", { camera_ip: ip, control_port: port, wait_seconds: 5 });
    if (!box) return;

    if (!r.success) {
      box.textContent = "Error binding port " + port + ": " + r.error + "\n(another process may be using this port)";
      return;
    }

    if (r.count === 0) {
      box.textContent = "📻 Listened on port " + port + " for 5 s — no packets received.\n\n"
        + "Possible reasons:\n"
        + "  • Camera broadcasts on a different port (try 9002, 5001)\n"
        + "  • Camera only sends after receiving a query first\n"
        + "  • Port " + port + " is already bound by another process\n\n"
        + "Try the Multi-Protocol Scan — it also passively listens and sends query packets.";
      showToast("No broadcasts heard on port " + port, "info");
      return;
    }

    let text = "📻 Got " + r.count + " packet(s) on port " + port + ":\n\n";
    r.packets.forEach((p, i) => {
      text += "Packet " + (i + 1) + " from " + p.from + " (" + p.len + " B):\n";
      text += "  ASCII: " + p.ascii + "\n";
      text += "  Hex:   " + p.hex + "\n\n";
    });
    box.textContent = text;
    showToast("Got " + r.count + " broadcast packet(s)!", "success");
  });

  // Raw command terminal
  on("btn-raw-send", "click", async () => {
    const ip   = document.getElementById("inp-camera-ip")?.value   || "192.168.144.108";
    const port = parseInt(document.getElementById("inp-control-port")?.value || "5000", 10);
    const cmd  = document.getElementById("inp-raw-cmd")?.value?.trim() || "";
    const addCrc = document.getElementById("chk-raw-crc")?.checked !== false;
    const box  = document.getElementById("raw-cmd-result");

    if (!cmd) { showToast("Enter a command first", "error"); return; }

    if (box) {
      box.textContent = "Sending " + cmd + " …";
      box.className = "conn-probe-result visible";
    }

    const r = await apiPost("/api/raw_command", {
      cmd, add_crc: addCrc, camera_ip: ip, port, wait_reply: true,
    });

    if (!box) return;
    let text = "";
    text += "Sent:  " + (r.sent_ascii || cmd) + "\n";
    text += "Hex:   " + (r.sent_hex || "") + "\n";
    if (r.reply === "no_reply") {
      text += "Reply: (none within 2 s)\n";
    } else if (r.reply_ascii) {
      text += "Reply: " + r.reply_ascii + "\n";
      text += "RHex:  " + (r.reply_hex || "") + "\n";
      if (r.reply_text) text += "Text:  " + r.reply_text + "\n";
    }
    box.textContent = text;
  });
}

// ─── Boot ────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initGimbalControls();
  initGotoAngle();
  initZoomControls();
  initZoomRatioControls();
  initCameraControls();
  initThermalControls();
  initTimeSyncControl();
  initImageSettings();
  initCalibration();
  initWorkingMode();
  initSpeedMode();
  initTracking();
  initStreamControls();
  initConnectionSettings();
  loadConfig();
  // Status polling is started by app.js (avoids duplicate intervals)
});
