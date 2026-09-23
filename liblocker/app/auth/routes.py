"""Authentication routes for admin login/logout."""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

from app.auth import (
    admin_required,
    check_admin_credentials,
    get_current_admin,
    get_failed_attempts_remaining,
    get_lockout_time_remaining,
    login_admin,
    logout_admin,
)

auth_bp = Blueprint("auth", __name__, template_folder="../templates")


@auth_bp.get("/admin/login")
def admin_login():
    """Render admin login page."""
    # If already logged in, redirect to dashboard
    if get_current_admin():
        return redirect(url_for("admin_pages.dashboard"))
    
    next_url = request.args.get("next", "")
    is_locked = get_lockout_time_remaining() > 0
    remaining_attempts = get_failed_attempts_remaining()
    
    return render_template(
        "admin/admin_login.html",
        next_url=next_url,
        is_locked=is_locked,
        remaining_attempts=remaining_attempts,
        lockout_time=get_lockout_time_remaining() if is_locked else 0,
    )


@auth_bp.post("/admin/login")
def admin_login_submit():
    """Handle admin login form submission."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    next_url = (request.form.get("next") or "").strip()
    
    # Check if account is locked
    if get_lockout_time_remaining() > 0:
        return render_template(
            "admin/admin_login.html",
            username=username,
            error="Account temporarily locked. Too many failed attempts. Please try again later.",
            next_url=next_url,
            is_locked=True,
            lockout_time=get_lockout_time_remaining(),
        ), 429
    
    # Validate credentials
    success, admin_data = check_admin_credentials(username, password)
    
    if success and admin_data:
        # Successful login
        login_admin(admin_data["id"], admin_data["username"])
        
        # Redirect to next URL or dashboard
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        
        return redirect(url_for("admin_pages.dashboard"))
    
    # Failed login
    remaining_attempts = get_failed_attempts_remaining()
    error_message = "Invalid username or password."
    
    if remaining_attempts == 0:
        error_message += " Account locked due to multiple failed attempts."
    elif remaining_attempts <= 2:
        error_message += f" {remaining_attempts} attempt(s) remaining."
    
    return render_template(
        "admin/admin_login.html",
        username=username,
        error=error_message,
        next_url=next_url,
        remaining_attempts=remaining_attempts,
    ), 401


@auth_bp.get("/admin/logout")
def admin_logout():
    """Logout the current admin user."""
    logout_admin()
    return redirect(url_for("auth.admin_login"))


@auth_bp.get("/api/admin/auth/check")
@admin_required
def api_check_auth():
    """API endpoint to check if user is authenticated."""
    admin = get_current_admin()
    if admin:
        return jsonify({"authenticated": True, "admin": admin})
    return jsonify({"authenticated": False}), 401


@auth_bp.get("/api/admin/auth/logout")
@admin_required
def api_logout():
    """API endpoint to logout."""
    logout_admin()
    return jsonify({"success": True})
