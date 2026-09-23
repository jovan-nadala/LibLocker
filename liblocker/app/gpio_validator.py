"""Configuration validation to catch GPIO setup issues early."""

import logging
import os
from typing import List, Tuple

logger = logging.getLogger(__name__)


def validate_gpio_configuration() -> Tuple[bool, List[str]]:
    """
    Validate GPIO configuration and return (is_valid, warnings_list).
    
    Returns:
        (True, []) if configuration looks correct
        (False, [warnings]) if critical issues found
    """
    warnings = []
    
    hardware_mode = os.getenv("HARDWARE_MODE", "PI").upper()
    if hardware_mode not in ("PI", "DEV", "MOCK", "TEST"):
        warnings.append(f"Invalid HARDWARE_MODE: {hardware_mode}")
        return False, warnings
    
    # Skip validation for development modes
    if hardware_mode in ("DEV", "MOCK", "TEST"):
        logger.info("Development mode detected - skipping GPIO validation")
        return True, []
    
    # Production (PI) mode - validate I2C configuration
    active_locker_count = int(os.getenv("ACTIVE_LOCKER_COUNT", "24"))
    
    # Check for direct GPIO fallback (only supports 8 lockers max)
    if active_locker_count > 8:
        gpio_use_i2c = os.getenv("GPIO_USE_I2C", "false").lower() in ("true", "1", "yes")
        if not gpio_use_i2c:
            warnings.append(
                "❌ CRITICAL: GPIO_USE_I2C is disabled but "
                f"ACTIVE_LOCKER_COUNT={active_locker_count} (max 8 for direct GPIO). "
                "Enable GPIO_USE_I2C=true and configure I2C addresses for MCP23017 modules."
            )
            return False, warnings
    
    # If using I2C, validate driver and addresses
    if os.getenv("GPIO_USE_I2C", "false").lower() in ("true", "1", "yes"):
        gpio_i2c_driver = os.getenv("GPIO_I2C_DRIVER", "relay_board").lower()
        relay_addresses = os.getenv("GPIO_RELAY_I2C_ADDRESSES", "").strip()
        
        if gpio_i2c_driver == "mcp23017" and not relay_addresses:
            warnings.append(
                "❌ CRITICAL: GPIO_I2C_DRIVER=mcp23017 but "
                "GPIO_RELAY_I2C_ADDRESSES is empty. "
                "Configure relay addresses (e.g., GPIO_RELAY_I2C_ADDRESSES=0x20,0x21)"
            )
            return False, warnings
        
        if gpio_i2c_driver == "mcp23017":
            logger.info(f"✓ I2C MCP23017 mode enabled with relay addresses: {relay_addresses}")
        elif gpio_i2c_driver == "relay_board":
            logger.info("✓ Generic I2C relay board mode enabled")
    
    return True, warnings


def check_hardware_setup() -> None:
    """Log hardware setup information at startup."""
    logger.info("="*70)
    logger.info("HARDWARE CONFIGURATION CHECK")
    logger.info("="*70)
    
    hardware_mode = os.getenv("HARDWARE_MODE", "PI").upper()
    logger.info(f"Hardware Mode: {hardware_mode}")
    logger.info(f"Active Lockers: {os.getenv('ACTIVE_LOCKER_COUNT', '24')}")
    
    if hardware_mode in ("DEV", "MOCK", "TEST"):
        logger.info("✓ Using mock/development hardware")
        return
    
    # Production mode details
    logger.info(f"GPIO Use I2C: {os.getenv('GPIO_USE_I2C', 'false')}")
    logger.info(f"GPIO I2C Driver: {os.getenv('GPIO_I2C_DRIVER', 'relay_board')}")
    logger.info(f"GPIO I2C Bus: {os.getenv('GPIO_I2C_BUS', '1')}")
    logger.info(f"GPIO Relay Addresses: {os.getenv('GPIO_RELAY_I2C_ADDRESSES', '(not set)')}")
    logger.info(f"GPIO Sensor Addresses: {os.getenv('GPIO_SENSOR_I2C_ADDRESSES', '(not set)')}")
    
    is_valid, warnings = validate_gpio_configuration()
    if not is_valid:
        logger.error("Configuration validation failed:")
        for warning in warnings:
            logger.error(warning)
    else:
        logger.info("✓ Hardware configuration validated successfully")
    
    logger.info("="*70)
