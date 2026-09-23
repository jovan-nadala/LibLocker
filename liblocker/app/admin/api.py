"""Admin dashboard JSON API endpoints."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from app.auth import admin_required
from app.db import get_db

admin_api_bp = Blueprint("admin_api", __name__)

LOCKER_STATUSES = {"available", "occupied", "maintenance"}
LOG_STATUSES    = {"success", "warning", "error"}
DATE_RE         = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_UNLOCK_REASONS = {"maintenance", "stuck", "manual_request", "test", "emergency"}
MAX_LOCKER_COUNT = 24


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _active_locker_count() -> int:
    configured = current_app.config.get("ACTIVE_LOCKER_COUNT", MAX_LOCKER_COUNT)
    return max(1, min(_to_int(configured, MAX_LOCKER_COUNT), MAX_LOCKER_COUNT))


def _json_response(payload: dict[str, Any], status_code: int = 200):
    return jsonify(payload), status_code


def _parse_details_object(details: Any) -> dict[str, Any]:
    """Return activity details as a dict when the payload contains JSON."""
    if isinstance(details, dict):
        return details
    if not isinstance(details, str) or not details.strip():
        return {}
    try:
        parsed = json.loads(details)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _log_activity(
    db,
    activity_type: str,
    locker_id: int | None = None,
    user_id:   int | None = None,
    details:   str | dict[str, Any] | None = None,
    status:    str = "success",
) -> None:
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=True)
    safe_status = status if status in LOG_STATUSES else "success"
    db.execute(
        """
        INSERT INTO activity_logs(timestamp, activity_type, locker_id, user_id, details, status)
        VALUES (datetime('now'), ?, ?, ?, ?, ?)
        """,
        (activity_type, locker_id, user_id, details, safe_status),
    )


def _locker_payload(row) -> dict[str, Any]:
    locker_id = int(row["id"])
    return {
        "id":                 locker_id,
        "label":              row["label"] or str(locker_id),
        "level":              row["level"],
        "status":             row["status"],
        "locker_number":      row["locker_number"] if row["locker_number"] is not None else locker_id,
        "locker_group":       row["locker_group"] or "upper1",
        "updated_at":         row["updated_at"],
        "current_user_id":    row["current_user_id"],
        "current_session_id": row["current_session_id"],
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@admin_api_bp.get("/summary")
@admin_required
def summary():
    db = get_db()
    active_count = _active_locker_count()
    row = db.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='available'    THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN status='occupied'     THEN 1 ELSE 0 END) AS occupied,
            SUM(CASE WHEN status='maintenance'  THEN 1 ELSE 0 END) AS maintenance
        FROM lockers
        WHERE COALESCE(locker_number, id) BETWEEN 1 AND ?
        """
        ,
        (active_count,),
    ).fetchone()
    return _json_response({
        "total":         int(row["total"]        or 0),
        "available":     int(row["available"]    or 0),
        "occupied":      int(row["occupied"]     or 0),
        "maintenance":   int(row["maintenance"]  or 0),
        "system_status": "Online",
    })


# ---------------------------------------------------------------------------
# Locker list
# ---------------------------------------------------------------------------

@admin_api_bp.get("/lockers")
@admin_required
def list_lockers():
    db = get_db()
    active_count = _active_locker_count()
    rows = db.execute(
        """
        SELECT id, label, level, status, updated_at,
               locker_number, locker_group,
               current_user_id, current_session_id
        FROM   lockers
        WHERE  COALESCE(locker_number, id) BETWEEN 1 AND ?
        ORDER  BY COALESCE(locker_number, id) ASC
        """,
        (active_count,),
    ).fetchall()
    return _json_response({"lockers": [_locker_payload(r) for r in rows]})


# ---------------------------------------------------------------------------
# Locker detail (for modal)
# ---------------------------------------------------------------------------

