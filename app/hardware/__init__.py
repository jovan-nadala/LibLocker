"""Hardware abstraction and factory for LibLocker.

Production deployment: Real Pi hardware (RC522 RFID, GPIO relay, Picamera2).
Components are created lazily so an RFID read does not fail just because
the relay controller or camera stack has its own init issue.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from flask import current_app, g

from .camera import PiCamera
from .gpio_controller import PiGPIOController
from .mock import MockGPIOController
from .rfid_reader import HFReader


@dataclass
class HardwareBundle:
    """Container for hardware adapters with lazy construction.
    
    Supports context manager protocol for proper resource cleanup.
    """

    _rfid_factory: Callable[[], Any]
    _gpio_factory: Callable[[], Any]
    _cam_factory: Callable[[], Any]
    _rfid: Any | None = field(default=None, init=False, repr=False)
    _gpio: Any | None = field(default=None, init=False, repr=False)
    _cam: Any | None = field(default=None, init=False, repr=False)

    @property
    def rfid(self) -> Any:
        if self._rfid is None:
            self._rfid = self._rfid_factory()
        return self._rfid

    @property
    def gpio(self) -> Any:
        if self._gpio is None:
            self._gpio = self._gpio_factory()
        return self._gpio

    @property
    def cam(self) -> Any:
        if self._cam is None:
            self._cam = self._cam_factory()
        return self._cam
    
    def cleanup(self) -> None:
        """Cleanup all hardware resources.
        
        Should be called before application shutdown to properly
        release all hardware resources (GPIO, camera, RFID).
        """
        if self._gpio is not None:
            try:
                if hasattr(self._gpio, 'cleanup'):
                    self._gpio.cleanup()
            except Exception as e:
                # Use print instead of logger since this might be called during shutdown
                print(f"Warning: Error cleaning up GPIO: {e}")
            self._gpio = None
        
        if self._cam is not None:
            try:
                if hasattr(self._cam, 'cleanup'):
                    self._cam.cleanup()
            except Exception as e:
                print(f"Warning: Error cleaning up camera: {e}")
            self._cam = None
        
        if self._rfid is not None:
            try:
                if hasattr(self._rfid, 'cleanup'):
                    self._rfid.cleanup()
            except Exception as e:
                print(f"Warning: Error cleaning up RFID: {e}")
            self._rfid = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False  # Don't suppress exceptions



def _config_bool(key: str, default: bool = False) -> bool:
    """Read boolean-ish values from Flask config safely."""
    value = current_app.config.get(key, default)

    if isinstance(value, bool):
        return value

    if value is None:
        return default

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _config_int(key: str, default: int) -> int:
    """Read integer config safely."""
    value = current_app.config.get(key, default)

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_float(key: str, default: float) -> float:
    """Read float config safely."""
    value = current_app.config.get(key, default)

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_hardware() -> HardwareBundle:
    """Prepare lazy factories for the configured hardware stack."""
    hardware_mode = str(current_app.config.get("HARDWARE_MODE", "PI")).strip().upper()

    hf_enabled = _config_bool("HF_RFID_ENABLED", True)

    cam_enabled = _config_bool("CAMERA_ENABLED", True)
    pulse = _config_float("GPIO_PULSE_DURATION", 0.5)
    active_high = _config_bool("GPIO_ACTIVE_HIGH", True)
    use_i2c = _config_bool("GPIO_USE_I2C", False)
    i2c_driver = current_app.config.get("GPIO_I2C_DRIVER", "relay_board")
    i2c_address = current_app.config.get("GPIO_I2C_ADDRESS", "0x20")
    relay_i2c_addresses = current_app.config.get("GPIO_RELAY_I2C_ADDRESSES", "")
    active_locker_count = _config_int("ACTIVE_LOCKER_COUNT", 24)
    photos_dir = current_app.config.get("EVIDENCE_PHOTOS_DIR", "instance/evidence")

    hardware_cache = current_app.extensions.setdefault("liblocker_hardware_cache", {})

    def build_rfid() -> Any:
        if "rfid" in hardware_cache:
            return hardware_cache["rfid"]

        if hf_enabled:
            current_app.logger.info("Initializing HF RFID reader")
            hardware_cache["rfid"] = HFReader()
            return hardware_cache["rfid"]

        raise RuntimeError("No RFID reader enabled. Enable HF_RFID_ENABLED.")

    def build_gpio() -> Any:
        if "gpio" not in hardware_cache:
            if hardware_mode in {"DEV", "MOCK", "TEST"}:
                current_app.logger.info(
                    "Using MockGPIOController (hardware mode: %s)",
                    hardware_mode,
                )
                hardware_cache["gpio"] = MockGPIOController()
            else:
                try:
                    hardware_cache["gpio"] = PiGPIOController(
                        pulse_duration=float(pulse),
                        active_high=bool(active_high),
                        use_i2c=bool(use_i2c),
                        i2c_driver=str(i2c_driver),
                        i2c_address=str(i2c_address),
                        active_locker_count=int(active_locker_count),
                        relay_i2c_addresses=str(relay_i2c_addresses),
                    )
                except Exception as gpio_exc:
                    current_app.logger.warning(
                        "Failed to initialize PiGPIOController: %s. "
                        "Falling back to MockGPIOController.",
                        gpio_exc,
                    )
                    hardware_cache["gpio"] = MockGPIOController()

        return hardware_cache["gpio"]

    def build_cam() -> Any:
        if "cam" not in hardware_cache:
            hardware_cache["cam"] = PiCamera(
                enabled=bool(cam_enabled),
                photos_dir=str(photos_dir),
            )

        return hardware_cache["cam"]

    return HardwareBundle(
        _rfid_factory=build_rfid,
        _gpio_factory=build_gpio,
        _cam_factory=build_cam,
    )


def get_hardware() -> HardwareBundle:
    """Return a request-scoped hardware bundle."""
    if "hardware_bundle" not in g:
        g.hardware_bundle = _build_hardware()

    return g.hardware_bundle