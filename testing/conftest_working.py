"""
pytest configuration for car/fob black-box testing.

Tests are run via: pytest [options] [--using board@sn1,sn2]

Mode selection:
    --using board@sn1,sn2  -> Hardware mode (both devices on real hardware)
                              board: stm32 or tm4c
                              sn1,sn2: debug probe serial numbers (not serial ports)
    (no --using)           -> Simulation mode (x86 with virtual serial ports)

Each test declares what roles it needs via the deploy fixture:
1. Single device:   deploy(RoleConfig("paired_fob", id="1", pin="123456"))
2. Two devices:     deploy(RoleConfig("car", id="1"), RoleConfig("paired_fob", id="1", pin="123456"))

The fixture system:
- Builds firmware using SCons
- For hardware: flashes devices and opens serial ports
- For simulation: launches x86 processes with virtual serial ports
- Returns DeployedDevice objects for testing
- Cleans up resources after test completes
"""

import pytest
import subprocess
import serial
import os
import time
from pathlib import Path
from typing import Optional, Union, overload
from dataclasses import dataclass

# Add tools directory to path for imports
import sys
tools_dir = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_dir))

from devices import DeployedDevice
from simulate import SimulationEnvironment

# Constants
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass
class HardwareConfig:
    """Hardware configuration: board type and list of probe serial numbers."""
    board: str  # "stm32" or "tm4c"
    identifiers: list[str]  # Serial numbers of debug probes


@dataclass
class RoleConfig:
    """Configuration for a device role to deploy."""
    role: str  # "car", "paired_fob", or "unpaired_fob"
    id: Optional[str] = None  # Required for car and paired_fob
    pin: Optional[str] = None  # Required for paired_fob


# ============================================================================
# Command-line Option Parsing
# ============================================================================

def pytest_addoption(parser):
    """Add custom command-line options for pytest."""
    parser.addoption(
        "--using",
        type=str,
        default=None,
        help="Hardware mode: board@sn1,sn2 (e.g., stm32@066DFF555051897267073723,0670FF494849897267154049)"
    )


@pytest.fixture(scope="session")
def hardware_config(request) -> Optional[HardwareConfig]:
    """
    Parse --using argument into HardwareConfig, or None for simulation mode.

    Returns:
        HardwareConfig if --using is provided, None otherwise (simulation mode)
    """
    using = request.config.getoption("--using")
    if not using:
        return None

    if "@" not in using:
        raise ValueError(
            f"Invalid --using format: '{using}'\n"
            f"Expected: board@sn1,sn2 (e.g., stm32@066DFF555051897267073723,0670FF494849897267154049)"
        )

    board, ids_str = using.split("@", 1)
    identifiers = [i.strip() for i in ids_str.split(",")]

    # Validate board type
    if board not in ["stm32", "tm4c"]:
        raise ValueError(f"Unknown board '{board}'. Supported: stm32, tm4c")

    # Require exactly 2 identifiers (since tests deploy 1 or 2 devices)
    if len(identifiers) < 2:
        raise ValueError("Hardware mode requires at least 2 serial numbers: --using board@sn1,sn2")

    return HardwareConfig(board=board, identifiers=identifiers)


# ============================================================================
# Main Deploy Fixture
# ============================================================================

# Type hints for deploy() using overload
@overload
def _deploy(cfg1: RoleConfig) -> DeployedDevice: ...

@overload
def _deploy(cfg1: RoleConfig, cfg2: RoleConfig) -> tuple[DeployedDevice, DeployedDevice]: ...