@admin_api_bp.get("/lockers/<int:locker_id>")
@admin_required
def locker_detail(locker_id: int):
    db = get_db()
    row = db.execute(
        """
        SELECT l.id, l.label, l.level, l.status, l.updated_at,
               l.current_user_id, l.current_session_id,
               l.locker_number, l.locker_group, l.last_opened_at,
               u.full_name, u.student_id, u.rfid_uid
        FROM   lockers l
        LEFT JOIN users u ON l.current_user_id = u.id
        WHERE  l.id = ?
        """,
        (locker_id,),
    ).fetchone()
    if not row:
        return _json_response({"error": "Locker not found."}, 404)

    payload = _locker_payload(row)
    payload.update({
        "locker_number": row["locker_number"],
        "locker_group":  row["locker_group"],
        "last_opened_at": row["last_opened_at"],
        "occupant": {
            "full_name":  row["full_name"],
            "student_id": row["student_id"],
            "rfid_uid":   row["rfid_uid"],
        } if row["current_user_id"] else None,
    })
    return _json_response({"locker": payload})


# ---------------------------------------------------------------------------
# Patch locker status
# ---------------------------------------------------------------------------

@admin_api_bp.patch("/lockers/<int:locker_id>")
@admin_required
def patch_locker(locker_id: int):
    payload     = request.get_json(silent=True) or {}
    next_status = str(payload.get("status", "")).strip().lower()

    if next_status not in LOCKER_STATUSES:
        return _json_response(
            {"error": "Invalid status. Allowed: available, occupied, maintenance."}, 400
        )

    db = get_db()
    current = db.execute(
        "SELECT id, label, status, current_user_id, current_session_id FROM lockers WHERE id = ?",
        (locker_id,),
    ).fetchone()
    if not current:
        return _json_response({"error": "Locker not found."}, 404)

    prev_status      = str(current["status"])
    occupied_flag    = 1 if next_status == "occupied" else 0
    clear_assignment = next_status in {"available", "maintenance"}

    if prev_status != "maintenance" and next_status == "maintenance":
        act = "maintenance_started"
    elif prev_status == "maintenance" and next_status == "available":
        act = "maintenance_completed"
    else:
        act = "status_changed"

    try:
        db.execute(
            """
            UPDATE lockers
            SET    status             = ?,
                   is_occupied        = ?,
                   updated_at         = datetime('now'),
                   current_user_id   = CASE WHEN ? THEN NULL ELSE current_user_id   END,
                   current_session_id = CASE WHEN ? THEN NULL ELSE current_session_id END
            WHERE  id = ?
            """,
            (next_status, occupied_flag,
             int(clear_assignment), int(clear_assignment),
             locker_id),
        )
        _log_activity(db, activity_type=act, locker_id=locker_id,
                      details={"from": prev_status, "to": next_status, "source": "admin_dashboard"},
                      status="success")
        db.commit()
    except Exception:
        db.rollback()
        raise

    updated = db.execute(
        "SELECT id, label, level, status, updated_at, current_user_id, current_session_id FROM lockers WHERE id = ?",
        (locker_id,),
    ).fetchone()
    return _json_response({"ok": True, "locker": _locker_payload(updated)})


# ---------------------------------------------------------------------------
# Force unlock  (production-ready with auth + reason)
# ---------------------------------------------------------------------------

@admin_api_bp.post("/lockers/<int:locker_id>/force-unlock")
@admin_required
def force_unlock_locker(locker_id: int):
    """Physically unlock a locker and update database.

    Requires admin authentication.
    Accepts JSON body: {"reason": "maintenance|stuck|manual_request|test|emergency"}
    """
    data   = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip().lower()

    if not reason:
        return _json_response(
            {"error": f"'reason' is required. Valid values: {', '.join(sorted(VALID_UNLOCK_REASONS))}"},
            400,
        )
    if reason not in VALID_UNLOCK_REASONS:
        return _json_response(
            {"error": f"Invalid reason. Valid values: {', '.join(sorted(VALID_UNLOCK_REASONS))}"},
            400,
        )

    db = get_db()
    locker = db.execute(
        "SELECT id, label, locker_number, status FROM lockers WHERE id = ?", (locker_id,)
    ).fetchone()
    if not locker:
        return _json_response({"error": "Locker not found."}, 404)

    locker_number = int(locker["locker_number"])
    gpio_success = False
    hold_open_seconds = float(current_app.config.get("GPIO_RETRIEVE_OPEN_SECONDS", 10))

    # Attempt physical unlock
    try:
        from app.hardware import get_hardware
        hw = get_hardware()
        gpio_success = bool(
            hw.gpio.open_locker_window(
                locker_number,
                hold_open_seconds=hold_open_seconds,
            )
        )
    except Exception as exc:
        current_app.logger.error("Force-unlock GPIO error locker=%d: %s", locker_number, exc)
        gpio_success = False

    # Release in database regardless of GPIO result (operator is taking over)
    try:
        db.execute(
            """
            UPDATE lockers
            SET    status             = 'available',
                   is_occupied        = 0,
                   current_user_id   = NULL,
                   current_session_id = NULL,
                   current_rfid_uid  = NULL,
                   updated_at        = datetime('now'),
                   last_opened_at    = datetime('now')
            WHERE  id = ?
            """,
            (locker_id,),
        )
        _log_activity(db, "admin_manual_unlock", locker_id=locker_id,
                      details={
                          "locker_number": locker_number,
                          "reason":        reason,
                          "gpio_success":  gpio_success,
                          "admin_ip":      request.remote_addr,
                          "prev_status":   locker["status"],
                      },
                      status="warning" if not gpio_success else "success")
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _json_response({
        "ok":           True,
        "gpio_success": gpio_success,
        "message":      "Locker released" + (" (GPIO failed – manual check required)" if not gpio_success else ""),
    })


