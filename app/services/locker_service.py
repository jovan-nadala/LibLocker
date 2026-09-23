"""Locker service layer for deposit and retrieval workflows."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from flask import current_app

from app.db import get_db

logger = logging.getLogger(__name__)


class LockerServiceError(Exception):
    """Base locker service exception."""


class ValidationError(LockerServiceError):
    """Raised for invalid input."""


class ConflictError(LockerServiceError):
    """Raised when allocation is not possible."""


class NotFoundError(LockerServiceError):
    """Raised when an expected locker/user assignment is missing."""


class HardwareError(LockerServiceError):
    """Raised for GPIO or hardware-level failures."""


VALID_LOCKER_GROUPS = {"upper1", "upper2", "lower1", "lower2", "upper", "lower", "any"}
MAX_RECOVERY_RETRIES = 3
RECOVERY_BASE_DELAY = 0.5  # Base delay in seconds for exponential backoff
RECOVERY_MAX_DELAY = 5.0   # Maximum delay between retries
CIRCUIT_BREAKER_THRESHOLD = 5  # Number of consecutive failures before circuit opens
CIRCUIT_BREAKER_TIMEOUT = 300  # Seconds before attempting to close circuit again

# Circuit breaker state tracking (in-memory, resets on service restart)
_circuit_breaker_state = {
    "failure_count": 0,
    "last_failure_time": None,
    "is_open": False
}


def _check_circuit_breaker() -> bool:
    """Check if circuit breaker allows operation.
    
    Returns True if operation should proceed, False if circuit is open.
    Implements automatic recovery after timeout.
    """
    import time as time_module
    
    if not _circuit_breaker_state["is_open"]:
        return True
    
    # Check if timeout has elapsed
    if _circuit_breaker_state["last_failure_time"]:
        elapsed = time_module.time() - _circuit_breaker_state["last_failure_time"]
        if elapsed >= CIRCUIT_BREAKER_TIMEOUT:
            # Attempt to close circuit (half-open state)
            logger.info("Circuit breaker timeout elapsed, attempting to close circuit")
            _circuit_breaker_state["is_open"] = False
            _circuit_breaker_state["failure_count"] = 0
            return True
    
    logger.warning("Circuit breaker is OPEN - blocking recovery operation")
    return False


def _record_recovery_failure() -> None:
    """Record a recovery failure for circuit breaker tracking."""
    import time as time_module
    
    _circuit_breaker_state["failure_count"] += 1
    _circuit_breaker_state["last_failure_time"] = time_module.time()
    
    if _circuit_breaker_state["failure_count"] >= CIRCUIT_BREAKER_THRESHOLD:
        _circuit_breaker_state["is_open"] = True
        logger.error(
            "Circuit breaker OPENED after %d consecutive failures - will retry after %d seconds",
            CIRCUIT_BREAKER_THRESHOLD,
            CIRCUIT_BREAKER_TIMEOUT
        )


def _record_recovery_success() -> None:
    """Reset circuit breaker on successful recovery."""
    _circuit_breaker_state["failure_count"] = 0
    _circuit_breaker_state["is_open"] = False
    _circuit_breaker_state["last_failure_time"] = None


def _safe_rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _active_locker_count() -> int:
    configured = current_app.config.get("ACTIVE_LOCKER_COUNT", 24)
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = 24
    return max(1, min(parsed, 24))


_DEFAULT_UPPER: set[int] = {1, 2, 3, 4, 5, 6, 13, 14, 15, 16, 17, 18}
_DEFAULT_LOWER: set[int] = {7, 8, 9, 10, 11, 12, 19, 20, 21, 22, 23, 24}


def _parse_locker_set(raw: Any, default: set[int]) -> set[int]:
    """Parse a comma-separated list of locker numbers. Falls back to *default*."""
    if raw is None or str(raw).strip() == "":
        return set(default)
    try:
        parsed = {int(x.strip()) for x in str(raw).split(",") if x.strip()}
        return parsed if parsed else set(default)
    except (ValueError, AttributeError):
        return set(default)


def _get_upper_lockers() -> set[int]:
    """Return the set of upper-row locker numbers (1-6, 13-18 by default)."""
    return _parse_locker_set(current_app.config.get("UPPER_LEVEL_LOCKERS"), _DEFAULT_UPPER)


def _get_lower_lockers() -> set[int]:
    """Return the set of lower-row locker numbers (7-12, 19-24 by default)."""
    return _parse_locker_set(current_app.config.get("LOWER_LEVEL_LOCKERS"), _DEFAULT_LOWER)


def normalize_group(locker_group: str) -> str:
    key = (locker_group or "").strip().lower()
    if key not in VALID_LOCKER_GROUPS:
        raise ValidationError(f"Invalid locker group '{key}'.")
    return key


def _locker_scope_clause(group_key: str) -> tuple[str, tuple[Any, ...]]:
    """Build the WHERE-fragment that restricts assignment to *group_key*.

    The caller combines this with ``ORDER BY COALESCE(locker_number, id) ASC
    LIMIT 1`` so the chosen locker is always the **lowest-numbered available
    locker in the set**.

    Behaviour:
      - ``any``   → any locker in 1..active_count
                    (lowest number wins → 1 first, then 2, 3, ...)
      - ``upper`` → locker in the upper set  (1-6 and 13-18)
                    (1 first, then 2..6, then 13, 14..18)
      - ``lower`` → locker in the lower set  (7-12 and 19-24)
                    (7 first, then 8..12, then 19, 20..24)

    Legacy quarter keys (``upper1`` / ``upper2`` / ``lower1`` / ``lower2``)
    fall through to a direct ``locker_group`` column match.
    """
    active_count = _active_locker_count()

    if group_key == "any":
        return "COALESCE(locker_number, id) BETWEEN ? AND ?", (1, active_count)

    if group_key == "upper":
        numbers = sorted(n for n in _get_upper_lockers() if 1 <= n <= active_count)
        if not numbers:
            numbers = [1]
        placeholders = ",".join("?" * len(numbers))
        return f"COALESCE(locker_number, id) IN ({placeholders})", tuple(numbers)

    if group_key == "lower":
        numbers = sorted(n for n in _get_lower_lockers() if 1 <= n <= active_count)
        if not numbers:
            numbers = [active_count]
        placeholders = ",".join("?" * len(numbers))
        return f"COALESCE(locker_number, id) IN ({placeholders})", tuple(numbers)

    # Legacy quarter-key support (upper1 / upper2 / lower1 / lower2)
    return (
        "locker_group = ? AND COALESCE(locker_number, id) BETWEEN ? AND ?",
        (group_key, 1, active_count),
    )


def _find_user_assigned_locker(db, user_id: int):
    return db.execute(
        """
        SELECT id, locker_number, locker_group, current_user_id
        FROM lockers
        WHERE current_user_id = ? AND (is_occupied = 1 OR status = 'occupied')
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def _clear_locker_assignment(db, locker_id: int) -> None:
    db.execute(
        """
        UPDATE lockers
        SET    is_occupied        = 0,
               status             = 'available',
               current_user_id    = NULL,
               current_session_id = NULL,
               current_rfid_uid   = NULL,
               last_opened_at     = datetime('now'),
               updated_at         = datetime('now')
        WHERE  id = ?
        """,
        (locker_id,),
    )


