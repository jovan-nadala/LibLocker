"""Admin dashboard routes."""

from flask import Blueprint, render_template

from app.services.audit_service import list_recent_logs
from app.services.locker_service import count_occupied_lockers, list_lockers_with_status
from app.services.user_service import count_users

admin_bp = Blueprint("admin", __name__, template_folder="../templates")


@admin_bp.get("/")
def dashboard():
    """Render admin dashboard summary."""
    total_users = count_users()
    occupied = count_occupied_lockers()
    lockers = list_lockers_with_status()
    total_lockers = len(lockers)
    return render_template(
        "admin/dashboard.html",
        users=total_users,
        occupied=occupied,
        total_lockers=total_lockers,
    )


@admin_bp.get("/lockers")
def lockers():
    """Render locker status table."""
    rows = list_lockers_with_status()
    return render_template("admin/lockers.html", lockers=rows)


@admin_bp.get("/logs")
def logs():
    """Render latest audit logs."""
    rows = list_recent_logs(limit=200)
    return render_template("admin/logs.html", logs=rows)
