"""API routes for LibLocker kiosk flows."""

import json
import re
import secrets
import sqlite3

from flask import Blueprint, current_app, jsonify, request, session

from app.db import get_db
from app.hardware import get_hardware
from app.services.audit_service import log_audit_event
from app.services.locker_service import (
    ConflictError as LockerConflictError,
    HardwareError,
    LockerServiceError,
    NotFoundError as LockerNotFoundError,
    ValidationError as LockerValidationError,
    assign_locker_to_user,
    recover_failed_locker_release,
    release_locker_for_user,
)
from app.services.rfid_capture_service import get_rfid_capture_manager
from app.services.user_service import (
    ValidationError as UserValidationError,
    get_user_by_rfid,
)

api_bp = Blueprint("api", __name__)
MAX_LOCKER_COUNT = 24

FULL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .,'-]{2,99}$")
# Enhanced student ID pattern: 6-12 digits, optionally with institution prefix
STUDENT_ID_PATTERN = re.compile(r"^\d{6,12}$")
# Optional: Institution-specific pattern (can be configured via environment)
INSTITUTION_STUDENT_ID_PATTERN = re.compile(
    r"^(?:\d{4}-\d{4}|\d{6,12})$"  # Supports formats like: 2024-1234 or 202412345
)
RFID_UID_PATTERN = re.compile(r"^[0-9A-F]{6,32}$")


def _validate_student_id_checksum(student_id: str) -> bool:
    """Validate student ID using Luhn algorithm (mod-10 checksum).
    
    This is commonly used for student IDs, credit cards, etc.
    Can be disabled by setting VALIDATE_STUDENT_ID_CHECKSUM=false
    
    Returns True if valid or if checksum validation is disabled.
    """
    if not current_app.config.get("VALIDATE_STUDENT_ID_CHECKSUM", False):
        return True  # Checksum validation disabled
    
    # Remove any non-digit characters
    digits = [int(d) for d in student_id if d.isdigit()]
    
    if len(digits) < 2:
        return False
    
    # Luhn algorithm
    checksum = 0
    reverse_digits = digits[::-1]
    
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:  # Every second digit (from right)
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    
    return checksum % 10 == 0


def api_response(ok: bool, data: dict | None = None, error: str | None = None, status: int = 200):
    """Create consistent API response envelope."""
    return jsonify({"ok": ok, "data": data or {}, "error": error}), status


def active_locker_count() -> int:
    """Return the configured active locker count."""
    configured = current_app.config.get("ACTIVE_LOCKER_COUNT", MAX_LOCKER_COUNT)
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = MAX_LOCKER_COUNT
    return max(1, min(parsed, MAX_LOCKER_COUNT))


