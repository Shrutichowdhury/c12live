/**
 * app.js — SkyDroid C12 Control Dashboard
 *
 * Lightweight bootstrap: starts the status poll immediately on page load.
 * All button logic and API calls live in controls.js.
 * Keyboard shortcuts live in keyboard.js.
 */

"use strict";

// Start polling as soon as the DOM is ready.
// fetchStatus() is defined in controls.js (loaded after this file).
document.addEventListener("DOMContentLoaded", () => {
  if (typeof fetchStatus === "function") {
    fetchStatus();
    setInterval(fetchStatus, 1000);
  }
});
