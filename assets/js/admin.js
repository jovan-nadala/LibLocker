(function () {
  "use strict";

  /* ─────────────────────────────────────────────────────────────
     SHARED UTILITIES
  ───────────────────────────────────────────────────────────── */

  function safeText(v) {
    return String(v == null ? "" : v)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  // Force every admin timestamp display to render in Philippine time
  // (UTC+8) regardless of the browser/OS timezone.
  var PHT_TZ = "Asia/Manila";

  function fmtDateTime(raw) {
    var d = parseApiTimestamp(raw);
    if (!d) return raw || "-";
    return d.toLocaleDateString("en-US",
      { timeZone: PHT_TZ, month: "short", day: "numeric", year: "numeric" })
      + " " + d.toLocaleTimeString("en-US",
      { timeZone: PHT_TZ, hour: "2-digit", minute: "2-digit", hour12: true });
  }

  function fmtTimeOnly(raw) {
    var d = parseApiTimestamp(raw);
    if (!d) return raw || "-";
    return d.toLocaleTimeString("en-US",
      { timeZone: PHT_TZ, hour: "2-digit", minute: "2-digit", hour12: true });
  }

  // Parse a timestamp the API returned. SQLite "datetime('now')" always
  // returns UTC (regardless of the system clock's timezone configuration),
  // so a bare "YYYY-MM-DD HH:MM:SS" must be treated as UTC. We then format
  // it explicitly in Asia/Manila for display.
  function parseApiTimestamp(raw) {
    if (!raw) return null;
    var s = String(raw).trim();
    if (!s) return null;
    if (s.indexOf("T") < 0) s = s.replace(" ", "T");
    // Bare timestamp → tag as UTC so the browser converts correctly.
    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) s += "Z";
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  // Relative time shown in the recent-activity feed. Granularity is
  // *minute*-level (no per-second labels) because the ticker only re-runs
  // once a minute — second-level labels would otherwise lie for up to 59s.
  function fmtRelativeTime(raw) {
    var d = parseApiTimestamp(raw);
    if (!d) return "-";
    var diff = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
    if (diff < 60)       return "just now";
    if (diff < 3600)     return Math.floor(diff / 60) + "m ago";
    if (diff < 86400)    return Math.floor(diff / 3600) + "h ago";
    if (diff < 604800)   return Math.floor(diff / 86400) + "d ago";
    return d.toLocaleDateString("en-US",
      { timeZone: PHT_TZ, month: "short", day: "numeric" })
      + ", " + d.toLocaleTimeString("en-US",
      { timeZone: PHT_TZ, hour: "2-digit", minute: "2-digit", hour12: true });
  }

  function parseDetailsObject(raw) {
    if (!raw || typeof raw !== "string") return {};
    try {
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function normalizeEvidenceUrl(rawUrl, rawFilename) {
    var url = String(rawUrl || "").trim();
    if (url) {
      if (/^https?:\/\//i.test(url) || url.charAt(0) === "/") return url;
      return "/evidence/" + url.replace(/^\/+/, "");
    }

    var filename = String(rawFilename || "").trim();
    if (!filename) return "";
    return "/evidence/" + filename.replace(/^\/+/, "");
  }

  function getAdminToken() {
    var bt = (document.body.dataset.adminToken || "").trim();
    if (bt) return bt;
    var m = document.querySelector('meta[name="admin-token"]');
    if (m && m.content) return m.content.trim();
    return (new URLSearchParams(window.location.search)).get("token") || "";
  }

  function withToken(path) {
    var t = getAdminToken();
    if (!t) return path;
    return path + (path.indexOf("?") >= 0 ? "&" : "?") + "token=" + encodeURIComponent(t);
  }

  async function fetchAdminJson(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (opts.body && !opts.headers["Content-Type"]) {
      opts.headers["Content-Type"] = "application/json";
    }
    var res = await fetch(withToken(path), opts);
    
    // Handle authentication failures
    if (res.status === 401) {
      // Redirect to login page
      window.location.href = "/admin/login";
      throw new Error("Unauthorized - redirecting to login");
    }
    
    if (res.status === 403) {
      window.location.href = "/admin/unauthorized";
      throw new Error("Unauthorized");
    }
    
    var payload = {};
    try { payload = await res.json(); } catch(e) { payload = {}; }
    if (!res.ok) throw new Error(payload.error || "Request failed.");
    return payload;
  }

  /* ─────────────────────────────────────────────────────────────
     LOCKER TILE RENDERING  (grouped by section)
  ───────────────────────────────────────────────────────────── */

  var TILE_ICONS  = { available: "🟢", occupied: "🔒", maintenance: "🔧" };
  var TILE_STATUS = { available: "Available", occupied: "Occupied", maintenance: "Maintenance" };
  var TILE_CLS    = {
    available:   "locker-tile--available",
    occupied:    "locker-tile--occupied",
    maintenance: "locker-tile--maintenance",
  };

  // Display labels for the four DB locker_group values.
  // Physical layout (numbers stay as seeded):
  //   upper1 = 1–6   → Upper Section A
  //   upper2 = 7–12  → Lower Section A   ← label swapped
  //   lower1 = 13–18 → Upper Section B   ← label swapped
  //   lower2 = 19–24 → Lower Section B
  var GROUP_LABELS = {
    upper1: "Upper Section A",
    upper2: "Lower Section A",
    lower1: "Upper Section B",
    lower2: "Lower Section B",
  };
  var GROUP_ORDER = ["upper1", "upper2", "lower1", "lower2"];

  function sectionKeyForLocker(locker) {
    return locker.locker_group || "upper1";
  }

  function sectionLabelForLocker(locker) {
    return GROUP_LABELS[sectionKeyForLocker(locker)] || "—";
  }

  function makeTile(locker, clickable) {
    var el = document.createElement(clickable ? "button" : "div");
    if (clickable) el.type = "button";
    var cls = TILE_CLS[locker.status] || "locker-tile--available";
    el.className = "locker-tile " + cls;
    el.dataset.lockerId = String(locker.id);
    var num = locker.locker_number || locker.id;
    el.innerHTML =
      '<span class="tile-num">' + safeText(String(num)) + '</span>' +
      '<span class="tile-icon">' + (TILE_ICONS[locker.status] || "◆") + '</span>' +
      '<span class="tile-status-lbl">' + (TILE_STATUS[locker.status] || locker.status) + '</span>';
    return el;
  }

  function renderLockerSections(wrap, lockers, clickable) {
    if (!wrap) return;
    wrap.innerHTML = "";

    if (!Array.isArray(lockers) || lockers.length === 0) {
      wrap.innerHTML =
        '<div class="grid-state-wrap" style="padding:40px 0;">' +
        '<div class="grid-state-icon">📭</div>' +
        '<p class="grid-state-msg">No lockers found in database.<br>' +
        '<small style="font-size:11px;">Run the DB reset command to re-seed locker data.</small></p>' +
        '</div>';
      return;
    }

    // Group lockers by their DB locker_group field.
    var groups = {};
    lockers.forEach(function(l) {
      var g = l.locker_group || "upper1";
      if (!groups[g]) groups[g] = [];
      groups[g].push(l);
    });

    GROUP_ORDER.forEach(function(key) {
      if (!groups[key] || groups[key].length === 0) return;
      var section = document.createElement("div");
      section.className = "locker-section";

      var header = document.createElement("div");
      header.className = "locker-section-header";

      var avail = groups[key].filter(function(l){ return l.status === "available"; }).length;
      var occup = groups[key].filter(function(l){ return l.status === "occupied"; }).length;
      header.innerHTML =
        '<span class="lsh-title">' + safeText(GROUP_LABELS[key] || key) + '</span>' +
        '<span class="lsh-badges">' +
          '<span class="lsh-badge lsh-badge--green">' + avail + ' free</span>' +
          (occup > 0 ? '<span class="lsh-badge lsh-badge--red">' + occup + ' in use</span>' : '') +
        '</span>';

      var grid = document.createElement("div");
      grid.className = "locker-grid";

      groups[key].forEach(function(locker) {
        grid.appendChild(makeTile(locker, clickable));
      });

      section.appendChild(header);
      section.appendChild(grid);
      wrap.appendChild(section);
    });
  }

  // Legacy shim used by dashboard (non-grouped, non-clickable)
  function renderLockerGrid(container, lockers, clickable) {
    if (!container) return;
    container.innerHTML = "";
    if (!Array.isArray(lockers) || lockers.length === 0) {
      container.innerHTML = '<p style="color:var(--text-3);font-size:13px;padding:8px 0;">No lockers.</p>';
      return;
    }
    lockers.forEach(function(locker) {
      container.appendChild(makeTile(locker, clickable));
    });
  }

  /* ─────────────────────────────────────────────────────────────
     ACTIVITY FEED RENDERING  (matches reference: icon, name, time, badge)
  ───────────────────────────────────────────────────────────── */

  var ACT_ICON = {
    deposit:               "📦",
    retrieve:              "📤",
    registration:          "👤",
    maintenance_started:   "🔧",
    maintenance_completed: "✅",
    status_changed:        "🔄",
    session_timeout:       "⏱",
    admin_manual_unlock:   "🔓",
  };

  var ACT_LABEL = {
    deposit:               "Bag Stored",
    retrieve:              "Bag Retrieved",
    registration:          "Registration",
    maintenance_started:   "Maintenance Started",
    maintenance_completed: "Maintenance Completed",
    status_changed:        "Status Changed",
    session_timeout:       "Session Timeout",
    admin_manual_unlock:   "Admin Unlock",
  };

  var ACT_TONE = {
    deposit:               "dot-green",
    retrieve:              "dot-red",
    registration:          "dot-gray",
    maintenance_started:   "dot-gray",
    maintenance_completed: "dot-green",
    status_changed:        "dot-gray",
    session_timeout:       "dot-gray",
    admin_manual_unlock:   "dot-red",
  };

  // Cache of recent-activity rows by id so the global evidence modal
  // can look up the row when the user clicks "View".
  var activityRowsById = new Map();

  function getActivityEvidenceMeta(item) {
    if (!item || item.id == null) return null;
    var details = parseDetailsObject(item.details);
    var photo = item.evidence_photo || details.evidence_photo || "";
    var url = normalizeEvidenceUrl(
      item.evidence_photo_url || details.evidence_photo_url || "",
      photo
    );
    if (!url) return null;
    var filename = photo
      || (url.split("/").pop() || "")
      || "Evidence photo";
    return {
      id: String(item.id),
      activity: ACT_LABEL[item.activity_type] || item.activity_type || "Activity",
      locker: item.locker_label || "-",
      timestamp: item.timestamp || "",
      filename: filename,
      url: url,
    };
  }

  function renderRecentActivity(activities) {
    var container = document.getElementById("recentActivityList");
    if (!container) return;

    activityRowsById.clear();

    if (!Array.isArray(activities) || activities.length === 0) {
      container.innerHTML = '<div class="activity-empty">No recent activity yet.</div>';
      return;
    }

    container.innerHTML = activities.map(function(item) {
      activityRowsById.set(String(item.id), item);

      var type    = item.activity_type || "";
      var icon    = ACT_ICON[type]  || "•";
      var tone    = ACT_TONE[type]  || "dot-gray";
      var label   = ACT_LABEL[type] || type;
      var lockerL = (item.locker_label && item.locker_label !== "-")
        ? item.locker_label
        : (type === "registration" ? "New User" : "System");
      var rawTs = item.timestamp || "";
      var d = parseApiTimestamp(rawTs);
      var titleStr = d
        ? d.toLocaleString("en-US", { timeZone: PHT_TZ, hour12: true })
        : (rawTs || "");
      var timeStr = fmtRelativeTime(rawTs);

      var hasEvidence = Boolean(getActivityEvidenceMeta(item));
      var rightCol = hasEvidence
        ? '<button class="activity-evidence-btn" type="button" '
            + 'data-activity-evidence="' + safeText(String(item.id)) + '" '
            + 'title="View transaction photo">'
            + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            +   'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
            +   '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
            +   '<circle cx="12" cy="12" r="3"/>'
            + '</svg> View'
          + '</button>'
        : '<span class="activity-evidence-placeholder">' + safeText(lockerL) + '</span>';

      return '<div class="activity-row' + (hasEvidence ? ' has-evidence' : '') + '" '
          + 'data-activity-id="' + safeText(String(item.id)) + '">'
        + '<div class="activity-dot-icon ' + tone + '">' + icon + '</div>'
        + '<div>'
          + '<div class="activity-info-name">' + safeText(label) + '</div>'
          + '<div class="activity-info-time">'
            + '<span class="activity-info-time-rel" '
            +   'data-activity-time="' + safeText(rawTs) + '" '
            +   'title="' + safeText(titleStr) + '">'
            +   safeText(timeStr)
            + '</span>'
            + ' · ' + safeText(lockerL)
          + '</div>'
        + '</div>'
        + rightCol
      + '</div>';
    }).join("");
  }

  // Re-render visible activity timestamps once a minute so "5m ago"
  // rolls forward without waiting for a full data refresh. Cheap: text-only.
  function tickActivityTimes() {
    var nodes = document.querySelectorAll(".activity-info-time-rel[data-activity-time]");
    if (!nodes.length) return;
    nodes.forEach(function(n) {
      var raw = n.getAttribute("data-activity-time");
      if (!raw) return;
      var next = fmtRelativeTime(raw);
      if (n.textContent !== next) n.textContent = next;
    });
  }

  /* ─────────────────────────────────────────────────────────────
     SHARED EVIDENCE MODAL OPENER
     Used by the dashboard activity feed AND the logs page.
  ───────────────────────────────────────────────────────────── */

  function openEvidenceModalFromMeta(meta) {
    if (!meta) return;

    var $ = function(id) { return document.getElementById(id); };
    var imgEl   = $("logEvidenceImage");
    var emptyEl = $("logEvidenceEmpty");

    if (meta.url) {
      if (imgEl) {
        imgEl.src = meta.url;
        imgEl.alt = meta.activity + " evidence photo";
        imgEl.hidden = false;
      }
      if (emptyEl) emptyEl.hidden = true;
    } else {
      if (imgEl) imgEl.hidden = true;
      if (emptyEl) emptyEl.hidden = false;
    }

    if ($("logEvidenceActivity"))  $("logEvidenceActivity").textContent  = meta.activity;
    if ($("logEvidenceLocker"))    $("logEvidenceLocker").textContent    = meta.locker;
    if ($("logEvidenceTimestamp")) $("logEvidenceTimestamp").textContent = fmtDateTime(meta.timestamp);
    if ($("logEvidenceFilename"))  $("logEvidenceFilename").textContent  = meta.filename;
    if ($("logEvidenceModalSub"))  $("logEvidenceModalSub").textContent  =
      meta.activity + " photo for " + meta.locker + ".";

    var modalEl = document.getElementById("logEvidenceModal");
    if (modalEl && window.bootstrap && window.bootstrap.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  }

  function openEvidenceFromActivityId(id) {
    var item = activityRowsById.get(String(id));
    var meta = getActivityEvidenceMeta(item);
    if (meta) openEvidenceModalFromMeta(meta);
  }

  /* ─────────────────────────────────────────────────────────────
     STATUS PILLS
  ───────────────────────────────────────────────────────────── */

  function statusPill(status) {
    var cls = {
      available:   "spill--available",
      occupied:    "spill--occupied",
      maintenance: "spill--maintenance",
      success:     "spill--success",
      warning:     "spill--warning",
      error:       "spill--error",
    }[String(status||"").toLowerCase()] || "spill--maintenance";
    return '<span class="spill ' + cls + '">' + safeText(status || "unknown") + '</span>';
  }

  /* ─────────────────────────────────────────────────────────────
     ACTIVITY TABLE HELPERS
  ───────────────────────────────────────────────────────────── */

  function activityLabel(type) { return ACT_LABEL[type] || type || "Unknown"; }

  function activityIcon(type) {
    var m = { deposit:"UP", retrieve:"DN", registration:"USR",
              maintenance_started:"MNT", maintenance_completed:"OK", status_changed:"CHG" };
    return m[type] || "•";
  }

  function activityTone(type) {
    if (type === "retrieve") return "red";
    if (["registration","maintenance_started","status_changed","session_timeout"].includes(type)) return "gray";
    return "green";
  }

  function getLogEvidenceMeta(row) {
    if (!row || row.id == null) return null;

    var details = parseDetailsObject(row.details);
    var evidencePhoto = row.evidence_photo || details.evidence_photo || "";
    var evidenceUrl = normalizeEvidenceUrl(
      row.evidence_photo_url || details.evidence_photo_url || "",
      evidencePhoto
    );

    if (!evidenceUrl) return null;

    var filename = evidencePhoto
      || (evidenceUrl.split("/").pop() || "")
      || "Evidence photo";

    return {
      id: String(row.id),
      activity: activityLabel(row.activity_type),
      locker: row.locker_label || "-",
      timestamp: row.time_date || "",
      filename: filename,
      url: evidenceUrl,
    };
  }

  function renderLogEvidenceAction(row) {
    var evidence = getLogEvidenceMeta(row);
    if (!evidence) {
      return '<span class="logs-no-evidence">No image</span>';
    }
    return '<button type="button" class="btn-ghost-sm btn-view-log" data-log-view="' + safeText(evidence.id) + '">View</button>';
  }

  /* ─────────────────────────────────────────────────────────────
     SYSTEM STATUS BADGE
  ───────────────────────────────────────────────────────────── */

  async function updateSystemStatusBadge() {
    var badge = document.getElementById("systemStatusBadge");
    if (!badge) return;
    try {
      var s = await fetchAdminJson("/api/admin/summary");
      badge.textContent = s.system_status || "Online";
    } catch(e) {
      badge.textContent = "Offline";
    }
  }

  /* ─────────────────────────────────────────────────────────────
     DASHBOARD PAGE
  ───────────────────────────────────────────────────────────── */

  var dashTimer = null;

  async function initDashboardPage() {
    // Wire up the recent-activity feed: clicking the "View" button (or
    // anywhere on a row that has evidence) opens the global evidence modal.
    var feed = document.getElementById("recentActivityList");
    if (feed) {
      feed.addEventListener("click", function(e) {
        var btn = e.target.closest("[data-activity-evidence]");
        if (btn) {
          e.preventDefault();
          openEvidenceFromActivityId(btn.getAttribute("data-activity-evidence"));
          return;
        }
        var row = e.target.closest(".activity-row.has-evidence");
        if (row) openEvidenceFromActivityId(row.getAttribute("data-activity-id"));
      });
    }

    await refreshDashboard();
    dashTimer = setInterval(refreshDashboard, 4000);

    // Re-tick relative timestamps once a minute. Granularity in
    // fmtRelativeTime is also minute-level so this matches.
    var timeTicker = setInterval(tickActivityTimes, 60000);

    window.addEventListener("beforeunload", function() {
      clearInterval(dashTimer);
      clearInterval(timeTicker);
    });
  }

  async function refreshDashboard() {
    // Use allSettled so one failing endpoint doesn't blank the whole dashboard.
    var results = await Promise.allSettled([
      fetchAdminJson("/api/admin/summary"),
      fetchAdminJson("/api/admin/lockers"),
      fetchAdminJson("/api/admin/activity?limit=6"),
    ]);

    var summary      = results[0].status === "fulfilled" ? results[0].value : null;
    var lockersData  = results[1].status === "fulfilled" ? results[1].value : null;
    var activityData = results[2].status === "fulfilled" ? results[2].value : null;

    if (summary) {
      var set = function(id, v) { var el = document.getElementById(id); if (el) el.textContent = String(v||0); };
      set("statTotal",       summary.total);
      set("statAvailable",   summary.available);
      set("statOccupied",    summary.occupied);
      set("statMaintenance", summary.maintenance);

      var badge = document.getElementById("systemStatusBadge");
      if (badge) badge.textContent = summary.system_status || "Online";
    } else {
      console.error("Dashboard summary failed:", results[0].reason);
    }

    if (lockersData) {
      renderLockerGrid(
        document.getElementById("statusOverviewGrid"),
        lockersData.lockers || [],
        false
      );
    } else {
      console.error("Dashboard lockers failed:", results[1].reason);
    }

    if (activityData) {
      renderRecentActivity(activityData.activities || []);
    } else {
      console.error("Dashboard activity failed:", results[2].reason);
    }
  }

  /* ─────────────────────────────────────────────────────────────
     LOCKERS PAGE
  ───────────────────────────────────────────────────────────── */

  var lockersCache     = [];
  var selectedLockerId = null;
  var lockerModal      = null;
  var lockersAutoTimer = null;

  async function initLockersPage() {
    var sectionsWrap = document.getElementById("lockerSectionsWrap");
    var modalEl      = document.getElementById("lockerActionModal");
    var refreshBtn   = document.getElementById("lockerRefreshBtn");

    if (!sectionsWrap || !modalEl) return;

    if (window.bootstrap && window.bootstrap.Modal) {
      lockerModal = new window.bootstrap.Modal(modalEl);
    }

    sectionsWrap.addEventListener("click", function(e) {
      var tile = e.target.closest("[data-locker-id]");
      if (tile) openLockerModal(Number(tile.dataset.lockerId));
    });

    modalEl.addEventListener("click", function(e) {
      var action = e.target.getAttribute("data-locker-action");
      if (action) handleLockerAction(action);
    });

    if (refreshBtn) {
      refreshBtn.addEventListener("click", function() {
        var icon = document.getElementById("refreshIcon");
        if (icon) icon.classList.add("spin");
        window.refreshLockersGrid().finally(function() {
          setTimeout(function() {
            if (icon) icon.classList.remove("spin");
          }, 500);
        });
      });
    }

    await window.refreshLockersGrid();

    // Auto-refresh every 8 seconds
    lockersAutoTimer = setInterval(window.refreshLockersGrid, 8000);
    window.addEventListener("beforeunload", function() { clearInterval(lockersAutoTimer); });
  }

  window.refreshLockersGrid = async function() {
    var loading     = document.getElementById("lockerGridLoading");
    var errorWrap   = document.getElementById("lockerGridError");
    var sectionsWrap = document.getElementById("lockerSectionsWrap");

    // Show loading only on first load (when sections are hidden)
    if (sectionsWrap && sectionsWrap.hidden && loading) loading.hidden = false;
    if (errorWrap) errorWrap.hidden = true;

    try {
      var data = await fetchAdminJson("/api/admin/lockers");
      lockersCache = Array.isArray(data.lockers) ? data.lockers : [];

      // Update stats bar
      var counts = { total: lockersCache.length, available: 0, occupied: 0, maintenance: 0 };
      lockersCache.forEach(function(l) { if (counts[l.status] !== undefined) counts[l.status]++; });
      var sb = function(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; };
      sb("lsbTotal",       counts.total);
      sb("lsbAvailable",   counts.available);
      sb("lsbOccupied",    counts.occupied);
      sb("lsbMaintenance", counts.maintenance);

      // Render grouped sections
      if (sectionsWrap) {
        renderLockerSections(sectionsWrap, lockersCache, true);
        sectionsWrap.hidden = false;
      }
      if (loading) loading.hidden = true;

    } catch(e) {
      console.error("Locker grid refresh failed:", e);
      if (loading) loading.hidden = true;
      if (sectionsWrap) sectionsWrap.hidden = true;
      if (errorWrap) {
        var msgEl = document.getElementById("lockerGridErrorMsg");
        if (msgEl) msgEl.textContent = e.message || "Failed to load locker data.";
        errorWrap.hidden = false;
      }
    }
  };

  function openLockerModal(id) {
    selectedLockerId = id;
    var locker = lockersCache.find(function(l) { return Number(l.id) === id; });
    if (!locker) return;

    var $  = function(eid) { return document.getElementById(eid); };
    var fb = $("lockerActionFeedback");
    if (fb) { fb.textContent = ""; fb.style.color = ""; }

    // Header
    var sub = $("modalLockerSub");
    if (sub) sub.textContent = "Section: " + sectionLabelForLocker(locker);

    // Status banner
    var bannerIcons = { available: "🟢", occupied: "🔴", maintenance: "🟡" };
    var bannerCls   = { available: "banner--available", occupied: "banner--occupied", maintenance: "banner--maintenance" };
    var banner      = $("modalStatusBanner");
    if (banner) {
      banner.className = "modal-status-banner " + (bannerCls[locker.status] || "");
      var si = $("modalStatusIcon"); if (si) si.textContent = bannerIcons[locker.status] || "◆";
      var st = $("modalStatusText"); if (st) st.textContent = TILE_STATUS[locker.status] || locker.status;
    }

    // Info rows
    var num = $("modalLockerNumber"); if (num) num.textContent = locker.locker_number || locker.id;
    var grp = $("modalLockerGroup");  if (grp) grp.textContent = sectionLabelForLocker(locker);
    var upd = $("modalLockerUpdatedAt"); if (upd) upd.textContent = fmtDateTime(locker.updated_at);

    // Occupant panel
    var oPanel = $("modalOccupantPanel");
    if (oPanel) {
      if (locker.current_user_id && locker.status === "occupied") {
        // Fetch detail for occupant info
        fetchAdminJson("/api/admin/lockers/" + id).then(function(det) {
          var oc = det.locker && det.locker.occupant;
          if (oc) {
            var n = $("modalOccupantName"); if (n) n.textContent = oc.full_name || "—";
            var s = $("modalOccupantSid");  if (s) s.textContent = oc.student_id || "—";
            var r = $("modalOccupantRfid"); if (r) r.textContent = oc.rfid_uid || "—";
            oPanel.hidden = false;
          }
        }).catch(function(){});
      } else {
        oPanel.hidden = true;
      }
    }

    showLockerModal();
  }

  function showLockerModal() {
    var el = document.getElementById("lockerActionModal");
    if (!el) return;
    if (lockerModal) { lockerModal.show(); return; }
    el.style.display = "block"; el.classList.add("show");
    document.body.classList.add("modal-open");
    if (!document.querySelector(".modal-backdrop")) {
      var bd = document.createElement("div");
      bd.className = "modal-backdrop fade show";
      bd.addEventListener("click", hideLockerModal);
      document.body.appendChild(bd);
    }
  }

  function hideLockerModal() {
    var el = document.getElementById("lockerActionModal");
    if (!el) return;
    if (lockerModal) { lockerModal.hide(); return; }
    el.classList.remove("show"); el.style.display = "none";
    document.body.classList.remove("modal-open");
    var bd = document.querySelector(".modal-backdrop");
    if (bd) bd.remove();
  }

  function setModalFeedback(msg, isErr) {
    var el = document.getElementById("lockerActionFeedback");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "var(--red)" : "var(--accent)";
  }

  async function handleLockerAction(action) {
    if (!selectedLockerId) return;
    try {
      if (action === "set-available") {
        await fetchAdminJson("/api/admin/lockers/" + selectedLockerId, {
          method: "PATCH", body: JSON.stringify({ status: "available" }),
        });
        setModalFeedback("✓ Locker set to Available.", false);
      } else if (action === "set-maintenance") {
        await fetchAdminJson("/api/admin/lockers/" + selectedLockerId, {
          method: "PATCH", body: JSON.stringify({ status: "maintenance" }),
        });
        setModalFeedback("✓ Locker set to Maintenance.", false);
      } else if (action === "force-unlock") {
        var reason = window.prompt("Enter reason (maintenance / stuck / manual_request / test / emergency):");
        if (!reason) return;
        await fetchAdminJson("/api/admin/lockers/" + selectedLockerId + "/force-unlock", {
          method: "POST",
          body: JSON.stringify({ reason: reason.trim().toLowerCase() }),
          headers: { "X-Admin-Token": getAdminToken() },
        });
        setModalFeedback("✓ Force unlock sent.", false);
      }
      await window.refreshLockersGrid();
      openLockerModal(selectedLockerId);
    } catch(e) {
      setModalFeedback(e.message || "Action failed.", true);
    }
  }

  /* ─────────────────────────────────────────────────────────────
     LOGS PAGE
  ───────────────────────────────────────────────────────────── */

  var logsDataTable = null;
  var logRowsById = new Map();
  var logEvidenceModal = null;

  function initLogsPage() {
    var applyBtn  = document.getElementById("applyLogFilters");
    var clearBtn  = document.getElementById("clearLogFilters");
    var searchInp = document.getElementById("filterSearch");
    var tableEl   = document.getElementById("activityLogsTable");
    var modalEl   = document.getElementById("logEvidenceModal");

    if (applyBtn)  applyBtn.addEventListener("click", reloadLogsTable);
    if (clearBtn)  clearBtn.addEventListener("click", function() { resetFilters(); reloadLogsTable(); });
    if (searchInp) searchInp.addEventListener("keydown", function(e) { if (e.key==="Enter") reloadLogsTable(); });
    if (modalEl && window.bootstrap && window.bootstrap.Modal) {
      logEvidenceModal = new window.bootstrap.Modal(modalEl);
    }
    if (tableEl) {
      tableEl.addEventListener("click", function(e) {
        var viewBtn = e.target.closest("[data-log-view]");
        if (!viewBtn) return;
        openLogEvidenceModal(viewBtn.getAttribute("data-log-view"));
      });
    }

    if (window.jQuery && window.jQuery.fn && window.jQuery.fn.DataTable) {
      initDataTable();
    } else {
      reloadLogsFallback();
    }
  }

  function resetFilters() {
    ["filterStartDate","filterEndDate","filterType","filterSearch"].forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.value = "";
    });
  }

  function collectFilters() {
    var g = function(id) { var el = document.getElementById(id); return el ? el.value : ""; };
    return { start_date: g("filterStartDate"), end_date: g("filterEndDate"), type: g("filterType"), search: g("filterSearch").trim() };
  }

  function initDataTable() {
    var tbl = window.jQuery("#activityLogsTable");
    logsDataTable = tbl.DataTable({
      processing: true, serverSide: true, searching: false,
      lengthChange: false,                    // hide "Show N entries" dropdown
      pageLength: 15, order: [[0,"desc"]],
      dom: 'rtip',                            // remove length menu (l) + filter (f)
      ajax: {
        url: withToken("/api/admin/logs"), type: "GET",
        data: function(d) { var f = collectFilters(); d.start_date=f.start_date; d.end_date=f.end_date; d.type=f.type; d.search=f.search; },
      },
      columns: [
        { data:"time_date", render: function(v) { return safeText(fmtDateTime(v)); } },
        { data:"activity_type", render: function(v) {
            return '<div class="act-cell">'
              + '<div class="act-icon ' + (activityTone(v)==="green"?"dot-green":activityTone(v)==="red"?"dot-red":"dot-gray") + '">'
              + (ACT_ICON[v]||"•") + '</div>'
              + safeText(activityLabel(v)) + '</div>';
          }
        },
        { data:"locker_label", render: function(v) { return safeText(v||"-"); } },
        { data:"status", render: function(v) { return statusPill(v); } },
        { data:null, orderable:false, searchable:false, render: function(v, type, row) {
            logRowsById.set(String(row.id), row);
            return renderLogEvidenceAction(row);
          }
        },
      ],
      createdRow: function(row, data) {
        var t = activityTone(data.activity_type);
        if (t === "green" || t === "red") {
          row.classList.add("row--" + t);
        }
      },
      language: { emptyTable: "No activity logs found.", },
    });
  }

  function openLogEvidenceModal(logId) {
    var row = logRowsById.get(String(logId));
    var evidence = getLogEvidenceMeta(row);
    if (!evidence) return;
    openEvidenceModalFromMeta(evidence);
    return;

    // (Inline fallback below kept dead-coded for reference; the shared
    //  opener already handles all rendering.)
    var imageEl = document.getElementById("logEvidenceImage");
    var activityEl = document.getElementById("logEvidenceActivity");
    var lockerEl = document.getElementById("logEvidenceLocker");
    var timestampEl = document.getElementById("logEvidenceTimestamp");
    var filenameEl = document.getElementById("logEvidenceFilename");
    var subEl = document.getElementById("logEvidenceModalSub");

    if (imageEl) {
      imageEl.src = evidence.url;
      imageEl.alt = evidence.activity + " evidence photo";
    }
    if (activityEl) activityEl.textContent = evidence.activity;
    if (lockerEl) lockerEl.textContent = evidence.locker;
    if (timestampEl) timestampEl.textContent = fmtDateTime(evidence.timestamp);
    if (filenameEl) filenameEl.textContent = evidence.filename;
    if (subEl) subEl.textContent = evidence.activity + " image for " + evidence.locker + ".";

    if (logEvidenceModal) {
      logEvidenceModal.show();
    }
  }

  function reloadLogsTable() {
    if (logsDataTable) { logsDataTable.ajax.reload(); return; }
    reloadLogsFallback();
  }

  async function reloadLogsFallback() {
    var tbody = document.getElementById("logsFallbackBody");
    if (!tbody) return;
    var f = collectFilters();
    var params = new URLSearchParams({ draw:"1",start:"0",length:"200" });
    if (f.start_date) params.set("start_date", f.start_date);
    if (f.end_date)   params.set("end_date",   f.end_date);
    if (f.type)       params.set("type",        f.type);
    if (f.search)     params.set("search",      f.search);
    try {
      var data = await fetchAdminJson("/api/admin/logs?" + params.toString());
      var rows = Array.isArray(data.data) ? data.data : [];
      logRowsById.clear();
      if (rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:40px;">No activity logs found.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function(r) {
        logRowsById.set(String(r.id), r);
        var t = activityTone(r.activity_type);
        var rowCls = t==="green"?"row--green":t==="red"?"row--red":"";
        return '<tr class="' + rowCls + '">'
          + '<td style="color:var(--text-3);">' + safeText(fmtDateTime(r.time_date)) + '</td>'
          + '<td><div class="act-cell"><div class="act-icon ' + (t==="green"?"dot-green":t==="red"?"dot-red":"dot-gray") + '">'
              + (ACT_ICON[r.activity_type]||"•") + '</div>' + safeText(activityLabel(r.activity_type)) + '</div></td>'
          + '<td style="font-family:var(--mono);font-size:12px;">' + safeText(r.locker_label||"-") + '</td>'
          + '<td>' + statusPill(r.status) + '</td>'
          + '<td>' + renderLogEvidenceAction(r) + '</td>'
          + '</tr>';
      }).join("");
    } catch(e) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--red);padding:40px;">Failed to load logs.</td></tr>';
    }
  }

  /* ─────────────────────────────────────────────────────────────
     INIT
  ───────────────────────────────────────────────────────────── */

  document.addEventListener("DOMContentLoaded", function() {
    var page = document.body.dataset.page || "";

    if (page === "dashboard") {
      initDashboardPage();
      return;
    }

    updateSystemStatusBadge();

    if (page === "lockers") { initLockersPage(); return; }
    if (page === "logs")    { initLogsPage();    return; }
    // users page is self-contained via inline <script>
  });

})();
