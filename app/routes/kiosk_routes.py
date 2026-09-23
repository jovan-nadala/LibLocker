"""Static kiosk page routes."""

from pathlib import Path

from flask import Blueprint, current_app, send_from_directory

kiosk_bp = Blueprint("kiosk", __name__)

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "assets"
PAGES_DIR = ROOT / "pages"


def _evidence_dir() -> Path:
    """Resolve evidence directory from config."""
    configured = Path(current_app.config.get("EVIDENCE_PHOTOS_DIR", ROOT / "instance" / "evidence"))
    if configured.is_absolute():
        return configured
    return (ROOT / configured).resolve()


@kiosk_bp.get("/")
def landing():
    """Serve landing page."""
    return send_from_directory(ROOT, "index.html")


@kiosk_bp.get("/home")
def home():
    """Serve kiosk home menu."""
    return send_from_directory(PAGES_DIR, "home.html")


@kiosk_bp.get("/dashboard")
def dashboard():
    """Serve kiosk dashboard page."""
    return send_from_directory(PAGES_DIR, "dashboard.html")


@kiosk_bp.get("/register_complete")
def register_complete():
    """Serve registration complete page."""
    return send_from_directory(PAGES_DIR, "register_complete.html")


@kiosk_bp.get("/monitor")
def monitor():
    """Serve database monitoring dashboard."""
    return send_from_directory(PAGES_DIR, "monitor.html")


@kiosk_bp.get("/assets/<path:filename>")
def assets(filename: str):
    """Serve shared asset files."""
    return send_from_directory(ASSETS_DIR, filename)


@kiosk_bp.get("/pages/<path:filename>")
def pages(filename: str):
    """Serve kiosk flow pages."""
    return send_from_directory(PAGES_DIR, filename)


@kiosk_bp.get("/evidence/<path:filename>")
def evidence(filename: str):
    """Serve stored evidence photos."""
    return send_from_directory(_evidence_dir(), filename)
