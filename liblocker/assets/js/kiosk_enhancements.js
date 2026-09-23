(function () {
  "use strict";

  // ─── Configuration ──────────────────────────────────────────────────────

  var INACTIVITY_TIMEOUT_MS = 3 * 60 * 1000; // 3 minutes → return to /home
  var FADE_DURATION_MS      = 400;
  var HOME_URL              = "/home";

  // Pages where we do NOT apply the inactivity timer
  var EXEMPT_PATHS = ["/", "/home", "/index.html"];

  // ─── Kiosk lockdown ────────────────────────────────────────────────────

  function enableKioskMode() {
    // Prevent browser back navigation
    window.history.pushState(null, null, window.location.href);
    window.addEventListener("popstate", function () {
      window.history.pushState(null, null, window.location.href);
    });

    // Block common developer shortcuts
    document.addEventListener("keydown", function (e) {
      var devKeys =
        e.key === "F12" ||
        (e.ctrlKey && e.shiftKey && (e.key === "J" || e.key === "I" || e.key === "C")) ||
        (e.ctrlKey && e.key === "u");
      if (devKeys) e.preventDefault();
    }, false);

    // Disable right-click context menu
    document.addEventListener("contextmenu", function (e) {
      e.preventDefault();
    }, false);
  }

  // ─── Offline / Online detection ────────────────────────────────────────

  function showOfflineBanner() {
    var banner = document.getElementById("__kiosk_offline_banner");
    if (banner) { banner.style.display = "flex"; return; }

    banner = document.createElement("div");
    banner.id = "__kiosk_offline_banner";
    Object.assign(banner.style, {
      position:       "fixed",
      top:            "0",
      left:           "0",
      right:          "0",
      padding:        "12px 24px",
      background:     "rgba(160,30,30,0.92)",
      color:          "#fff",
      fontWeight:     "700",
      fontSize:       "16px",
      textAlign:      "center",
      zIndex:         "99999",
      display:        "flex",
      alignItems:     "center",
      justifyContent: "center",
      gap:            "10px",
    });
    banner.innerHTML = "⚠ No internet connection – some features may be unavailable.";
    document.body.appendChild(banner);
  }

  function hideOfflineBanner() {
    var banner = document.getElementById("__kiosk_offline_banner");
    if (banner) banner.style.display = "none";
  }

  function initOfflineDetection() {
    if (!navigator.onLine) showOfflineBanner();
    window.addEventListener("offline", showOfflineBanner);
    window.addEventListener("online",  hideOfflineBanner);
  }

  // ─── Inactivity timeout ────────────────────────────────────────────────

  var _inactivityTimer = null;

  function isExemptPage() {
    var path = window.location.pathname.toLowerCase().replace(/\/+$/, "") || "/";
    return EXEMPT_PATHS.indexOf(path) !== -1;
  }

  function fadeToHome() {
    document.body.style.transition = "opacity " + (FADE_DURATION_MS / 1000) + "s ease";
    document.body.style.opacity    = "0";
    setTimeout(function () {
      window.location.href = HOME_URL;
    }, FADE_DURATION_MS);
  }

  function resetInactivityTimer() {
    if (isExemptPage()) return;
    clearTimeout(_inactivityTimer);
    _inactivityTimer = setTimeout(fadeToHome, INACTIVITY_TIMEOUT_MS);
  }

  function initInactivityTimeout() {
    if (isExemptPage()) return;

    var events = ["mousedown", "mousemove", "keypress", "touchstart", "scroll", "click"];
    events.forEach(function (ev) {
      document.addEventListener(ev, resetInactivityTimer, { passive: true, capture: true });
    });
    resetInactivityTimer();
  }

  // ─── Loading overlay ───────────────────────────────────────────────────

  function _ensureLoadingOverlay() {
    if (document.getElementById("__kiosk_loading")) return;

    var overlay = document.createElement("div");
    overlay.id = "__kiosk_loading";
    Object.assign(overlay.style, {
      position:        "fixed",
      inset:           "0",
      background:      "rgba(0,0,0,0.55)",
      display:         "none",
      alignItems:      "center",
      justifyContent:  "center",
      flexDirection:   "column",
      gap:             "18px",
      zIndex:          "99998",
    });

    overlay.innerHTML =
      '<div style="' +
        "width:48px;height:48px;" +
        "border:5px solid rgba(255,255,255,0.3);" +
        "border-top-color:#fff;" +
        "border-radius:50%;" +
        'animation:__kiosk_spin 0.9s linear infinite;">' +
      "</div>" +
      '<p style="color:#fff;font-weight:700;font-size:18px;margin:0">Processing…</p>';

    // Keyframe
    var style = document.createElement("style");
    style.textContent =
      "@keyframes __kiosk_spin{to{transform:rotate(360deg)}}";
    document.head.appendChild(style);
    document.body.appendChild(overlay);
  }

  /** Show the full-screen processing spinner. */
  window.kioskShowLoading = function (msg) {
    _ensureLoadingOverlay();
    var el = document.getElementById("__kiosk_loading");
    var p  = el && el.querySelector("p");
    if (p && msg) p.textContent = msg;
    if (el)       el.style.display = "flex";
  };

  /** Hide the processing spinner. */
  window.kioskHideLoading = function () {
    var el = document.getElementById("__kiosk_loading");
    if (el) el.style.display = "none";
  };

  // ─── Page fade-in ──────────────────────────────────────────────────────

  function initPageFadeIn() {
    document.body.style.opacity    = "0";
    document.body.style.transition = "opacity 0.35s ease";
    // requestAnimationFrame ensures the initial opacity:0 is painted first
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        document.body.style.opacity = "1";
      });
    });
  }

  // ─── Initialise ────────────────────────────────────────────────────────

  function init() {
    enableKioskMode();
    // Offline banner intentionally disabled — the kiosk is fully
    // offline-capable (Flask + SQLite + RFID + relays all live on the Pi),
    // so a "no internet" warning would be misleading. Re-enable the line
    // below if you ever want it back.
    // initOfflineDetection();
    initInactivityTimeout();
    initPageFadeIn();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
