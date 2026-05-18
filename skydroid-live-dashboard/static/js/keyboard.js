/**
 * keyboard.js — SkyDroid C12 Keyboard & Joystick Control
 *
 * Keyboard shortcuts:
 *   W / Arrow Up    — Pitch up
 *   S / Arrow Down  — Pitch down
 *   A / Arrow Left  — Yaw left
 *   D / Arrow Right — Yaw right
 *   Q               — Roll left
 *   E               — Roll right
 *   Space           — Stop motion
 *   C               — Center all
 *   Z               — Zoom in
 *   X               — Zoom out
 *
 * Hold-aware: a key held down fires the first command immediately, then
 * repeats on a timer rather than relying on the browser's key-repeat
 * (which is slow and uneven).
 */

"use strict";

// Map key codes → API endpoints
const KEY_MAP = {
  KeyW:       "/api/gimbal/pitch_up",
  ArrowUp:    "/api/gimbal/pitch_up",
  KeyS:       "/api/gimbal/pitch_down",
  ArrowDown:  "/api/gimbal/pitch_down",
  KeyA:       "/api/gimbal/yaw_left",
  ArrowLeft:  "/api/gimbal/yaw_left",
  KeyD:       "/api/gimbal/yaw_right",
  ArrowRight: "/api/gimbal/yaw_right",
  KeyQ:       "/api/gimbal/roll_left",
  KeyE:       "/api/gimbal/roll_right",
};

// One-shot keys (fire once per keydown, no repeat)
const ONESHOT_MAP = {
  Space:  "/api/gimbal/stop",
  KeyC:   "/api/gimbal/center",
  KeyZ:   "/api/camera/zoom_in",
  KeyX:   "/api/camera/zoom_out",
};

// Repeat interval in ms while a key is held
const HOLD_INTERVAL = 140;

// Track which keys are currently held (code → interval id)
const _held = new Map();

// ─── Helpers ────────────────────────────────────────────────────────────────

async function kbPost(endpoint) {
  try {
    await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch (_) { /* silently ignore network errors during keyboard control */ }
}

function startKey(code) {
  const endpoint = KEY_MAP[code];
  if (!endpoint || _held.has(code)) return;

  kbPost(endpoint); // fire immediately
  const id = setInterval(() => kbPost(endpoint), HOLD_INTERVAL);
  _held.set(code, id);
  _highlightKey(code, true);
}

function stopKey(code) {
  if (!_held.has(code)) return;
  clearInterval(_held.get(code));
  _held.delete(code);
  _highlightKey(code, false);
  // Only send stop if no other motion key is still held
  if (_held.size === 0) {
    kbPost("/api/gimbal/stop");
  }
}

function stopAllKeys() {
  _held.forEach((id, code) => {
    clearInterval(id);
    _highlightKey(code, false);
  });
  _held.clear();
}

// ─── Key event listeners ─────────────────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  // Skip if user is typing into an input/textarea/select
  const tag = document.activeElement?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

  // Prevent page scroll on arrow/space keys
  if (["Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.code)) {
    e.preventDefault();
  }

  // One-shot keys
  if (ONESHOT_MAP[e.code] && !e.repeat) {
    kbPost(ONESHOT_MAP[e.code]);
    _flashKey(e.code);
    return;
  }

  // Hold keys
  if (KEY_MAP[e.code] && !e.repeat) {
    startKey(e.code);
  }
});

document.addEventListener("keyup", (e) => {
  stopKey(e.code);
});

// Stop everything if the window loses focus
window.addEventListener("blur", stopAllKeys);

// ─── Optional: visual key highlight ─────────────────────────────────────────

// Maps key code → element id in the gimbal pad (matches controls in index.html)
const KEY_EL_MAP = {
  KeyW:       "btn-pitch-up",
  ArrowUp:    "btn-pitch-up",
  KeyS:       "btn-pitch-down",
  ArrowDown:  "btn-pitch-down",
  KeyA:       "btn-yaw-left",
  ArrowLeft:  "btn-yaw-left",
  KeyD:       "btn-yaw-right",
  ArrowRight: "btn-yaw-right",
  KeyQ:       "btn-roll-left",
  KeyE:       "btn-roll-right",
  Space:      "btn-stop",
  KeyC:       "btn-center",
  KeyZ:       "btn-zoom-in",
  KeyX:       "btn-zoom-out",
};

function _highlightKey(code, active) {
  const id = KEY_EL_MAP[code];
  if (!id) return;
  const el = document.getElementById(id);
  if (el) el.classList.toggle("kb-active", active);
}

function _flashKey(code) {
  const id = KEY_EL_MAP[code];
  if (!id) return;
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add("kb-active");
  setTimeout(() => el.classList.remove("kb-active"), 180);
}

// ─── Keyboard shortcut overlay ───────────────────────────────────────────────

// Show a small overlay with shortcut hints when ? is pressed
document.addEventListener("keydown", (e) => {
  if (e.code === "Slash" && e.shiftKey) {  // Shift+? = ?
    const overlay = document.getElementById("kb-overlay");
    if (overlay) overlay.classList.toggle("visible");
  }
  if (e.code === "Escape") {
    const overlay = document.getElementById("kb-overlay");
    if (overlay) overlay.classList.remove("visible");
  }
});
