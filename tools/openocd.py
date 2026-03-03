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
        "erase_sector": 6,
        "lock_cmd": "stm32f2x lock 0",
        "unlock_cmd": "stm32f2x unlock 0",
    },
    "tm4c": {
        "config_file": "board/ti_ek-tm4c123gxl.cfg",
        "erase_sector": 255,
        "lock_cmd": "",
        "unlock_cmd": "",
    },
}


def flash(platform, serial_number, file_path, lock=1):
    """
    Flash firmware to the specified board.

    Args:
        platform (str): Board platform identifier ('stm32' or 'tm4c')
        serial_number (str): Serial number of the device to target
        file_path (str): Path to the firmware binary file to flash
        lock (int): Lock the device after flashing (1=lock, 0=skip lock, default: 1)

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
        "-c", "halt",
        "-c", f"flash erase_sector 0 {sector} {sector}",
        "-c", f"program {file_path} verify",
    ]
    if lock and config["lock_cmd"]:
        # After setting RDP, a POR (power-on reset) is required — not just a
        # system reset — per the STM32 reference manual. OpenOCD cannot trigger
        # a POR, so just disconnect cleanly and let the user power cycle.
        cmd += ["-c", config["lock_cmd"]]
        print("NOTE: A full power-cycle is needed after locking to reload the option byte.")
    else:
        cmd += ["-c", "reset run"]

    cmd += ["-c", "shutdown"]

    print(f"Flashing {platform} device {serial_number} with {file_path}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    # OpenOCD's return code is unreliable (can be non-zero on success due to warnings)
    # Check for verification success in the output instead
    combined_output = result.stdout + result.stderr
    print(combined_output)

    if "** Verified OK **" in combined_output:
        return 0  # Success
    else:
        # Print output to help debug the failure
        return 1  # Failure


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


def unlock(platform, serial_number):
    """
    Unlock a locked device to allow reprogramming.

    For STM32, this removes read protection (RDP) via 'stm32f2x unlock 0', which
    also triggers a mass erase of flash. After unlocking, the device must be
    power-cycled or reset before reprogramming.

    Args:
        platform (str): Board platform identifier ('stm32')
        serial_number (str): Serial number of the device to target

    Returns:
        int: Return code from the OpenOCD process (0 = success)

    Raises:
        ValueError: If platform is not supported
    """
    if platform not in BOARD_CONFIG:
        raise ValueError(f"Unsupported platform: {platform}")

    config = BOARD_CONFIG[platform]
    board_config = config["config_file"]

    cmd = [
        "openocd",
        "-f", board_config,
        "-c", f"adapter serial {serial_number}",
        "-c", "init",
        "-c", "halt",
    ] + ["-c", config["unlock_cmd"]] + ["-c", "reset exit"]

    print(f"Unlocking {platform} device {serial_number}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    combined_output = result.stdout + result.stderr
    print(combined_output)

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
    flash_parser.add_argument(
        "--lock",
        type=int,
        default=1,
        choices=[0, 1],
        help="Lock the device after flashing (default: 1)",
    )
    flash_parser.set_defaults(func=lambda args: sys.exit(flash(
        args.platform,
        args.serial_number,
        args.file,
        args.lock,
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

    # Unlock subcommand
    unlock_parser = subparsers.add_parser("unlock", help="Unlock a locked device to allow reprogramming")
    unlock_parser.add_argument(
        "platform",
        choices=["stm32"],
        help="Board platform identifier",
    )
    unlock_parser.add_argument(
        "serial_number",
        help="Serial number of the device",
    )
    unlock_parser.set_defaults(func=lambda args: sys.exit(unlock(
        args.platform,
        args.serial_number,
    )))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
