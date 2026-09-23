"""Admin authentication module."""

from .admin_auth import (
    admin_required,
    check_admin_credentials,
    create_default_admin,
    get_current_admin,
    get_failed_attempts_remaining,
    get_lockout_time_remaining,
    init_admin_auth,
    login_admin,
    logout_admin,
)

__all__ = [
    "admin_required",
    "check_admin_credentials",
    "create_default_admin",
    "get_current_admin",
    "get_failed_attempts_remaining",
    "get_lockout_time_remaining",
    "init_admin_auth",
    "login_admin",
    "logout_admin",
]
