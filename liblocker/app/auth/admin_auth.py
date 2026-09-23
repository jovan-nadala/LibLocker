"""Secure admin authentication system for LibLocker."""

import logging
import time
from datetime import datetime
from functools import wraps
from typing import Optional, Tuple

from flask import current_app, redirect, session, url_for, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db

logger = logging.getLogger(__name__)

# Brute force protection
BRUTE_FORCE_MAX_ATTEMPTS = 5
BRUTE_FORCE_LOCKOUT_SECONDS = 30
FAILED_ATTEMPTS_KEY = "admin_failed_attempts"
LOCKOUT_TIME_KEY = "admin_lockout_time"


def init_admin_auth(app):
    """Initialize admin authentication on app startup."""
    with app.app_context():
        try:
            create_default_admin()
        except Exception as e:
            logger.error(f"Failed to initialize default admin: {e}")


def _execute_sql(sql: str, params: Optional[Tuple] = None, fetch_one: bool = False):
    """Execute SQL query safely."""
    db = get_db()
    try:
        cursor = db.execute(sql, params or ())
        if fetch_one:
            return cursor.fetchone()
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise


def _ensure_admins_table_exists():
    """Ensure the admins table exists."""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)
    db.commit()


def create_default_admin(
    username: str = "liblocker",
    password: str = "liblocker123"
) -> None:
    """
    Create default admin account if it doesn't exist.
    
    ⚠️  Warning: This uses default credentials. Change immediately in production!
    """
    _ensure_admins_table_exists()
    
    db = get_db()
    
    # Check if admin already exists
    existing = _execute_sql("SELECT id FROM admins WHERE username = ?", (username,), fetch_one=True)
    
    if existing:
        logger.info(f"Admin user '{username}' already exists")
        return
    
    # Create default admin
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    _execute_sql(
        """
        INSERT INTO admins (username, password_hash, created_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (username, password_hash)
    )
    db.commit()
    
    # Print warning to console
    print("\n" + "=" * 70)
    print("⚠️  DEFAULT ADMIN CREDENTIALS IN USE")
    print("=" * 70)
    print(f"Username: {username}")
    print(f"Password: {password}")
    print("\n🔐 IMPORTANT: Change admin credentials immediately in production!")
    print("=" * 70 + "\n")
    
    logger.warning(f"Default admin user '{username}' created with default password. Change immediately!")


def check_admin_credentials(username: str, password: str) -> Tuple[bool, Optional[dict]]:
    """
    Verify admin credentials.
    
    Returns: (success: bool, admin_data: Optional[dict])
    """
    _ensure_admins_table_exists()
    
    # Check brute force protection
    if _is_brute_force_locked():
        return False, None
    
    db = get_db()
    admin = _execute_sql(
        "SELECT id, username, password_hash, is_active FROM admins WHERE username = ?",
        (username,),
        fetch_one=True
    )
    
    if not admin or not admin[3]:  # is_active check
        _record_failed_attempt()
        return False, None
    
    # Verify password
    if check_password_hash(admin[2], password):
        # Clear failed attempts on success
        _clear_failed_attempts()
        
        # Update last login
        db.execute(
            "UPDATE admins SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (admin[0],)
        )
        db.commit()
        
        return True, {
            "id": admin[0],
            "username": admin[1],
        }
    
    _record_failed_attempt()
    return False, None


def _is_brute_force_locked() -> bool:
    """Check if admin account is locked due to brute force."""
    lockout_time = session.get(LOCKOUT_TIME_KEY)
    
    if lockout_time is None:
        return False
    
    elapsed = time.time() - lockout_time
    if elapsed < BRUTE_FORCE_LOCKOUT_SECONDS:
        return True
    
    # Lockout expired, clear it
    session.pop(LOCKOUT_TIME_KEY, None)
    session.pop(FAILED_ATTEMPTS_KEY, None)
    return False


def _record_failed_attempt() -> None:
    """Record a failed login attempt."""
    attempts = session.get(FAILED_ATTEMPTS_KEY, 0)
    attempts += 1
    session[FAILED_ATTEMPTS_KEY] = attempts
    
    if attempts >= BRUTE_FORCE_MAX_ATTEMPTS:
        session[LOCKOUT_TIME_KEY] = time.time()
        logger.warning(f"Admin login brute force detected. Account locked for {BRUTE_FORCE_LOCKOUT_SECONDS}s")


def _clear_failed_attempts() -> None:
    """Clear failed login attempts after successful login."""
    session.pop(FAILED_ATTEMPTS_KEY, None)
    session.pop(LOCKOUT_TIME_KEY, None)


def get_current_admin() -> Optional[dict]:
    """Get the currently logged-in admin."""
    if "admin_logged_in" not in session or "admin_id" not in session:
        return None
    
    db = get_db()
    admin = _execute_sql(
        "SELECT id, username FROM admins WHERE id = ? AND is_active = 1",
        (session["admin_id"],),
        fetch_one=True
    )
    
    if not admin:
        # Clear invalid session
        session.clear()
        return None
    
    return {
        "id": admin[0],
        "username": admin[1],
    }


def admin_required(f):
    """
    Decorator to protect routes that require admin authentication.
    
    For page routes: Redirects to login if not authenticated
    For API routes: Returns 401 JSON response if not authenticated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin = get_current_admin()
        
        if admin is None:
            # Determine if this is an API request or page request
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            
            # Redirect to login page
            return redirect(url_for("auth.admin_login", next=request.url))
        
        return f(*args, **kwargs)
    
    return decorated_function


def login_admin(admin_id: int, admin_username: str) -> None:
    """Set session variables for a logged-in admin and regenerate session ID."""
    # Clear old session data
    session.clear()
    
    # Regenerate session ID to prevent session fixation attacks
    session.modified = True
    
    # Set new session data
    session["admin_logged_in"] = True
    session["admin_id"] = admin_id
    session["admin_username"] = admin_username
    session.permanent = True  # Use permanent session with timeout
    
    logger.info(f"Admin '{admin_username}' logged in successfully")


def logout_admin() -> None:
    """Clear admin session."""
    session.clear()


def get_failed_attempts_remaining() -> int:
    """Get remaining failed attempts before lockout."""
    if _is_brute_force_locked():
        return 0
    
    attempts = session.get(FAILED_ATTEMPTS_KEY, 0)
    return max(0, BRUTE_FORCE_MAX_ATTEMPTS - attempts)


def get_lockout_time_remaining() -> int:
    """Get remaining lockout time in seconds."""
    lockout_time = session.get(LOCKOUT_TIME_KEY)
    
    if lockout_time is None:
        return 0
    
    elapsed = time.time() - lockout_time
    remaining = BRUTE_FORCE_LOCKOUT_SECONDS - elapsed
    
    return max(0, int(remaining))
