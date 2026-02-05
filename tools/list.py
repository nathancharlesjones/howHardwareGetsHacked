#!/usr/bin/env python3
"""
Utilities for listing and finding serial devices.
"""

from serial.tools.list_ports import comports
from typing import Optional


def list_devices():
    """List all serial devices (excluding 'n/a' descriptions)."""
    ports = comports()
    devices = [device for device in ports if device.description != "n/a"]
    return devices


def find_port_by_serial_number(serial_number: str) -> Optional[str]:
    """
    Find a serial port by the debug probe's serial number.

    Args:
        serial_number: Serial number of the debug probe

    Returns:
        Port device path (e.g., "/dev/ttyACM0") or None if not found
    """
    ports = comports()
    for port in ports:
        if port.serial_number == serial_number:
            return port.device
    return None


if __name__ == "__main__":
    devices = list_devices()
    if len(devices) == 0:
        print("No attached devices")
    else:
        for device in devices:
            print(device.description)
            print(f"  SN: {device.serial_number}")
            print(f"  Port: {device.device}")