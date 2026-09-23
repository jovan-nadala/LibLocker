(function () {
  "use strict";

  const API_BASE = "/api";
  const RFID_TIMEOUT_MS = 10000;
  const LANGUAGE_STORAGE_KEY = "liblocker_language";
  // Use sessionStorage for sensitive data (cleared when browser closes)
  const USE_SESSION_STORAGE = true;
  const UI_TRANSLATIONS = {
    en: {
      landingTouchPrefix: "Touch the screen",
      landingTouchSuffix: "to start",
      subtitle: "Self-Service E-Library Locker System. Select an action below to begin.",
      registerTitle: "Register",
      registerDesc: "Create a new account to use lockers",
      storeTitle: "Store Bag",
      storeDesc: "Secure your belonging for the day.",
      retrieveTitle: "Retrieve Bag",
      retrieveDescHome: "Collect your stored items.",
      retrieveDescDashboard: "Collect your stored items using your access code or ID.",
      helpRfidLine1: "Choose an action, then tap your RFID card.",
      helpRfidLine2: "Wait for confirmation before leaving the kiosk.",
      helpPrivacyLine1: "Keep your access code and RFID private.",
      helpPrivacyLine2: "You need one of them to retrieve your bag.",
      helpLanguageLine1: "Need assistance or language help?",
      helpLanguageLine2: "Tap the ? button at the bottom right.",
      languageLabel: "Language:",
      optionEnglish: "English",
      optionFilipino: "Filipino",
      registerPageTitle: "Register",
      registerPlaceholderFullName: "Full Name",
      registerPlaceholderStudentId: "Student ID Number",
      registerConfirmDetails: "Confirm Details",
      commonBack: "Back",
      commonNext: "Next",
      registerScanTitle: "Tap your RFID card to link your account.",
      registerScanWaiting: "Waiting for scan...",
      registerRightCaptionLine1: "Get one RFID card from the",
      registerRightCaptionLine2: "container below.",
      stepLockerSelection: "Locker Selection",
      depositTitle: "Deposit Bag",
      storeSelectSubtitle: "Please select your preferred locker position.",
      lockerLowerLevel: "Lower Level",
      lockerUpperLevel: "Upper Level",
      lockerAnyAvailable: "Any Available",
      rfidStepSubtitle: "Follow the steps to tap your RFID card.",
      rfidStepLocateReader: "Locate the RFID reader on the kiosk.",
      rfidStepTapFob: "Tap your registered RFID card.",
      statusWaitingRfidTap: "Waiting for RFID tap...",
      depositCompleteHeading: "Locker Assigned",
      depositCompleteSubtitle: "Your locker has been assigned. Please proceed to the locker shown below.",
      depositCompleteNote: "Place your bag inside and close the door firmly.",
      depositDoorWaiting: "Pull the locker door open to place your bag.",
      depositDoorOpen: "Door is open. Place your bag and close it firmly.",
      depositDoorClosing: "Door closed. Securing locker…",
      depositDoorSecured: "Locker secured. You may leave.",
      depositOpenTimerLabel: "Locker unlocks for",
      depositOpenTimerOpen: "Door is open",
      depositOpenTimerSecured: "Locker secured",
      depositOpenTimerExpired: "Locker re-locked",
      doorStillOpenWarning: "The locker door is still open. Please close it immediately.",
      processCompleteTitle: "Process Complete",
      processCompleteSubtitle: "Your locker is now open. Please take your belongings and close the locker door.",
      registrationCompleteTitle: "Registration Complete",
      registrationCompleteLine1: "Your RFID card is now linked.",
      registrationCompleteLine2: "You may now use Store Bag or Retrieve Bag.",
      returningMainMenu: "Returning to main menu...",
      noLockersTitle: "No Lockers Available",
      noLockersMsg: "All lockers are currently in use. Please try again later.",
      noLockersRedirect: "Returning to home in",
      noBagTitle: "No Bag Found",
      noBagMsg: "There's no bag stored for this card. Please deposit a bag first.",
      cardNotRegisteredTitle: "Card Not Registered",
      cardNotRegisteredMsg: "This RFID card isn't registered yet. Please register first.",
      stepSelectAction: "Select Action",
      stepRfidVerification: "RFID Verification",
      stepCompleteProcess: "Complete Process",
      statusLockerAssignedPrefix: "Locker assigned",
      errorLockerAssignmentFailed: "Locker assignment failed.",
      errorRetrieveFailed: "Retrieve failed.",
      statusLockerOpenedCompletingProcess: "Locker opened. Completing process...",
      registerConfirm: "Confirm",
      registerContinue: "Continue",
      registerValidationNameAndId: "Please enter your full name and student ID.",
      registerValidationCompleteFields: "Please complete the highlighted fields.",
      registerNameRequired: "Full name is required.",
      registerNameInvalid: "Please enter a valid full name.",
      registerStudentIdRequired: "Student ID is required.",
      registerStudentIdExactDigits: "Student ID must be exactly 9 digits.",
      registerDetailsConfirmed: "Details confirmed. Tap your RFID card, then press Continue.",
      registerRegistrationFailed: "Registration failed.",
      registerRegistrationSuccessful: "Registration successful.",
      errorRequestTimedOut: "Request timed out.",
      errorNetworkTryAgain: "Network error. Please try again.",
      registerFlowNameRequired: "Full Name is required.",
      registerFlowNameMinChars: "Full Name must be at least {min} characters.",
      registerFlowStudentIdRequired: "Student ID is required.",
      registerFlowStudentIdDigitsOnly: "Student ID must contain digits only.",
      registerFlowStudentIdRange: "Student ID must be {min}-{max} digits.",
      registerFlowRfidUnavailable: "RFID reader unavailable.",
      registerFlowRfidUnavailableContact: "RFID reader unavailable. Please contact staff.",
      registerFlowUnableStartCapture: "Unable to start RFID capture.",
      registerFlowSystemError: "System error. Try again.",
      registerFlowRfidDetectedLinking: "RFID detected. Linking...",
      registerFlowRfidExists: "RFID card already linked.",
      registerFlowNoPendingRegistration: "No pending registration.",
      registerFlowStudentIdExists: "Student ID already registered."
    },
    fil: {
      landingTouchPrefix: "Pindutin ang screen",
      landingTouchSuffix: "para magsimula",
      subtitle: "Self-Service E-Library Locker System. Pumili ng aksyon sa ibaba para magsimula.",
      registerTitle: "Magparehistro",
      registerDesc: "Gumawa ng bagong account para gumamit ng lockers",
      storeTitle: "I-store ang Bag",
      storeDesc: "I-secure ang iyong gamit para sa araw na ito.",
      retrieveTitle: "Kunin ang Bag",
      retrieveDescHome: "Kunin ang iyong naka-store na gamit.",
      retrieveDescDashboard: "Kunin ang iyong naka-store na gamit gamit ang iyong access code o ID.",
      helpRfidLine1: "Pumili ng aksyon, tapos i-tap ang iyong RFID card.",
      helpRfidLine2: "Hintayin ang confirmation bago umalis sa kiosk.",
      helpPrivacyLine1: "Panatilihing private ang iyong access code at RFID.",
      helpPrivacyLine2: "Kailangan mo ng isa sa mga ito para makuha ang iyong bag.",
      helpLanguageLine1: "Kailangan mo ba ng tulong o help sa language?",
      helpLanguageLine2: "I-tap ang ? button sa ibabang kanan.",
      languageLabel: "Wika:",
      optionEnglish: "Ingles",
      optionFilipino: "Filipino",
      registerPageTitle: "Magparehistro",
      registerPlaceholderFullName: "Buong Pangalan",
      registerPlaceholderStudentId: "Student ID Number",
      registerConfirmDetails: "Kumpirmahin ang Detalye",
      commonBack: "Bumalik",
      commonNext: "Susunod",
      registerScanTitle: "I-tap ang iyong RFID card para ma-link ang iyong account.",
      registerScanWaiting: "Naghihintay ng scan...",
      registerRightCaptionLine1: "Kumuha ng isang RFID card mula sa",
      registerRightCaptionLine2: "lalagyan sa ibaba.",
      stepLockerSelection: "Pili ng Locker",
      depositTitle: "I-store ang Bag",
      storeSelectSubtitle: "Piliin ang gusto mong posisyon ng locker.",
      lockerLowerLevel: "Ibabang Level",
      lockerUpperLevel: "Itaas na Level",
      lockerAnyAvailable: "Kahit Anong Available",
      rfidStepSubtitle: "Sundin ang mga hakbang para i-tap ang iyong RFID card.",
      rfidStepLocateReader: "Hanapin ang RFID reader sa kiosk.",
      rfidStepTapFob: "I-tap ang iyong registered RFID card.",
      statusWaitingRfidTap: "Naghihintay ng RFID tap...",
      depositCompleteHeading: "Naka-assign na Locker",
      depositCompleteSubtitle: "Naka-assign na ang iyong locker. Mangyaring pumunta sa locker na nasa ibaba.",
      depositCompleteNote: "Ilagay ang iyong bag sa loob at isara nang maigi ang pinto.",
      depositDoorWaiting: "Hilahin ang pinto ng locker para ilagay ang iyong bag.",
      depositDoorOpen: "Bukas na ang pinto. Ilagay ang bag at isara nang maigi.",
      depositDoorClosing: "Sarado na ang pinto. Sini-secure ang locker…",
      depositDoorSecured: "Secure na ang locker. Pwede ka nang umalis.",
      depositOpenTimerLabel: "Bukas ang locker sa loob ng",
      depositOpenTimerOpen: "Bukas ang pinto",
      depositOpenTimerSecured: "Secure na ang locker",
      depositOpenTimerExpired: "Naka-lock na ulit ang locker",
      doorStillOpenWarning: "Bukas pa ang pinto ng locker. Pakisara agad.",
      processCompleteTitle: "Kumpleto na ang Proseso",
      processCompleteSubtitle: "Bukas na ang iyong locker. Kunin ang iyong mga gamit at isara nang maayos ang pinto ng locker.",
      registrationCompleteTitle: "Kumpleto na ang Registration",
      registrationCompleteLine1: "Naka-link na ang iyong RFID card.",
      registrationCompleteLine2: "Pwede mo nang gamitin ang Store Bag o Retrieve Bag.",
      returningMainMenu: "Babalik sa main menu...",
      noLockersTitle: "Walang Available na Locker",
      noLockersMsg: "Puno na ang lahat ng locker sa ngayon. Pakisubukan muli mamaya.",
      noLockersRedirect: "Babalik sa home sa loob ng",
      noBagTitle: "Walang Nakitang Bag",
      noBagMsg: "Walang naka-store na bag para sa card na ito. Mag-deposit muna ng bag.",
      cardNotRegisteredTitle: "Hindi Rehistrado ang Card",
      cardNotRegisteredMsg: "Hindi pa nakarehistro ang RFID card na ito. Magparehistro muna.",
      stepSelectAction: "Pili ng Aksyon",
      stepRfidVerification: "RFID Verification",
      stepCompleteProcess: "Kumpletuhin ang Proseso",
      statusLockerAssignedPrefix: "Naka-assign na locker",
      errorLockerAssignmentFailed: "Hindi nagtagumpay ang locker assignment.",
      errorRetrieveFailed: "Hindi nagtagumpay ang pagkuha.",
      statusLockerOpenedCompletingProcess: "Bukas na ang locker. Kinukumpleto ang proseso...",
      registerConfirm: "Kumpirmahin",
      registerContinue: "Magpatuloy",
      registerValidationNameAndId: "Pakilagay ang iyong buong pangalan at student ID.",
      registerValidationCompleteFields: "Pakikumpleto ang naka-highlight na fields.",
      registerNameRequired: "Kailangan ang buong pangalan.",
      registerNameInvalid: "Pakilagay ang tamang buong pangalan.",
      registerStudentIdRequired: "Kailangan ang student ID.",
      registerStudentIdExactDigits: "Ang student ID ay dapat eksaktong 9 digits.",
      registerDetailsConfirmed: "Nakumpirma na ang detalye. I-tap ang iyong RFID card, tapos pindutin ang Continue.",
      registerRegistrationFailed: "Hindi nagtagumpay ang registration.",
      registerRegistrationSuccessful: "Matagumpay ang registration.",
      errorRequestTimedOut: "Nag-time out ang request.",
      errorNetworkTryAgain: "May network error. Pakisubukan muli.",
      registerFlowNameRequired: "Kailangan ang Full Name.",
      registerFlowNameMinChars: "Ang Full Name ay dapat may hindi bababa sa {min} characters.",
      registerFlowStudentIdRequired: "Kailangan ang Student ID.",
      registerFlowStudentIdDigitsOnly: "Ang Student ID ay dapat digits lang.",
      registerFlowStudentIdRange: "Ang Student ID ay dapat {min}-{max} digits.",
      registerFlowRfidUnavailable: "Hindi available ang RFID reader.",
      registerFlowRfidUnavailableContact: "Hindi available ang RFID reader. Paki-contact ang staff.",
      registerFlowUnableStartCapture: "Hindi ma-start ang RFID capture.",
      registerFlowSystemError: "May system error. Pakisubukan muli.",
      registerFlowRfidDetectedLinking: "Na-detect ang RFID. Lina-link...",
      registerFlowRfidExists: "Naka-link na ang RFID card.",
      registerFlowNoPendingRegistration: "Walang pending registration.",
      registerFlowStudentIdExists: "Naka-register na ang Student ID."
    }
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function normalizeLanguageCode(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "fil" || normalized === "filipino" || normalized === "tagalog") {
      return "fil";
    }
    return "en";
  }

  /**
   * Get stored language preference (uses localStorage - not sensitive data)
   */
  function getStoredLanguage() {
    try {
      return normalizeLanguageCode(localStorage.getItem(LANGUAGE_STORAGE_KEY));
    } catch (_) {
      return "en";
    }
  }

  /**
   * Set stored language preference (uses localStorage - not sensitive data)
   */
  function setStoredLanguage(languageCode) {
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, normalizeLanguageCode(languageCode));
    } catch (_) {
      // Ignore storage errors and keep language switching functional.
    }
  }

  /**
   * Get sensitive data from sessionStorage (auto-cleared on browser close).
   * For non-sensitive data like language, use localStorage.
   */
  function getSessionData(key, fallback) {
    try {
      const storage = USE_SESSION_STORAGE ? sessionStorage : localStorage;
      return storage.getItem(key) || fallback;
    } catch (_) {
      return fallback;
    }
  }

  /**
   * Set sensitive data to sessionStorage (auto-cleared on browser close).
   * For non-sensitive data like language, use localStorage.
   */
  function setSessionData(key, value) {
    try {
      const storage = USE_SESSION_STORAGE ? sessionStorage : localStorage;
      if (value === null || value === undefined) {
        storage.removeItem(key);
      } else {
        storage.setItem(key, value);
      }
    } catch (_) {
      // Ignore storage errors
    }
  }

  function t(key, fallback, languageCode) {
    const normalizedLanguage = normalizeLanguageCode(languageCode || getStoredLanguage());
    const languageMap = UI_TRANSLATIONS[normalizedLanguage] || UI_TRANSLATIONS.en;
    const fallbackMap = UI_TRANSLATIONS.en;

    if (Object.prototype.hasOwnProperty.call(languageMap, key)) {
      return languageMap[key];
    }

    if (Object.prototype.hasOwnProperty.call(fallbackMap, key)) {
      return fallbackMap[key];
    }

    return typeof fallback === "string" ? fallback : "";
  }

  function applyLanguage(languageCode) {
    const normalizedLanguage = normalizeLanguageCode(languageCode);

    const translatableNodes = document.querySelectorAll("[data-i18n-key]");
    translatableNodes.forEach((node) => {
      const key = node.getAttribute("data-i18n-key");
      if (!key) return;
      node.textContent = t(key, node.textContent, normalizedLanguage);
    });

    const placeholderNodes = document.querySelectorAll("[data-i18n-placeholder-key]");
    placeholderNodes.forEach((node) => {
      const key = node.getAttribute("data-i18n-placeholder-key");
      if (!key) return;
      node.setAttribute("placeholder", t(key, node.getAttribute("placeholder") || "", normalizedLanguage));
    });

    document.documentElement.lang = normalizedLanguage === "fil" ? "fil" : "en";
    setStoredLanguage(normalizedLanguage);
    return normalizedLanguage;
  }

  window.LibLockerI18n = {
    applyLanguage,
    getLanguage: getStoredLanguage,
    normalizeLanguageCode,
    setLanguage: setStoredLanguage,
    t
  };

  function goHome() {
    window.location.href = "/home";
  }

  function goPage(name) {
    const page = String(name || "").replace(/^\/+/, "");
    window.location.href = `/pages/${page}`;
  }

  window.goHome = goHome;
  window.goPage = goPage;

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function formatDate(d) {
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  }

  function initClock() {
    const timeEl = byId("time");
    const dateEl = byId("date");
    if (!timeEl || !dateEl) return;

    function tick() {
      const now = new Date();
      timeEl.textContent = `${pad2(now.getHours())}:${pad2(now.getMinutes())}`;
      dateEl.textContent = formatDate(now);
    }

    tick();
    setInterval(tick, 1000);
  }

  function setStatus(el, message, ok) {
    if (!el) return;
    el.textContent = message;
    if (typeof ok === "boolean") {
      el.style.color = ok ? "rgba(47,125,68,0.95)" : "rgba(160,30,30,0.90)";
    } else {
      el.style.color = "";
    }
  }

  async function apiPost(path, payload, timeoutMs) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs || RFID_TIMEOUT_MS);

    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
        signal: controller.signal
      });

      let body;
      try {
        body = await response.json();
      } catch (_) {
        body = { ok: false, data: {}, error: "Invalid JSON response." };
      }

      if (typeof body.ok !== "boolean" || typeof body.data !== "object" || !("error" in body)) {
        body = { ok: false, data: {}, error: "Unexpected API response format." };
      }

      return { httpStatus: response.status, body };
    } catch (error) {
      if (error && error.name === "AbortError") {
        return {
          httpStatus: 0,
          body: { ok: false, data: {}, error: t("errorRequestTimedOut", "Request timed out.") }
        };
      }

      return {
        httpStatus: 0,
        body: { ok: false, data: {}, error: t("errorNetworkTryAgain", "Network error. Please try again.") }
      };
    } finally {
      clearTimeout(timeout);
    }
  }


  async function apiGet(path, timeoutMs) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs || RFID_TIMEOUT_MS);

    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal: controller.signal
      });

      let body;
      try {
        body = await response.json();
      } catch (_) {
        body = { ok: false, data: {}, error: "Invalid JSON response." };
      }

      if (typeof body.ok !== "boolean" || typeof body.data !== "object" || !("error" in body)) {
        body = { ok: false, data: {}, error: "Unexpected API response format." };
      }

      return { httpStatus: response.status, body };
    } catch (error) {
      if (error && error.name === "AbortError") {
        return {
          httpStatus: 0,
          body: { ok: false, data: {}, error: t("errorRequestTimedOut", "Request timed out.") }
        };
      }

      return {
        httpStatus: 0,
        body: { ok: false, data: {}, error: t("errorNetworkTryAgain", "Network error. Please try again.") }
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  async function readRfid() {
    const result = await apiPost("/rfid/read", {});
    if (!result.body.ok) {
      throw new Error(result.body.error || "RFID read failed.");
    }
    return result.body.data.rfid_uid;
  }

  function initLandingPage() {
    const body = document.body;
    if (!body || !body.classList.contains("page-landing")) return;

    let navigating = false;

    function proceedToHome() {
      if (navigating) return;
      navigating = true;
      window.location.href = "/home";
    }

    function onActivate(event) {
      if (event.type === "keydown") {
        const isEnter = event.key === "Enter";
        const isSpace = event.key === " " || event.key === "Spacebar" || event.code === "Space";
        if (!isEnter && !isSpace) return;
        event.preventDefault();
      }

      proceedToHome();
    }

    document.addEventListener("click", onActivate);
    document.addEventListener("touchstart", onActivate, { passive: true });
    document.addEventListener("keydown", onActivate);
  }

  function initRfidCarousel() {
    const carousel = document.querySelector(".rfid-carousel");
    if (!carousel) return;

    const slides = Array.from(carousel.querySelectorAll(".rfid-slide"));
    const dots = Array.from(carousel.querySelectorAll(".rfid-dot"));
    if (!slides.length) return;

    const AUTO_ROTATE_MS = 4000;
    const PAUSE_AFTER_INTERACTION_MS = 10000;
    const SWIPE_THRESHOLD_PX = 40;

    let currentIndex = slides.findIndex((slide) => slide.classList.contains("is-active"));
    if (currentIndex < 0) currentIndex = 0;

    let autoTimer = null;
    let resumeTimer = null;
    let touchStartX = null;
    let touchStartY = null;
    let suppressNextClick = false;

    function updateUi(nextIndex) {
      currentIndex = (nextIndex + slides.length) % slides.length;

      slides.forEach((slide, index) => {
        const isActive = index === currentIndex;
        slide.classList.toggle("is-active", isActive);
        slide.setAttribute("aria-hidden", isActive ? "false" : "true");
      });

      dots.forEach((dot, index) => {
        const isActive = index === currentIndex;
        dot.classList.toggle("is-active", isActive);
        dot.setAttribute("aria-current", isActive ? "true" : "false");
      });
    }

    function stopAutoRotation() {
      if (autoTimer) {
        clearInterval(autoTimer);
        autoTimer = null;
      }
    }

    function startAutoRotation() {
      stopAutoRotation();
      autoTimer = setInterval(function () {
        updateUi(currentIndex + 1);
      }, AUTO_ROTATE_MS);
    }

    function pauseThenResume() {
      stopAutoRotation();
      if (resumeTimer) clearTimeout(resumeTimer);
      resumeTimer = setTimeout(startAutoRotation, PAUSE_AFTER_INTERACTION_MS);
    }

    function showSlide(index, fromUserInteraction) {
      updateUi(index);
      if (fromUserInteraction) pauseThenResume();
    }

    function nextSlide(fromUserInteraction) {
      showSlide(currentIndex + 1, fromUserInteraction);
    }

    dots.forEach((dot, index) => {
      dot.addEventListener("click", function (event) {
        event.stopPropagation();
        showSlide(index, true);
      });
    });

    carousel.addEventListener("click", function () {
      if (suppressNextClick) {
        suppressNextClick = false;
        return;
      }
      nextSlide(true);
    });

    carousel.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        showSlide(currentIndex + 1, true);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        showSlide(currentIndex - 1, true);
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        nextSlide(true);
      }
    });

    carousel.addEventListener(
      "touchstart",
      function (event) {
        if (!event.touches || event.touches.length !== 1) return;
        touchStartX = event.touches[0].clientX;
        touchStartY = event.touches[0].clientY;
      },
      { passive: true }
    );

    carousel.addEventListener(
      "touchend",
      function (event) {
        if (touchStartX === null || touchStartY === null || !event.changedTouches || !event.changedTouches.length) {
          touchStartX = null;
          touchStartY = null;
          return;
        }

        const dx = event.changedTouches[0].clientX - touchStartX;
        const dy = event.changedTouches[0].clientY - touchStartY;
        const isHorizontalSwipe = Math.abs(dx) >= SWIPE_THRESHOLD_PX && Math.abs(dx) > Math.abs(dy);

        if (isHorizontalSwipe) {
          suppressNextClick = true;
          showSlide(dx < 0 ? currentIndex + 1 : currentIndex - 1, true);
        }

        touchStartX = null;
        touchStartY = null;
      },
      { passive: true }
    );

    updateUi(currentIndex);
    if (slides.length > 1) startAutoRotation();
  }

  function initHomePage() {
    initRfidCarousel();

    const cards = document.querySelectorAll(".action-card");
    if (cards.length) {
      cards.forEach((card) => {
        card.addEventListener("click", () => {
          cards.forEach((c) => c.classList.remove("action-card--active"));
          card.classList.add("action-card--active");
        });
      });
    }

    const help = document.querySelector(".help-btn");
    const langPill = document.querySelector(".lang-pill");
    if (help && langPill) {
      function setLangPillOpen(isOpen) {
        langPill.classList.toggle("lang-pill--open", isOpen);
        help.setAttribute("aria-expanded", isOpen ? "true" : "false");
      }

      function toggleLangPill() {
        const isOpen = !langPill.classList.contains("lang-pill--open");
        setLangPillOpen(isOpen);
      }

      setLangPillOpen(false);

      help.addEventListener("click", function (event) {
        event.stopPropagation();
        toggleLangPill();
      });

      help.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggleLangPill();
        }
      });

      langPill.addEventListener("click", function (event) {
        event.stopPropagation();
      });

      document.addEventListener("click", function () {
        setLangPillOpen(false);
      });

      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          setLangPillOpen(false);
        }
      });
    }

    const langSelect = byId("langSelect");
    if (!langSelect) return;

    Array.from(langSelect.options).forEach((option) => {
      option.value = normalizeLanguageCode(option.value || option.textContent);
    });

    const appliedInitialLanguage = applyLanguage(getStoredLanguage());
    langSelect.value = appliedInitialLanguage;

    langSelect.addEventListener("change", function () {
      const selectedLanguage = normalizeLanguageCode(langSelect.value);
      const appliedLanguage = applyLanguage(selectedLanguage);
      langSelect.value = appliedLanguage;
    });
  }

  function initRegisterPage(pathname) {
    if (!pathname.endsWith("/register.html")) return;
    if (document.body && document.body.dataset.registerFlow === "guided-v2") return;

    const fullName = byId("fullName");
    const studentId = byId("studentId");
    const formAlert = byId("formAlert");
    const rfidRow = byId("rfidRow");
    const continueBtn = byId("continueBtn");

    if (!fullName || !studentId || !continueBtn) return;

    let detailsConfirmed = false;
    let fullNameTouched = false;
    let studentIdTouched = false;
    let submitAttempted = false;

    function setFormAlert(message, ok) {
      setStatus(formAlert, message || "", ok);
    }

    function resetConfirmation() {
      detailsConfirmed = false;
      continueBtn.textContent = t("registerConfirm", "Confirm");
      if (rfidRow) {
        rfidRow.classList.add("rfid-row--hidden");
        rfidRow.classList.remove("rfid-row--visible");
      }
      setFormAlert("", null);
    }

    function showRfidPrompt() {
      if (!rfidRow) return;
      rfidRow.classList.remove("rfid-row--hidden");
      rfidRow.classList.add("rfid-row--visible");
    }

    function normalizeStudentIdInput() {
      const digits = studentId.value.replace(/\D/g, "").slice(0, 9);
      if (digits !== studentId.value) {
        studentId.value = digits;
      }
    }

    function buildValidationMessage(nameError, sidError) {
      if (nameError && sidError) {
        if (!fullName.value.trim() && !studentId.value.trim()) {
          return t("registerValidationNameAndId", "Please enter your full name and student ID.");
        }
        return t("registerValidationCompleteFields", "Please complete the highlighted fields.");
      }
      return nameError || sidError || "";
    }

    function validate(showInlineError) {
      const name = fullName.value.trim();
      const sid = studentId.value.trim();
      let nameError = "";
      let sidError = "";

      if (!name) {
        nameError = t("registerNameRequired", "Full name is required.");
      } else if (name.length < 2 || name.length > 100) {
        nameError = t("registerNameInvalid", "Please enter a valid full name.");
      }

      if (!sid) {
        sidError = t("registerStudentIdRequired", "Student ID is required.");
      } else if (!/^\d{9}$/.test(sid)) {
        sidError = t("registerStudentIdExactDigits", "Student ID must be exactly 9 digits.");
      }

      const shouldShowInline = showInlineError || submitAttempted || fullNameTouched || studentIdTouched;

      fullName.classList.toggle("input-invalid", shouldShowInline && Boolean(nameError));
      studentId.classList.toggle("input-invalid", shouldShowInline && Boolean(sidError));

      if (shouldShowInline) {
        const message = buildValidationMessage(nameError, sidError);
        setFormAlert(message, message ? false : null);
      }

      if (nameError || sidError) {
        return { nameError, sidError };
      }
      return null;
    }

    async function submitRegistration() {
      submitAttempted = true;
      const validationErrors = validate(true);
      if (validationErrors) {
        if (validationErrors.nameError) {
          fullName.focus();
        } else if (validationErrors.sidError) {
          studentId.focus();
        }
        return;
      }

      if (!detailsConfirmed) {
        detailsConfirmed = true;
        showRfidPrompt();
        continueBtn.textContent = t("registerContinue", "Continue");
        setFormAlert(
          t("registerDetailsConfirmed", "Details confirmed. Tap your RFID card, then press Continue."),
          null
        );
        return;
      }

      continueBtn.disabled = true;
      setFormAlert(t("statusWaitingRfidTap", "Waiting for RFID tap..."), null);

      try {
        const rfidUid = await readRfid();

        const result = await apiPost("/register", {
          full_name: fullName.value.trim(),
          student_id: studentId.value.trim(),
          rfid_uid: rfidUid
        });

        if (!result.body.ok) {
          setFormAlert(result.body.error || t("registerRegistrationFailed", "Registration failed."), false);
          return;
        }

        setFormAlert(t("registerRegistrationSuccessful", "Registration successful."), true);
        setTimeout(function () {
          goPage("register_complete.html");
        }, 800);
      } catch (error) {
        setFormAlert(error.message || t("registerRegistrationFailed", "Registration failed."), false);
      } finally {
        continueBtn.disabled = false;
      }
    }

    continueBtn.addEventListener("click", submitRegistration);
    fullName.addEventListener("input", function () {
      if (detailsConfirmed) {
        resetConfirmation();
      }
      if (submitAttempted || fullNameTouched) {
        validate(true);
      }
    });
    fullName.addEventListener("blur", function () {
      fullNameTouched = true;
      validate(true);
    });

    studentId.addEventListener("input", function () {
      normalizeStudentIdInput();
      if (detailsConfirmed) {
        resetConfirmation();
      }
      if (submitAttempted || studentIdTouched) {
        validate(true);
      }
    });

    studentId.addEventListener("blur", function () {
      studentIdTouched = true;
      validate(true);
    });

    [fullName, studentId].forEach((input) => {
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          submitRegistration();
        }
      });
    });
  }

  function initRegisterCompletePage(pathname) {
    if (!pathname.endsWith("/register_complete.html")) return;

    const loaderEl = byId("registerCompleteLoader");
    const RETURN_AFTER_MS = 8000;
    const LOADER_HIDE_MS = 3000;

    let returnTimeoutId = null;
    let loaderTimeoutId = null;
    let cleanupTimeoutId = null;
    let finished = false;

    function finish() {
      if (finished) return;
      finished = true;
      if (returnTimeoutId) clearTimeout(returnTimeoutId);
      if (loaderTimeoutId) clearTimeout(loaderTimeoutId);
      if (cleanupTimeoutId) clearTimeout(cleanupTimeoutId);
      goHome();
    }

    document.body.classList.add("register-complete-loading");

    function hideLoader() {
      document.body.classList.remove("register-complete-loading");
      if (!loaderEl) return;
      loaderEl.classList.add("is-hidden");
      cleanupTimeoutId = setTimeout(function () {
        if (loaderEl && loaderEl.parentNode) {
          loaderEl.parentNode.removeChild(loaderEl);
        }
      }, 500);
    }

    loaderTimeoutId = setTimeout(hideLoader, LOADER_HIDE_MS);
    returnTimeoutId = setTimeout(finish, RETURN_AFTER_MS);

    window.addEventListener("beforeunload", function () {
      if (returnTimeoutId) clearTimeout(returnTimeoutId);
      if (loaderTimeoutId) clearTimeout(loaderTimeoutId);
      if (cleanupTimeoutId) clearTimeout(cleanupTimeoutId);
    });
  }

  function normalizeGroupFromUi(value) {
    const key = String(value || "").toUpperCase();
    if (key === "UPPER") return "upper";
    if (key === "LOWER") return "lower";
    if (key === "ANY") return "any";
    return "any";
  }

  function initStoreSelectPage(pathname) {
    if (!pathname.endsWith("/store_select.html")) return;

    const options = Array.from(document.querySelectorAll(".locker-option"));
    const nextBtn = byId("nextBtn");
    if (!nextBtn || !options.length) return;

    function setSelected(button) {
      options.forEach((b) => {
        b.classList.remove("locker-option--active");
        b.setAttribute("aria-pressed", "false");
      });

      button.classList.add("locker-option--active");
      button.setAttribute("aria-pressed", "true");

      const rawValue = button.getAttribute("data-value");
      const group = normalizeGroupFromUi(rawValue);
      setSessionData("liblocker_locker_group", group);
      setSessionData("liblocker_locker_preference", rawValue || "ANY");

      nextBtn.disabled = false;
    }

    options.forEach((button) => {
      button.addEventListener("click", function () {
        setSelected(button);
      });
    });

    nextBtn.addEventListener("click", function () {
      goPage("deposit.html");
    });

    const saved = getSessionData("liblocker_locker_preference", null);
    if (saved) {
      const match = options.find((b) => (b.getAttribute("data-value") || "").toUpperCase() === saved.toUpperCase());
      if (match) {
        setSelected(match);
      }
    }
  }

  // ==================== CONTINUOUS DEPOSIT FLOW ====================
  function initDepositPage(pathname) {
    if (!pathname.endsWith("/deposit.html")) return;

    const statusEl = byId("retrieveStatus");
    let isPageActive = true; // Tracks if we should keep scanning

    // Full-screen "no lockers available" state with an auto-redirect home.
    function showNoLockersState() {
      isPageActive = false;
      const overlay = byId("noLockersOverlay");
      if (!overlay) { goHome(); return; }

      // Make sure the overlay text is in the selected language.
      try { applyLanguage(getStoredLanguage()); } catch (_) {}
      overlay.hidden = false;

      let remaining = 5;
      const countEl = byId("noLockersCountdown");
      const barEl   = byId("noLockersBar");
      if (countEl) countEl.textContent = String(remaining);
      if (barEl) {
        barEl.style.transition = "none";
        barEl.style.transform = "scaleX(1)";
        // Next frame: drain the bar smoothly over the countdown window.
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            barEl.style.transition = "transform " + remaining + "s linear";
            barEl.style.transform = "scaleX(0)";
          });
        });
      }

      const timer = setInterval(function () {
        remaining -= 1;
        if (countEl) countEl.textContent = String(Math.max(remaining, 0));
        if (remaining <= 0) {
          clearInterval(timer);
          goHome();
        }
      }, 1000);
    }

    async function runDepositFlow() {
      // Create an infinite loop that keeps trying to scan until successful
      while (isPageActive) {
        setStatus(statusEl, t("statusWaitingRfidTap", "Waiting for RFID tap..."), null);

        try {
          const group = getSessionData("liblocker_locker_group", "any");

          // Wait for a scan (times out after 8s from backend)
          const rfidUid = await readRfid();

          // If we successfully get a UID, stop the infinite loop
          isPageActive = false;
          setStatus(statusEl, `RFID detected: ${rfidUid}. Processing...`, true);

          // Assign the locker in the database
          const result = await apiPost("/deposit/assign", {
            rfid_uid: rfidUid,
            locker_group: group
          });

          // Handle Database/Logic Errors (e.g. User not found)
          if (!result.body.ok) {
            // All lockers occupied → dedicated full-screen state + go home.
            // Backend returns HTTP 409 for this case.
            const noLockers = result.httpStatus === 409
              || /no\s+available\s+locker/i.test(result.body.error || "");
            if (noLockers) {
              showNoLockersState();
              return; // stop the scan loop entirely
            }

            setStatus(statusEl, result.body.error || t("errorLockerAssignmentFailed", "Locker assignment failed."), false);
            // Pause for 3 seconds so the user can read the error, then resume scanning
            await new Promise(r => setTimeout(r, 3000));
            isPageActive = true;
            continue;
          }

          // SUCCESS! Save locker number and redirect
          const lockerNumber = result.body.data.locker_number;
          const lockerId = result.body.data.locker_id;
          const autoCloseSeconds = Number(result.body.data.auto_close_seconds || 10);
          setSessionData("liblocker_assigned_locker", String(lockerNumber));
          if (lockerId) setSessionData("liblocker_assigned_locker_id", String(lockerId));
          setSessionData("liblocker_deposit_auto_close_seconds", String(autoCloseSeconds));
          setStatus(statusEl, `${t("statusLockerAssignedPrefix", "Locker assigned")}: ${String(lockerNumber)}`, true);

          setTimeout(function () {
            goPage(
              `deposit_complete.html?locker=${encodeURIComponent(lockerNumber)}&locker_id=${encodeURIComponent(lockerId || "")}&open_seconds=${encodeURIComponent(autoCloseSeconds)}`
            );
          }, 1000);

        } catch (error) {
          // If the 8-second scan window just timed out normally, silently loop back and scan again
          if (error.message.includes("empty UID") || error.message.includes("timed out")) {
            continue;
          }

          // If it's a real network error, show it, pause, and try again
          setStatus(statusEl, error.message || t("errorLockerAssignmentFailed", "Locker assignment failed."), false);
          await new Promise(r => setTimeout(r, 3000));
        }
      }
    }

    // Stop scanning if the user navigates away using the back button
    window.addEventListener('beforeunload', () => { isPageActive = false; });

    setTimeout(runDepositFlow, 250);
  }

  // ==================== CONTINUOUS RETRIEVE FLOW ====================
  function initRetrievePage(pathname) {
    if (!pathname.endsWith("/retrieve.html")) return;

    const statusEl = byId("retrieveStatus");
    let isPageActive = true;

    // Grace window: how long we'll keep scanning before assuming the user
    // walked away. Each rfid/read call has its own ~8s timeout, so this lets
    // us run two-and-a-bit scan cycles before giving up and going home.
    const NO_TAP_GRACE_MS = 20000;
    const flowStartedAt = Date.now();

    function isNoCardError(error) {
      const msg = String((error && error.message) || "").toLowerCase();
      return (
        msg.includes("no rfid card") ||
        msg.includes("no card detected") ||
        msg.includes("empty uid") ||
        msg.includes("timed out") ||
        msg.includes("timeout")
      );
    }

    function returnToMainMenu() {
      isPageActive = false;
      setStatus(statusEl, t("statusWaitingRfidTap", "Waiting for RFID tap..."), null);
      // Brief fade so the transition feels intentional rather than a crash.
      try {
        document.body.style.transition = "opacity 0.25s";
        document.body.style.opacity = "0";
      } catch (_) { /* ignore */ }
      setTimeout(goHome, 280);
    }

    // Full-screen state when the tapped card has nothing to retrieve
    // (no active locker, or the card isn't registered). Redirects home.
    function showNoBagState(errorMessage) {
      isPageActive = false;
      const overlay = byId("noBagOverlay");
      if (!overlay) { returnToMainMenu(); return; }

      const notRegistered = /not\s+registered/i.test(errorMessage || "");
      try { applyLanguage(getStoredLanguage()); } catch (_) {}

      const titleEl = byId("noBagTitle");
      const msgEl   = byId("noBagMsg");
      if (notRegistered) {
        if (titleEl) titleEl.textContent = t("cardNotRegisteredTitle", "Card Not Registered");
        if (msgEl)   msgEl.textContent   = t("cardNotRegisteredMsg", "This RFID card isn't registered yet. Please register first.");
      } else {
        if (titleEl) titleEl.textContent = t("noBagTitle", "No Bag Found");
        if (msgEl)   msgEl.textContent   = t("noBagMsg", "There's no bag stored for this card. Please deposit a bag first.");
      }

      overlay.hidden = false;

      let remaining = 5;
      const countEl = byId("noBagCountdown");
      const barEl   = byId("noBagBar");
      if (countEl) countEl.textContent = String(remaining);
      if (barEl) {
        barEl.style.transition = "none";
        barEl.style.transform = "scaleX(1)";
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            barEl.style.transition = "transform " + remaining + "s linear";
            barEl.style.transform = "scaleX(0)";
          });
        });
      }

      const timer = setInterval(function () {
        remaining -= 1;
        if (countEl) countEl.textContent = String(Math.max(remaining, 0));
        if (remaining <= 0) {
          clearInterval(timer);
          goHome();
        }
      }, 1000);
    }

    async function runRetrieveFlow() {
      while (isPageActive) {
        setStatus(statusEl, t("statusWaitingRfidTap", "Waiting for RFID tap..."), null);

        try {
          const rfidUid = await readRfid();

          isPageActive = false; // Stop scanning
          setStatus(statusEl, `RFID detected: ${rfidUid}. Opening locker...`, true);

          // Attempt to release the locker (this triggers the Pi GPIO even if solenoids are missing)
          const result = await apiPost("/retrieve/release", {
            rfid_uid: rfidUid
          });

          if (!result.body.ok) {
            // Nothing to retrieve for this card → dedicated full-screen state
            // + go home. Backend returns HTTP 404 for both "no locker
            // assigned" and "RFID not registered".
            const nothingToRetrieve = result.httpStatus === 404
              || /no locker is currently assigned|not\s+registered/i.test(result.body.error || "");
            if (nothingToRetrieve) {
              showNoBagState(result.body.error);
              return; // stop the scan loop entirely
            }

            setStatus(statusEl, result.body.error || t("errorRetrieveFailed", "Retrieve failed."), false);
            await new Promise(r => setTimeout(r, 3000));
            isPageActive = true;
            continue;
          }

          // SUCCESS! Redirect to complete page
          const autoCloseSeconds = Number(result.body.data.auto_close_seconds || 10);
          setSessionData("liblocker_retrieve_auto_close_seconds", String(autoCloseSeconds));
          setStatus(statusEl, t("statusLockerOpenedCompletingProcess", "Locker opened. Completing process..."), true);
          setTimeout(function () {
            goPage(`complete_process.html?open_seconds=${encodeURIComponent(autoCloseSeconds)}`);
          }, 1000);

        } catch (error) {
          // No tap from the student — never show an error for this case.
          // Just loop until the grace window expires, then bounce home.
          if (isNoCardError(error)) {
            if (Date.now() - flowStartedAt >= NO_TAP_GRACE_MS) {
              returnToMainMenu();
              return;
            }
            continue;
          }
          // Real failures (network/hardware) still get shown briefly.
          setStatus(statusEl, error.message || t("errorRetrieveFailed", "Retrieve failed."), false);
          await new Promise(r => setTimeout(r, 3000));
        }
      }
    }

    window.addEventListener('beforeunload', () => { isPageActive = false; });

    setTimeout(runRetrieveFlow, 250);
  }

  function initDepositCompletePage(pathname) {
    if (!pathname.endsWith("/deposit_complete.html")) return;

    const lockerEl = byId("lockerNumber");
    const indicatorEl = byId("depositDoorIndicator");
    const indicatorTextEl = byId("depositDoorIndicatorText");
    if (!lockerEl || !indicatorEl || !indicatorTextEl) return;

    const params = new URLSearchParams(window.location.search);
    const paramLocker = params.get("locker");
    const paramLockerId = params.get("locker_id") || getSessionData("liblocker_assigned_locker_id", null);
    const storedLocker = getSessionData("liblocker_assigned_locker", null);
    const lockerNum = Number(paramLocker || storedLocker || 0);

    lockerEl.textContent = Number.isInteger(lockerNum) && lockerNum >= 1 && lockerNum <= 24
      ? String(lockerNum) : "--";

    function setIndicatorState(modifier, key, fallback) {
      const validModifiers = ["waiting", "open", "closing", "secured", "error"];
      validModifiers.forEach((m) => indicatorEl.classList.remove(`door-indicator--${m}`));
      indicatorEl.classList.add(`door-indicator--${modifier}`);
      indicatorTextEl.setAttribute("data-i18n-key", key);
      indicatorTextEl.textContent = t(key, fallback);
    }

    setIndicatorState("waiting", "depositDoorWaiting",
      "Pull the locker door open to place your bag.");

    let navigationTimer = null;
    function stopNavigation() {
      if (navigationTimer !== null) {
        clearTimeout(navigationTimer);
        navigationTimer = null;
      }
    }

    navigationTimer = setTimeout(() => {
      setIndicatorState("closing", "depositDoorClosing", "Door closed. Securing locker…");
      setTimeout(() => {
        setIndicatorState("secured", "depositDoorSecured", "Locker secured. You may leave.");
        setTimeout(goHome, 1000);
      }, 1000);
    }, 5000);

    window.addEventListener("beforeunload", stopNavigation);
  }

  function initCompleteProcessPage(pathname) {
    if (!pathname.endsWith("/complete_process.html")) return;

    const countdownEl = byId("retrieveAutoCloseCountdown");
    if (!countdownEl) return;

    const params = new URLSearchParams(window.location.search);
    const paramOpenSeconds = Number(
      params.get("open_seconds") || getSessionData("liblocker_retrieve_auto_close_seconds", "5")
    );

    let remaining = Math.max(1, Math.floor(
      Number.isFinite(paramOpenSeconds) && paramOpenSeconds > 0 ? paramOpenSeconds : 5
    ));
    countdownEl.textContent = `Locker will relock in ${remaining}s.`;

    const timer = setInterval(function () {
      remaining -= 1;
      if (remaining <= 0) {
        countdownEl.textContent = "Locker should now be closed. Take your belongings.";
        clearInterval(timer);
        return;
      }
      countdownEl.textContent = `Locker will relock in ${remaining}s.`;
    }, 1000);
  }

  function initPageLanguage() {
    applyLanguage(getStoredLanguage());
  }

  function bootstrap() {
    initClock();

    const pathname = window.location.pathname.toLowerCase();
    initPageLanguage();

    initLandingPage();
    initHomePage();
    initRegisterPage(pathname);
    initRegisterCompletePage(pathname);
    initStoreSelectPage(pathname);
    initDepositPage(pathname);
    initRetrievePage(pathname);
    initDepositCompletePage(pathname);
    initCompleteProcessPage(pathname);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }

  // ==================== ENHANCED CLOCK ====================
  function updateClock() {
    const now = new Date();
    const timeEl = document.getElementById('time');
    const dateEl = document.getElementById('date');
    
    if (timeEl) {
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      timeEl.textContent = `${hours}:${minutes}`;
    }
    
    if (dateEl) {
      const options = { month: 'short', day: 'numeric', year: 'numeric' };
      dateEl.textContent = now.toLocaleDateString('en-US', options);
    }
  }

  // ==================== ENHANCED CAROUSEL ====================
  function initCarousel() {
    const carousel = document.querySelector('.rfid-carousel');
    if (!carousel) return;

    const track = carousel.querySelector('.rfid-carousel-track');
    const slides = Array.from(carousel.querySelectorAll('.rfid-slide'));
    const dots = Array.from(carousel.querySelectorAll('.rfid-dot'));
    let currentIndex = 0;
    let autoPlayTimer;

    function goToSlide(index) {
      // Update slides
      slides.forEach((slide, i) => {
        slide.classList.toggle('is-active', i === index);
        slide.setAttribute('aria-hidden', i !== index);
      });

      // Update dots
      dots.forEach((dot, i) => {
        dot.classList.toggle('is-active', i === index);
        dot.setAttribute('aria-current', i === index);
      });

      currentIndex = index;
    }

    function nextSlide() {
      const next = (currentIndex + 1) % slides.length;
      goToSlide(next);
    }

    function startAutoPlay() {
      stopAutoPlay();
      autoPlayTimer = setInterval(nextSlide, 5000);
    }

    function stopAutoPlay() {
      if (autoPlayTimer) {
        clearInterval(autoPlayTimer);
        autoPlayTimer = null;
      }
    }

    // Dot navigation
    dots.forEach((dot, index) => {
      dot.addEventListener('click', () => {
        goToSlide(index);
        stopAutoPlay();
        startAutoPlay();
      });
    });

    // Keyboard navigation
    carousel.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') {
        const prev = (currentIndex - 1 + slides.length) % slides.length;
        goToSlide(prev);
        stopAutoPlay();
        startAutoPlay();
      } else if (e.key === 'ArrowRight') {
        nextSlide();
        stopAutoPlay();
        startAutoPlay();
      }
    });

    // Pause on hover
    carousel.addEventListener('mouseenter', stopAutoPlay);
    carousel.addEventListener('mouseleave', startAutoPlay);

    startAutoPlay();
  }

  // ==================== ENHANCED LOCKER SELECTION ====================
  function initLockerSelection() {
    const options = document.querySelectorAll('.locker-option');
    const nextBtn = document.getElementById('nextBtn');
    
    if (!options.length || !nextBtn) return;

    let selectedValue = null;

    options.forEach(option => {
      option.addEventListener('click', () => {
        // Deselect all
        options.forEach(opt => {
          opt.setAttribute('aria-pressed', 'false');
          opt.classList.remove('selected');
        });

        // Select clicked
        option.setAttribute('aria-pressed', 'true');
        option.classList.add('selected');
        selectedValue = option.getAttribute('data-value');

        // Enable next button
        nextBtn.disabled = false;
      });
    });

    nextBtn.addEventListener('click', () => {
      if (selectedValue) {
        // Store selection in sessionStorage (cleared when browser closes)
        setSessionData('selectedLockerLevel', selectedValue);
        // Navigate to deposit page
        window.location.href = 'deposit.html';
      }
    });
  }

  // ==================== ENHANCED FORM VALIDATION ====================
  function addInputEnhancement(inputId, errorId, validator) {
    const input = document.getElementById(inputId);
    const error = document.getElementById(errorId);
    
    if (!input || !error) return;

    let touched = false;

    function validate() {
      const message = validator(input.value);
      error.textContent = message;
      input.classList.toggle('input-invalid', Boolean(message && touched));
      return !message;
    }

    input.addEventListener('input', () => {
      if (touched) validate();
    });

    input.addEventListener('blur', () => {
      touched = true;
      validate();
    });

    return { validate, setTouched: () => { touched = true; } };
  }

  // ==================== ENHANCED NAVIGATION ====================
  function setupNavigation() {
    // Smooth scroll to top on navigation
    window.addEventListener('beforeunload', () => {
      window.scrollTo(0, 0);
    });

    // Handle back button
    window.addEventListener('popstate', () => {
      // Add fade out effect
      document.body.style.opacity = '0';
      setTimeout(() => {
        document.body.style.opacity = '1';
      }, 100);
    });
  }

  // ==================== ENHANCED INACTIVITY TIMEOUT ====================
  let inactivityTimer;
  // Increased from 60s to 120s (2 minutes) - more reasonable for library kiosk
  // Users may need time to read instructions, locate RFID card, etc.
  const INACTIVITY_TIMEOUT = 120000; // 120 seconds (2 minutes)

  function resetInactivityTimer() {
    clearTimeout(inactivityTimer);

    const body = document.body;
    const path = window.location.pathname;

    // Never auto-navigate away from the landing/attract screen itself.
    if (body.classList.contains('page-landing') || path === '/' || path.endsWith('/index.html')) {
      return;
    }

    // The HOME menu returns to the landing (attract) screen after idle;
    // every other page returns to the home menu.
    const isHome = body.classList.contains('page-home')
      || path === '/home'
      || path.endsWith('/home.html');
    const dest = isHome ? '/' : '/home';

    inactivityTimer = setTimeout(() => {
      // Fade out
      document.body.style.transition = 'opacity 0.3s';
      document.body.style.opacity = '0';

      setTimeout(() => {
        window.location.href = dest;
      }, 300);
    }, INACTIVITY_TIMEOUT);
  }

  function setupInactivityDetection() {
    ['mousedown', 'mousemove', 'keypress', 'touchstart', 'scroll'].forEach(event => {
      document.addEventListener(event, resetInactivityTimer);
    });
    
    resetInactivityTimer();
  }

  // ==================== ENHANCED PAGE LOAD ====================
  function onPageLoad() {
    // Fade in effect
    document.body.style.opacity = '0';
    setTimeout(() => {
      document.body.style.transition = 'opacity 0.3s';
      document.body.style.opacity = '1';
    }, 50);

    // Initialize features
    updateClock();
    setInterval(updateClock, 1000);
    
    initCarousel();
    initLockerSelection();
    setupNavigation();
    setupInactivityDetection();

    // Auto-redirect from the retrieve "complete_process" page (deposit_complete
    // is driven by the door-state indicator and self-navigates only after the
    // door is confirmed secured, so we exclude it here).
    const path = window.location.pathname;
    const isCompleteProcess = path.includes('complete_process.html');
    if (isCompleteProcess) {
      const urlParams = new URLSearchParams(window.location.search);
      const openSeconds = Number(urlParams.get('open_seconds') || 0);
      const redirectDelayMs = Number.isFinite(openSeconds) && openSeconds > 0
        ? Math.max(5000, (Math.floor(openSeconds) * 1000) + 1000)
        : 5000;
      setTimeout(() => {
        document.body.style.opacity = '0';
        setTimeout(() => {
          window.location.href = '/home';
        }, 300);
      }, redirectDelayMs);
    }
  }

  // ==================== GLOBAL HELPERS ====================
  window.goHome = function() {
    window.location.href = '/home';
  };

  window.goPage = function(page) {
    window.location.href = page;
  };

  // ==================== INITIALIZE ====================
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onPageLoad);
  } else {
    onPageLoad();
  }

})();
