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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Board configuration mapping
BOARD_CONFIG = {
    "stm32": {
        "config_file": "board/st_nucleo_f4.cfg",
        "erase_sector": 6,  # sector 6 = FLASH_DATA (fob state); cleared on each firmware flash
        # STM32 option bytes take effect only after a full power-on reset (POR),
        # not a system reset, per the STM32 reference manual. OpenOCD cannot
        # trigger a POR, so the user must power-cycle the board after locking.
        "post_lock_msg": "A full power cycle",
        "post_unlock_msg": "Nothing",
        "lock_cmds": ["stm32f2x lock 0"],
        "unlock_cmds": ["stm32f2x unlock 0"],
        # Flags live in sector 7 (0x08060000); programmed separately from firmware.
        "flash_flags_cmd": [
            "flash write_image erase {flags_path} 0x08060000 bin",
        ],
    },
    "tm4c": {
        "config_file": "board/ti_ek-tm4c123gxl.cfg",
        "erase_sector": 255,  # last flash page = fob state; cleared on each firmware flash
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
        # Flags live in EEPROM blocks 28-31; written directly via EEPROM controller
        # registers (never staged in target RAM).
        "flash_flags_cmd": [
            f"script {_PROJECT_ROOT / 'tools' / 'eeprom.tcl'}",
            "eeprom_write {flags_path} 0x700 256",
        ],
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

    cmd = [
        "openocd",
        "-f", board_config,
        "-c", f"adapter serial {serial_number}",
        "-c", "init",
        "-c", "reset halt",
        "-c", f"flash erase_sector 0 {sector} {sector}",
        "-c", f"program {file_path} verify",
    ]

    flags_path = file_path.parent / "flags.bin"
    if flags_path.exists() and "flash_flags_cmd" in config:
        for flags_cmd in config["flash_flags_cmd"]:
            cmd += ["-c", flags_cmd.format(flags_path=flags_path)]

    cmd += ["-c", "reset run", "-c", "shutdown"]

    print(f"Flashing {platform} device {serial_number} with {file_path}")
    if flags_path.exists():
        print(f"Also programming flags from {flags_path}")
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


def reset(platform, serial_number, halt=False):
    """
    Reset a device via OpenOCD, without touching its flash image.

    This is the debug-probe equivalent of an attacker toggling a MOSFET tied
    to the target's reset pin: used to recover a device that's hung (e.g.
    from a corrupted return address landing PC somewhere invalid) without
    re-flashing it. Unlike flash()/lock()/unlock(), this never needs to halt
    and reprogram the target, so it's just OpenOCD's own reset command -
    no gdb session required.

    Args:
        platform (str): Board platform identifier ('stm32' or 'tm4c')
        serial_number (str): Serial number of the device to target
        halt (bool): If True, reset and halt (leaves the target ready for a
            debugger to attach) instead of resetting and immediately
            resuming normal execution (the default - what a real reset-pin
            toggle would do).

    Returns:
        int: 0 if OpenOCD reported the reset succeeded, 1 otherwise

    Raises:
        ValueError: If platform is not supported
    """
    if platform not in BOARD_CONFIG:
        raise ValueError(f"Unsupported platform: {platform}")

    board_config = BOARD_CONFIG[platform]["config_file"]
    reset_cmd = "reset halt" if halt else "reset run"

    cmd = [
        "openocd",
        "-f", board_config,
        "-c", f"adapter serial {serial_number}",
        "-c", "init",
        "-c", reset_cmd,
        "-c", "shutdown",
    ]

    print(f"Resetting {platform} device {serial_number} ({reset_cmd})")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    # As with flash(): OpenOCD's return code is unreliable, so key off its
    # own "Error :" log lines instead. This only confirms OpenOCD itself
    # reported the reset went through - it's not proof the target actually
    # came back up responsive; the caller owns that check (e.g. by talking
    # to the target over its own UART afterward).
    combined_output = result.stdout + result.stderr
    print(combined_output)

    return 1 if "Error:" in combined_output else 0


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

    # Reset subcommand
    reset_parser = subparsers.add_parser("reset", help="Reset a device without reflashing it")
    reset_parser.add_argument(
        "platform",
        choices=["stm32", "tm4c"],
        help="Board platform identifier",
    )
    reset_parser.add_argument(
        "serial_number",
        help="Serial number of the device",
    )
    reset_parser.add_argument(
        "--halt",
        action="store_true",
        help="Reset and halt instead of reset and resume normal execution",
    )
    reset_parser.set_defaults(func=lambda args: sys.exit(reset(
        args.platform,
        args.serial_number,
        args.halt,
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
