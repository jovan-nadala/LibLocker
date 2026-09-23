"""GPIO controller for LibLocker using MCP23017 and direct RPi GPIO fallback."""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Thread-safe singleton lock
_singleton_lock = threading.Lock()
_pi_instance = None
_mock_instance = None

# ── RPi NATIVE GPIO BYPASS ───────────────────────────────────────────────
# Maps broken locker numbers to safe Raspberry Pi pins.
# Two maps because the pin-numbering mode may already be set by another
# library (the mfrc522 RFID reader sets BOARD mode). We adapt to whichever
# mode is active instead of forcing one and crashing.
DIRECT_PI_PINS = {
    9: 27,   # Locker 9  -> BCM 27 (Physical Pin 13)
    14: 22,  # Locker 14 -> BCM 22 (Physical Pin 15)
    17: 5    # Locker 17 -> BCM 5  (Physical Pin 29)
}
# Same pins expressed in BOARD (physical header) numbering
DIRECT_PI_PINS_BOARD = {
    9: 13,   # BCM 27 = Physical Pin 13
    14: 15,  # BCM 22 = Physical Pin 15
    17: 29,  # BCM 5  = Physical Pin 29
}

# ── MCP23017 register map ────────────────────────────────────────────────
IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13
OLATA  = 0x14
OLATB  = 0x15

MCP_ADDRESSES = [0x20, 0x21, 0x22]

class GPIOError(Exception): pass
class LockerOpenFailed(GPIOError): pass

@dataclass(frozen=True)
class _LockerPin:
    mcp_index: int
    bit: int

def _build_relay_map() -> Dict[int, _LockerPin]:
    relay_map: Dict[int, _LockerPin] = {}
    locker_number = 1
    for mcp_idx in range(len(MCP_ADDRESSES)):
        for bit in range(8):
            relay_map[locker_number] = _LockerPin(mcp_idx, bit)
            locker_number += 1
    return relay_map

RELAY_MAP = _build_relay_map()
MAX_LOCKERS = len(RELAY_MAP)


