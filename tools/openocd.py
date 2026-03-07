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
        # STM32 option bytes take effect only after a full power-on reset (POR),
        # not a system reset, per the STM32 reference manual. OpenOCD cannot
        # trigger a POR, so the user must power-cycle the board after locking.
        "post_lock_msg": "A full power cycle",
        "post_unlock_msg": "Nothing",
        "lock_cmds": ["stm32f2x lock 0"],
        "unlock_cmds": ["stm32f2x unlock 0"],
    },
    "tm4c": {
        "config_file": "board/ti_ek-tm4c123gxl.cfg",
        "erase_sector": 255,
        "post_lock_msg": "A hardware reset",
        # TM4C unlocking requires the ICDI debug controller to be addressed
        # directly — OpenOCD cannot do this. Use tools/icdi_unlock.py instead,
        # which will remind the user about any post-unlock steps.
        "post_unlock_msg": "",
        "lock_cmds": [
            # 1. Clear WRBUF and COMT bits in FMD (0x400FD004) to start fresh
            "mmw 0x400fd004 0x0 0x3",
            # 2. Write lock pattern to FMA (0x400FD000)
            "mww 0x400fd000 0x75100000",
            # 3. Write KEY and set COMT bit in FMC (0x400FD008) to commit
            "mww 0x400fd008 0xa4420008",
        ],
        "unlock_cmds": [],
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
        "-c", f"program {file_path} verify",
        "-c", "reset run",
        "-c", "shutdown",
    ]

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
        return 1  # Failure


def lock(platform, serial_number):
    """
    Lock a device to enable read protection.

    For STM32, this sets RDP Level 1 via 'stm32f2x lock 0'. The option byte
    takes effect only after a full power-on reset (POR); a reminder is printed
    since OpenOCD cannot trigger a POR.

    For TM4C, this writes the lock pattern to the flash memory controller
    registers and then resets the device automatically.

    Args:
        platform (str): Board platform identifier ('stm32' or 'tm4c')
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
    ]
    for lock_cmd in config["lock_cmds"]:
        cmd += ["-c", lock_cmd]
    cmd += ["-c", "shutdown"]

    print(f"Locking {platform} device {serial_number}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    combined_output = result.stdout + result.stderr
    print(combined_output)

    print(f"NOTE: {config['post_lock_msg']} is required for locking to take effect.")
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

    result = subprocess.run(cmd)
    return result.returncode


def unlock(platform, serial_number):
    """
    Unlock a locked device to allow reprogramming.

    For STM32, this removes read protection (RDP) via 'stm32f2x unlock 0', which
    also triggers a mass erase of flash. After unlocking, the device is reset
    automatically. A power-cycle may still be required before reprogramming.

    For TM4C, OpenOCD cannot unlock the device directly. Use tools/icdi_unlock.py
    instead, which communicates directly with the ICDI debug controller via USB.

    Args:
        platform (str): Board platform identifier ('stm32' or 'tm4c')
        serial_number (str): Serial number of the device to target

    Returns:
        int: Return code from the OpenOCD process (0 = success), or 1 if the
             platform requires an external unlock tool.

    Raises:
        ValueError: If platform is not supported
    """
    if platform not in BOARD_CONFIG:
        raise ValueError(f"Unsupported platform: {platform}")

    config = BOARD_CONFIG[platform]

    if not config["unlock_cmds"]:
        print(f"NOTE: {platform} cannot be unlocked via OpenOCD.")
        print("For TM4C, use tools/icdi_unlock.py instead.")
        return 1

    board_config = config["config_file"]

    cmd = [
        "openocd",
        "-f", board_config,
        "-c", f"adapter serial {serial_number}",
        "-c", "init",
        "-c", "halt",
    ]
    for unlock_cmd in config["unlock_cmds"]:
        cmd += ["-c", unlock_cmd]
    cmd += ["-c", "reset run", "-c", "shutdown"]

    print(f"Unlocking {platform} device {serial_number}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    combined_output = result.stdout + result.stderr
    print(combined_output)

    if config["post_unlock_msg"]:
        print(f"NOTE: {config['post_unlock_msg']} is required for unlocking to take effect.")

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

    # Lock subcommand
    lock_parser = subparsers.add_parser("lock", help="Enable read protection on a device")
    lock_parser.add_argument(
        "platform",
        choices=["stm32", "tm4c"],
        help="Board platform identifier",
    )
    lock_parser.add_argument(
        "serial_number",
        help="Serial number of the device",
    )
    lock_parser.set_defaults(func=lambda args: sys.exit(lock(
        args.platform,
        args.serial_number,
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
        choices=["stm32", "tm4c"],
        help="Board platform identifier (TM4C: see tools/icdi_unlock.py)",
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
