#!/usr/bin/env python3
"""
LibLocker – 24-locker hardware test script
==========================================
Tests triple MCP23017 relay outputs and NC reed switch inputs for lockers 1-24.
Bypasses relays for Lockers 9, 14, and 17 to direct Raspberry Pi GPIOs.
Chip 1 (0x20) handles lockers 1-8.
Chip 2 (0x21) handles lockers 9-16 (Sensors 9-12 Software-Reversed).
Chip 3 (0x22) handles lockers 17-24 (Sensors Software-Reversed).

Usage:
    cd /home/liblocker/liblocker
    source venv/bin/activate
    python3 test-24-lockers.py

Options:
    python3 test-24-lockers.py --relay-only   # skip reed switch test
    python3 test-24-lockers.py --reed-only    # only read switches, no relays
    python3 test-24-lockers.py --locker 22    # test only locker 22
    python3 test-24-lockers.py --watch        # continuously watch reed switches
"""
import sys
import time
import argparse

# ── Dependency Checks ───────────────────────────────────────────────────────
try:
    from smbus2 import SMBus
except ImportError:
    print("ERROR: smbus2 not installed. Run: pip install smbus2")
    sys.exit(1)

try:
    from gpiozero import OutputDevice
except ImportError:
    print("ERROR: gpiozero not installed. Run: pip install gpiozero")
    sys.exit(1)

# ── MCP23017 register constants ─────────────────────────────────────────────
IODIRA = 0x00
IODIRB = 0x01
GPPUB  = 0x0D
GPIOB  = 0x13
OLATA  = 0x14

MCP_ADDRS    = [0x20, 0x21, 0x22]  # L1-8, L9-16, L17-24
I2C_BUS      = 1
LOCKER_COUNT = 24
ACTIVE_HIGH  = False      # Most 8-channel relay boards are active LOW
PULSE_SEC    = 3          # How long to hold relay on

# ── RPi Native Bypass Configuration ─────────────────────────────────────────
# Maps broken locker numbers to BCM pins
# Pin 13 -> BCM 27, Pin 15 -> BCM 22, Pin 29 -> BCM 5
DIRECT_PI_PINS = {
    9: 27,   # Locker 9  -> Physical Pin 13
    14: 22,  # Locker 14 -> Physical Pin 15
    17: 5    # Locker 17 -> Physical Pin 29
}
native_pins = {}

# ── Low-level helpers ────────────────────────────────────────────────────────

def get_chip_and_bit(locker_number):
    """Maps a locker number (1-24) to its specific I2C address and GPIO bit."""
    if 1 <= locker_number <= 8:
        return 0x20, locker_number - 1
    elif 9 <= locker_number <= 16:
        return 0x21, locker_number - 9
    elif 17 <= locker_number <= 24:
        return 0x22, locker_number - 17
    else:
        raise ValueError(f"Invalid locker number: {locker_number}")

def mcp_write(bus, addr, reg, val):
    bus.write_byte_data(addr, reg, val & 0xFF)

def mcp_read(bus, addr, reg):
    return bus.read_byte_data(addr, reg) & 0xFF

def init_hardware(bus):
    """Configure all MCP23017s and Native GPIO Pins."""
    states = {}
    inactive = 0x00 if ACTIVE_HIGH else 0xFF

    # 1. Init MCP23017s
    for addr in MCP_ADDRS:
        mcp_write(bus, addr, IODIRA, 0x00)   # GPA all outputs
        mcp_write(bus, addr, IODIRB, 0xFF)   # GPB all inputs
        mcp_write(bus, addr, GPPUB,  0xFF)   # GPB pull-ups ON
        mcp_write(bus, addr, OLATA, inactive) # All relays OFF
        states[addr] = inactive

    # 2. Init Native Raspberry Pi Pins
    for locker, bcm_pin in DIRECT_PI_PINS.items():
        try:
            native_pins[locker] = OutputDevice(bcm_pin, active_high=ACTIVE_HIGH, initial_value=False)
            print(f"✓ Bypass Initialized: Locker {locker} on BCM {bcm_pin}")
        except Exception as e:
            print(f"✗ Failed to init Bypass BCM {bcm_pin}: {e}")

    return states