def read_json() -> dict:
    """Safely parse JSON body."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def get_capture_session_key() -> str:
    """Get or create RFID capture key bound to browser session."""
    capture_key = session.get("rfid_capture_key")
    if not capture_key:
        capture_key = secrets.token_hex(16)
        session["rfid_capture_key"] = capture_key
    return capture_key


def get_pending_student_id() -> str | None:
    """Return pending student ID for details-first registration flow."""
    pending = session.get("pending_student_id")
    return str(pending) if pending else None


def clear_pending_student_id() -> None:
    """Clear pending student registration marker."""
    session.pop("pending_student_id", None)


def get_pending_hf_rfid() -> str | None:
    """Return captured HF RFID UID during registration."""
    hf_rfid = session.get("pending_hf_rfid")
    return str(hf_rfid).upper() if hf_rfid else None


def set_pending_hf_rfid(uid: str | None) -> None:
    """Store captured HF RFID UID."""
    if uid:
        session["pending_hf_rfid"] = uid.upper()
    else:
        session.pop("pending_hf_rfid", None)


def validate_full_name(value: str) -> str:
    """Validate kiosk full-name format."""
    full_name = " ".join(str(value or "").strip().split())
    if not FULL_NAME_PATTERN.fullmatch(full_name):
        raise ValueError("Please enter a valid full name (at least 3 characters).")
    return full_name


def validate_student_id(value: str) -> str:
    """Validate kiosk student ID format with enhanced checks.
    
    Supports:
    - Basic format: 6-12 digits
    - Institution format: configurable pattern (e.g., YYYY-NNNN)
    - Optional Luhn checksum validation
    """
    student_id = str(value or "").strip()
    
    # Try institution-specific pattern first (if it matches more formats)
    use_institution_pattern = current_app.config.get("USE_INSTITUTION_STUDENT_ID_PATTERN", False)
    
    if use_institution_pattern:
        if not INSTITUTION_STUDENT_ID_PATTERN.fullmatch(student_id):
            raise ValueError(
                "Student ID must match institution format (e.g., 2024-1234 or 6-12 digits)."
            )
    else:
        if not STUDENT_ID_PATTERN.fullmatch(student_id):
            raise ValueError("Student ID must be numeric and 6 to 12 digits.")
    
    # Optional checksum validation
    if not _validate_student_id_checksum(student_id):
        current_app.logger.warning(
            "Student ID %s failed checksum validation (Luhn algorithm)",
            student_id[:4] + "****"  # Redact for privacy
        )
        raise ValueError("Student ID checksum validation failed.")
    
    return student_id


def validate_rfid_uid(value: str) -> str:
    """Validate UID format and normalize uppercase hex."""
    uid = str(value or "").strip().upper()
    if not RFID_UID_PATTERN.fullmatch(uid):
        raise ValueError("Invalid RFID UID format.")
    return uid


def log_activity_event(
    activity_type: str,
    locker_id: int | None = None,
    user_id: int | None = None,
    details: dict | str | None = None,
    status: str = "success",
) -> None:
    """Write an event into admin-facing activity_logs table."""
    db = get_db()
    details_value = details
    if isinstance(details, dict):
        details_value = json.dumps(details, ensure_ascii=True)
    db.execute(
        """
        INSERT INTO activity_logs(timestamp, activity_type, locker_id, user_id, details, status)
        VALUES (datetime('now'), ?, ?, ?, ?, ?)
        """,
        (activity_type, locker_id, user_id, details_value, status),
    )
    db.commit()


def create_deposit_session(user_id: int, locker_id: int, locker_group: str | None = None) -> int:
    """Create an active deposit session and map it to locker.current_session_id.
    
    Args:
        user_id: ID of the user making the deposit
        locker_id: ID of the assigned locker
        locker_group: Actual locker group stored on the assigned locker row
    """
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO sessions(user_id, locker_id, action, status, created_at)
        VALUES (?, ?, 'deposit', 'active', datetime('now'))
        """,
        (user_id, locker_id),
    )
    session_id = int(cur.lastrowid)
    
    # Store the student's location preference in the locker for audit/analytics
    db.execute(
        """
        UPDATE lockers
        SET current_session_id = ?,
            locker_group = COALESCE(?, locker_group),
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (session_id, locker_group, locker_id),
    )
    db.commit()
    return session_id


def complete_deposit_session(user_id: int, locker_id: int) -> None:
    """Complete latest active deposit session for user/locker pair."""
    db = get_db()
    session_row = db.execute(
        """
        SELECT id
        FROM sessions
        WHERE user_id = ?
          AND locker_id = ?
          AND action = 'deposit'
          AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, locker_id),
    ).fetchone()

    if session_row:
        db.execute(
            """
            UPDATE sessions
            SET status = 'completed',
                completed_at = datetime('now')
            WHERE id = ?
            """,
            (session_row["id"],),
        )

    db.execute(
        """
        UPDATE lockers
        SET current_session_id = NULL,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (locker_id,),
    )
    db.commit()


def rollback_deposit_assignment(locker_id: int, session_id: int | None = None) -> None:
    """Undo a just-created deposit assignment when the locker fails to open."""
    db = get_db()
    if session_id:
        db.execute(
            """
            UPDATE sessions
            SET status = 'canceled',
                completed_at = datetime('now')
            WHERE id = ?
            """,
            (session_id,),
        )

    db.execute(
        """
        UPDATE lockers
        SET is_occupied = 0,
            status = 'available',
            current_user_id = NULL,
            current_session_id = NULL,
            current_rfid_uid = NULL,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (locker_id,),
    )
    db.commit()


