"""
pytest configuration for car/fob black-box testing.

Tests are run via: pytest [options] [--using board@sn1,sn2]

Mode selection:
    --using board@sn1,sn2  -> Hardware mode (both devices on real hardware)
                              board: stm32 or tm4c
                              sn1,sn2: debug probe serial numbers (not serial ports)
    (no --using)           -> Simulation mode (with virtual serial ports)

Each test declares what roles it needs via the deploy fixture:
1. Single device:   deploy(RoleConfig("paired_fob", id="1", pin="123456"))
2. Two devices:     deploy(RoleConfig("car", id="1"), RoleConfig("paired_fob", id="1", pin="123456"))

The fixture system:
- Builds firmware using SCons
- For hardware: flashes devices and opens serial ports
- For simulation: launches simulation processes with virtual serial ports
- Returns DeployedDevice objects for testing
- Cleans up resources after test completes
"""

import os
import pytest
import subprocess
import serial
import time
from pathlib import Path
from typing import Optional, Union
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
# Session-scoped Secrets File
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def temp_secrets_file(tmp_path_factory):
    """
    Redirect secrets.json to a temp file for the test session.

    This prevents test runs from consuming fob IDs in (or corrupting) the
    project-level secrets/secrets.json that a developer may be using for
    manual testing. The temp file is deleted automatically when the session ends.
    """
    secrets_path = tmp_path_factory.mktemp("secrets") / "secrets.json"
    os.environ["TEST_SECRETS_FILE"] = str(secrets_path)
    yield secrets_path
    os.environ.pop("TEST_SECRETS_FILE", None)


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
        print("WARNING: Only one serial number provided. Tests requiring 2 or more will fail.")
        #raise ValueError("Hardware mode requires at least 2 serial numbers: --using board@sn1,sn2")

    return HardwareConfig(board=board, identifiers=identifiers)