def get_user_active_locker(user_id: int) -> Optional[Dict[str, Any]]:
    """Return the locker currently assigned to *user_id*, or None."""
    db = get_db()
    row = _find_user_assigned_locker(db, user_id)
    return dict(row) if row else None


def assign_locker_to_user(user_id: int, locker_group: str) -> Dict[str, Any]:
    """Atomically assign the first available locker in *locker_group*.
    
    Race condition fix: Uses database-level locking with BEGIN IMMEDIATE
    and atomic UPDATE in subquery to prevent TOCTOU issues.
    """
    group_key = normalize_group(locker_group)
    scope_clause, scope_params = _locker_scope_clause(group_key)
    db = get_db()

    try:
        # Start exclusive transaction immediately to prevent race conditions
        db.execute("BEGIN IMMEDIATE")

        # Check for existing assignment - use SELECT FOR UPDATE to lock the row
        existing_query = """
            SELECT id, locker_number, locker_group, current_user_id
            FROM lockers
            WHERE current_user_id = ? AND (is_occupied = 1 OR status = 'occupied')
            LIMIT 1
        """
        # Note: SQLite doesn't support FOR UPDATE, but BEGIN IMMEDIATE provides table-level lock
        existing = db.execute(existing_query, (user_id,)).fetchone()
        
        if existing:
            db.commit()
            logger.info(
                "Locker already assigned - user=%d locker=%d (reused)",
                user_id,
                existing["locker_number"],
            )
            return {
                "locker_id": int(existing["id"]),
                "locker_number": int(existing["locker_number"]),
                "locker_group": existing["locker_group"],
                "reused": True,
            }

        # Atomic UPDATE with subquery - prevents race condition by checking 
        # conditions again in WHERE clause after selecting the locker
        result = db.execute(
            f"""
            UPDATE lockers
            SET    is_occupied     = 1,
                   status          = 'occupied',
                   current_user_id = ?,
                   last_opened_at  = datetime('now'),
                   updated_at      = datetime('now')
            WHERE  id = (
                       SELECT id FROM lockers
                       WHERE  is_occupied = 0
                         AND  status = 'available'
                         AND  current_user_id IS NULL
                         AND  {scope_clause}
                       ORDER  BY COALESCE(locker_number, id) ASC
                       LIMIT  1
                   )
              AND  is_occupied = 0
              AND  current_user_id IS NULL
            """,
            (user_id, *scope_params),
        )

        if result.rowcount != 1:
            db.rollback()
            raise ConflictError("No available lockers in the selected section.")

        # Retrieve the assigned locker (still within transaction)
        assigned = db.execute(existing_query, (user_id,)).fetchone()
        
        if not assigned:
            db.rollback()
            raise LockerServiceError("Failed to retrieve assigned locker after update.")
        
        # Log transaction
        db.execute(
            "INSERT INTO transactions(user_id, locker_id, action, status) VALUES (?, ?, 'DEPOSIT', 'DONE')",
            (user_id, assigned["id"]),
        )
        db.commit()

        logger.info(
            "Locker assigned - user=%d locker=%d group=%s",
            user_id,
            assigned["locker_number"],
            assigned["locker_group"],
        )
        return {
            "locker_id": int(assigned["id"]),
            "locker_number": int(assigned["locker_number"]),
            "locker_group": assigned["locker_group"],
            "reused": False,
        }

    except LockerServiceError:
        _safe_rollback(db)
        raise
    except Exception as exc:
        _safe_rollback(db)
        logger.error("Locker assignment failed for user %d: %s", user_id, exc)
        raise LockerServiceError("Failed to assign locker.") from exc


