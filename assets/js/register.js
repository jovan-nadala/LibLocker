
(function () {
  "use strict";

  const CONFIG = {
    minNameLength: 3,
    minStudentIdLength: 6,
    maxStudentIdLength: 12,
    hfPollIntervalMs: 500,
  };

  // ── Helpers ──────────────────────────────────────────────────────────

  function byId(id) { return document.getElementById(id); }

  function t(key, fallback) {
    const i18n = window.LibLockerI18n;
    return (i18n && typeof i18n.t === "function") ? i18n.t(key, fallback) : fallback;
  }

  function formatTemplate(template, replacements) {
    let text = String(template || "");
    Object.keys(replacements || {}).forEach(function (k) {
      text = text.replace(`{${k}}`, String(replacements[k]));
    });
    return text;
  }

  async function requestJson(path, options) {
    try {
      const resp = await fetch(path, options);
      let body = {};
      try { body = await resp.json(); } catch (_) {}
      return { ok: resp.ok, status: resp.status, body };
    } catch (_) {
      return { ok: false, status: 0, body: {} };
    }
  }

  // ── Main registration flow ───────────────────────────────────────────

  function isRegisterPage() {
    return window.location.pathname.toLowerCase().endsWith("/register.html");
  }

  function initRegisterFlow() {
    if (!isRegisterPage()) return;

    const detailsView   = byId("detailsView");
    const scanView      = byId("scanView");
    const fullNameInput = byId("fullName");
    const studentIdInput = byId("studentId");
    const fullNameError = byId("fullNameError");
    const studentIdError = byId("studentIdError");
    const confirmBtn    = byId("confirmDetailsBtn");
    const scanSubtext   = byId("scanSubtext");
    const toast         = byId("registerToast");

    console.log("Register page elements:", { detailsView, scanView, fullNameInput, studentIdInput, confirmBtn });

    if (!detailsView || !scanView || !fullNameInput || !studentIdInput || !confirmBtn) {
      console.error("Register page init failed - missing required elements");
      return;
    }

    const touched = { fullName: false, studentId: false };
    let hfPollTimer     = null;
    let linkingInProgress = false;
    let startFailed     = false;
    let toastTimer      = null;
    // Guard: the Confirm button has BOTH an addEventListener handler and
    // an inline onclick fallback. A single tap fires both synchronously,
    // so without this flag two POSTs hit /api/register/details — the
    // first creates the user (201), the second 409s on the UNIQUE
    // constraint and (incorrectly) shows a "Student ID already registered"
    // toast even though the registration succeeded.
    let confirmInFlight = false;

    // ── Toast ──────────────────────────────────────────────────────────

    function showToast(message, type) {
      toast.textContent = message;
      toast.classList.remove("is-show", "is-error", "is-success");
      if (type === "error")   toast.classList.add("is-error");
      if (type === "success") toast.classList.add("is-success");
      toast.classList.add("is-show");
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { toast.classList.remove("is-show"); }, 3200);
    }

    // ── Validation ────────────────────────────────────────────────────

    function sanitizeStudentId() {
      const d = studentIdInput.value.replace(/\D+/g, "").slice(0, CONFIG.maxStudentIdLength);
      if (d !== studentIdInput.value) studentIdInput.value = d;
    }

    function validateFullName() {
      const v = fullNameInput.value.trim().replace(/\s+/g, " ");
      fullNameInput.value = v;
      if (!v) return t("registerFlowNameRequired", "Full Name is required.");
      if (v.length < CONFIG.minNameLength)
        return formatTemplate(
          t("registerFlowNameMinChars", "Full Name must be at least {min} characters."),
          { min: CONFIG.minNameLength }
        );
      return "";
    }

    function validateStudentId() {
      sanitizeStudentId();
      const v = studentIdInput.value.trim();
      if (!v) return t("registerFlowStudentIdRequired", "Student ID is required.");
      if (!/^\d+$/.test(v)) return t("registerFlowStudentIdDigitsOnly", "Student ID must contain digits only.");
      if (v.length < CONFIG.minStudentIdLength || v.length > CONFIG.maxStudentIdLength)
        return formatTemplate(
          t("registerFlowStudentIdRange", "Student ID must be {min}-{max} digits."),
          { min: CONFIG.minStudentIdLength, max: CONFIG.maxStudentIdLength }
        );
      return "";
    }

    function renderValidation(showAll) {
      const fnMsg  = validateFullName();
      const sidMsg = validateStudentId();
      const showFn  = showAll || touched.fullName;
      const showSid = showAll || touched.studentId;
      fullNameError.textContent  = showFn  ? fnMsg  : "";
      studentIdError.textContent = showSid ? sidMsg : "";
      fullNameInput.classList.toggle("input-invalid",  Boolean(showFn  && fnMsg));
      studentIdInput.classList.toggle("input-invalid", Boolean(showSid && sidMsg));
      return { valid: !fnMsg && !sidMsg };
    }

    // ── View transitions ──────────────────────────────────────────────

    function switchToScanView() {
      detailsView.classList.remove("register-view--active");
      detailsView.hidden = true;
      scanView.hidden = false;
      scanView.classList.add("register-view--active");
      if (scanSubtext) scanSubtext.textContent = t("registerScanWaiting", "Waiting for scan...");
    }

    function clearFormState() {
      fullNameInput.value = "";
      studentIdInput.value = "";
      touched.fullName = false;
      touched.studentId = false;
      fullNameError.textContent = "";
      studentIdError.textContent = "";
      fullNameInput.classList.remove("input-invalid");
      studentIdInput.classList.remove("input-invalid");
    }

    // ── HF RFID polling ───────────────────────────────────────────────

    function stopHfPolling() {
      if (hfPollTimer) { clearInterval(hfPollTimer); hfPollTimer = null; }
    }

    async function startHfCapture() {
      const result = await requestJson("/api/register/start_rfid", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      if (!result.ok) {
        startFailed = true;
        if (result.body && result.body.error === "RFID_UNAVAILABLE") {
          if (scanSubtext) scanSubtext.textContent = t("registerFlowRfidUnavailable", "RFID reader unavailable.");
          showToast(t("registerFlowRfidUnavailableContact", "RFID reader unavailable. Please contact staff."), "error");
          return false;
        }
        if (scanSubtext) scanSubtext.textContent = t("registerFlowUnableStartCapture", "Unable to start RFID capture.");
        showToast((result.body && result.body.message) || t("registerFlowSystemError", "System error. Try again."), "error");
        return false;
      }

      startFailed = false;
      if (scanSubtext) scanSubtext.textContent = t("registerScanWaiting", "Waiting for scan...");
      return true;
    }

    async function onHfUidDetected(uid) {
      if (linkingInProgress) return;
      linkingInProgress = true;
      if (scanSubtext) scanSubtext.textContent = t("registerFlowRfidDetectedLinking", "RFID detected. Linking...");

      const result = await requestJson("/api/register/link_rfid", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid }),
      });

      linkingInProgress = false;

      if (result.ok && result.body && result.body.ok) {
        // HF RFID linked — registration is complete.
        stopHfPolling();
        window.location.href = "/register_complete";
        return;
      }

      if (result.body && result.body.error === "RFID_EXISTS") {
        showToast(t("registerFlowRfidExists", "RFID card already linked."), "error");
        const restarted = await startHfCapture();
        if (restarted && scanSubtext) scanSubtext.textContent = t("registerScanWaiting", "Waiting for scan...");
        return;
      }

      if (result.body && result.body.error === "NO_PENDING") {
        stopHfPolling();
        showToast(t("registerFlowSystemError", "System error. Try again."), "error");
        if (scanSubtext) scanSubtext.textContent = t("registerFlowNoPendingRegistration", "No pending registration.");
        return;
      }

      showToast((result.body && result.body.message) || t("registerFlowSystemError", "System error. Try again."), "error");
      if (scanSubtext) scanSubtext.textContent = t("registerScanWaiting", "Waiting for scan...");
    }

    async function pollHfRfid() {
      if (startFailed || linkingInProgress) return;
      const result = await requestJson("/api/rfid/poll", { method: "GET" });
      if (!result.ok) {
        if (result.status === 503 || (result.body && result.body.error === "RFID_UNAVAILABLE")) {
          showToast(t("registerFlowRfidUnavailableContact", "RFID reader unavailable. Please contact staff."), "error");
          if (scanSubtext) scanSubtext.textContent = t("registerFlowRfidUnavailable", "RFID reader unavailable.");
          startFailed = true;
        }
        return;
      }
      const uid = String((result.body && result.body.uid) || "").trim().toUpperCase();
      if (!uid) return;
      await onHfUidDetected(uid);
    }

    function beginHfPolling() {
      stopHfPolling();
      hfPollTimer = setInterval(function () { void pollHfRfid(); }, CONFIG.hfPollIntervalMs);
      void pollHfRfid();
    }

    // ── Confirm details button ────────────────────────────────────────

    async function onConfirmDetails() {
      console.log("onConfirmDetails called");
      // Re-entry guard — block the duplicate inline-onclick + addEventListener
      // submit from sending two POSTs.
      if (confirmInFlight) {
        console.log("onConfirmDetails: already in flight, ignoring duplicate call");
        return;
      }

      touched.fullName = true;
      touched.studentId = true;
      const v = renderValidation(true);
      console.log("Validation result:", v);
      if (!v.valid) {
        console.log("Validation failed, returning");
        return;
      }

      confirmInFlight = true;
      confirmBtn.disabled = true;
      try {
        const result = await requestJson("/api/register/details", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            full_name: fullNameInput.value.trim(),
            student_id: studentIdInput.value.trim(),
          }),
        });

        if (!result.ok) {
          if (result.body && result.body.error === "STUDENT_ID_EXISTS") {
            showToast(t("registerFlowStudentIdExists", "Student ID already registered."), "error");
            studentIdInput.classList.add("input-invalid");
            studentIdInput.focus();
            return;
          }
          showToast((result.body && result.body.message) || t("registerFlowSystemError", "System error. Try again."), "error");
          return;
        }

        clearFormState();
        switchToScanView();
        const started = await startHfCapture();
        if (started) beginHfPolling();
      } finally {
        confirmInFlight = false;
        confirmBtn.disabled = false;
      }
    }

    // ── Input listeners ───────────────────────────────────────────────

    fullNameInput.addEventListener("input", function () {
      if (touched.fullName) renderValidation(false);
    });
    fullNameInput.addEventListener("blur", function () {
      touched.fullName = true; renderValidation(false);
    });

    studentIdInput.addEventListener("input", function () {
      sanitizeStudentId();
      if (touched.studentId) renderValidation(false);
    });
    studentIdInput.addEventListener("blur", function () {
      touched.studentId = true; renderValidation(false);
    });

    [fullNameInput, studentIdInput].forEach(function (input) {
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); void onConfirmDetails(); }
      });
    });

    confirmBtn.addEventListener("click", function (e) {
      console.log("Confirm button clicked (addEventListener)", e);
      void onConfirmDetails();
    });

    // Bulletproof fallback: expose the handler globally so an inline
    // onclick on the button in register.html also works, even if anything
    // above blocks the event listener path (overlapping CSS, another JS
    // throwing, etc.).
    window.__liblockerConfirmDetails = function (e) {
      console.log("Confirm button clicked (inline onclick fallback)", e);
      if (e && typeof e.preventDefault === "function") e.preventDefault();
      void onConfirmDetails();
      return false;
    };

    window.addEventListener("beforeunload", function () { stopHfPolling(); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRegisterFlow);
  } else {
    initRegisterFlow();
  }
})();