# ---------------------------------------------------------------------------
# Feature #6 – Real-time locker status stream (Server-Sent Events)
# ---------------------------------------------------------------------------

@admin_api_bp.get("/lockers/stream")
@admin_required
def stream_lockers():
    """Server-Sent Events endpoint: push locker status every 2 seconds.

    Connect from the browser with:
        const es = new EventSource('/api/admin/lockers/stream');
        es.onmessage = e => updateGrid(JSON.parse(e.data));
    """
    def generate():
        active_count = _active_locker_count()
        while True:
            try:
                db = get_db()
                rows = db.execute(
                    """
                    SELECT id, locker_number, status, is_occupied,
                           current_user_id, label, updated_at
                    FROM   lockers
                    WHERE  COALESCE(locker_number, id) BETWEEN 1 AND ?
                    ORDER  BY COALESCE(locker_number, id) ASC
                    """
                    ,
                    (active_count,),
                ).fetchall()
                payload = json.dumps([dict(r) for r in rows], ensure_ascii=True)
                yield f"data: {payload}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            time.sleep(2)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------

@admin_api_bp.get("/activity")
@admin_required
def recent_activity():
    limit = max(1, min(_to_int(request.args.get("limit"), 6), 50))
    db    = get_db()
    rows  = db.execute(
        """
        SELECT al.id, al.timestamp, al.activity_type,
               al.locker_id, al.user_id, al.details, al.status,
               COALESCE(l.label, CAST(al.locker_id AS TEXT)) AS locker_label
        FROM   activity_logs AS al
        LEFT JOIN lockers AS l ON l.id = al.locker_id
        ORDER  BY al.timestamp DESC, al.id DESC
        LIMIT  ?
        """,
        (limit,),
    ).fetchall()
    activities = []
    for r in rows:
        details_value = r["details"] or ""
        details_json = _parse_details_object(details_value)
        activities.append({
            "id":                  int(r["id"]),
            "timestamp":           r["timestamp"],
            "activity_type":       r["activity_type"],
            "locker_id":           r["locker_id"],
            "locker_label":        r["locker_label"] if r["locker_id"] else "-",
            "status":              r["status"],
            "details":             details_value,
            "evidence_photo":      details_json.get("evidence_photo"),
            "evidence_photo_url":  details_json.get("evidence_photo_url"),
            "evidence_photo_path": details_json.get("evidence_photo_path"),
        })
    return _json_response({"activities": activities})


# ---------------------------------------------------------------------------
# Logs DataTable endpoint
# ---------------------------------------------------------------------------