def create_retrieve_session(user_id: int, locker_id: int) -> int:
    """Create a completed retrieve session row."""
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO sessions(
            user_id,
            locker_id,
            action,
            status,
            created_at,
            completed_at
        )
        VALUES (?, ?, 'retrieve', 'completed', datetime('now'), datetime('now'))
        """,
        (user_id, locker_id),
    )
    db.commit()
    return int(cur.lastrowid)


def capture_session_evidence(
    hw,
    locker_number: int,
    session_id: int,
    capture_type: str,
) -> tuple[str | None, str | None, str | None]:
    """Capture and persist evidence for a deposit or retrieve session."""
    db = get_db()
    photo_filename = hw.cam.take_photo(
        locker_number=int(locker_number),
        session_id=int(session_id),
        capture_type=capture_type,
    )
    photo_url = hw.cam.get_photo_url(photo_filename)
    photo_path = str(hw.cam.get_photo_path(photo_filename).resolve())
    db.execute(
        "UPDATE sessions SET evidence_photo = ? WHERE id = ?",
        (photo_filename, session_id),
    )
    db.commit()
    current_app.logger.info("%s evidence photo path: %s", capture_type.capitalize(), photo_path)
    current_app.logger.info("%s evidence photo url: %s", capture_type.capitalize(), photo_url)
    return photo_filename, photo_url, photo_path


@api_bp.get("/health")
def health():
    """Health endpoint."""
    return api_response(
        True,
        {
            "status": "healthy",
            "hardware_mode": current_app.config.get("HARDWARE_MODE", "PI"),
        },
        None,
        200,
    )


@api_bp.post("/rfid/read")
def rfid_read():
    """Read one RFID tag from hardware adapter (production mode)."""
    try:
        hw = get_hardware()
        timeout = float(current_app.config.get("RFID_READ_TIMEOUT_SECONDS", 8))

        # Hardware read – will raise exceptions if reader unavailable
        try:
            uid_value = hw.rfid.read_rfid_once(timeout=timeout)
            uid = str(uid_value or "").strip().upper()
        except Exception as read_exc:
            log_audit_event("RFID read failed", level="ERROR", meta={"error": str(read_exc)})
            raise

        if not uid:
            log_audit_event("RFID read timeout (no card detected)", level="WARNING")
            return api_response(False, {}, "No RFID card detected. Please try again.", 408)

        return api_response(True, {"rfid_uid": uid}, None, 200)
    except Exception as exc:
        log_audit_event("RFID read failed", level="ERROR", meta={"error": str(exc)})
        return api_response(False, {}, "RFID reader error. Please contact staff.", 503)


@api_bp.post("/rfid/start")
def rfid_start():
    """Start a registration RFID capture session for current browser session."""
    manager = get_rfid_capture_manager()
    if not manager.is_reader_available():
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "RFID_UNAVAILABLE",
                    "message": "RFID reader unavailable. Please contact staff.",
                }
            ),
            503,
        )

    manager.start_capture(get_capture_session_key())
    return jsonify({"ok": True}), 200


@api_bp.get("/rfid/poll")
def rfid_poll():
    """Poll most recent RFID capture result for current browser session."""
    manager = get_rfid_capture_manager()
    if not manager.is_reader_available():
        print(f"[RFID POLL] Reader unavailable: {manager.reader_error()}")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "RFID_UNAVAILABLE",
                    "message": "RFID reader unavailable. Please contact staff.",
                }
            ),
            503,
        )

    capture_key = get_capture_session_key()
    pending_sid = get_pending_student_id()
    
    if not pending_sid:
        manager.clear_capture(capture_key)
        return jsonify({"ok": True, "uid": None}), 200

    uid = manager.poll_capture(capture_key)
    if uid:
        print(f"[RFID POLL] Card detected! UID: {uid} for student: {pending_sid}")
    return jsonify({"ok": True, "uid": uid}), 200


@api_bp.post("/register/details")
def register_details():
    """Save user details first, then wait for RFID linking step."""
    data = read_json()
    print(f"[REGISTER DETAILS] Request: {data}")
    
    try:
        full_name = validate_full_name(data.get("full_name", ""))
        student_id = validate_student_id(data.get("student_id", ""))
        print(f"[REGISTER DETAILS] Validated - Name: {full_name}, Student ID: {student_id}")
    except ValueError as exc:
        print(f"[REGISTER DETAILS] Validation error: {str(exc)}")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            ),
            400,
        )

    db = get_db()
    existing_student = db.execute(
        "SELECT id, rfid_uid FROM users WHERE student_id = ? LIMIT 1",
        (student_id,),
    ).fetchone()

    if existing_student and existing_student["rfid_uid"]:
        # Truly registered (RFID is linked) — block.
        print(f"[REGISTER DETAILS] Duplicate student ID with linked RFID: {student_id}")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "STUDENT_ID_EXISTS",
                    "message": "Student ID already registered.",
                }
            ),
            409,
        )

    try:
        if existing_student:
            # Orphan from a previous incomplete attempt (RFID never linked).
            # Reuse the row instead of failing — refresh the name and timestamp
            # so this attempt looks fresh.
            print(
                f"[REGISTER DETAILS] Reusing orphan row for student_id={student_id} "
                f"(no RFID was linked previously)"
            )
            db.execute(
                """
                UPDATE users
                SET    full_name  = ?,
                       created_at = datetime('now')
                WHERE  id = ?
                """,
                (full_name, existing_student["id"]),
            )
            db.commit()
        else:
            db.execute(
                """
                INSERT INTO users(full_name, student_id, rfid_uid, created_at)
                VALUES (?, ?, NULL, datetime('now'))
                """,
                (full_name, student_id),
            )
            db.commit()
            print(f"[REGISTER DETAILS] User created: {student_id}")
    except sqlite3.IntegrityError as exc:
        db.rollback()
        print(f"[REGISTER DETAILS] Database error: {str(exc)}")
        message = str(exc).lower()
        if "student_id" in message:
            # Race condition — another request created the same student_id
            # between the SELECT above and our INSERT. Treat as duplicate.
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "STUDENT_ID_EXISTS",
                        "message": "Student ID already registered.",
                    }
                ),
                409,
            )
        log_audit_event("Details registration failed", "ERROR", {"error": str(exc)})
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "REGISTRATION_FAILED",
                    "message": "System error. Try again.",
                }
            ),
            500,
        )

    session["pending_student_id"] = student_id
    print(f"[REGISTER DETAILS] Session updated with pending_student_id: {student_id}")
    return jsonify({"ok": True, "message": "Details saved"}), 201


@api_bp.post("/register/start_rfid")
def register_start_rfid():
    """Begin RFID capture for the current pending student registration."""
    pending_student_id = get_pending_student_id()
    print(f"[START RFID] Pending student: {pending_student_id}")
    
    if not pending_student_id:
        print(f"[START RFID] No pending registration!")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "NO_PENDING",
                    "message": "No pending registration.",
                }
            ),
            400,
        )

    manager = get_rfid_capture_manager()
    if not manager.is_reader_available():
        print(f"[START RFID] Reader unavailable: {manager.reader_error()}")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "RFID_UNAVAILABLE",
                    "message": "RFID reader unavailable. Please contact staff.",
                }
            ),
            503,
        )

    capture_key = get_capture_session_key()
    manager.start_capture(capture_key)
    print(f"[START RFID] Capture started for session: {capture_key}")
    return jsonify({"ok": True, "message": "RFID reader ready"}), 200


@api_bp.post("/register/link_rfid")
def register_link_rfid():
    """Link scanned HF RFID UID to the current pending student registration."""
    pending_student_id = get_pending_student_id()
    print(f"[LINK HF RFID] Linking for student: {pending_student_id}")
    
    if not pending_student_id:
        print(f"[LINK HF RFID] No pending registration!")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "NO_PENDING",
                    "message": "No pending registration.",
                }
            ),
            400,
        )

    data = read_json()
    print(f"[LINK HF RFID] Request data: {data}")
    
    try:
        uid = validate_rfid_uid(data.get("uid", ""))
        print(f"[LINK HF RFID] Validated UID: {uid}")
    except ValueError as e:
        print(f"[LINK HF RFID] Validation error: {str(e)}")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "VALIDATION_ERROR",
                    "message": "Invalid HF RFID UID format.",
                }
            ),
            400,
        )

    db = get_db()
    existing_uid = db.execute(
        "SELECT student_id FROM users WHERE UPPER(rfid_uid) = ? LIMIT 1",
        (uid,),
    ).fetchone()
    if existing_uid:
        print(f"[LINK HF RFID] UID already exists! Linked to: {existing_uid['student_id']}")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "RFID_EXISTS",
                    "message": "HF RFID card already linked.",
                }
            ),
            409,
        )

    student_row = db.execute(
        "SELECT id FROM users WHERE student_id = ? LIMIT 1",
        (pending_student_id,),
    ).fetchone()
    if not student_row:
        print(f"[LINK HF RFID] Student not found: {pending_student_id}")
        clear_pending_student_id()
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "NO_PENDING",
                    "message": "No pending registration.",
                }
            ),
            400,
        )

    user_id = student_row["id"]

    try:
        db.execute(
            """
            UPDATE users
            SET rfid_uid = ?
            WHERE student_id = ?
            """,
            (uid, pending_student_id),
        )
        db.commit()
        print(f"[LINK HF RFID] Successfully linked! User ID: {user_id}, UID: {uid}")
        set_pending_hf_rfid(uid)
    except sqlite3.IntegrityError:
        db.rollback()
        print(f"[LINK HF RFID] Database integrity error when linking UID")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "RFID_EXISTS",
                    "message": "HF RFID card already linked.",
                }
            ),
            409,
        )

    # Surface the new registration in the admin Activity Log feed and
    # the audit log. The dashboard filter dropdown expects activity_type
    # = "registration" (see app/templates/admin/logs.html).
    full_name_row = db.execute(
        "SELECT full_name FROM users WHERE id = ?", (user_id,),
    ).fetchone()
    log_audit_event(
        "User registered",
        "INFO",
        {"user_id": user_id, "student_id": pending_student_id, "rfid_uid": uid},
    )
    log_activity_event(
        "registration",
        user_id=user_id,
        details={
            "student_id": pending_student_id,
            "full_name":  (full_name_row["full_name"] if full_name_row else ""),
            "rfid_uid":   uid,
        },
        status="success",
    )

    manager = get_rfid_capture_manager()
    manager.clear_capture(get_capture_session_key())

    return jsonify({
        "ok": True,
        "user_id": user_id,
        "message": "HF RFID linked successfully. Registration complete.",
        "next_step": "complete",
    }), 200



@api_bp.post("/register")
def register():
    """Register user with name, student ID, and RFID UID."""
    data = read_json()
    try:
        full_name = validate_full_name(data.get("full_name", ""))
        student_id = validate_student_id(data.get("student_id", ""))
        rfid_uid = validate_rfid_uid(data.get("rfid_uid", ""))
    except ValueError as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            ),
            400,
        )

    db = get_db()

    existing_student = db.execute(
        "SELECT id FROM users WHERE student_id = ? LIMIT 1",
        (student_id,),
    ).fetchone()
    if existing_student:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "STUDENT_ID_EXISTS",
                    "message": "Student ID already registered.",
                }
            ),
            409,
        )

    existing_uid = db.execute(
        "SELECT id FROM users WHERE UPPER(rfid_uid) = ? LIMIT 1",
        (rfid_uid,),
    ).fetchone()
    if existing_uid:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "RFID_EXISTS",
                    "message": "RFID card already linked.",
                }
            ),
            409,
        )

    try:
        cur = db.execute(
            """
            INSERT INTO users(full_name, student_id, rfid_uid, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (full_name, student_id, rfid_uid),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        message = str(exc).lower()
        if "student_id" in message:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "STUDENT_ID_EXISTS",
                        "message": "Student ID already registered.",
                    }
                ),
                409,
            )
        if "rfid_uid" in message:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "RFID_EXISTS",
                        "message": "RFID card already linked.",
                    }
                ),
                409,
            )
        log_audit_event("User registration failed", "ERROR", {"error": str(exc)})
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "REGISTRATION_FAILED",
                    "message": "Registration failed. Please try again.",
                }
            ),
            500,
        )

    user_id = int(cur.lastrowid)
    log_audit_event("User registered", "INFO", {"user_id": user_id, "student_id": student_id})
    log_activity_event(
        "registration",
        user_id=user_id,
        details={"student_id": student_id, "full_name": full_name},
        status="success",
    )
    return jsonify({"ok": True, "message": "Registration successful."}), 201


