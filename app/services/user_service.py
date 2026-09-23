"""User service layer."""

import re
import sqlite3
from typing import Any

from app.db import get_db


class UserServiceError(Exception):
    """Base error for user service."""


class ValidationError(UserServiceError):
    """Raised when request data is invalid."""


class ConflictError(UserServiceError):
    """Raised on uniqueness or resource conflicts."""


def _row_to_dict(row) -> dict[str, Any] | None:
    """Convert SQLite row to plain dict."""
    return dict(row) if row else None


def validate_full_name(full_name: str) -> str:
    """Validate and normalize full name."""
    value = (full_name or "").strip()
    if len(value) < 2 or len(value) > 100:
        raise ValidationError("Full name must be 2 to 100 characters.")
    return value


def validate_student_id(student_id: str) -> str:
    """Validate and normalize student ID with enhanced checks.
    
    Supports both alphanumeric IDs (backwards compatible) and
    institution-specific numeric-only IDs with optional checksum.
    """
    value = (student_id or "").strip()
    
    # Basic format check (alphanumeric, 4-32 chars)
    if not re.fullmatch(r"[A-Za-z0-9\-]{4,32}", value):
        raise ValidationError("Student ID must be 4 to 32 characters (letters, numbers, hyphen).")
    
    # If student ID is numeric-only, optionally validate with Luhn checksum
    if value.replace("-", "").isdigit():
        # Try to validate checksum if configured
        try:
            from flask import current_app
            if current_app.config.get("VALIDATE_STUDENT_ID_CHECKSUM", False):
                # Remove hyphens for checksum calculation
                digits_only = value.replace("-", "")
                if not _validate_luhn_checksum(digits_only):
                    raise ValidationError(
                        "Student ID checksum validation failed. "
                        "Please verify your student ID number."
                    )
        except RuntimeError:
            # No app context (e.g., during testing), skip checksum validation
            pass
    
    return value


def _validate_luhn_checksum(numeric_id: str) -> bool:
    """Validate numeric ID using Luhn algorithm (mod-10 checksum)."""
    if len(numeric_id) < 2:
        return False
    
    digits = [int(d) for d in numeric_id]
    checksum = 0
    reverse_digits = digits[::-1]
    
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:  # Every second digit (from right)
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    
    return checksum % 10 == 0


def validate_rfid_uid(rfid_uid: str) -> str:
    """Validate and normalize RFID UID."""
    value = (rfid_uid or "").strip()
    if len(value) < 4 or len(value) > 64:
        raise ValidationError("RFID UID must be 4 to 64 characters.")
    return value


def create_user(full_name: str, student_id: str, rfid_uid: str) -> dict[str, Any]:
    """Create a new user and return user record."""
    name = validate_full_name(full_name)
    sid = validate_student_id(student_id)
    uid = validate_rfid_uid(rfid_uid)

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users(full_name, student_id, rfid_uid) VALUES(?,?,?)",
            (name, sid, uid),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise ConflictError("Student ID or RFID is already registered.") from exc

    return get_user_by_id(cur.lastrowid)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Get user by ID."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row)


def get_user_by_rfid(rfid_uid: str) -> dict[str, Any] | None:
    """Get user by RFID UID."""
    uid = validate_rfid_uid(rfid_uid)
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE rfid_uid = ?", (uid,)).fetchone()
    return _row_to_dict(row)


def count_users() -> int:
    """Return total number of users."""
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    return int(row["c"])
