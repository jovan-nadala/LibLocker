"""Application factory for LibLocker."""

import logging
import threading
import time

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from .admin.api import admin_api_bp
from .admin.routes import admin_pages_bp
from .auth import init_admin_auth
from .auth.routes import auth_bp
from .config import Config
from .db import init_db, register_db
from .gpio_validator import check_hardware_setup, validate_gpio_configuration
from .routes.api_routes import api_bp
from .routes.kiosk_routes import kiosk_bp
from .services.rfid_capture_service import init_rfid_capture_manager

logger = logging.getLogger(__name__)


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)

    # Enable CSRF protection
    csrf = CSRFProtect(app)
    
    # Exempt kiosk API routes from CSRF (they use session-based flow without forms)
    csrf.exempt(api_bp)

    register_db(app)
    init_rfid_capture_manager(app)

    with app.app_context():
        init_db()
        init_admin_auth(app)

        check_hardware_setup()
        is_valid, warnings = validate_gpio_configuration()

        if not is_valid:
            for warning in warnings:
                logger.error(warning)

        app.gpio_config_valid = is_valid

    app.register_blueprint(kiosk_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_pages_bp, url_prefix="/admin")
    app.register_blueprint(admin_api_bp, url_prefix="/api/admin")

    from pathlib import Path

    evidence_dir = Path(app.config.get("EVIDENCE_PHOTOS_DIR", "instance/evidence"))
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _start_session_cleanup_thread(app)

    return app


def _start_session_cleanup_thread(app: Flask) -> None:
    """Start a daemon thread that periodically cleans expired sessions."""
    if not _as_bool(app.config.get("ENABLE_SESSION_CLEANUP", True), True):
        logger.info("Session cleanup disabled via config")
        return

    interval = int(app.config.get("SESSION_CLEANUP_INTERVAL_SECONDS", 300))
    max_age = int(app.config.get("SESSION_TIMEOUT_MINUTES", 120))

    def _run() -> None:
        logger.info(
            "Session cleanup thread started – interval=%ds max_age=%dmin",
            interval,
            max_age,
        )

        time.sleep(30)

        while True:
            try:
                with app.app_context():
                    from app.services.locker_service import cleanup_expired_sessions

                    cleaned = cleanup_expired_sessions(max_age_minutes=max_age)

                    if cleaned:
                        logger.info("Auto-cleanup: released %d stale session(s)", cleaned)

            except Exception as exc:
                logger.error("Session cleanup thread error: %s", exc)

            time.sleep(interval)

    thread = threading.Thread(
        target=_run,
        name="liblocker-session-cleanup",
        daemon=True,
    )
    thread.start()