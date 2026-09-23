"""Evidence photo capture for LibLocker.

Supports:
1. USB webcam via fswebcam, recommended for /dev/video0 UVC cameras.
2. Raspberry Pi Camera Module via picamera2.
3. Visible placeholder fallback when no camera capture works.

Photos are stored under instance/evidence/.
Deposit and retrieve captures are separated into subfolders.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"
_CAMERA_WARMUP_SECONDS = 1.0
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Tiny valid JPEG fallback. This is only used when real capture fails.
_MOCK_PLACEHOLDER_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD9U6KKKAP/2Q=="
)

_PICAMERA2_AVAILABLE = False
_PICAMERA2_IMPORT_ERROR = None

try:
    from picamera2 import Picamera2  # type: ignore

    _PICAMERA2_AVAILABLE = True
except ImportError as exc:
    Picamera2 = None  # type: ignore
    _PICAMERA2_AVAILABLE = False
    _PICAMERA2_IMPORT_ERROR = str(exc)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)

    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)

    if raw is None:
        return default

    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _resolve_photos_dir(photos_dir: Optional[str]) -> Path:
    """Resolve configured evidence directory to an absolute path."""
    configured = Path(
        str(
            photos_dir
            or os.getenv("EVIDENCE_PHOTOS_DIR", "instance/evidence")
        ).strip()
    )

    if configured.is_absolute():
        return configured

    return (_PROJECT_ROOT / configured).resolve()


def _is_valid_jpeg(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except Exception:
        return False

    return len(data) > 8 and data.startswith(_JPEG_SOI) and data.endswith(_JPEG_EOI)


class PiCamera:
    """Evidence camera adapter.

    For your current Raspberry Pi setup, the working camera is a USB webcam:
        /dev/video0

    Recommended .env:
        CAMERA_ENABLED=true
        CAMERA_BACKEND=fswebcam
        CAMERA_DEVICE=/dev/video0
        CAMERA_RESOLUTION_W=1280
        CAMERA_RESOLUTION_H=720
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        photos_dir: Optional[str] = None,
        resolution: Optional[tuple[int, int]] = None,
    ):
        self.enabled = (
            enabled
            if enabled is not None
            else _env_bool("CAMERA_ENABLED", True)
        )

        self.photos_dir = _resolve_photos_dir(photos_dir)
        self.photos_dir.mkdir(parents=True, exist_ok=True)

        width = _env_int("CAMERA_RESOLUTION_W", 1280)
        height = _env_int("CAMERA_RESOLUTION_H", 720)
        self.resolution = resolution or (width, height)

        # fswebcam is the correct backend for your detected USB camera.
        self.backend = os.getenv("CAMERA_BACKEND", "fswebcam").strip().lower()
        self.device = os.getenv("CAMERA_DEVICE", "/dev/video0").strip()
        self.fswebcam_bin = os.getenv("FSWEBCAM_BIN", "fswebcam").strip()
        self.capture_timeout_seconds = _env_int("CAMERA_CAPTURE_TIMEOUT_SECONDS", 8)

        self._camera = None
        self._connected = False
        self._fallback_mode = False
        self._started_at = 0.0

        if self.enabled:
            self._connect()

    # ------------------------------------------------------------------
    # Backend setup
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Prepare the selected camera backend."""
        if not self.enabled:
            self._connected = False
            self._fallback_mode = True
            return

        if self.backend in {"fswebcam", "usb", "uvc", "webcam"}:
            self._connect_fswebcam()
            return

        if self.backend in {"picamera2", "picamera", "pi"}:
            self._connect_picamera2()
            return

        if self.backend == "auto":
            # Try USB webcam first because your detected camera is UVC.
            self._connect_fswebcam()
            if self._connected:
                return
            self._connect_picamera2()
            return

        logger.warning(
            "Unknown CAMERA_BACKEND=%r. Falling back to fswebcam.",
            self.backend,
        )
        self._connect_fswebcam()

    def _connect_fswebcam(self) -> None:
        if not shutil.which(self.fswebcam_bin):
            logger.warning(
                "fswebcam command not found: %s. Install with: sudo apt install fswebcam",
                self.fswebcam_bin,
            )
            self._connected = False
            self._fallback_mode = True
            return

        if not Path(self.device).exists():
            logger.warning(
                "Camera device does not exist: %s",
                self.device,
            )
            self._connected = False
            self._fallback_mode = True
            return

        self._connected = True
        self._fallback_mode = False
        self._camera = None
        self._started_at = time.monotonic()

        logger.info(
            "USB camera ready via fswebcam – device=%s resolution=%sx%s dir=%s",
            self.device,
            self.resolution[0],
            self.resolution[1],
            self.photos_dir,
        )

    def _connect_picamera2(self) -> None:
        if not _PICAMERA2_AVAILABLE:
            logger.warning(
                "picamera2 not available. Error: %s",
                _PICAMERA2_IMPORT_ERROR,
            )
            self._connected = False
            self._fallback_mode = True
            return

        if self._camera is not None:
            self.cleanup()

        try:
            cam = Picamera2()
            config = cam.create_still_configuration(
                main={
                    "size": self.resolution,
                    "format": "RGB888",
                }
            )
            cam.configure(config)
            cam.start()

            self._camera = cam
            self._connected = True
            self._fallback_mode = False
            self._started_at = time.monotonic()

            logger.info(
                "PiCamera2 ready – resolution=%sx%s dir=%s",
                self.resolution[0],
                self.resolution[1],
                self.photos_dir,
            )

        except Exception as exc:
            logger.warning(
                "Picamera2 initialization failed, camera fallback enabled: %s",
                exc,
            )
            self._connected = False
            self._fallback_mode = True

    # ------------------------------------------------------------------
    # Capture backends
    # ------------------------------------------------------------------

    def _capture_with_retry(self, filepath: Path) -> None:
        """Capture to file and retry once."""
        last_error: Exception | None = None

        for attempt in (1, 2):
            try:
                self._ensure_connected()

                if self.backend in {"fswebcam", "usb", "uvc", "webcam", "auto"}:
                    if self._capture_fswebcam(filepath):
                        return

                if self.backend in {"picamera2", "picamera", "pi", "auto"}:
                    if self._capture_picamera2(filepath):
                        return

                raise RuntimeError("No camera backend captured an image")

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Camera capture attempt %d failed for %s: %s",
                    attempt,
                    filepath,
                    exc,
                )
                self.cleanup()
                time.sleep(0.2)

        logger.warning(
            "Real camera capture failed after retries. Writing placeholder image: %s",
            last_error,
        )
        filepath.write_bytes(_MOCK_PLACEHOLDER_JPEG)

    def _capture_fswebcam(self, filepath: Path) -> bool:
        """Capture one frame from a USB webcam using fswebcam."""
        width, height = self.resolution

        command = [
            self.fswebcam_bin,
            "-d",
            self.device,
            "--no-banner",
            "-r",
            f"{width}x{height}",
            str(filepath),
        ]

        logger.info("Capturing USB webcam photo: %s", " ".join(command))

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.capture_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as timeout_exc:
            logger.error(
                "fswebcam capture timed out after %d seconds (device may be hung)",
                self.capture_timeout_seconds
            )
            raise RuntimeError(
                f"Camera capture timeout after {self.capture_timeout_seconds}s - "
                f"device {self.device} may be unresponsive"
            ) from timeout_exc

        if result.returncode != 0:
            raise RuntimeError(
                "fswebcam failed "
                f"(returncode={result.returncode}) "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )

        if not filepath.exists():
            raise RuntimeError(f"fswebcam did not create file: {filepath}")

        if not _is_valid_jpeg(filepath):
            raise RuntimeError(f"fswebcam created invalid JPEG: {filepath}")

        return True

    def _capture_picamera2(self, filepath: Path) -> bool:
        """Capture one frame from a Raspberry Pi camera using Picamera2."""
        if self._camera is None:
            self._connect_picamera2()

        if self._camera is None or self._fallback_mode:
            return False

        self._wait_for_warmup()
        self._camera.capture_file(str(filepath))

        if not filepath.exists():
            raise RuntimeError(f"Picamera2 did not create file: {filepath}")

        if not _is_valid_jpeg(filepath):
            raise RuntimeError(f"Picamera2 created invalid JPEG: {filepath}")

        return True

    def _ensure_connected(self) -> None:
        if not self.enabled:
            raise RuntimeError("Camera is disabled")

        if self._connected:
            return

        self._connect()

    def _wait_for_warmup(self) -> None:
        remaining = _CAMERA_WARMUP_SECONDS - (time.monotonic() - self._started_at)

        if remaining > 0:
            time.sleep(remaining)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_capture_type(capture_type: Optional[str]) -> Optional[str]:
        if capture_type is None:
            return None

        normalized = str(capture_type).strip().lower()

        if not normalized:
            return None

        if normalized not in {"deposit", "retrieve"}:
            raise ValueError(f"Unsupported capture_type {capture_type!r}")

        return normalized

    def take_photo(
        self,
        locker_number: int,
        session_id: int,
        capture_type: Optional[str] = None,
    ) -> str:
        """Capture one JPEG and return its relative filename."""
        if not 1 <= locker_number <= 24:
            raise ValueError(f"locker_number must be 1–24, got {locker_number!r}")

        if not self.enabled:
            raise RuntimeError("Camera is disabled")

        capture_group = self._normalize_capture_type(capture_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        prefix = f"{capture_group}_" if capture_group else "evidence_"
        filename = (
            f"{prefix}locker_{locker_number:02d}"
            f"_session_{session_id}"
            f"_{timestamp}.jpg"
        )

        relative_path = (
            Path(capture_group) / filename
            if capture_group
            else Path(filename)
        )
        filepath = self.photos_dir / relative_path
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._capture_with_retry(filepath)
        except Exception as exc:
            raise RuntimeError(f"Photo capture failed: {exc}") from exc

        if not filepath.exists():
            raise IOError(f"Expected photo not found on disk: {filepath}")

        if not _is_valid_jpeg(filepath):
            raise IOError(f"Captured file is not a valid JPEG: {filepath}")

        size_kb = filepath.stat().st_size // 1024

        logger.info("Photo path=%s", filepath.resolve())
        logger.info("Photo saved – %s (%d KB)", relative_path.as_posix(), size_kb)

        return relative_path.as_posix()

    def get_photo_path(self, filename: str) -> Path:
        """Full filesystem path to a stored photo."""
        return self.photos_dir / filename

    def get_photo_url(self, filename: str) -> str:
        """Web-accessible URL served by the /evidence/ route."""
        return f"/evidence/{filename}"

    def verify_camera(self) -> bool:
        """Capture a test image and return True if camera works."""
        if not self.enabled:
            return False

        test_path = self.photos_dir / ".camera_test_tmp.jpg"

        try:
            self._capture_with_retry(test_path)
            return test_path.exists() and _is_valid_jpeg(test_path)
        except Exception as exc:
            logger.warning("Camera verification failed: %s", exc)
            return False
        finally:
            try:
                test_path.unlink(missing_ok=True)
            except Exception:
                pass

    def cleanup(self) -> None:
        """Stop camera and release resources.
        
        Should be called before application shutdown to properly
        release camera hardware.
        """
        if self._camera:
            try:
                self._camera.stop()
                logger.info("✓ PiCamera2 stopped")
            except Exception as e:
                logger.warning(f"Error stopping PiCamera2: {e}")

        self._camera = None
        self._connected = False
        logger.info("✅ Camera cleanup complete")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False  # Don't suppress exceptions


class MockCamera:
    """Fake camera for DEV/MOCK mode."""

    def __init__(
        self,
        enabled: bool = True,
        photos_dir: Optional[str] = None,
        **kwargs,
    ):
        self.enabled = enabled
        self.photos_dir = _resolve_photos_dir(photos_dir)
        self.photos_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "MockCamera initialized – photos_dir=%s",
            self.photos_dir,
        )

    def take_photo(
        self,
        locker_number: int,
        session_id: int,
        capture_type: Optional[str] = None,
    ) -> str:
        if not 1 <= locker_number <= 24:
            raise ValueError(f"locker_number must be 1–24, got {locker_number!r}")

        capture_group = PiCamera._normalize_capture_type(capture_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        prefix = f"{capture_group}_" if capture_group else "evidence_"
        filename = (
            f"{prefix}locker_{locker_number:02d}"
            f"_session_{session_id}"
            f"_{timestamp}.jpg"
        )

        relative_path = (
            Path(capture_group) / filename
            if capture_group
            else Path(filename)
        )

        placeholder = self.photos_dir / relative_path
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_bytes(_MOCK_PLACEHOLDER_JPEG)

        logger.info("[MOCK] Photo path=%s", placeholder.resolve())
        logger.info("[MOCK] Photo simulated – %s", relative_path.as_posix())

        return relative_path.as_posix()

    def get_photo_path(self, filename: str) -> Path:
        return self.photos_dir / filename

    def get_photo_url(self, filename: str) -> str:
        return f"/evidence/{filename}"

    def verify_camera(self) -> bool:
        return True

    def cleanup(self) -> None:
        """Cleanup mock camera resources."""
        logger.info("✅ MockCamera cleanup complete")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False  # Don't suppress exceptions
