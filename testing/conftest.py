"""
pytest configuration for car/fob black-box testing.

Tests are run via: ./project.py test [categories] [--using platform@port1,port2]

Each test declares what roles it needs. The fixture system:
1. Builds each role (via project.py build --test-build)
2. For hardware: flashes and opens serial ports
3. For x86: launches processes with virtual serial ports
4. Returns serial port objects to the test
5. Cleans up after test completes

Mode selection:
    --using board@id1,id2  -> Hardware mode (both devices on real hardware)
                              board: stm32 or tm4c
                              id1,id2: probe serial numbers OR serial port paths
    (no --using)           -> Simulation mode (x86 with virtual serial ports)

x86 simulation wiring (using PyVirtualSerialPorts):
    Test <--[host1]--> exe1 <--[board]--> exe2 <--[host2]--> Test
"""

import pytest
import subprocess
import serial
import os
import signal
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple
from virtualserialports import VirtualSerialPorts

import sys
from pathlib import Path
tools_dir = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_dir))

from flashing import flash_device, FlashError


PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_SCRIPT = PROJECT_ROOT / "project.py"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


@dataclass
class HardwareConfig:
    """Hardware configuration: board type and list of probe identifiers."""
    board: str  # "stm32" or "tm4c"
    identifiers: List[str]  # Serial numbers or paths


@dataclass
class RoleConfig:
    role: str
    id: Optional[str] = None
    pin: Optional[str] = None


