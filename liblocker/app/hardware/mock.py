"""Mock hardware implementations for DEV mode."""

from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MOCK_PLACEHOLDER_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD9U6KKKAP/2Q=="
)


class MockRFIDReader:
    """Mock RFID reader that returns a fixed UID after a tiny delay."""

    def __init__(self, fixed_uid: str = "TEST-TAG-0001"):
        self.fixed_uid = fixed_uid
        self.available = True
        self.last_error = ""

    def read_rfid_once(self, timeout: float = 0.15) -> str:
        time.sleep(max(float(timeout), 0.01))
        logger.debug("[MOCK] RFID read -> %s", self.fixed_uid)
        return self.fixed_uid

    def read_uid(self, timeout: float = 10.0) -> str:
        return self.read_rfid_once(timeout=timeout)

    def read_no_block(self) -> Optional[str]:
        return self.fixed_uid

    def cleanup(self) -> None:
        pass


class MockGPIOController:
    """Mock locker controller that mirrors the real GPIO controller API."""

    LOCKER_GPIO_MAP: Dict[int, int] = {i: 0 for i in range(1, 25)}
    SENSOR_GPIO_MAP: Dict[int, int] = {}

    def __init__(self, **kwargs):
        self._relay_unlocked: Dict[int, bool] = {}
        self._door_closed: Dict[int, bool] = {}
        self.initialized = True
        logger.info("[MOCK] GPIO controller initialised")

    def unlock_locker(self, locker_number: int) -> bool:
        if not 1 <= locker_number <= 24:
            raise ValueError(f"Invalid locker number {locker_number!r}")
        self._relay_unlocked[locker_number] = True
        return True

    def lock_locker(self, locker_number: int, cancel_window: bool = True) -> bool:
        _ = cancel_window
        if not 1 <= locker_number <= 24:
            raise ValueError(f"Invalid locker number {locker_number!r}")
        self._relay_unlocked[locker_number] = False
        return True

    def open_locker(self, locker_number: int, hold_open_seconds: Optional[float] = None) -> bool:
        self.unlock_locker(locker_number)
        time.sleep(min(float(hold_open_seconds or 0.15), 0.3))
        self.lock_locker(locker_number, cancel_window=False)
        logger.info("[MOCK] Locker %d pulsed open (simulated)", locker_number)
        return True

    def open_locker_window(self, locker_number: int, hold_open_seconds: Optional[float] = None) -> bool:
        if not 1 <= locker_number <= 24:
            raise ValueError(f"Invalid locker number {locker_number!r}")

        self.unlock_locker(locker_number)
        self._door_closed[locker_number] = False

        def _relock() -> None:
            time.sleep(min(float(hold_open_seconds or 1.0), 1.0))
            self._door_closed[locker_number] = True
            self.lock_locker(locker_number, cancel_window=False)

        threading.Thread(
            target=_relock,
            name=f"mock-relock-{locker_number}",
            daemon=True,
        ).start()
        logger.info("[MOCK] Locker %d opened for access window (simulated)", locker_number)
        return True

    def open_multiple_lockers(self, locker_numbers: List[int]) -> Dict[str, List[int]]:
        success, failed = [], []
        for locker_number in locker_numbers:
            try:
                self.open_locker_window(locker_number)
                success.append(locker_number)
            except Exception:
                failed.append(locker_number)
        return {"success": success, "failed": failed}

    def reset_all(self) -> None:
        """Reset all mock GPIO states."""
        self._relay_unlocked.clear()
        self._door_closed.clear()

    def cleanup(self) -> None:
        """Cleanup mock GPIO resources."""
        self.reset_all()