def release_locker_for_user(
    user_id: int,
    gpio_controller,
    hold_open_seconds: float = 10.0,
) -> Dict[str, Any]:
    """Unlock a user's locker and mark it as available in the database."""
    db = get_db()

    try:
        db.execute("BEGIN IMMEDIATE")

        assigned = _find_user_assigned_locker(db, user_id)
        if not assigned:
            raise NotFoundError("No locker is currently assigned to this RFID.")

        locker_id = int(assigned["id"])
        locker_number = int(assigned["locker_number"])
        locker_group = assigned["locker_group"]

        try:
            gpio_controller.open_locker_window(locker_number, hold_open_seconds=hold_open_seconds)
        except Exception as exc:
            raise HardwareError(f"Failed to open locker hardware: {exc}") from exc

        _clear_locker_assignment(db, locker_id)
        db.execute(
            "INSERT INTO transactions(user_id, locker_id, action, status) VALUES (?, ?, 'RETRIEVE', 'DONE')",
            (user_id, locker_id),
        )
        db.commit()

        logger.info("Locker released - user=%d locker=%d", user_id, locker_number)
        return {
            "locker_id": locker_id,
            "locker_number": locker_number,
            "locker_group": locker_group,
        }

    except LockerServiceError:
        _safe_rollback(db)
        raise
    except Exception as exc:
        _safe_rollback(db)
        raise LockerServiceError("Failed to release locker.") from exc