@api_bp.post("/deposit/assign")
def deposit_assign():
    """Assign locker to an existing RFID user for deposit flow.

    Also opens the locker for deposit and captures an evidence photo.
    """
    data         = read_json()
    rfid_uid     = data.get("rfid_uid", "")
    locker_group = data.get("locker_group", "any")

    try:
        user = get_user_by_rfid(rfid_uid)
        if not user:
            return api_response(False, {}, "RFID is not registered.", 404)

        group_display = locker_group.upper() if locker_group else "ANY"
        print(f"📦 Student {user['student_id']} selected location: {group_display}")

        assigned = assign_locker_to_user(user["id"], locker_group)
        print(f"✓ Assigned locker #{assigned['locker_number']} from {group_display} section")

        # Store the RFID UID on the locker for retrieval verification
        db = get_db()
        db.execute(
            "UPDATE lockers SET current_rfid_uid = ? WHERE id = ?",
            (rfid_uid, int(assigned["locker_id"]))
        )
        db.commit()

        # Create or retrieve session
        session_id = None
        if not assigned["reused"]:
            session_id = create_deposit_session(
                user["id"],
                int(assigned["locker_id"]),
                str(assigned["locker_group"]),
            )
        else:
            row = db.execute(
                "SELECT current_session_id FROM lockers WHERE id = ?",
                (int(assigned["locker_id"]),),
            ).fetchone()
            if row:
                session_id = row["current_session_id"]

        # ── Evidence photo capture (non-fatal) ──────────────────────────
        auto_close_seconds = float(current_app.config.get("GPIO_DEPOSIT_OPEN_SECONDS", 5))

        try:
            hw = get_hardware()
            gpio = hw.gpio
            locker_number = int(assigned["locker_number"])
            gpio.open_locker_window(locker_number, hold_open_seconds=auto_close_seconds)
        except Exception as hw_exc:
            current_app.logger.error(
                "🔴 GPIO HARDWARE ERROR during deposit for locker %d: %s",
                assigned["locker_number"], hw_exc
            )
            if not assigned["reused"]:
                rollback_deposit_assignment(
                    int(assigned["locker_id"]),
                    int(session_id) if session_id else None,
                )

            log_audit_event(
                "Locker open failed during deposit",
                "ERROR",
                {
                    "user_id": user["id"],
                    "locker_number": assigned["locker_number"],
                    "locker_id": assigned["locker_id"],
                    "error": str(hw_exc),
                },
            )
            return api_response(
                False,
                {},
                "Locker assigned but failed to open. Please try again or contact staff.",
                503,
            )

        photo_filename = None
        photo_url = None
        photo_path = None
        if session_id:
            try:
                photo_filename, photo_url, photo_path = capture_session_evidence(
                    hw=hw,
                    locker_number=int(assigned["locker_number"]),
                    session_id=int(session_id),
                    capture_type="deposit",
                )
                print(f"📷 Evidence photo: {photo_filename}")
            except Exception as cam_exc:
                current_app.logger.warning(
                    "Camera capture failed (deposit will continue): %s", cam_exc
                )
        # ────────────────────────────────────────────────────────────────

        log_audit_event(
            "Locker assigned", "INFO",
            {
                "user_id":               user["id"],
                "student_id":            user["student_id"],
                "locker_number":         assigned["locker_number"],
                "locker_group":          assigned["locker_group"],
                "student_selected_group": locker_group,
                "rfid_uid":              rfid_uid,
                "reused":                assigned["reused"],
                "evidence_photo":        photo_filename,
                "evidence_photo_url":    photo_url,
                "evidence_photo_path":   photo_path,
                "auto_close_seconds":    auto_close_seconds,
            },
        )
        log_activity_event(
            "deposit",
            locker_id=int(assigned["locker_id"]),
            user_id=user["id"],
            details={
                "locker_number":  assigned["locker_number"],
                "locker_group":   assigned["locker_group"],
                "session_id":     session_id,
                "evidence_photo": photo_filename,
                "evidence_photo_url": photo_url,
                "evidence_photo_path": photo_path,
                "auto_close_seconds": auto_close_seconds,
            },
            status="success",
        )

        return api_response(
            True,
            {
                "locker_number":  assigned["locker_number"],
                "locker_group":   assigned["locker_group"],
                "reused":         assigned["reused"],
                "evidence_photo": photo_filename,
                "evidence_photo_url": photo_url,
                "evidence_photo_path": photo_path,
                "auto_close_seconds": auto_close_seconds,
            },
            None, 200,
        )

    except LockerValidationError as exc:
        return api_response(False, {}, str(exc), 400)
    except LockerConflictError as exc:
        return api_response(False, {}, str(exc), 409)
    except LockerServiceError as exc:
        log_audit_event("Locker assignment failed", "ERROR", {"error": str(exc)})
        return api_response(False, {}, "Locker assignment failed.", 500)
    except UserValidationError as exc:
        return api_response(False, {}, str(exc), 400)
    except Exception as exc:
        current_app.logger.exception("Unexpected deposit error: %s", exc)
        return api_response(False, {}, "Deposit process failed. Please try again.", 500)


