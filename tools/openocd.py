#!/usr/bin/env python3
"""
OpenOCD wrapper tool for flashing and debugging STM32 and TM4C microcontrollers.

Provides a unified interface for:
- Flashing firmware to supported boards
- Launching debug sessions with GDB/Telnet access

Supports both CLI usage and Python imports for integration with other scripts.
"""

import argparse
import subprocess
import sys
from pathlib import Path


# Board configuration mapping
BOARD_CONFIG = {
    "stm32": {
        "config_file": "board/st_nucleo_f4.cfg",
        "erase_sector": 5,
    },
    "tm4c": {
        "config_file": "board/ti_ek-tm4c123gxl.cfg",
        "erase_sector": 0,
    },
}


def flash(platform, serial_number, file_path):
    """
    Flash firmware to the specified board.

    Args:
        platform (str): Board platform identifier ('stm32' or 'tm4c')
        serial_number (str): Serial number of the device to target
        file_path (str): Path to the firmware binary file to flash

    Returns:
        int: Return code from the OpenOCD process (0 = success)

    Raises:
        ValueError: If platform is not supported
        FileNotFoundError: If the firmware file does not exist
    """
    if platform not in BOARD_CONFIG:
        raise ValueError(f"Unsupported platform: {platform}")

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Firmware file not found: {file_path}")

    config = BOARD_CONFIG[platform]
    board_config = config["config_file"]
    sector = config["erase_sector"]

    # Construct the OpenOCD command
    cmd = [
        "openocd",
        "-f", board_config,
        "-c", f"adapter serial {serial_number}",
        "-c", "init",
        "-c", "reset halt",
        "-c", f"flash erase_sector 0 {sector} {sector}",
        "-c", f"program {file_path} verify reset exit",
    ]

    print(f"Flashing {platform} device {serial_number} with {file_path}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd)
    return result.returncode


def debug(platform, serial_number, gdb_port=3333, telnet_port=4444):
    """
    Launch a debug session with OpenOCD for the specified board.

    Starts OpenOCD with GDB and Telnet server ports. This function blocks until
    OpenOCD exits. After this function is called, you can:
    - Connect GDB to localhost:{gdb_port}
    - Connect Telnet to localhost:{telnet_port}

    Placeholder for gdbgui integration: future versions will launch gdbgui
    automatically with the appropriate firmware symbols. This will require
    adding a 'file_path' parameter and running OpenOCD in the background.

    Args:
        platform (str): Board platform identifier ('stm32' or 'tm4c')
        serial_number (str): Serial number of the device to target
        gdb_port (int): GDB server port (default: 3333)
        telnet_port (int): Telnet port (default: 4444)

    Returns:
        int: Return code from the OpenOCD process (0 = success)

    Raises:
        ValueError: If platform is not supported
    """
    if platform not in BOARD_CONFIG:
        raise ValueError(f"Unsupported platform: {platform}")

    config = BOARD_CONFIG[platform]
    board_config = config["config_file"]

    # Construct the OpenOCD command
    cmd = [
        "openocd",
        "-f", board_config,
        "-c", f"adapter serial {serial_number}",
        "-c", f"gdb_port {gdb_port}",
        "-c", f"telnet_port {telnet_port}",
    ]

    print(f"Starting debug session for {platform} device {serial_number}")
    print(f"GDB port: {gdb_port}, Telnet port: {telnet_port}")
    print(f"Command: {' '.join(cmd)}")
    print("\n[TODO] gdbgui integration will be added here once file_path parameter is included\n")

    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Parse command-line arguments and execute the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        description="OpenOCD wrapper for flashing and debugging microcontrollers"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Flash subcommand
    flash_parser = subparsers.add_parser("flash", help="Flash firmware to a device")
    flash_parser.add_argument(
        "platform",
        choices=["stm32", "tm4c"],
        help="Board platform identifier",
    )
    flash_parser.add_argument(
        "serial_number",
        help="Serial number of the device",
    )
    flash_parser.add_argument(
        "file",
        help="Path to the firmware binary file",
    )
    flash_parser.set_defaults(func=lambda args: sys.exit(flash(
        args.platform,
        args.serial_number,
        args.file,
    )))

    # Debug subcommand
    debug_parser = subparsers.add_parser("debug", help="Launch a debug session")
    debug_parser.add_argument(
        "platform",
        choices=["stm32", "tm4c"],
        help="Board platform identifier",
    )
    debug_parser.add_argument(
        "serial_number",
        help="Serial number of the device",
    )
    debug_parser.add_argument(
        "--gdb-port",
        type=int,
        default=3333,
        help="GDB server port (default: 3333)",
    )
    debug_parser.add_argument(
        "--telnet-port",
        type=int,
        default=4444,
        help="Telnet port (default: 4444)",
    )
    debug_parser.set_defaults(func=lambda args: sys.exit(debug(
        args.platform,
        args.serial_number,
        args.gdb_port,
        args.telnet_port,
    )))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