@dataclass
class DeployedDevice:
    role: str
    serial: serial.Serial
    platform: str
    _pid: Optional[int] = None
    _vsp: Optional[VirtualSerialPorts] = None

    def send(self, data: str) -> None:
        if not data.endswith('\n'):
            data += '\n'
        self.serial.write(data.encode('ascii'))
        self.serial.flush()

    def recv(self, timeout: Optional[float] = None) -> str:
        old_timeout = self.serial.timeout
        if timeout is not None:
            self.serial.timeout = timeout
        try:
            return self.serial.readline().decode('ascii', errors='replace').strip()
        finally:
            self.serial.timeout = old_timeout

    def send_recv(self, data: str, timeout: Optional[float] = None) -> str:
        self.send(data)
        return self.recv(timeout)

    def close(self):
        self.serial.close()
        if self._pid:
            try:
                os.kill(self._pid, signal.SIGTERM)
                time.sleep(0.05)
                os.kill(self._pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except OSError:
                pass
        if self._vsp:
            self._vsp.stop()
            self._vsp.close()


def build_role(cfg: RoleConfig, platform: str) -> Path:
    """Build firmware for a role, returns path to binary."""
    cmd = ["python3", str(PROJECT_SCRIPT), "build",
           "--platform", platform, "--role", cfg.role, "--test-build"]
    if cfg.id:
        cmd += ["--id", cfg.id]
    if cfg.pin:
        cmd += ["--pin", cfg.pin]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Build failed for {cfg.role}:\n{result.stderr}")

    folder = f"{cfg.role}_{cfg.id}" if cfg.id else cfg.role
    build_dir = PROJECT_ROOT / "hardware" / platform / "build" / folder
    exe = build_dir / f"{folder}.bin"
    if not exe.exists():
        candidates = [f for f in build_dir.iterdir() if f.is_file() and f.suffix not in ['.h', '.o']]
        exe = candidates[0] if candidates else exe
    return exe


def find_serial_port_for_probe(identifier: str, board: str) -> str:
    """
    Find the serial port associated with a debug probe.
    
    Args:
        identifier: Either a serial number or already a port path
        board: Board type for VID/PID matching
        
    Returns:
        Serial port path (e.g., /dev/ttyACM0)
    """
    # If it looks like a port path already, return it
    if identifier.startswith('/dev/') or identifier.startswith('COM'):
        return identifier
    
    # Otherwise, search by serial number
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        
        # VID/PID pairs for debug probes that have serial ports
        # ST-Link on Nucleo boards exposes a virtual COM port
        # TI ICDI on Tiva LaunchPads also exposes a virtual COM port
        for port in ports:
            if port.serial_number == identifier:
                return port.device
            # Also check if identifier is in the hardware ID
            if identifier in (port.hwid or ''):
                return port.device
        
        # If not found by serial, try matching by VID/PID and position
        # This is a fallback - ideally users should use serial numbers
        raise RuntimeError(
            f"Could not find serial port for probe '{identifier}'.\n"
            f"Available ports: {[p.device for p in ports]}\n"
            f"Hint: Use 'list probes' to see connected debug probes."
        )
    except ImportError:
        raise RuntimeError("pyserial not installed. Install with: pip install pyserial")


def flash_hardware(board: str, identifier: str, binary: Path) -> str:
    """
    Flash binary to hardware device using OpenOCD.
    
    Args:
        board: Board type ("stm32" or "tm4c")
        identifier: Probe serial number or serial port path
        binary: Path to binary fiboardle
        
    Returns:
        Serial port path for communicating with the device
    """
    # Determine the probe identifier (serial number) for OpenOCD
    # If identifier is a port path, we need to find the associated probe
    if identifier.startswith('/dev/') or identifier.startswith('COM'):
        # User gave us a port - we'll use it for serial, but need probe SN for flashing
        # For now, if only one probe is connected, OpenOCD will find it
        # For multi-probe setups, users should use serial numbers
        probe_id = None
        serial_port = identifier
    else:
        probe_id = identifier
        serial_port = find_serial_port_for_probe(identifier, board)
    
    # Flash using our flashing module
    try:
        flash_device(
            platform=board,
            binary_path=str(binary),
            identifier=probe_id,
            verify=True,
            reset=True,
            verbose=False,
        )
    except FlashError as e:
        raise RuntimeError(f"Flash failed:\n{e}")
    
    return serial_port


def pytest_addoption(parser):
    parser.addoption("--using", type=str, default=None,
                     help="Hardware: board@id1,id2 (e.g., stm32@SN1,SN2 or tm4c@/dev/ttyACM0,/dev/ttyACM1)")


@pytest.fixture(scope="session")
def hardware_config(request) -> Optional[HardwareConfig]:
    """Parse --using argument into HardwareConfig, or None for simulation mode."""
    using = request.config.getoption("--using")
    if not using:
        return None
    
    if "@" not in using:
        raise ValueError(
            f"Invalid --using format: '{using}'\n"
            f"Expected: board@id1,id2 (e.g., stm32@SN1,SN2 or tm4c@/dev/ttyACM0,/dev/ttyACM1)"
        )
    
    board, ids_str = using.split("@", 1)
    identifiers = [i.strip() for i in ids_str.split(",")]
    
    # Validate board type
    if board not in ["stm32", "tm4c"]:
        raise ValueError(f"Unknown board '{board}'. Supported: stm32, tm4c")
    
    if len(identifiers) < 2:
        raise ValueError("Hardware mode requires at least 2 identifiers: --using board@id1,id2")
    
    return HardwareConfig(board=board, identifiers=identifiers)


@pytest.fixture
def deploy(hardware_config):
    """
    Factory fixture for deploying roles.
    
    Automatically selects hardware or simulation mode based on --using flag.
    
    Usage:
        def test_something(deploy):
            car = deploy(RoleConfig("car", id="123"))
            fob = deploy(RoleConfig("paired_fob", id="123", pin="654321"))
    """
    deployed = []
    
    if hardware_config:
        # Hardware mode
        id_idx = 0
        
        def _deploy(cfg: RoleConfig) -> DeployedDevice:
            nonlocal id_idx
            if id_idx >= len(hardware_config.identifiers):
                raise RuntimeError(
                    f"Not enough hardware devices "
                    f"(have {len(hardware_config.identifiers)}, need more)"
                )
            
            identifier = hardware_config.identifiers[id_idx]
            id_idx += 1
            
            # Build firmware for hardware platform
            binary = build_role(cfg, hardware_config.board)
            
            # Flash and get serial port
            serial_port = flash_hardware(hardware_config.board, identifier, binary)
            print(f"serial_port for {identifier}: {serial_port}")
            
            # Give device time to reset and boot
            time.sleep(0.2)
            
            # Open serial connection
            ser = serial.Serial(serial_port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
            time.sleep(0.1)
            ser.reset_input_buffer()
            
            # Wait for "OK: started" message
            startup = ser.readline().decode('ascii', errors='replace').strip()
            #if not startup.startswith("OK"):
            #    raise RuntimeError(f"Device didn't start properly, got: {startup}")
            
            dev = DeployedDevice(cfg.role, ser, hardware_config.board)
            deployed.append(dev)
            return dev
    
    else:
        # Simulation mode - create all virtual ports upfront
        # Board connection: exe1 <-> exe2
        board_vsp = VirtualSerialPorts(2)
        board_vsp.open()
        board_vsp.start()
        board_ports = board_vsp.ports  # [exe1_board, exe2_board]
        
        # Host connections: test <-> exe1, test <-> exe2
        host_vsps = []
        exe_idx = 0
        
        def _deploy(cfg: RoleConfig) -> DeployedDevice:
            nonlocal exe_idx
            if exe_idx >= 2:
                raise RuntimeError("Simulation mode only supports 2 devices")
            
            binary = build_role(cfg, "x86")
            
            # Create host connection for this exe
            host_vsp = VirtualSerialPorts(2)
            host_vsp.open()
            host_vsp.start()
            host_vsps.append(host_vsp)
            test_port, exe_host_port = host_vsp.ports
            
            # Get this exe's board port
            exe_board_port = board_ports[exe_idx]
            exe_idx += 1
            
            # Test connects to its end
            ser = serial.Serial(test_port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
            ser.reset_input_buffer()

            # Launch exe
            pid = os.fork()
            if pid == 0:
                os.setsid()
                os.execv(str(binary), [str(binary), f"host={exe_host_port}", f"board={exe_board_port}"])
            
            time.sleep(0.1)
                        
            # Wait for "OK: started" message
            startup = ser.readline().decode('ascii', errors='replace').strip()
            if not startup.startswith("OK"):
                raise RuntimeError(f"Device didn't start properly, got: {startup}")
            
            dev = DeployedDevice(cfg.role, ser, "x86", _pid=pid, _vsp=host_vsp)
            deployed.append(dev)
            return dev
    
    yield _deploy
    
    # Cleanup
    for d in deployed:
        d.close()
    
    if not hardware_config:
        # Clean up board VSP (only in simulation mode)
        board_vsp.stop()
        board_vsp.close()


# =============================================================================
# Convenience Fixtures
# =============================================================================

@pytest.fixture
def paired_fob(deploy):
    return deploy(RoleConfig("paired_fob", id="1", pin="123456"))


@pytest.fixture
def unpaired_fob(deploy):
    return deploy(RoleConfig("unpaired_fob"))


@pytest.fixture
def car_and_paired_fob(deploy):
    car = deploy(RoleConfig("car", id="1"))
    fob = deploy(RoleConfig("paired_fob", id="1", pin="123456"))
    return car, fob


@pytest.fixture
def paired_and_unpaired_fob(deploy):
    paired = deploy(RoleConfig("paired_fob", id="1", pin="123456"))
    unpaired = deploy(RoleConfig("unpaired_fob"))
    return paired, unpaired


@pytest.fixture
def car_paired_unpaired(deploy):
    car = deploy(RoleConfig("car", id="1"))
    paired = deploy(RoleConfig("paired_fob", id="1", pin="123456"))
    unpaired = deploy(RoleConfig("unpaired_fob"))
    return car, paired, unpaired
