/**
 * app.js — SkyDroid Live Streaming Dashboard
 *
 * Polls /api/status every second and updates status badges, FPS counters,
 * and uptime. Handles Start / Stop buttons via fetch().
 */

"use strict";

// ─── DOM references ────────────────────────────────────────────────────────
const elVisibleStatus = document.getElementById("visible-status");
const elThermalStatus = document.getElementById("thermal-status");
const elVisibleFps    = document.getElementById("visible-fps");
const elThermalFps    = document.getElementById("thermal-fps");
const elVisibleFpsOv  = document.getElementById("visible-fps-overlay");
const elThermalFpsOv  = document.getElementById("thermal-fps-overlay");
const elUptime        = document.getElementById("uptime");
const elBtnStart      = document.getElementById("btn-start");
const elBtnStop       = document.getElementById("btn-stop");
const elBtnRefresh    = document.getElementById("btn-refresh");
const elToast         = document.getElementById("toast");

// ─── Poll interval (ms) ────────────────────────────────────────────────────
const POLL_INTERVAL = 1000;
let pollTimer = null;

// ─── Status polling ────────────────────────────────────────────────────────
async function fetchStatus() {
  try {
    const res  = await fetch("/api/status");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.warn("Status poll failed:", err.message);
  }
}

function updateUI(data) {
  // Status badges
  setStatusBadge(elVisibleStatus, data.visible_connected);
  setStatusBadge(elThermalStatus, data.thermal_connected);

  // FPS
  const visFps = data.visible_fps.toFixed(1);
  const thrFps = data.thermal_fps.toFixed(1);
  elVisibleFps.textContent = `${visFps} fps`;
  elThermalFps.textContent = `${thrFps} fps`;
  if (elVisibleFpsOv) elVisibleFpsOv.textContent = `${visFps} fps`;
  if (elThermalFpsOv) elThermalFpsOv.textContent = `${thrFps} fps`;

  // Uptime
  elUptime.textContent = formatUptime(data.uptime_seconds);
}

function setStatusBadge(el, isOnline) {
  if (isOnline) {
    el.className = "badge badge-online";
    el.innerHTML = '<span class="badge-dot"></span> Online';
  } else {
    el.className = "badge badge-offline";
    el.innerHTML = '<span class="badge-dot"></span> Offline';
  }
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [
    h > 0 ? `${h}h` : null,
    m > 0 ? `${m}m` : null,
    `${s}s`,
  ].filter(Boolean).join(" ");
}

function startPolling() {
  fetchStatus(); // immediate first call
  pollTimer = setInterval(fetchStatus, POLL_INTERVAL);
}

// ─── Buttons ────────────────────────────────────────────────────────────────
elBtnStart.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/start", { method: "POST" });
    const data = await res.json();
    showToast("▶ Streams started");
  } catch (err) {
    showToast("Error starting streams");
  }
});

elBtnStop.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/stop", { method: "POST" });
    const data = await res.json();
    showToast("■ Streams stopped");
  } catch (err) {
    showToast("Error stopping streams");
  }
});

elBtnRefresh.addEventListener("click", () => {
  fetchStatus();
  // Reload the img src to force reconnect in the browser
  const imgs = document.querySelectorAll(".video-wrapper img");
  imgs.forEach(img => {
    const src = img.src.split("?")[0];
    img.src = `${src}?t=${Date.now()}`;
  });
  showToast("↻ Status refreshed");
});

// ─── Toast notification ─────────────────────────────────────────────────────
let toastTimer = null;

function showToast(message) {
  elToast.textContent = message;
  elToast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elToast.classList.remove("show"), 2800);
}

// ─── Init ───────────────────────────────────────────────────────────────────
startPolling();