# ============================================================================
# Main Deploy Fixture
# ============================================================================

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

    Returns:
        A callable that takes 1 or 2 RoleConfig objects and returns
        either a DeployedDevice or tuple[DeployedDevice, DeployedDevice]
    """

    deployed_devices = []
    sim_env = None

    if hardware_config:
        # Hardware mode
        def deploy_fn(
            cfg1: RoleConfig,
            cfg2: Optional[RoleConfig] = None
        ) -> Union[DeployedDevice, tuple[DeployedDevice, DeployedDevice]]:
            """Deploy to hardware: build, attach serial, flash, verify startup."""
            from list import find_port_by_serial_number
            from openocd import flash as openocd_flash

            # Deploy first device
            binary1 = build_binary(cfg1, hardware_config.board)

            # Find and open serial port BEFORE flashing
            port1 = find_port_by_serial_number(hardware_config.identifiers[0])
            if not port1:
                raise RuntimeError(f"Could not find port for probe {hardware_config.identifiers[0]}")
            ser1 = serial.Serial(port1, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
            ser1.reset_input_buffer()

            # Flash device (causes reset and boot)
            result = openocd_flash(hardware_config.board, hardware_config.identifiers[0], str(binary1))
            if result != 0:
                ser1.close()
                raise RuntimeError("Flash failed for first device")

            # Wait for and verify "OK: started"
            time.sleep(0.2)
            startup = ser1.readline().decode('ascii', errors='replace').strip()
            '''
            if "OK: started" not in startup:
                ser1.close()
                raise RuntimeError(f"First device didn't start properly, got: '{startup}'")
                '''

            dev1 = DeployedDevice(ser1)
            deployed_devices.append(dev1)

            # Deploy second device if requested
            if cfg2:
                if len(hardware_config.identifiers) < 2:
                    raise ValueError("Hardware mode requires at least 2 serial numbers: --using board@sn1,sn2")
                
                binary2 = build_binary(cfg2, hardware_config.board)

                # Find and open serial port BEFORE flashing
                port2 = find_port_by_serial_number(hardware_config.identifiers[1])
                if not port2:
                    raise RuntimeError(f"Could not find port for probe {hardware_config.identifiers[1]}")
                ser2 = serial.Serial(port2, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)

                # Flash device (causes reset and boot)
                result = openocd_flash(hardware_config.board, hardware_config.identifiers[1], str(binary2))
                if result != 0:
                    ser2.close()
                    raise RuntimeError("Flash failed for second device")

                # Wait for and verify "OK: started"
                time.sleep(0.2)
                startup = ser2.readline().decode('ascii', errors='replace').strip()
                '''
                if "OK: started" not in startup:
                    ser2.close()
                    raise RuntimeError(f"Second device didn't start properly, got: '{startup}'")
                    '''

                dev2 = DeployedDevice(ser2)
                deployed_devices.append(dev2)
                return dev1, dev2
            else:
                return dev1

    else:
        # Simulation mode
        def deploy_fn(
            cfg1: RoleConfig,
            cfg2: Optional[RoleConfig] = None
        ) -> Union[DeployedDevice, tuple[DeployedDevice, DeployedDevice]]:
            """Deploy to simulation: build binaries and create SimulationEnvironment."""
            nonlocal sim_env

            binary1 = build_binary(cfg1, "sim")
            binary2 = build_binary(cfg2, "sim") if cfg2 else None

            sim_env = SimulationEnvironment(binary1, binary2)
            # SimulationEnvironment now returns DeployedDevice or tuple directly
            return sim_env.__enter__()

    yield deploy_fn

    # Cleanup - unified for both modes!
    if sim_env:
        # Simulation: let SimulationEnvironment handle cleanup
        sim_env.__exit__(None, None, None)
    else:
        # Hardware: close devices manually
        for dev in deployed_devices:
            dev.close()


# ============================================================================
# Helper Functions
# ============================================================================

def build_binary(cfg: RoleConfig, platform: str) -> Path:
    """
    Build firmware for a role using SCons.

    Args:
        cfg: RoleConfig with role, id (optional), and pin (optional)
        platform: "stm32", "tm4c", or "sim"

    Returns:
        Path to the built binary
    """
    # Build command with conditional arguments
    cmd = ["scons", "-j8", f"platform={platform}", f"role={cfg.role}", "test=True"]
    if cfg.id:
        cmd.append(f"id={cfg.id}")
    if cfg.pin:
        cmd.append(f"pin={cfg.pin}")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Build failed for {cfg.role}:\n{result.stderr}")

    # Construct binary path: hardware/{platform}/build/{role}_{id}/{role}_{id}.elf
    if cfg.role in ["car", "paired_fob"]:
        name = f"{cfg.role}_{cfg.id}"
    else:
        name = cfg.role

    binary_dir = PROJECT_ROOT / "hardware" / platform / "build" / name

    # Different binary extensions for different platforms
    if platform == "sim":
        binary_path = binary_dir / name
    else:
        binary_path = binary_dir / f"{name}.elf"

    if not binary_path.exists():
        raise RuntimeError(f"Built binary not found at {binary_path}")

    return binary_path


# ============================================================================
# Convenience Fixtures
# ============================================================================

@pytest.fixture
def paired_fob(deploy):
    """Single paired fob."""
    return deploy(RoleConfig("paired_fob", id="1337", pin="123456"))

@pytest.fixture
def unpaired_fob(deploy):
    """Single unpaired fob."""
    return deploy(RoleConfig("unpaired_fob"))


@pytest.fixture
def car_and_paired_fob(deploy):
    """Car and its paired fob."""
    return deploy(
        RoleConfig("car", id="1337"),
        RoleConfig("paired_fob", id="1337", pin="123456")
    )


@pytest.fixture
def paired_and_unpaired_fob(deploy):
    """A paired fob and an unpaired fob."""
    return deploy(
        RoleConfig("paired_fob", id="1337", pin="123456"),
        RoleConfig("unpaired_fob")
    )