def open_locker(bus, locker_number, current_states):
    """Pulse relay for locker_number. Handles bypassed native pins automatically."""

    # Check if this locker is routed to a direct Raspberry Pi pin
    if locker_number in native_pins:
        print(f" [Native BCM] ", end="")
        native_pins[locker_number].on()
        time.sleep(PULSE_SEC)
        native_pins[locker_number].off()
        return current_states
            # Otherwise, route to standard I2C MCP chip
    addr, bit = get_chip_and_bit(locker_number)
    state = current_states[addr]

    if ACTIVE_HIGH:
        active   = state | (1 << bit)
        inactive = state & ~(1 << bit)
    else:
        active   = state & ~(1 << bit)  # LOW = relay ON
        inactive = state | (1 << bit)   # HIGH = relay OFF

    mcp_write(bus, addr, OLATA, active)
    time.sleep(PULSE_SEC)
    mcp_write(bus, addr, OLATA, inactive)

    current_states[addr] = inactive
    return current_states


def read_reed(bus, locker_number):
    """Read NC reed switch for locker_number."""
    addr, bit = get_chip_and_bit(locker_number)

    # Hardware traces reversed for Chip 3 (0x22)
    if addr == 0x22:
        bit = 7 - bit

    # Hardware traces reversed for Chip 2 (0x21) ONLY for pins 9-12 (bits 0-3)
    if addr == 0x21 and bit < 4:
        bit = 3 - bit

    gpb = mcp_read(bus, addr, GPIOB)
    pin = (gpb >> bit) & 0x01
    return pin == 0  # LOW = door closed


def read_all_reeds(bus):
    """Read all 24 reed switches across all three I2C chips."""
    result = {}
    for addr in MCP_ADDRS:
        gpb = mcp_read(bus, addr, GPIOB)

        if addr == 0x20:
            for bit in range(8):
                result[1 + bit] = ((gpb >> bit) & 0x01) == 0
        elif addr == 0x21:
            for bit in range(8):
                if bit < 4:
                    locker = 12 - bit # bit 0->12, 1->11, 2->10, 3->9
                else:
                    locker = 9 + bit  # bit 4->13, 5->14, 6->15, 7->16
                result[locker] = ((gpb >> bit) & 0x01) == 0
        elif addr == 0x22:
            for bit in range(8):
                locker = 24 - bit
                result[locker] = ((gpb >> bit) & 0x01) == 0
    return result


# ── Test routines ────────────────────────────────────────────────────────────

def print_header():
    print("=" * 55)
    print("  LibLocker 24-Locker Hardware Test (Hybrid Bypass)")
    print("=" * 55)
    print(f"  MCP23017 (1-8)   : 0x{MCP_ADDRS[0]:02X}")
    print(f"  MCP23017 (9-16)  : 0x{MCP_ADDRS[1]:02X}")
    print(f"  MCP23017 (17-24) : 0x{MCP_ADDRS[2]:02X}")
    print(f"  I2C bus          : {I2C_BUS}")
    print(f"  Relay type       : {'active HIGH' if ACTIVE_HIGH else 'active LOW'}")
    print(f"  Pulse duration   : {PULSE_SEC}s")
    print(f"  Reed switch type : Normally Closed (NC)")
    print()

def test_reed_switches(bus):
    print("── Reed switch status ──────────────────────────────")
    states = read_all_reeds(bus)
    all_ok = True
    for locker in range(1, 25):
        closed = states.get(locker)
        if closed is None:
            icon, status = "?", "READ ERROR"
            all_ok = False
        elif closed:
            icon, status = "✓", "CLOSED (door shut)"
        else:
            icon, status = "!", "OPEN   (door open or no magnet)"

        # Add a visual separator between the chips
        if locker == 9:
            print("  --- Chip 2 (0x21) ---")
        elif locker == 17:
            print("  --- Chip 3 (0x22) ---")

        print(f"  {icon} Locker {locker:<2}: {status}")
    print()
    return all_ok


