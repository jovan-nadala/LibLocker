/* =========================================================
   LibLocker — Kiosk On-Screen Keypad
   - Numeric keypad for `data-kk-keypad="numeric"`
   - Alpha (compact QWERTY) for `data-kk-keypad="alpha"`
   - Auto-uppercase for `.uppercase-input`
   - Numeric-only sanitiser for `.numeric-input`
   - Suppresses OS virtual keyboard via `inputmode="none"`
     (physical keyboards still work for staff)

   Self-contained, idempotent, no external deps.
========================================================= */

(function () {
  "use strict";

  if (window.__libLockerKeypadLoaded) return;
  window.__libLockerKeypadLoaded = true;

  // ── Config ────────────────────────────────────────────────────────────
  const NUMERIC_KEYS = ["1","2","3","4","5","6","7","8","9"];
  const ALPHA_ROWS = [
    ["Q","W","E","R","T","Y","U","I","O","P"],
    ["A","S","D","F","G","H","J","K","L"],
    ["Z","X","C","V","B","N","M"],
  ];

  const SVG_BACKSPACE =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 5H8.5a2 2 0 0 0-1.6.8L2 12l4.9 6.2a2 2 0 0 0 1.6.8H21a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2z"/>' +
    '<line x1="18" y1="9" x2="12" y2="15"/><line x1="12" y1="9" x2="18" y2="15"/></svg>';

  // ── State ─────────────────────────────────────────────────────────────
  let activeInput = null;
  let activeMode  = null;            // "numeric" | "alpha"
  let blurTimer   = null;            // suppresses hide on key tap
  let numericPad  = null;
  let alphaPad    = null;

  // ── Helpers ───────────────────────────────────────────────────────────

  function isUppercaseInput(el) {
    return el && el.classList && el.classList.contains("uppercase-input");
  }
  function isNumericInput(el) {
    return el && el.classList && el.classList.contains("numeric-input");
  }
  function isKeypadTarget(el) {
    return !!(el && el.matches && el.matches('input[data-kk-keypad="numeric"], input[data-kk-keypad="alpha"]'));
  }

  function dispatchInput(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Insert text at the caret, preserving selection / cursor position.
  // Honors the input's maxLength.
  function insertAtCaret(input, text) {
    if (!input) return;
    const max = parseInt(input.getAttribute("maxlength") || "0", 10);
    const start = input.selectionStart != null ? input.selectionStart : input.value.length;
    const end   = input.selectionEnd   != null ? input.selectionEnd   : input.value.length;

    const before = input.value.slice(0, start);
    const after  = input.value.slice(end);
    let next = before + text + after;
    if (max > 0 && next.length > max) {
      next = next.slice(0, max);
    }
    input.value = next;
    const newCaret = Math.min((before + text).length, next.length);
    try { input.setSelectionRange(newCaret, newCaret); } catch (_) {}
    dispatchInput(input);
  }

  function backspaceAtCaret(input) {
    if (!input) return;
    const start = input.selectionStart != null ? input.selectionStart : input.value.length;
    const end   = input.selectionEnd   != null ? input.selectionEnd   : input.value.length;

    if (start === end) {
      if (start === 0) return;
      const next = input.value.slice(0, start - 1) + input.value.slice(end);
      input.value = next;
      try { input.setSelectionRange(start - 1, start - 1); } catch (_) {}
    } else {
      const next = input.value.slice(0, start) + input.value.slice(end);
      input.value = next;
      try { input.setSelectionRange(start, start); } catch (_) {}
    }
    dispatchInput(input);
  }

  function clearInput(input) {
    if (!input) return;
    input.value = "";
    try { input.setSelectionRange(0, 0); } catch (_) {}
    dispatchInput(input);
  }

  // ── Auto-uppercase + numeric sanitiser ────────────────────────────────

  function applyUppercase(input) {
    if (!isUppercaseInput(input)) return;
    const start = input.selectionStart;
    const end   = input.selectionEnd;
    const upper = input.value.toUpperCase();
    if (input.value !== upper) {
      input.value = upper;
      try { input.setSelectionRange(start, end); } catch (_) {}
    }
  }

  function applyNumericSanitise(input) {
    if (!isNumericInput(input)) return;
    const start = input.selectionStart;
    const cleaned = input.value.replace(/\D+/g, "");
    if (input.value !== cleaned) {
      input.value = cleaned;
      const newCaret = Math.min(start, cleaned.length);
      try { input.setSelectionRange(newCaret, newCaret); } catch (_) {}
    }
  }

  function onAnyInput(e) {
    const el = e.target;
    if (!el || el.tagName !== "INPUT") return;
    applyUppercase(el);
    applyNumericSanitise(el);
    syncDisplay(el);
  }

  // ── Keypad construction ───────────────────────────────────────────────

  function buildPad(mode) {
    const pad = document.createElement("div");
    pad.className = "kk-keypad kk-keypad--" + mode;
    pad.setAttribute("role", "group");
    pad.setAttribute("aria-label",
      mode === "numeric" ? "Numeric keypad" : "Alphabet keypad");

    // Keep focus on the input when keys are tapped.
    //
    // ⚠️  Do NOT preventDefault on touchstart — Chromium treats a cancelled
    // touchstart as cancelling the synthetic click event chain, which means
    // our key buttons never get their click handler fired and tapped digits
    // never reach the input. We only intercept mousedown (desktop / synthesized
    // from touch *after* touchstart succeeds) — that's enough to stop focus
    // from moving to the button while letting click events fire normally.
    pad.addEventListener("mousedown", function (e) {
      if (e.target.closest(".kk-keypad")) {
        e.preventDefault();
      }
    });

    // Mirror display
    const display = document.createElement("div");
    display.className = "kk-keypad-display";
    display.innerHTML =
      '<span class="kk-keypad-display-label" data-kk-display-label></span>' +
      '<span class="kk-keypad-display-value" data-kk-display-value data-placeholder=""></span>' +
      '<button type="button" class="kk-keypad-close" aria-label="Close keypad" data-kk-close>&times;</button>';
    pad.appendChild(display);

    const keysWrap = document.createElement("div");
    keysWrap.className = "kk-keys";
    pad.appendChild(keysWrap);

    if (mode === "numeric") {
      buildNumericKeys(keysWrap);
    } else {
      buildAlphaKeys(keysWrap);
    }

    document.body.appendChild(pad);

    // Wire close
    pad.querySelector("[data-kk-close]").addEventListener("click", function (e) {
      e.preventDefault();
      hidePad();
    });

    return pad;
  }

  function makeKey(label, opts) {
    opts = opts || {};
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "kk-key" + (opts.className ? " " + opts.className : "");
    if (opts.html) {
      btn.innerHTML = opts.html;
    } else {
      btn.textContent = label;
    }
    if (opts.aria) btn.setAttribute("aria-label", opts.aria);
    btn.setAttribute("tabindex", "-1");

    const action = opts.action || function () {
      insertAtCaret(activeInput, label);
    };

    // click handles both touch + mouse + accessibility
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      // Cancel any pending hide-on-blur so the keypad stays open while the
      // user is actively tapping keys.
      if (blurTimer) { clearTimeout(blurTimer); blurTimer = null; }
      btn.classList.add("is-press");
      setTimeout(function () { btn.classList.remove("is-press"); }, 110);
      action();
      // Re-focus the target input so the caret stays put, the visual ring
      // stays applied, and a subsequent tap on the input doesn't re-toggle
      // the keypad off then back on.
      if (activeInput) {
        try { activeInput.focus({ preventScroll: true }); } catch (_) {}
      }
    });

    return btn;
  }

  function buildNumericKeys(wrap) {
    NUMERIC_KEYS.forEach(function (n) { wrap.appendChild(makeKey(n)); });
    wrap.appendChild(makeKey("Clear", {
      className: "kk-key--danger",
      aria: "Clear input",
      action: function () { clearInput(activeInput); },
    }));
    wrap.appendChild(makeKey("0"));
    wrap.appendChild(makeKey("", {
      className: "kk-key--ghost kk-key--icon",
      aria: "Backspace",
      html: SVG_BACKSPACE,
      action: function () { backspaceAtCaret(activeInput); },
    }));
    wrap.appendChild(makeKey("Done", {
      className: "kk-key--solid kk-key--done",
      aria: "Done",
      action: function () { advanceOrClose(); },
    }));
  }

  function buildAlphaKeys(wrap) {
    // Row 1: Q-P
    const r1 = document.createElement("div"); r1.className = "kk-row kk-row--r1";
    ALPHA_ROWS[0].forEach(function (l) { r1.appendChild(makeKey(l)); });
    wrap.appendChild(r1);

    // Row 2: A-L
    const r2 = document.createElement("div"); r2.className = "kk-row kk-row--r2";
    ALPHA_ROWS[1].forEach(function (l) { r2.appendChild(makeKey(l)); });
    wrap.appendChild(r2);

    // Row 3: Z-M + backspace at right (and a placeholder dot at left for symmetry)
    const r3 = document.createElement("div"); r3.className = "kk-row kk-row--r3";
    r3.appendChild(makeKey(".", {
      className: "kk-key--ghost",
      aria: "Period",
      action: function () { insertAtCaret(activeInput, "."); },
    }));
    ALPHA_ROWS[2].forEach(function (l) { r3.appendChild(makeKey(l)); });
    r3.appendChild(makeKey("", {
      className: "kk-key--ghost kk-key--icon",
      aria: "Backspace",
      html: SVG_BACKSPACE,
      action: function () { backspaceAtCaret(activeInput); },
    }));
    wrap.appendChild(r3);

    // Row 4: Clear  -  space  -  Done
    const r4 = document.createElement("div"); r4.className = "kk-row kk-row--r4";
    r4.appendChild(makeKey("Clear", {
      className: "kk-key--danger",
      aria: "Clear input",
      action: function () { clearInput(activeInput); },
    }));
    r4.appendChild(makeKey("-", {
      className: "kk-key--ghost",
      aria: "Hyphen",
      action: function () { insertAtCaret(activeInput, "-"); },
    }));
    r4.appendChild(makeKey("Space", {
      className: "kk-key--ghost",
      aria: "Space",
      action: function () { insertAtCaret(activeInput, " "); },
    }));
    r4.appendChild(makeKey("'", {
      className: "kk-key--ghost",
      aria: "Apostrophe",
      action: function () { insertAtCaret(activeInput, "'"); },
    }));
    r4.appendChild(makeKey("Done", {
      className: "kk-key--solid",
      aria: "Done",
      action: function () { advanceOrClose(); },
    }));
    wrap.appendChild(r4);
  }

  // ── Display sync ──────────────────────────────────────────────────────

  function syncDisplay(input) {
    if (!input) return;
    const pad = activeMode === "numeric" ? numericPad : alphaPad;
    if (!pad || !pad.classList.contains("is-open")) return;
    const valueEl = pad.querySelector("[data-kk-display-value]");
    const labelEl = pad.querySelector("[data-kk-display-label]");
    if (valueEl) valueEl.textContent = input.value || "";
    if (valueEl) valueEl.setAttribute("data-placeholder",
      input.getAttribute("placeholder") || "");
    if (labelEl) {
      const label = input.getAttribute("data-kk-label") ||
                    input.getAttribute("aria-label") ||
                    input.getAttribute("placeholder") ||
                    "Input";
      labelEl.textContent = label;
    }
  }

  // ── Show / hide ───────────────────────────────────────────────────────

  function showPadFor(input) {
    if (!input) return;
    const mode = input.getAttribute("data-kk-keypad");
    if (mode !== "numeric" && mode !== "alpha") return;

    activeInput = input;
    activeMode  = mode;

    if (mode === "numeric" && !numericPad) numericPad = buildPad("numeric");
    if (mode === "alpha"   && !alphaPad)   alphaPad   = buildPad("alpha");

    // Hide the OTHER pad if it's open
    if (mode === "numeric" && alphaPad)   alphaPad.classList.remove("is-open");
    if (mode === "alpha"   && numericPad) numericPad.classList.remove("is-open");

    const pad = mode === "numeric" ? numericPad : alphaPad;
    pad.classList.add("is-open");
    document.body.classList.add("kk-keypad-open");
    input.classList.add("kk-input-active");
    syncDisplay(input);
  }

  function hidePad() {
    if (numericPad) numericPad.classList.remove("is-open");
    if (alphaPad)   alphaPad.classList.remove("is-open");
    if (activeInput) {
      activeInput.classList.remove("kk-input-active");
      try { activeInput.blur(); } catch (_) {}
    }
    document.body.classList.remove("kk-keypad-open");
    activeInput = null;
    activeMode  = null;
  }

  function advanceOrClose() {
    // Find the next .kk-input/keypad-target that's visible
    const all = Array.from(document.querySelectorAll(
      'input[data-kk-keypad="numeric"], input[data-kk-keypad="alpha"]'
    )).filter(function (el) {
      // visible-ish: not hidden, has layout
      return el.offsetParent !== null && !el.disabled && !el.readOnly;
    });
    const i = all.indexOf(activeInput);
    if (i >= 0 && i < all.length - 1) {
      const next = all[i + 1];
      next.focus();
      // showPadFor is called by focus handler too; explicit for safety
      showPadFor(next);
    } else {
      hidePad();
    }
  }

  // ── Focus / blur wiring ───────────────────────────────────────────────

  function onFocusIn(e) {
    const el = e.target;
    if (!isKeypadTarget(el)) return;
    if (blurTimer) { clearTimeout(blurTimer); blurTimer = null; }
    showPadFor(el);
  }

  function onFocusOut(e) {
    const el = e.target;
    if (!isKeypadTarget(el)) return;
    // Defer: tapping a keypad button briefly steals focus, we don't want
    // to hide and re-show.
    if (blurTimer) clearTimeout(blurTimer);
    blurTimer = setTimeout(function () {
      const ae = document.activeElement;
      if (!isKeypadTarget(ae)) {
        hidePad();
      }
    }, 140);
  }

  // ── Boot ──────────────────────────────────────────────────────────────

  function init() {
    // Suppress the OS virtual keyboard on flagged inputs
    document.querySelectorAll(
      'input[data-kk-keypad="numeric"], input[data-kk-keypad="alpha"]'
    ).forEach(function (el) {
      // Always set inputmode="none" so chromium-on-pi doesn't pop a soft kbd
      if (el.getAttribute("inputmode") !== "none") {
        el.setAttribute("inputmode", "none");
      }
      // Don't autocomplete on a kiosk
      el.setAttribute("autocomplete", "off");
      el.setAttribute("autocapitalize", "off");
      el.setAttribute("spellcheck", "false");
    });

    document.addEventListener("input",   onAnyInput,   true);
    document.addEventListener("focusin", onFocusIn,    true);
    document.addEventListener("focusout", onFocusOut,  true);

    // Tap outside both inputs and keypad => hide
    document.addEventListener("click", function (e) {
      const t = e.target;
      if (!t) return;
      if (t.closest(".kk-keypad")) return;
      if (isKeypadTarget(t)) return;
      // give focusout a chance to run first
      setTimeout(function () {
        if (!isKeypadTarget(document.activeElement)) hidePad();
      }, 0);
    });

    // ESC closes (kiosk staff convenience)
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && activeInput) hidePad();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