class PiGPIOController:
    """Thread-safe singleton GPIO controller for Raspberry Pi.
    
    Uses double-checked locking pattern for thread safety.
    """
    LOCKER_GPIO_MAP = {i: i for i in RELAY_MAP.keys()}
    SENSOR_GPIO_MAP: Dict[int, int] = {}

    def __new__(cls, *args, **kwargs):
        global _pi_instance
        # First check (without lock for performance)
        if _pi_instance is None:
            # Acquire lock for initialization
            with _singleton_lock:
                # Second check (with lock for thread safety)
                if _pi_instance is None:
                    instance = super().__new__(cls)
                    instance._is_setup = False
                    _pi_instance = instance
        return _pi_instance

    def __init__(self, pulse_duration: Optional[float] = None, active_high: Optional[bool] = None, i2c_bus: int = 1, **kwargs):
        if getattr(self, "_is_setup", False):
            return 

        self.pulse_duration = pulse_duration or float(os.getenv("GPIO_PULSE_DURATION", "0.5"))
        _ah_env = os.getenv("GPIO_ACTIVE_HIGH", "false").strip().lower()
        self.active_high = active_high if active_high is not None else _ah_env in ("1", "true", "yes")
        self.i2c_bus = i2c_bus
        self._bus = None
        self._io_lock = threading.Lock()
        self._relay_state: List[int] = []
        self._pending_relock_events: Dict[int, threading.Event] = {}
        self.initialized = False
        self.active_locker_count = MAX_LOCKERS
        self._in_fallback_mode = False
        self.GPIO = None
        self._native_pin_map: Dict[int, int] = {}
        self._native_available = False
        self._is_setup = True
        try:
            self._setup()
        except Exception:
            # Don't leave a poisoned singleton behind - allow a future retry
            global _pi_instance
            self._is_setup = False
            with _singleton_lock:
                _pi_instance = None
            raise

    def _setup(self) -> None:
        # 1. Setup I2C MCP23017s FIRST - this is the critical path for 21 of
        #    24 lockers and does not depend on RPi.GPIO. A failure here is fatal.
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self.i2c_bus)
        except Exception as exc:
            raise GPIOError(f"Cannot open I2C bus {self.i2c_bus}: {exc}") from exc

        inactive_mcp = 0x00 if self.active_high else 0xFF

        for mcp_idx, addr in enumerate(MCP_ADDRESSES):
            try:
                self._write(addr, IODIRA, 0x00)
                self._write(addr, OLATA,  inactive_mcp)
                self._relay_state.append(inactive_mcp)
                self._write(addr, IODIRB, 0xFF)
                logger.info(f"✓ MCP23017 #{mcp_idx + 1} (0x{addr:02X}) initialised")
            except Exception as exc:
                raise GPIOError(f"MCP23017 #{mcp_idx + 1} init failed (0x{addr:02X}): {exc}") from exc

        # 2. Setup native RPi GPIO bypass (lockers 9, 14, 17). NON-FATAL:
        #    if this fails (e.g. GPIO mode already set by the RFID library),
        #    the I2C lockers still work.
        self._setup_native_pins()

        self.initialized = True
        logger.info(
            "✅ Hybrid GPIO controller initialised – %d lockers total (native bypass: %s)",
            self.active_locker_count,
            "ON" if self._native_available else "OFF",
        )

    def _setup_native_pins(self) -> None:
        """Configure the direct-GPIO bypass pins.

        Adapts to whichever pin-numbering mode is already active. The mfrc522
        RFID library sets BOARD mode when it initialises, so if we blindly
        forced BCM we'd crash with 'A different mode has already been set!'.
        Never raises: on failure the bypass lockers are simply disabled.
        """
        try:
            import RPi.GPIO as GPIO
        except ImportError:
            logger.warning(
                "RPi.GPIO not installed - native bypass lockers %s disabled",
                list(DIRECT_PI_PINS),
            )
            self.GPIO = None
            self._native_available = False
            return

        try:
            GPIO.setwarnings(False)
            existing_mode = GPIO.getmode()

            if existing_mode == GPIO.BCM:
                # Something already set BCM - honour it.
                pin_map = dict(DIRECT_PI_PINS)
                mode_name = "BCM"
            else:
                # Either BOARD is already set (by the mfrc522 RFID reader) or no
                # mode is set yet. Use BOARD in both cases so we always agree
                # with the RFID library and never trigger a mode conflict.
                if existing_mode is None:
                    GPIO.setmode(GPIO.BOARD)
                pin_map = dict(DIRECT_PI_PINS_BOARD)
                mode_name = "BOARD"

            inactive_state = GPIO.LOW if self.active_high else GPIO.HIGH
            for locker, pin in pin_map.items():
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, inactive_state)

            self.GPIO = GPIO
            self._native_pin_map = pin_map
            self._native_available = True
            logger.info(
                "✓ Native GPIO bypass ready (%s mode) for lockers: %s",
                mode_name, list(pin_map),
            )
        except Exception as exc:
            logger.warning(
                "Native GPIO bypass unavailable (%s). Lockers %s cannot open via "
                "bypass; I2C lockers are unaffected.",
                exc, list(DIRECT_PI_PINS),
            )
            self.GPIO = None
            self._native_available = False

    def _write(self, addr: int, reg: int, value: int) -> None:
        self._bus.write_byte_data(addr, reg, value & 0xFF)

    def _validate_locker_number(self, locker_number: int) -> None:
        if locker_number not in RELAY_MAP and locker_number not in DIRECT_PI_PINS:
            raise ValueError(f"Locker {locker_number!r} not configured.")
        if not self.initialized:
            raise GPIOError("GPIO controller not initialised")

    def _set_native(self, locker_number: int, active: bool) -> None:
        """Drive a native-GPIO bypass locker on (active) or off (inactive)."""
        if not self._native_available:
            raise LockerOpenFailed(
                f"Locker {locker_number} uses the native GPIO bypass, which is "
                f"unavailable (GPIO pin-mode conflict). Cannot open."
            )
        pin = self._native_pin_map[locker_number]
        if active:
            state = self.GPIO.HIGH if self.active_high else self.GPIO.LOW
        else:
            state = self.GPIO.LOW if self.active_high else self.GPIO.HIGH
        self.GPIO.output(pin, state)

    def _set_mcp(self, locker_number: int, active: bool) -> None:
        """Drive an MCP23017 relay on (active) or off (inactive).

        Caller must hold self._io_lock (relay-state is shared).
        """
        pin_data = RELAY_MAP[locker_number]
        addr = MCP_ADDRESSES[pin_data.mcp_index]
        current = self._relay_state[pin_data.mcp_index]
        if active:
            next_value = (current | (1 << pin_data.bit)) if self.active_high else (current & ~(1 << pin_data.bit))
        else:
            next_value = (current & ~(1 << pin_data.bit)) if self.active_high else (current | (1 << pin_data.bit))
        # Write the output latch FIRST, then (re-)assert GPIOA as outputs.
        #
        # Why: a solenoid's inductive kick can brown-out/glitch the MCP23017,
        # reverting IODIRA to its power-on default (all inputs) and OLATA to
        # 0x00. When that happens, a plain OLATA write still "succeeds" over
        # I2C but no longer drives the pins, so the relay silently stops
        # actuating on the *next* operation (exactly the deposit-works /
        # retrieve-doesn't symptom). Re-asserting IODIRA=0x00 recovers it.
        # Doing OLATA before IODIRA means that if outputs were disabled, they
        # come back already holding the correct state instead of momentarily
        # energizing every relay on the chip. Both writes are cheap and
        # idempotent when the chip is already configured correctly.
        self._write(addr, OLATA, next_value)
        self._write(addr, IODIRA, 0x00)
        self._relay_state[pin_data.mcp_index] = next_value

    def _apply(self, locker_number: int, active: bool) -> None:
        """Route a locker on/off to native GPIO or MCP23017 as appropriate."""
        if locker_number in DIRECT_PI_PINS:
            self._set_native(locker_number, active)
        else:
            self._set_mcp(locker_number, active)

    def unlock_locker(self, locker_number: int) -> bool:
        self._validate_locker_number(locker_number)
        with self._io_lock:
            self._apply(locker_number, active=True)
        return True

    def lock_locker(self, locker_number: int) -> bool:
        self._validate_locker_number(locker_number)
        with self._io_lock:
            self._apply(locker_number, active=False)
        return True

    def open_locker(self, locker_number: int, hold_open_seconds: Optional[float] = None) -> bool:
        """Open a locker with a simple pulse (blocking call)."""
        self._validate_locker_number(locker_number)
        pulse_seconds = self.pulse_duration if hold_open_seconds is None else max(float(hold_open_seconds), 0.0)

        with self._io_lock:  # ✅ HOLD LOCK FOR ENTIRE OPERATION
            try:
                self._apply(locker_number, active=True)
                time.sleep(pulse_seconds)
                self._apply(locker_number, active=False)
                return True
            except LockerOpenFailed:
                raise
            except Exception as exc:
                raise LockerOpenFailed(f"Relay pulse failed: {exc}") from exc

    def open_locker_window(self, locker_number: int, hold_open_seconds: Optional[float] = None) -> bool:
        """Open a locker and auto-relock after a window period (non-blocking)."""
        self._validate_locker_number(locker_number)
        window_seconds = self.pulse_duration if hold_open_seconds is None else max(float(hold_open_seconds), 0.0)

        with self._io_lock:  # ✅ HOLD LOCK FOR UNLOCK
            try:
                # Cancel any existing auto-relock for this locker
                previous_stop_event = self._pending_relock_events.pop(locker_number, None)
                if previous_stop_event is not None:
                    previous_stop_event.set()

                # Unlock the locker
                self._apply(locker_number, active=True)
                logger.info(
                    "🔓 Locker %d relay ENERGIZED (auto-relock in %.1fs)",
                    locker_number, window_seconds,
                )

                # Setup auto-relock event
                stop_event = threading.Event()
                self._pending_relock_events[locker_number] = stop_event

            except LockerOpenFailed:
                raise
            except Exception as exc:
                raise LockerOpenFailed(f"Window unlock failed: {exc}") from exc

        # Start auto-relock thread (outside the lock to avoid deadlock)
        def _auto_relock() -> None:
            try:
                # Wait for the window period (or until cancelled)
                if stop_event.wait(window_seconds):
                    logger.info("Locker %d auto-relock cancelled (re-opened)", locker_number)
                    return  # Cancelled

                # Time's up - relock the locker
                with self._io_lock:  # ✅ ACQUIRE LOCK FOR RELOCK
                    self._apply(locker_number, active=False)
                logger.info("🔒 Locker %d relay DE-ENERGIZED (window elapsed)", locker_number)

            except Exception as e:
                logger.error(f"Auto-relock failed for locker {locker_number}: {e}")
            finally:
                # Clean up the event
                with self._io_lock:
                    current_event = self._pending_relock_events.get(locker_number)
                    if current_event is stop_event:
                        self._pending_relock_events.pop(locker_number, None)

        threading.Thread(target=_auto_relock, daemon=True, name=f"AutoRelock-L{locker_number}").start()
        return True

    def reset_all(self) -> None:
        """Reset all GPIO states (for error recovery)."""
        if not self.initialized:
            return

        with self._io_lock:
            inactive_mcp = 0x00 if self.active_high else 0xFF

            # Reset native RPi pins (if available)
            if self._native_available:
                for locker in self._native_pin_map:
                    try:
                        self._set_native(locker, active=False)
                    except Exception as e:
                        logger.warning(f"Failed to reset native locker {locker}: {e}")

            # Reset MCP23017 chips
            for mcp_idx, addr in enumerate(MCP_ADDRESSES):
                try:
                    self._write(addr, OLATA, inactive_mcp)
                    self._relay_state[mcp_idx] = inactive_mcp
                except Exception as e:
                    logger.warning(f"Failed to reset MCP23017 #{mcp_idx + 1} (0x{addr:02X}): {e}")

    def cleanup(self) -> None:
        """Cleanup GPIO resources and prepare for shutdown.

        This method should be called before application shutdown to properly
        release hardware resources.
        """
        global _pi_instance

        if not self.initialized:
            return

        logger.info("Cleaning up GPIO controller resources...")

        with self._io_lock:
            # Cancel all pending auto-relock threads
            for locker_num, event in list(self._pending_relock_events.items()):
                event.set()  # Signal thread to stop
            self._pending_relock_events.clear()

            # Reset all relays to inactive state
            try:
                self.reset_all()
            except Exception as e:
                logger.error(f"Error resetting GPIOs during cleanup: {e}")

            # Cleanup only OUR native pins (not a global GPIO.cleanup(), which
            # would also tear down the RFID reader's pins in the same process).
            try:
                if self.GPIO is not None and self._native_pin_map:
                    self.GPIO.cleanup(list(self._native_pin_map.values()))
                    logger.info("✓ Native GPIO pins cleaned up")
            except Exception as e:
                logger.warning(f"Error cleaning up native GPIO pins: {e}")

            # Close I2C bus
            try:
                if self._bus is not None:
                    self._bus.close()
                    self._bus = None
                    logger.info("✓ I2C bus closed")
            except Exception as e:
                logger.warning(f"Error closing I2C bus: {e}")

            self.initialized = False

        # Reset singleton instance
        with _singleton_lock:
            _pi_instance = None

        logger.info("✅ GPIO controller cleanup complete")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False  # Don't suppress exceptions

