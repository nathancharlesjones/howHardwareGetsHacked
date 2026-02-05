"""
Refactored deploy() fixture for conftest.py

This shows how to use the new SimulationEnvironment with overload + conditional return.
Replace the entire @pytest.fixture def deploy(...) section in conftest.py with this code.

Key patterns:
1. Import: from simulate import SimulationEnvironment, RoleConfig
2. Both hardware and simulation modes support exactly 1 or 2 roles via deploy(cfg1, cfg2=None)
3. Return type depends on whether cfg2 is provided (using @overload for type hints)
"""

import pytest
import subprocess
import serial
import os
import time
from pathlib import Path
from typing import Optional, Union, overload
from devices import DeployedDevice
from simulate import SimulationEnvironment, RoleConfig


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
            dev1 = DeployedDevice(ser1, hardware_config.board)
            deployed_devices.append(dev1)
            
            # Deploy second device if requested
            if cfg2:
                binary2 = build_binary(cfg2, hardware_config.board)
                port2 = flash_and_open_port(hardware_config.board, hardware_config.identifiers[1], binary2)
                ser2 = serial.Serial(port2, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
                time.sleep(0.1)
                ser2.reset_input_buffer()
                dev2 = DeployedDevice(ser2, hardware_config.board)
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
            return sim_env.__enter__()
        
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
# Helper Functions for Hardware Mode
# ============================================================================

DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


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
        f"Available ports: {[p.device for p in ports]}"
    )


# ============================================================================
# Example Updated Convenience Fixtures
# ============================================================================

@pytest.fixture
def paired_fob(deploy):
    """Single paired fob."""
    dev, = (deploy(RoleConfig("paired_fob", id="1", pin="123456")),)  # Unpack single
    return dev


@pytest.fixture
def unpaired_fob(deploy):
    """Single unpaired fob."""
    dev, = (deploy(RoleConfig("unpaired_fob")),)  # Unpack single
    return dev


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


# ============================================================================
# Note on fixture definitions
# ============================================================================

# For single-device fixtures, you have two options:
#
# Option 1 (unpacking, shown above):
#   dev, = (deploy(...),)  # Unpack single-element tuple, then use dev
#
# Option 2 (simpler - just use deploy directly):
#   dev = deploy(RoleConfig(...))  # Type checker knows this returns DeployedDevice
#
# Option 2 is cleaner. The unpacking above was just to show the pattern.
# In practice, just do:
#
#   @pytest.fixture
#   def paired_fob(deploy):
#       return deploy(RoleConfig("paired_fob", id="1", pin="123456"))
