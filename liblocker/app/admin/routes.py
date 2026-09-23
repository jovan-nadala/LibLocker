"""Admin dashboard page routes."""

from flask import Blueprint, current_app, redirect, render_template, url_for

from app.auth import admin_required

admin_pages_bp = Blueprint("admin_pages", __name__, template_folder="../templates")


@admin_pages_bp.get("")
@admin_pages_bp.get("/")
def admin_home():
    return redirect(url_for("admin_pages.dashboard"))


@admin_pages_bp.get("/dashboard")
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        page_key="dashboard",
        locker_capacity=current_app.config.get("ACTIVE_LOCKER_COUNT", 24),
    )


@admin_pages_bp.get("/lockers")
@admin_required
def lockers():
    return render_template("admin/lockers.html", page_key="lockers")


@admin_pages_bp.get("/users")
@admin_required
def users():
    return render_template("admin/users.html", page_key="users")


@admin_pages_bp.get("/logs")
@admin_required
def logs():
    return render_template("admin/logs.html", page_key="logs")


@admin_pages_bp.get("/unauthorized")
def unauthorized():
    return render_template("admin/unauthorized.html"), 403