class MockGPIOController:
    """Thread-safe singleton mock GPIO controller for testing/development.
    
    Uses double-checked locking pattern for thread safety.
    """
    LOCKER_GPIO_MAP = {i: i for i in range(1, 25)}
    SENSOR_GPIO_MAP: Dict[int, int] = {}
    
    def __new__(cls, *args, **kwargs):
        global _mock_instance
        # First check (without lock for performance)
        if _mock_instance is None:
            # Acquire lock for initialization
            with _singleton_lock:
                # Second check (with lock for thread safety)
                if _mock_instance is None:
                    instance = super().__new__(cls)
                    instance._is_setup = False
                    _mock_instance = instance
        return _mock_instance
    
    def __init__(self, **kwargs):
        if getattr(self, "_is_setup", False):
            return
        self.pulse_duration = 0.5
        self.active_locker_count = 24
        self.initialized = True
        self._is_setup = True
        logger.info("✅ MockGPIOController initialized")
    
    def unlock_locker(self, locker_number: int) -> bool:
        logger.debug(f"[MOCK] Unlocking locker {locker_number}")
        return True
    
    def lock_locker(self, locker_number: int) -> bool:
        logger.debug(f"[MOCK] Locking locker {locker_number}")
        return True
    
    def open_locker(self, locker_number: int, hold_open_seconds: Optional[float] = None) -> bool:
        duration = hold_open_seconds or self.pulse_duration
        logger.debug(f"[MOCK] Opening locker {locker_number} for {duration}s")
        return True
    
    def open_locker_window(self, locker_number: int, hold_open_seconds: Optional[float] = None) -> bool:
        duration = hold_open_seconds or self.pulse_duration
        logger.debug(f"[MOCK] Opening locker window {locker_number} for {duration}s")
        return True
    
    def reset_all(self) -> None:
        logger.debug("[MOCK] Resetting all GPIO states")
        pass
    
    def cleanup(self) -> None:
        """Cleanup mock GPIO resources."""
        global _mock_instance
        logger.info("Cleaning up MockGPIOController...")
        self.initialized = False
        
        with _singleton_lock:
            _mock_instance = None
        
        logger.info("✅ MockGPIOController cleanup complete")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False  # Don't suppress exceptions