@pytest.fixture
def deploy(hardware_config):
    """
    Deploy one or two roles for testing.

    Automatically selects hardware or simulation mode based on --using flag.

    Usage (single device):
        def test_something(deploy):
            fob = deploy(RoleConfig("paired_fob", id="1", pin="123456"))

    Usage (two devices):
        def test_something(deploy):
            car, fob = deploy(
                RoleConfig("car", id="1"),
                RoleConfig("paired_fob", id="1", pin="123456")
            )
    """

    deployed_devices = []
    sim_env = None

    if hardware_config:
        # Hardware mode
        def _deploy_hw(cfg1: RoleConfig, cfg2: Optional[RoleConfig] = None) -> Union[DeployedDevice, tuple[DeployedDevice, DeployedDevice]]:
            """Deploy to hardware: build, flash, open ports for both devices (or one if cfg2=None)."""

            # Deploy first device
            binary1 = build_binary(cfg1, hardware_config.board)
            port1 = flash_and_open_port(hardware_config.board, hardware_config.identifiers[0], binary1)
            ser1 = serial.Serial(port1, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
            time.sleep(0.1)
            ser1.reset_input_buffer()
            dev1 = DeployedDevice(ser1)
            deployed_devices.append(dev1)

            # Deploy second device if requested
            if cfg2:
                binary2 = build_binary(cfg2, hardware_config.board)
                port2 = flash_and_open_port(hardware_config.board, hardware_config.identifiers[1], binary2)
                ser2 = serial.Serial(port2, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
                time.sleep(0.1)
                ser2.reset_input_buffer()
                dev2 = DeployedDevice(ser2)
                deployed_devices.append(dev2)
                return dev1, dev2
            else:
                return dev1

        deploy_fn = _deploy_hw

    else:
        # Simulation mode
        def _deploy_sim(cfg1: RoleConfig, cfg2: Optional[RoleConfig] = None) -> Union[DeployedDevice, tuple[DeployedDevice, DeployedDevice]]:
            """Deploy to simulation: build binaries and create SimulationEnvironment."""
            nonlocal sim_env

            binary1 = build_binary(cfg1, "x86")
            binary2 = build_binary(cfg2, "x86") if cfg2 else None

            sim_env = SimulationEnvironment(binary1, binary2)
            devices = sim_env.__enter__()

            if devices.secondary:
                return devices.primary, devices.secondary
            else:
                return devices.primary

        deploy_fn = _deploy_sim

    yield deploy_fn

    # Cleanup
    if hardware_config:
        for dev in deployed_devices:
            dev.close()
    else:
        if sim_env:
            sim_env.__exit__(None, None, None)


# ============================================================================
# Helper Functions
# ============================================================================

def build_binary(cfg: RoleConfig, platform: str) -> Path:
    """
    Build firmware for a role using SCons.

    Args:
        cfg: RoleConfig with role, id (optional), and pin (optional)
        platform: "stm32", "tm4c", or "x86"

    Returns:
        Path to the built binary
    """
    # Build command with conditional arguments
    cmd = ["scons", f"platform={platform}", f"role={cfg.role}", "test=True"]
    if cfg.id:
        cmd.append(f"id={cfg.id}")
    if cfg.pin:
        cmd.append(f"pin={cfg.pin}")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Build failed for {cfg.role}:\n{result.stderr}")

    # Construct binary path: hardware/{platform}/build/{role}_{id}/{role}_{id}.bin
    if cfg.role in ["car", "paired_fob"]:
        name = f"{cfg.role}_{cfg.id}"
    else:
        name = cfg.role

    binary_dir = PROJECT_ROOT / "hardware" / platform / "build" / name

    # Different binary extensions for different platforms
    if platform == "x86":
        binary_path = binary_dir / name
    else:
        binary_path = binary_dir / f"{name}.bin"

    if not binary_path.exists():
        raise RuntimeError(f"Built binary not found at {binary_path}")

    return binary_path


def flash_and_open_port(board: str, serial_number: str, binary: Path) -> str:
    """
    Flash a binary to hardware and return the serial port for communication.

    Args:
        board: Board type ("stm32" or "tm4c")
        serial_number: Serial number of the debug probe
        binary: Path to the firmware binary

    Returns:
        Serial port path (e.g., "/dev/ttyACM0")
    """
    from openocd import flash as openocd_flash
    from serial.tools.list_ports import comports

    # Flash using OpenOCD
    result = openocd_flash(board, serial_number, str(binary))
    if result != 0:
        raise RuntimeError(f"Flash failed with code {result}")

    # Find the serial port associated with this debug probe's serial number
    ports = comports()
    for port in ports:
        if port.serial_number == serial_number:
            return port.device

    raise RuntimeError(
        f"Could not find serial port for probe '{serial_number}'.\n"
        f"Available ports: {[(p.device, p.serial_number) for p in ports]}"
    )


# ============================================================================
# Convenience Fixtures
# ============================================================================

@pytest.fixture
def paired_fob(deploy):
    """Single paired fob."""
    return deploy(RoleConfig("paired_fob", id="1", pin="123456"))


@pytest.fixture
def unpaired_fob(deploy):
    """Single unpaired fob."""
    return deploy(RoleConfig("unpaired_fob"))


@pytest.fixture
def car_and_paired_fob(deploy):
    """Car and its paired fob."""
    return deploy(
        RoleConfig("car", id="1"),
        RoleConfig("paired_fob", id="1", pin="123456")
    )


@pytest.fixture
def paired_and_unpaired_fob(deploy):
    """A paired fob and an unpaired fob."""
    return deploy(
        RoleConfig("paired_fob", id="1", pin="123456"),
        RoleConfig("unpaired_fob")
    )
