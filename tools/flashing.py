"""
Hardware flashing utilities using OpenOCD.

This module provides the core logic for flashing firmware to embedded targets.
Used by both tests (import directly) and CLI (via project.py).

Supported boards:
    - stm32: Nucleo-F411RE (ST-Link interface)
    - tm4c:  EK-TM4C123GXL (TI ICDI interface)

Identifier can be:
    - Serial number (for selecting specific probe when multiple connected)
    - Serial port path (e.g., /dev/ttyACM0) - we'll extract the associated probe
    - None (auto-detect single connected device)
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class BoardConfig:
    """OpenOCD configuration for a specific board type."""
    name: str
    openocd_board_cfg: str
    # Alternative: interface + target configs if board config doesn't exist
    openocd_interface_cfg: Optional[str] = None
    openocd_target_cfg: Optional[str] = None


# Board configurations
# Using board configs where available (they set up interface + target + any quirks)
BOARD_CONFIGS = {
    "stm32": BoardConfig(
        name="Nucleo-F411RE",
        openocd_board_cfg="board/st_nucleo_f4.cfg",
    ),
    "tm4c": BoardConfig(
        name="EK-TM4C123GXL",
        openocd_board_cfg="board/ti_ek-tm4c123gxl.cfg",
    ),
}


class FlashError(Exception):
    """Raised when flashing fails."""
    pass


def find_openocd() -> str:
    """Find OpenOCD executable, raise if not found."""
    openocd = shutil.which("openocd")
    if not openocd:
        raise FlashError(
            "OpenOCD not found. Install with:\n"
            "  Ubuntu/Debian: sudo apt install openocd\n"
            "  macOS: brew install openocd\n"
            "  Arch: sudo pacman -S openocd"
        )
    return openocd


def get_supported_boards() -> List[str]:
    """Return list of supported board identifiers."""
    return list(BOARD_CONFIGS.keys())


def _build_openocd_config_args(platform: str, identifier: Optional[str] = None) -> List[str]:
    """
    Build OpenOCD configuration arguments for a board.
    
    Args:
        board: Board type ("stm32" or "tm4c")
        identifier: Optional serial number or adapter identifier
        
    Returns:
        List of OpenOCD arguments for configuration
    """
    if platform not in BOARD_CONFIGS:
        raise FlashError(
            f"Unknown board '{platform}'. Supported: {', '.join(BOARD_CONFIGS.keys())}"
        )
    
    cfg = BOARD_CONFIGS[platform]
    args = []
    
    # If identifier provided, add adapter serial selection
    # This must come BEFORE the interface config
    if identifier:
        # OpenOCD uses "adapter serial" command to select specific probe
        args.extend(["-c", f"adapter serial {identifier}"])
    
    # Use board config (preferred) or interface+target
    if cfg.openocd_board_cfg:
        args.extend(["-f", cfg.openocd_board_cfg])
    else:
        if cfg.openocd_interface_cfg:
            args.extend(["-f", cfg.openocd_interface_cfg])
        if cfg.openocd_target_cfg:
            args.extend(["-f", cfg.openocd_target_cfg])
    
    return args


def flash_device(
    platform: str,
    binary_path: str,
    identifier: Optional[str] = None,
    verify: bool = True,
    reset: bool = True,
    verbose: bool = False,
) -> None:
    """
    Flash a binary to an embedded device using OpenOCD.
    
    Args:
        platform: Platform type - "stm32" or "tm4c"
        binary_path: Path to the binary file (.bin or .elf)
        identifier: Serial number of the debug probe (optional, for multi-device)
        verify: Verify flash after programming (default: True)
        reset: Reset device after programming (default: True)
        verbose: Print OpenOCD output (default: False)
        
    Raises:
        FlashError: If flashing fails
        FileNotFoundError: If binary doesn't exist
    """
    # Validate binary exists
    binary = Path(binary_path)
    if not binary.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")
    
    # Find OpenOCD
    openocd = find_openocd()
    
    # Build command
    cmd = [openocd]
    cmd.extend(_build_openocd_config_args(platform, identifier))
    
    # Build the program command
    # OpenOCD's "program" command handles erase + write + optional verify + reset
    program_cmd = f"program {binary.absolute()}"
    if verify:
        program_cmd += " verify"
    if reset:
        program_cmd += " reset"
    program_cmd += " exit"
    
    cmd.extend(["-c", program_cmd])
    
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    
    # Run OpenOCD
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        error_msg = f"Flash failed for {platform}"
        if identifier:
            error_msg += f" (identifier: {identifier})"
        error_msg += f"\n\nOpenOCD output:\n{result.stderr}"
        
        # Add helpful hints for common errors
        if "no device found" in result.stderr.lower() or "unable to find" in result.stderr.lower():
            error_msg += "\n\nHint: Check that the device is connected and you have permissions."
            error_msg += "\nOn Linux, you may need udev rules. Try: sudo openocd ..."
        
        raise FlashError(error_msg)
    
    if verbose:
        print(result.stdout)
        print(result.stderr)


def start_gdb_server(
    platform: str,
    identifier: Optional[str] = None,
    gdb_port: int = 3333,
    telnet_port: int = 4444,
    verbose: bool = False,
) -> subprocess.Popen:
    """
    Start an OpenOCD GDB server for debugging.
    
    Args:
        platform: Platform type - "stm32" or "tm4c"
        identifier: Serial number of the debug probe (optional)
        gdb_port: GDB server port (default: 3333)
        telnet_port: Telnet server port (default: 4444)
        verbose: Print OpenOCD output to console (default: False)
        
    Returns:
        subprocess.Popen: The OpenOCD process (caller must manage lifecycle)
        
    Raises:
        FlashError: If OpenOCD fails to start
    """
    openocd = find_openocd()
    
    cmd = [openocd]
    cmd.extend(_build_openocd_config_args(platform, identifier))
    cmd.extend(["-c", f"gdb_port {gdb_port}"])
    cmd.extend(["-c", f"telnet_port {telnet_port}"])
    
    if verbose:
        print(f"Starting GDB server: {' '.join(cmd)}")
        print(f"  GDB port: {gdb_port}")
        print(f"  Telnet port: {telnet_port}")
    
    # Start OpenOCD in background
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
    
    # Give it a moment to start
    import time
    time.sleep(0.5)
    
    # Check if it's still running
    if proc.poll() is not None:
        raise FlashError(f"OpenOCD exited immediately with code {proc.returncode}")
    
    return proc


def reset_device(
    platform: str,
    identifier: Optional[str] = None,
    halt: bool = False,
    verbose: bool = False,
) -> None:
    """
    Reset a device without flashing.
    
    Args:
        platform: Platform type
        identifier: Serial number of the debug probe (optional)
        halt: If True, halt after reset (for debugging). Default: run after reset.
        verbose: Print OpenOCD output
    """
    openocd = find_openocd()
    
    cmd = [openocd]
    cmd.extend(_build_openocd_config_args(platform, identifier))
    
    reset_cmd = "reset halt" if halt else "reset run"
    cmd.extend(["-c", "init", "-c", reset_cmd, "-c", "exit"])
    
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise FlashError(f"Reset failed:\n{result.stderr}")


# CLI interface when run directly
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Flash firmware to embedded devices")
    parser.add_argument("--platform", "-p", required=True, choices=get_supported_boards(),
                        help="Target platform type")
    parser.add_argument("--binary", "-f", required=True,
                        help="Path to binary file")
    parser.add_argument("--identifier", "-i",
                        help="Debug probe serial number (for multi-device setups)")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip verification after flashing")
    parser.add_argument("--no-reset", action="store_true",
                        help="Don't reset after flashing")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    
    args = parser.parse_args()
    
    try:
        flash_device(
            platform=args.platform,
            binary_path=args.binary,
            identifier=args.identifier,
            verify=not args.no_verify,
            reset=not args.no_reset,
            verbose=args.verbose,
        )
        print(f"✓ Successfully flashed {args.binary} to {args.platform}")
    except (FlashError, FileNotFoundError) as e:
        print(f"✗ {e}")
        exit(1)