@api_bp.post("/retrieve/release")
def retrieve_release():
    """Release locker for an RFID user in retrieve flow.

    On HardwareError, automatically attempts recovery up to 3 times before
    returning a 503 asking the user to contact staff.
    """
    data     = read_json()
    rfid_uid = data.get("rfid_uid", "")

    try:
        user = get_user_by_rfid(rfid_uid)
        if not user:
            return api_response(False, {}, "RFID is not registered.", 404)

        # Warn if RFID on locker differs (still allow retrieve – user may have re-registered)
        db = get_db()
        locker_row = db.execute(
            """
            SELECT id, locker_number, current_rfid_uid
            FROM   lockers
            WHERE  current_user_id = ? AND (is_occupied = 1 OR status = 'occupied')
            LIMIT  1
            """,
            (user["id"],),
        ).fetchone()

        if locker_row and locker_row["current_rfid_uid"] and locker_row["current_rfid_uid"] != rfid_uid:
            print(f"⚠️  RFID mismatch – locker #{locker_row['locker_number']}: "
                  f"stored={locker_row['current_rfid_uid']} got={rfid_uid}")
            log_audit_event(
                "RFID mismatch on retrieve", "WARNING",
                {
                    "user_id":       user["id"],
                    "locker_number": locker_row["locker_number"],
                    "expected_uid":  locker_row["current_rfid_uid"],
                    "provided_uid":  rfid_uid,
                },
            )

        hw = get_hardware()

        recovery_retries = None
        auto_close_seconds = float(current_app.config.get("GPIO_RETRIEVE_OPEN_SECONDS", 10))

        # ── Primary attempt ─────────────────────────────────────────────
        try:
            released = release_locker_for_user(
                user["id"],
                hw.gpio,
                hold_open_seconds=auto_close_seconds,
            )

        except HardwareError as hw_exc:
            # Always log hardware errors prominently
            current_app.logger.error(
                "🔴 GPIO HARDWARE ERROR during retrieve for user %d: %s",
                user["id"], hw_exc
            )
            # ── Automatic recovery (Feature #7) ─────────────────────────
            if current_app.config.get("ENABLE_ERROR_RECOVERY", True) and locker_row:
                current_app.logger.warning(
                    "GPIO error for locker %d – attempting recovery: %s",
                    locker_row["locker_number"], hw_exc,
                )
                log_audit_event(
                    "Locker hardware open failed – starting recovery", "WARNING",
                    {"locker_number": locker_row["locker_number"], "error": str(hw_exc)},
                )
                recovery = recover_failed_locker_release(
                    int(locker_row["id"]),
                    hw.gpio,
                    hold_open_seconds=auto_close_seconds,
                )

                if recovery["success"]:
                    log_audit_event(
                        "Locker recovery succeeded", "INFO",
                        {"retries": recovery["retries"], "locker_id": locker_row["id"]},
                    )
                    recovery_retries = recovery["retries"]
                    released = {
                        "locker_id": recovery["locker_id"],
                        "locker_number": recovery["locker_number"],
                        "locker_group": recovery["locker_group"],
                    }
                else:
                    log_audit_event(
                        "Locker recovery failed – manual intervention required", "ERROR",
                        {"retries": recovery["retries"], "locker_id": locker_row["id"]},
                    )
                    return api_response(
                        False, {},
                        "Locker mechanism stuck. Please contact staff for manual unlock.",
                        503,
                    )
            # No recovery configured – bubble up
            raise
        # ────────────────────────────────────────────────────────────────

        print(f"✓ Locker #{released['locker_number']} released (RFID {rfid_uid})")

        complete_deposit_session(user["id"], int(released["locker_id"]))
        session_id = create_retrieve_session(
            user["id"],
            int(released["locker_id"]),
        )
        photo_filename = None
        photo_url = None
        photo_path = None

        try:
            photo_filename, photo_url, photo_path = capture_session_evidence(
                hw=hw,
                locker_number=int(released["locker_number"]),
                session_id=int(session_id),
                capture_type="retrieve",
            )
            print(f"📷 Retrieve evidence photo: {photo_filename}")
        except Exception as cam_exc:
            current_app.logger.warning(
                "Camera capture failed during retrieve (locker release will continue): %s",
                cam_exc,
            )

        log_audit_event(
            "Locker released", "INFO",
            {
                "user_id":       user["id"],
                "student_id":    user["student_id"],
                "locker_number": released["locker_number"],
                "locker_group":  released["locker_group"],
                "rfid_uid":      rfid_uid,
                "recovery_retries": recovery_retries,
                "evidence_photo": photo_filename,
                "evidence_photo_url": photo_url,
                "evidence_photo_path": photo_path,
                "auto_close_seconds": auto_close_seconds,
            },
        )
        log_activity_event(
            "retrieve",
            locker_id=int(released["locker_id"]),
            user_id=user["id"],
            details={
                "locker_number": released["locker_number"],
                "locker_group":  released["locker_group"],
                "session_id":    session_id,
                "recovery_retries": recovery_retries,
                "evidence_photo": photo_filename,
                "evidence_photo_url": photo_url,
                "evidence_photo_path": photo_path,
                "auto_close_seconds": auto_close_seconds,
            },
            status="success",
        )
        response_data = {
            "locker_number": released["locker_number"],
            "locker_group":  released["locker_group"],
            "evidence_photo": photo_filename,
            "evidence_photo_url": photo_url,
            "evidence_photo_path": photo_path,
            "auto_close_seconds": auto_close_seconds,
        }
        if recovery_retries is not None:
            response_data["recovery_retries"] = recovery_retries

        return api_response(
            True,
            response_data,
            None, 200,
        )

    except LockerNotFoundError as exc:
        return api_response(False, {}, str(exc), 404)
    except HardwareError as exc:
        log_audit_event("Locker hardware open failed", "ERROR", {"error": str(exc)})
        return api_response(False, {}, str(exc), 500)
    except LockerServiceError as exc:
        log_audit_event("Locker retrieve flow failed", "ERROR", {"error": str(exc)})
        return api_response(False, {}, "Retrieve process failed.", 500)
    except UserValidationError as exc:
        return api_response(False, {}, str(exc), 400)
    except Exception as exc:
        current_app.logger.exception("Unexpected retrieve error: %s", exc)
        return api_response(False, {}, "Retrieve process failed. Please try again.", 500)


