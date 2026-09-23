"""Background RFID capture manager used by kiosk registration flow."""

from __future__ import annotations

import atexit
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from flask import current_app

from app.hardware.rfid_reader import HFReader

_EXTENSION_KEY = "rfid_capture_manager"
_FALLBACK_UID = "04A1B23C9F"


def _as_bool(value: Any, default: bool = False) -> bool:
    """Parse truthy/falsey values from config."""
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_uid(uid: str) -> str:
    """Normalize arbitrary UID-like strings into uppercase hex."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", str(uid or "")).upper()
    return cleaned if len(cleaned) >= 6 else _FALLBACK_UID


@dataclass
class _CaptureState:
    active: bool = False
    uid: str | None = None
    started_at: float = 0.0
    captured_at: float = 0.0


class RFIDCaptureManager:
    """Thread-safe, non-blocking RFID capture state manager."""

    def __init__(self, config: dict[str, Any]):
        self._read_interval_seconds = float(config.get("RFID_READ_INTERVAL_SECONDS", 0.15))
        self._read_timeout_seconds = float(config.get("RFID_BACKGROUND_READ_TIMEOUT_SECONDS", 0.1))
        self._scan_cooldown_seconds = float(config.get("RFID_SCAN_COOLDOWN_SECONDS", 2.0))

        self._lock = threading.Lock()
        self._sessions: dict[str, _CaptureState] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_scan_at = 0.0

        self._reader: Any = None
        self._reader_available = True
        self._reader_error = ""
        self._init_reader()

    def _init_reader(self) -> None:
        """Initialize production RFID hardware reader."""
        try:
            reader = HFReader()
            
            if not getattr(reader, "available", False):
                self._reader_available = False
                self._reader_error = getattr(reader, "error_message", "RFID reader unavailable.")
                self._reader = None
                return
                
            self._reader = reader
            self._reader_available = True
            self._reader_error = ""
            
        except Exception as exc:
            import traceback
            print("\n❌ RFID READER INITIALIZATION FAILED:")
            traceback.print_exc()
            
            self._reader_available = False
            self._reader_error = str(exc)
            self._reader = None

    def ensure_started(self) -> None:
        """Start the background polling thread if it is not running yet."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="liblocker-rfid-capture",
                daemon=True,
            )
            self._thread.start()

    def shutdown(self) -> None:
        """Stop background thread."""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.5)

    def is_reader_available(self) -> bool:
        """Return whether RFID reader stack is available."""
        return self._reader_available

    def reader_error(self) -> str:
        """Return last reader availability error."""
        return self._reader_error

    def start_capture(self, capture_key: str) -> None:
        """Activate capture window for a browser session key."""
        self.ensure_started()
        now = time.monotonic()
        with self._lock:
            state = self._sessions.get(capture_key) or _CaptureState()
            state.active = True
            state.uid = None
            state.started_at = now
            state.captured_at = 0.0
            self._sessions[capture_key] = state

    def poll_capture(self, capture_key: str) -> str | None:
        """Return last captured UID for a session, if any."""
        with self._lock:
            state = self._sessions.get(capture_key)
            if not state:
                return None
            return state.uid

    def clear_capture(self, capture_key: str) -> None:
        """Clear capture state for a session key."""
        with self._lock:
            state = self._sessions.get(capture_key)
            if not state:
                return
            state.active = False
            state.uid = None
            state.started_at = 0.0
            state.captured_at = 0.0

    def queue_mock_uid(self, uid: str | None = None) -> bool:
        """Not supported in production mode."""
        return False

    def _capture_candidates(self) -> list[str]:
        with self._lock:
            return [
                key
                for key, state in self._sessions.items()
                if state.active and not state.uid
            ]

    def _read_uid(self) -> str | None:
        """Read one UID from production RFID hardware."""
        if not self._reader_available:
            return None

        if self._reader is None:
            return None

        try:
            uid = self._reader.read_rfid_once(timeout=self._read_timeout_seconds)
            if not uid:
                return None
            return _normalize_uid(uid)
        except Exception as exc:
            self._reader_available = False
            self._reader_error = str(exc)
            return None

    def _run(self) -> None:
        """Read tags continuously and publish to active capture sessions."""
        while not self._stop_event.is_set():
            capture_keys = self._capture_candidates()
            if not capture_keys:
                self._stop_event.wait(self._read_interval_seconds)
                continue

            if not self._reader_available:
                self._stop_event.wait(self._read_interval_seconds)
                continue

            now = time.monotonic()
            if (now - self._last_scan_at) < self._scan_cooldown_seconds:
                self._stop_event.wait(self._read_interval_seconds)
                continue

            uid = self._read_uid()
            if uid:
                self._last_scan_at = time.monotonic()
                with self._lock:
                    captured_at = time.monotonic()
                    for key in capture_keys:
                        state = self._sessions.get(key)
                        if not state or not state.active or state.uid:
                            continue
                        state.uid = uid
                        state.active = False
                        state.captured_at = captured_at

            self._stop_event.wait(self._read_interval_seconds)


def init_rfid_capture_manager(app) -> None:
    """Initialize app-scoped RFID capture manager."""
    manager = RFIDCaptureManager(app.config)
    app.extensions[_EXTENSION_KEY] = manager
    atexit.register(manager.shutdown)


def get_rfid_capture_manager() -> RFIDCaptureManager:
    """Return app-scoped RFID capture manager."""
    manager = current_app.extensions.get(_EXTENSION_KEY)
    if manager is None:
        manager = RFIDCaptureManager(current_app.config)
        current_app.extensions[_EXTENSION_KEY] = manager
        atexit.register(manager.shutdown)

    manager.ensure_started()
    return manager
