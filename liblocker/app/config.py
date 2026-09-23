"""Configuration module for LibLocker."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(
    value: str | None,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default

    return max(minimum, min(parsed, maximum))


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


class Config:
    """Base Flask config loaded from environment variables."""

    BASE_DIR = Path(__file__).resolve().parents[1]

    # --- Core Flask -------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        str(BASE_DIR / "instance" / "liblocker.sqlite"),
    )
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "liblocker-admin-dev")

    # --- Hardware mode ---------------------------------------------------
    HARDWARE_MODE = os.getenv("HARDWARE_MODE", "PI").upper()
    ACTIVE_LOCKER_COUNT = _bounded_int(
        os.getenv("ACTIVE_LOCKER_COUNT"),
        24,
        1,
        24,
    )

    # --- Locker-level sets -----------------------------------------------
    UPPER_LEVEL_LOCKERS = os.getenv(
        "UPPER_LEVEL_LOCKERS",
        "1,2,3,4,5,6,13,14,15,16,17,18",
    )
    LOWER_LEVEL_LOCKERS = os.getenv(
        "LOWER_LEVEL_LOCKERS",
        "7,8,9,10,11,12,19,20,21,22,23,24",
    )

    # --- HF RFID / RC522 -------------------------------------------------
    # Used for kiosk registration and retrieval.
    RFID_READ_TIMEOUT_SECONDS = _safe_int(
        os.getenv("RFID_READ_TIMEOUT_SECONDS"),
        8,
    )
    RFID_READ_INTERVAL_SECONDS = _safe_float(
        os.getenv("RFID_READ_INTERVAL_SECONDS"),
        0.15,
    )
    RFID_BACKGROUND_READ_TIMEOUT_SECONDS = _safe_float(
        os.getenv("RFID_BACKGROUND_READ_TIMEOUT_SECONDS"),
        0.1,
    )
    RFID_SCAN_COOLDOWN_SECONDS = _safe_float(
        os.getenv("RFID_SCAN_COOLDOWN_SECONDS"),
        2.0,
    )
    HF_RFID_ENABLED = _to_bool(os.getenv("HF_RFID_ENABLED"), True)

    # --- GPIO / Relay -----------------------------------------------------
    GPIO_ACTIVE_HIGH = _to_bool(os.getenv("GPIO_ACTIVE_HIGH"), True)
    GPIO_PULSE_DURATION = _safe_float(os.getenv("GPIO_PULSE_DURATION"), 0.5)
    GPIO_DEPOSIT_OPEN_SECONDS = _safe_float(
        os.getenv("GPIO_DEPOSIT_OPEN_SECONDS"),
        5.0,
    )
    GPIO_RETRIEVE_OPEN_SECONDS = _safe_float(
        os.getenv("GPIO_RETRIEVE_OPEN_SECONDS"),
        10.0,
    )

    GPIO_USE_I2C = _to_bool(os.getenv("GPIO_USE_I2C"), False)
    GPIO_I2C_DRIVER = os.getenv("GPIO_I2C_DRIVER", "relay_board")
    GPIO_I2C_ADDRESS = os.getenv("GPIO_I2C_ADDRESS", "0x20")
    GPIO_I2C_BUS = _safe_int(os.getenv("GPIO_I2C_BUS"), 1)
    GPIO_RELAY_I2C_ADDRESSES = os.getenv("GPIO_RELAY_I2C_ADDRESSES", "")

    # --- Camera -----------------------------------------------------------
    CAMERA_ENABLED = _to_bool(os.getenv("CAMERA_ENABLED"), True)
    EVIDENCE_PHOTOS_DIR = os.getenv(
        "EVIDENCE_PHOTOS_DIR",
        str(BASE_DIR / "instance" / "evidence"),
    )
    CAMERA_RESOLUTION_W = _safe_int(os.getenv("CAMERA_RESOLUTION_W"), 1920)
    CAMERA_RESOLUTION_H = _safe_int(os.getenv("CAMERA_RESOLUTION_H"), 1080)

    # --- Session management ----------------------------------------------
    SESSION_TIMEOUT_MINUTES = _safe_int(
        os.getenv("SESSION_TIMEOUT_MINUTES"),
        120,
    )
    SESSION_CLEANUP_INTERVAL_SECONDS = _safe_int(
        os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS"),
        300,
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _to_bool(os.getenv("SESSION_COOKIE_SECURE"), False)

    # --- Feature flags ----------------------------------------------------
    ENABLE_SESSION_CLEANUP = _to_bool(
        os.getenv("ENABLE_SESSION_CLEANUP"),
        True,
    )
    ENABLE_ERROR_RECOVERY = _to_bool(
        os.getenv("ENABLE_ERROR_RECOVERY"),
        True,
    )
    ENABLE_ADMIN_UNLOCK = _to_bool(
        os.getenv("ENABLE_ADMIN_UNLOCK"),
        True,
    )