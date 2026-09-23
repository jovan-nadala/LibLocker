#!/usr/bin/env python3
"""RFID reader adapter for LibLocker.

HFReader handles RC522 13.56 MHz cards for user registration and locker access.
"""

from __future__ import annotations

import os
import time

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    GPIO = None  # type: ignore
    HAS_GPIO = False

try:
    from mfrc522 import SimpleMFRC522
    HAS_MFRC522 = True
except ImportError:
    SimpleMFRC522 = None  # type: ignore
    HAS_MFRC522 = False


class HFReader:
    """RC522 RFID reader handler (13.56 MHz, SPI)."""

    def __init__(self):
        self.reader = None
        self.enabled = os.getenv("HF_RFID_ENABLED", "true").lower() == "true"
        self.error_message = ""

        if not self.enabled:
            print("RC522 disabled via HF_RFID_ENABLED=false")
            self.error_message = "HF RFID disabled via HF_RFID_ENABLED=false"
            return

        if not HAS_GPIO:
            print("RPi.GPIO not available (are you on a Raspberry Pi?)")
            self.enabled = False
            self.error_message = "RPi.GPIO not available - are you on a Raspberry Pi?"
            return

        if not HAS_MFRC522:
            print("mfrc522 library not available - install with: pip install mfrc522")
            self.enabled = False
            self.error_message = "mfrc522 library not available - run: pip install mfrc522"
            return

        try:
            self.reader = SimpleMFRC522()
            print("RC522 HF RFID reader initialized")
        except Exception as exc:
            print(f"Failed to initialize RC522: {exc}")
            self.enabled = False
            self.error_message = f"RC522 initialization failed: {exc}"

    @property
    def available(self) -> bool:
        return self.enabled

    def read_uid(self, timeout: float = 10.0):
        if not self.enabled or self.reader is None:
            return self._simulate_read()

        started_at = time.time()

        while (time.time() - started_at) < timeout:
            try:
                card_id = self._read_uid_no_auth()

                if card_id:
                    return hex(card_id)[2:].upper().zfill(12)
            except Exception:
                pass

            time.sleep(0.05)

        return None

    def read_no_block(self):
        if not self.enabled or self.reader is None:
            return None

        try:
            card_id = self._read_uid_no_auth()
            return hex(card_id)[2:].upper().zfill(12) if card_id else None
        except Exception:
            return None

    def _read_uid_no_auth(self):
        if self.reader is None:
            return None

        for method_name in ("read_id_no_block", "read_no_block", "read_id"):
            method = getattr(self.reader, method_name, None)

            if callable(method):
                result = method()

                if isinstance(result, tuple):
                    return result[0]

                return result

        result = self.reader.read()

        if isinstance(result, tuple):
            return result[0]

        return result

    def read_rfid_once(self, timeout: float = 10.0):
        return self.read_uid(timeout)

    def write_text(self, text: str, timeout: float = 10.0) -> bool:
        if not self.enabled or self.reader is None:
            print("Cannot write in simulation mode")
            return False

        started_at = time.time()

        while (time.time() - started_at) < timeout:
            try:
                self.reader.write(text)
                return True
            except Exception:
                time.sleep(0.1)

        return False

    def _simulate_read(self):
        import random

        return "".join(random.choices("0123456789ABCDEF", k=12))

    def cleanup(self):
        """Cleanup GPIO resources used by RFID reader.
        
        Should be called before application shutdown to properly
        release GPIO pins.
        """
        if not HAS_GPIO or GPIO is None:
            return

        try:
            GPIO.cleanup()
            print("✓ RFID reader GPIO cleaned up")
        except Exception as e:
            print(f"Warning: Error cleaning up RFID GPIO: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False  # Don't suppress exceptions


def read_hf_rfid(timeout: float = 10.0):
    """Read HF RFID card UID with timeout."""
    reader = HFReader()

    try:
        return reader.read_uid(timeout)
    finally:
        reader.cleanup()


if __name__ == "__main__":
    reader = HFReader()
    uid = reader.read_uid(timeout=10)
    print(uid or "No card detected")
    reader.cleanup()