def recover_failed_locker_release(
    locker_id: int,
    gpio_controller,
    hold_open_seconds: float = 10.0,
) -> Dict[str, Any]:
    """Retry a failed locker release and complete the DB release on success.
    
    Implements exponential backoff and circuit breaker pattern to prevent
    infinite loops and reduce system load during persistent failures.
    """
    # Check circuit breaker first
    if not _check_circuit_breaker():
        return {
            "success": False,
            "retries": 0,
            "manual_action_required": True,
            "error": "Circuit breaker is open - too many recent failures"
        }
    
    db = get_db()
    last_exception = None

    for attempt in range(1, MAX_RECOVERY_RETRIES + 1):
        try:
            db.execute("BEGIN IMMEDIATE")
            locker = db.execute(
                """
                SELECT id, locker_number, locker_group, current_user_id
                FROM lockers
                WHERE id = ?
                """,
                (locker_id,),
            ).fetchone()

            if not locker or locker["current_user_id"] is None:
                _safe_rollback(db)
                # Success case - locker already cleared
                _record_recovery_success()
                return {"success": False, "retries": attempt - 1, "manual_action_required": True}

            locker_number = int(locker["locker_number"])
            user_id = int(locker["current_user_id"])

            logger.info(
                "Recovery attempt %d/%d for locker %d",
                attempt,
                MAX_RECOVERY_RETRIES,
                locker_number,
            )

            # Try to reset GPIO - with timeout protection
            try:
                gpio_controller.reset_all()
                time.sleep(0.25)
                gpio_controller.open_locker_window(locker_number, hold_open_seconds=hold_open_seconds)
            except Exception as hw_exc:
                logger.warning("Hardware error during recovery attempt %d: %s", attempt, hw_exc)
                raise HardwareError(f"GPIO operation failed: {hw_exc}") from hw_exc

            # Success - clear assignment
            _clear_locker_assignment(db, locker_id)
            db.execute(
                "INSERT INTO transactions(user_id, locker_id, action, status) VALUES (?, ?, 'RETRIEVE', 'DONE')",
                (user_id, locker_id),
            )
            db.commit()

            logger.info("Recovery succeeded on attempt %d for locker %d", attempt, locker_number)
            _record_recovery_success()
            
            return {
                "success": True,
                "retries": attempt,
                "manual_action_required": False,
                "locker_id": locker_id,
                "locker_number": locker_number,
                "locker_group": locker["locker_group"],
            }

        except Exception as exc:
            _safe_rollback(db)
            last_exception = exc
            logger.warning(
                "Recovery attempt %d/%d failed for locker %d: %s",
                attempt,
                MAX_RECOVERY_RETRIES,
                locker_id,
                exc
            )
            
            # Don't sleep after the last attempt
            if attempt < MAX_RECOVERY_RETRIES:
                # Exponential backoff: delay = base * (2 ^ attempt-1), capped at max
                delay = min(RECOVERY_BASE_DELAY * (2 ** (attempt - 1)), RECOVERY_MAX_DELAY)
                logger.debug("Waiting %.2f seconds before retry...", delay)
                time.sleep(delay)

    # All retries exhausted
    logger.error(
        "All %d recovery attempts failed for locker %d. Last error: %s",
        MAX_RECOVERY_RETRIES,
        locker_id,
        last_exception
    )
    
    # Record failure for circuit breaker
    _record_recovery_failure()
    
    return {
        "success": False,
        "retries": MAX_RECOVERY_RETRIES,
        "manual_action_required": True,
        "error": str(last_exception) if last_exception else "Unknown error"
    }


def cleanup_expired_sessions(max_age_minutes: int = 120) -> int:
    """Release lockers held by sessions older than *max_age_minutes*."""
    from datetime import datetime, timedelta

    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()

    stale = db.execute(
        """
        SELECT s.id AS session_id, s.locker_id, s.user_id
        FROM   sessions s
        WHERE  s.status = 'active'
          AND  s.created_at < ?
        LIMIT  200
        """,
        (cutoff,),
    ).fetchall()

    cleaned = 0
    for row in stale:
        try:
            if row["locker_id"]:
                _clear_locker_assignment(db, int(row["locker_id"]))
            db.execute(
                """
                UPDATE sessions
                SET    status = 'canceled',
                       completed_at = datetime('now')
                WHERE  id = ?
                """,
                (row["session_id"],),
            )
            db.execute(
                """
                INSERT INTO activity_logs(timestamp, activity_type, locker_id, user_id, details, status)
                VALUES (datetime('now'), 'session_timeout', ?, ?, ?, 'warning')
                """,
                (
                    row["locker_id"],
                    row["user_id"],
                    f'{{"session_id": {row["session_id"]}, "reason": "auto_cleanup"}}',
                ),
            )
            cleaned += 1
        except Exception as exc:
            logger.error("Failed to clean session %d: %s", row["session_id"], exc)

    if cleaned:
        db.commit()
        logger.info("Session cleanup released %d expired session(s)", cleaned)

    return cleaned


def count_occupied_lockers() -> int:
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS c FROM lockers WHERE status = 'occupied'").fetchone()
    return int(row["c"])


def list_lockers_with_status() -> List[Dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT locker_number, locker_group, is_occupied, status, label,
               updated_at, current_user_id, last_opened_at
        FROM lockers
        ORDER BY locker_number ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]