@api_bp.get("/status/database")
def get_database_status():
    """Return real-time database status for monitoring dashboard."""
    db = get_db()
    active_count = active_locker_count()
    
    # Get locker statistics
    lockers = db.execute(
        """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_occupied = 0 THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN is_occupied = 1 THEN 1 ELSE 0 END) as occupied
        FROM lockers
        WHERE COALESCE(locker_number, id) BETWEEN 1 AND ?
        """
        ,
        (active_count,),
    ).fetchone()
    
    # Get currently occupied lockers with student info
    occupied_lockers = db.execute(
        """
        SELECT 
            l.locker_number,
            l.locker_group,
            l.current_rfid_uid,
            u.student_id,
            u.full_name,
            s.created_at as assigned_time,
            s.action
        FROM lockers l
        LEFT JOIN users u ON l.current_user_id = u.id
        LEFT JOIN sessions s ON l.current_session_id = s.id
        WHERE l.is_occupied = 1
          AND COALESCE(l.locker_number, l.id) BETWEEN 1 AND ?
        ORDER BY l.locker_number ASC
        """
        ,
        (active_count,),
    ).fetchall()
    
    # Get recent activity (last 20)
    recent_activity = db.execute(
        """
        SELECT 
            al.timestamp,
            al.activity_type,
            al.locker_id,
            l.locker_number,
            u.student_id,
            u.full_name,
            al.status
        FROM activity_logs al
        LEFT JOIN lockers l ON al.locker_id = l.id
        LEFT JOIN users u ON al.user_id = u.id
        ORDER BY al.timestamp DESC
        LIMIT 20
        """
    ).fetchall()
    
    # Get user registration count
    users_row = db.execute("SELECT COUNT(*) as total FROM users").fetchone()
    
    return api_response(
        True,
        {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "lockers": {
                "total": lockers["total"] or 0,
                "available": lockers["available"] or 0,
                "occupied": lockers["occupied"] or 0,
            },
            "occupied_lockers": [dict(row) for row in occupied_lockers],
            "recent_activity": [dict(row) for row in recent_activity],
            "users": {
                "total": users_row["total"] or 0,
            },
        },
        None,
        200,
    )
