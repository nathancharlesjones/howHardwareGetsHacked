"""
pytest configuration for car/fob black-box testing.

Tests are run via: ./project.py test [categories] [--using platform@port,...]

Each test declares what roles it needs. The fixture system:
1. Builds each role (via project.py build)
2. For hardware: flashes and opens serial port
3. For x86: launches processes with virtual serial ports
4. Returns serial port objects to the test
5. Cleans up after test completes

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
from typing import Optional, Tuple
from virtualserialports import VirtualSerialPorts


PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_SCRIPT = PROJECT_ROOT / "project.py"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


@dataclass
class HardwareTarget:
    platform: str
    port: str


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
    _vsp: Optional[VirtualSerialPorts] = None  # Keep reference for cleanup

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
    cmd = ["python3", str(PROJECT_SCRIPT), "build", "--platform", platform, "--role", cfg.role]
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
    cmd = [
        "python3", str(PROJECT_SCRIPT), "flash",
        "--platform", platform,
        "--port", port,
        "--bin", str(binary)
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Flash failed:\n{result.stderr}")


def deploy_hardware(cfg: RoleConfig, hw: HardwareTarget) -> DeployedDevice:
    binary = build_role(cfg, hw.platform)
    flash_hardware(hw.platform, hw.port, binary)
    ser = serial.Serial(hw.port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
    time.sleep(0.1)
    ser.reset_input_buffer()
    return DeployedDevice(cfg.role, ser, hw.platform)


def deploy_x86(cfg: RoleConfig, board_port: Optional[str]) -> Tuple[DeployedDevice, str]:
    """
    Deploy an x86 executable.

    Args:
        cfg: Role configuration
        board_port: Port for board connection (None for first exe, which creates it)

    Returns:
        (DeployedDevice, board_port_for_next_exe)
    """
    binary = build_role(cfg, "x86")

    # Create host connection (test <-> exe)
    host_vsp = VirtualSerialPorts(2)
    host_vsp.open()
    host_vsp.start()
    test_port, exe_host_port = host_vsp.ports

    # Create or reuse board connection
    board_vsp = None
    if board_port is None:
        board_vsp = VirtualSerialPorts(2)
        board_vsp.open()
        board_vsp.start()
        exe_board_port, next_board_port = board_vsp.ports
    else:
        exe_board_port = board_port
        next_board_port = None  # Already used

    # Launch exe
    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.execv(str(binary), [str(binary), f"host={exe_host_port}", f"board={exe_board_port}"])

    time.sleep(0.1)

    # Test connects to its end
    ser = serial.Serial(test_port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
    ser.reset_input_buffer()

    device = DeployedDevice(cfg.role, ser, "x86", _pid=pid, _vsp=host_vsp)

    # First exe owns the board_vsp for cleanup
    if board_vsp:
        device._board_vsp = board_vsp

    return device, next_board_port


def pytest_addoption(parser):
    parser.addoption("--using", action="append", default=[],
                     help="Hardware: platform@port (e.g., stm32@/dev/ttyUSB0)")


@pytest.fixture(scope="session")
def hardware_targets(request) -> list[HardwareTarget]:
    targets = []
    for spec in request.config.getoption("--using"):
        platform, port = spec.split("@", 1)
        targets.append(HardwareTarget(platform, port))
    return targets


@pytest.fixture
def deploy(hardware_targets):
    """
    Factory fixture for deploying roles.

    Usage:
        def test_something(deploy):
            car = deploy(RoleConfig("car", id="123"))
            fob = deploy(RoleConfig("paired_fob", id="123", pin="654321"))
    """
    deployed = []
    hw_idx = 0
    board_port = None

    def _deploy(cfg: RoleConfig) -> DeployedDevice:
        nonlocal hw_idx, board_port
        if hw_idx < len(hardware_targets):
            hw = hardware_targets[hw_idx]
            hw_idx += 1
            dev = deploy_hardware(cfg, hw)
        else:
            dev, board_port = deploy_x86(cfg, board_port)
        deployed.append(dev)
        return dev

    yield _deploy

    for d in deployed:
        d.close()
        if hasattr(d, '_board_vsp') and d._board_vsp:
            d._board_vsp.stop()
            d._board_vsp.close()


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