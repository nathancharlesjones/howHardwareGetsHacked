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
    --using platform@port1,port2  -> Hardware mode (both devices on real hardware)
    (no --using)                  -> Simulation mode (x86 with virtual serial ports)

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
from typing import Optional, List
from virtualserialports import VirtualSerialPorts


PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_SCRIPT = PROJECT_ROOT / "project.py"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


@dataclass
class HardwareConfig:
    """Hardware configuration: platform and list of serial ports."""
    platform: str
    ports: List[str]


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
    exe = build_dir / folder
    if not exe.exists():
        candidates = [f for f in build_dir.iterdir() if f.is_file() and f.suffix not in ['.h', '.o']]
        exe = candidates[0] if candidates else exe
    return exe


def flash_hardware(platform: str, port: str, binary: Path):
    """Flash binary to hardware device."""
    cmd = [
        "python3", str(PROJECT_SCRIPT), "flash",
        "--platform", platform,
        "--port", port,
        "--bin", str(binary)
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Flash failed:\n{result.stderr}")


def pytest_addoption(parser):
    parser.addoption("--using", type=str, default=None,
                     help="Hardware: platform@port1,port2 (e.g., stm32@/dev/ttyUSB0,/dev/ttyUSB1)")


@pytest.fixture(scope="session")
def hardware_config(request) -> Optional[HardwareConfig]:
    """Parse --using argument into HardwareConfig, or None for simulation mode."""
    using = request.config.getoption("--using")
    if not using:
        return None
    
    platform, ports_str = using.split("@", 1)
    ports = [p.strip() for p in ports_str.split(",")]
    
    if len(ports) < 2:
        raise ValueError("Hardware mode requires at least 2 ports: --using platform@port1,port2")
    
    return HardwareConfig(platform=platform, ports=ports)


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
        port_idx = 0
        
        def _deploy(cfg: RoleConfig) -> DeployedDevice:
            nonlocal port_idx
            if port_idx >= len(hardware_config.ports):
                raise RuntimeError(f"Not enough hardware ports (have {len(hardware_config.ports)}, need more)")
            
            port = hardware_config.ports[port_idx]
            port_idx += 1
            
            binary = build_role(cfg, hardware_config.platform)
            flash_hardware(hardware_config.platform, port, binary)
            
            ser = serial.Serial(port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
            time.sleep(0.1)
            ser.reset_input_buffer()
            
            # Wait for "OK: started" message
            startup = ser.readline().decode('ascii', errors='replace').strip()
            if not startup.startswith("OK"):
                raise RuntimeError(f"Device didn't start properly, got: {startup}")
            
            dev = DeployedDevice(cfg.role, ser, hardware_config.platform)
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