def test_single_relay(bus, locker_number, states):
    """Test one locker relay. Returns updated states dict."""
    print(f"  Opening locker {locker_number:<2}...", end=" ", flush=True)
    try:
        new_states = open_locker(bus, locker_number, states)
        time.sleep(0.1)
        closed = read_reed(bus, locker_number)
        reed_str = "door closed" if closed else "door OPEN" if closed is False else "reed err"
        print(f"✓ relay clicked  [{reed_str}]")
        return new_states
    except Exception as exc:
        print(f"✗ FAILED: {exc}")
        return states


def test_all_relays(bus, states):
    print("── Relay test (lockers 1-24) ───────────────────────")
    print("  You should hear each relay click in sequence.")
    print()
    try:
        for locker in range(1, 25):
            states = test_single_relay(bus, locker, states)
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n  Test cancelled")
        for addr in MCP_ADDRS:
            mcp_write(bus, addr, OLATA, states[addr])
    print()


def watch_reed_switches(bus):
    """Continuously monitor all 24 reed switches until Ctrl+C."""
    print("── Watching reed switches (Ctrl+C to stop) ─────────")
    print("  Open and close locker doors to see status change.\n")
    prev = {}
    try:
        while True:
            states = read_all_reeds(bus)
            if states != prev:
                ts = time.strftime("%H:%M:%S")
                part1 = "  ".join(f"L{i}:{('C' if states[i] else 'O')}" for i in range(1, 9))
                part2 = "  ".join(f"L{i}:{('C' if states[i] else 'O')}" for i in range(9, 17))
                part3 = "  ".join(f"L{i}:{('C' if states[i] else 'O')}" for i in range(17, 25))
                print(f"  [{ts}] CHIP 1 (1-8)   : {part1}")
                print(f"  [{ts}] CHIP 2 (9-16)  : {part2}")
                print(f"  [{ts}] CHIP 3 (17-24) : {part3}\n")
                prev = dict(states)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n  Watch stopped.")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LibLocker 24-locker hardware test")
    parser.add_argument("--relay-only", action="store_true", help="Skip reed switch display")
    parser.add_argument("--reed-only",  action="store_true", help="Only read reed switches")
    parser.add_argument("--locker",     type=int, metavar="N", help="Test only locker N (1-24)")
    parser.add_argument("--watch",      action="store_true",   help="Continuously watch reed switches")
    args = parser.parse_args()

    print_header()

    # ── Connect to I2C bus ──────────────────────────────────────────────────
    try:
        bus = SMBus(I2C_BUS)
        print(f"✓ Opened I2C bus {I2C_BUS}")
    except Exception as exc:
        print(f"✗ Cannot open I2C bus: {exc}")
        sys.exit(1)

    # ── Init Hardware ───────────────────────────────────────────────
    try:
        relay_states = init_hardware(bus)
        print(f"✓ Triple MCP23017s (0x20, 0x21, 0x22) initialised\n")
    except Exception as exc:
        print(f"✗ Hardware init failed: {exc}")
        bus.close()
        sys.exit(1)

    # ── Watch mode ──────────────────────────────────────────────────────────
    if args.watch:
        watch_reed_switches(bus)
        bus.close()
        return
    
    # ── Single locker test ──────────────────────────────────────────────────
    if args.locker:
        n = args.locker
        if not 1 <= n <= 24:
            print(f"✗ Locker must be 1-24, got {n}")
            sys.exit(1)
        print(f"── Testing locker {n} only ─────────────────────────")
        if not args.relay_only:
            closed = read_reed(bus, n)
            print(f"  Reed switch: {'CLOSED' if closed else 'OPEN'}")
        if not args.reed_only:
            relay_states = test_single_relay(bus, n, relay_states)
        bus.close()
        return

    # ── Full test ───────────────────────────────────────────────────────────
    if not args.relay_only:
        test_reed_switches(bus)

    if not args.reed_only:
        test_all_relays(bus, relay_states)

    if not args.relay_only:
        print("── Final reed switch state ─────────────────────────")
        test_reed_switches(bus)

    bus.close()
    print("✓ Test complete. I2C bus closed.")


if __name__ == "__main__":
    main()