@admin_api_bp.get("/logs")
@admin_required
def logs_datatable():
    db = get_db()

    draw       = max(0, _to_int(request.args.get("draw"), 1))
    start      = max(0, _to_int(request.args.get("start"), 0))
    length     = min(max(_to_int(request.args.get("length"), 10), 1), 100)
    start_date = (request.args.get("start_date") or "").strip()
    end_date   = (request.args.get("end_date")   or "").strip()
    type_filter   = (request.args.get("type")    or "").strip().lower()
    search_text   = (request.args.get("search")  or request.args.get("search[value]") or "").strip()

    clauses: list[str] = []
    params:  list[Any] = []

    if DATE_RE.match(start_date):
        clauses.append("strftime('%Y-%m-%d', al.timestamp) >= ?")
        params.append(start_date)
    if DATE_RE.match(end_date):
        clauses.append("strftime('%Y-%m-%d', al.timestamp) <= ?")
        params.append(end_date)
    if type_filter:
        clauses.append("al.activity_type = ?")
        params.append(type_filter)
    if search_text:
        like = f"%{search_text}%"
        clauses.append(
            "(COALESCE(l.label, CAST(al.locker_id AS TEXT)) LIKE ?"
            " OR al.activity_type LIKE ?"
            " OR COALESCE(al.details,'') LIKE ?"
            " OR al.status LIKE ?)"
        )
        params.extend([like, like, like, like])

    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    order_col = (request.args.get("order[0][column]") or "0")
    col_key   = (request.args.get(f"columns[{order_col}][data]") or "time_date")
    dir_      = (request.args.get("order[0][dir]") or "desc").lower()
    order_dir = "ASC" if dir_ == "asc" else "DESC"
    col_map   = {
        "time_date":     "al.timestamp",
        "activity_type": "al.activity_type",
        "locker_label":  "COALESCE(l.label, CAST(al.locker_id AS TEXT))",
        "status":        "al.status",
    }
    order_sql = col_map.get(col_key, "al.timestamp")

    total_row    = db.execute("SELECT COUNT(*) AS c FROM activity_logs").fetchone()
    filtered_row = db.execute(
        f"SELECT COUNT(*) AS c FROM activity_logs AS al LEFT JOIN lockers AS l ON l.id=al.locker_id{where_sql}",
        tuple(params),
    ).fetchone()

    data_rows = db.execute(
        f"""
        SELECT al.id, al.timestamp, al.activity_type, al.locker_id,
               COALESCE(l.label, CAST(al.locker_id AS TEXT)) AS locker_label,
               al.status, COALESCE(al.details,'') AS details
        FROM   activity_logs AS al
        LEFT JOIN lockers AS l ON l.id = al.locker_id
        {where_sql}
        ORDER BY {order_sql} {order_dir}, al.id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [length, start]),
    ).fetchall()

    rows_payload = []
    for r in data_rows:
        details_value = r["details"] or ""
        details_json = _parse_details_object(details_value)
        rows_payload.append(
            {
                "id":            int(r["id"]),
                "time_date":     r["timestamp"],
                "activity_type": r["activity_type"],
                "locker_id":     r["locker_id"] if r["locker_id"] is not None else "-",
                "locker_label":  r["locker_label"] if r["locker_id"] is not None else "-",
                "status":        r["status"],
                "details":       details_value,
                "evidence_photo": details_json.get("evidence_photo"),
                "evidence_photo_url": details_json.get("evidence_photo_url"),
                "evidence_photo_path": details_json.get("evidence_photo_path"),
            }
        )

    return _json_response({
        "draw":            draw,
        "recordsTotal":    int(total_row["c"]    or 0),
        "recordsFiltered": int(filtered_row["c"] or 0),
        "data": rows_payload,
    })


@admin_api_bp.get("/users")
@admin_required
def list_users():
    """Return all registered users with active locker info."""
    db = get_db()
    rows = db.execute(
        """
        SELECT
            u.id,
            u.full_name,
            u.student_id,
            u.rfid_uid,
            u.created_at,
            l.id            AS active_locker_id,
            l.locker_number AS active_locker_number,
            l.label         AS active_locker_label
        FROM users u
        LEFT JOIN lockers l
            ON l.current_user_id = u.id
            AND (l.is_occupied = 1 OR l.status = 'occupied')
        ORDER BY u.created_at DESC
        """
    ).fetchall()

    return _json_response({
        "users": [
            {
                "id":                   int(row["id"]),
                "full_name":            row["full_name"] or "",
                "student_id":           row["student_id"] or "",
                "rfid_uid":             row["rfid_uid"] or "",
                "created_at":           row["created_at"] or "",
                "active_locker_id":     row["active_locker_id"],
                "active_locker_number": row["active_locker_number"],
                "active_locker_label":  row["active_locker_label"],
            }
            for row in rows
        ]
    })


# ---------------------------------------------------------------------------
# Delete user account
# ---------------------------------------------------------------------------

@admin_api_bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id: int):
    """Permanently delete a student account.

    - If the student has a bag currently stored, the locker is force-released
      and the active session is cancelled before deletion.
    - Cascades automatically delete the student's sessions, violations, and
      audit references (per the schema FK rules).
    """
    db = get_db()

    user = db.execute(
        "SELECT id, full_name, student_id, rfid_uid FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user:
        return _json_response({"error": "User not found."}, 404)

    # Check for an active locker assignment
    active_locker = db.execute(
        """
        SELECT id, locker_number, label
        FROM   lockers
        WHERE  current_user_id = ?
          AND  (is_occupied = 1 OR status = 'occupied')
        LIMIT  1
        """,
        (user_id,),
    ).fetchone()

    try:
        if active_locker:
            # Force-release the locker
            db.execute(
                """
                UPDATE lockers
                SET    status             = 'available',
                       is_occupied        = 0,
                       current_user_id   = NULL,
                       current_session_id = NULL,
                       current_rfid_uid  = NULL,
                       updated_at        = datetime('now')
                WHERE  id = ?
                """,
                (active_locker["id"],),
            )
            # Cancel any active sessions for this user
            db.execute(
                """
                UPDATE sessions
                SET    status       = 'canceled',
                       completed_at = datetime('now')
                WHERE  user_id = ? AND status = 'active'
                """,
                (user_id,),
            )

        _log_activity(
            db,
            activity_type="user_deleted",
            details={
                "deleted_user_id":  user_id,
                "student_id":       user["student_id"],
                "full_name":        user["full_name"],
                "rfid_uid":         user["rfid_uid"] or "",
                "had_active_locker": bool(active_locker),
                "locker_number":    active_locker["locker_number"] if active_locker else None,
                "admin_ip":         request.remote_addr,
            },
            status="warning" if active_locker else "success",
        )

        # Delete the user — FK CASCADE handles sessions, violations, etc.
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()

    except Exception:
        db.rollback()
        raise

    return _json_response({
        "ok":               True,
        "message":          f"Account for {user['full_name']} ({user['student_id']}) deleted.",
        "had_active_locker": bool(active_locker),
    })


# ---------------------------------------------------------------------------
# Unlink RFID card only (keep account, let student re-register a new card)
# ---------------------------------------------------------------------------

@admin_api_bp.patch("/users/<int:user_id>/unlink-rfid")
@admin_required
def unlink_rfid(user_id: int):
    """Clear the HF RFID UID and UHF EPC from a student account.

    The account itself is kept intact so the student can register a new card
    without losing their history (useful when a card is lost or damaged).
    """
    db = get_db()

    user = db.execute(
        "SELECT id, full_name, student_id, rfid_uid FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user:
        return _json_response({"error": "User not found."}, 404)

    # Block unlink while the student has a bag stored — the locker needs the
    # RFID for the retrieval step.
    active_locker = db.execute(
        "SELECT locker_number FROM lockers WHERE current_user_id = ? AND is_occupied = 1 LIMIT 1",
        (user_id,),
    ).fetchone()
    if active_locker:
        return _json_response(
            {
                "error": "ACTIVE_LOCKER",
                "message": (
                    f"Student has a bag in Locker {active_locker['locker_number']}. "
                    "Ask them to retrieve it first, then unlink."
                ),
            },
            409,
        )

    try:
        db.execute(
            "UPDATE users SET rfid_uid = NULL WHERE id = ?",
            (user_id,),
        )
        # Also clear the rfid_uid stored on any lockers from this user
        db.execute(
            "UPDATE lockers SET current_rfid_uid = NULL WHERE current_user_id = ?",
            (user_id,),
        )
        _log_activity(
            db,
            activity_type="rfid_unlinked",
            user_id=user_id,
            details={
                "student_id":    user["student_id"],
                "full_name":     user["full_name"],
                "old_rfid_uid":  user["rfid_uid"] or "",
                "admin_ip":      request.remote_addr,
            },
            status="success",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _json_response({
        "ok":      True,
        "message": f"RFID card unlinked from {user['full_name']}. Student can now register a new card.",
    })
