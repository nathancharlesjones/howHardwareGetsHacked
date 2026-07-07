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
    pairing_delay_ms: Optional[str] = None  # Override anti-brute-force pairing delay (paired_fob only)


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

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--using", default=None):
        skip = pytest.mark.skip(reason="requires hardware (pass --using board@sn1,sn2)")
        for item in items:
            if item.get_closest_marker("hardware_only"):
                item.add_marker(skip)

    if not config.getoption("--run-birthday-bound-attack-full", default=False):
        skip = pytest.mark.skip(reason="full birthday bound attack reproduction; pass --run-birthday-bound-attack-full to enable")
        for item in items:
            if item.get_closest_marker("birthday_bound_attack_full"):
                item.add_marker(skip)


def pytest_addoption(parser):
    """Add custom command-line options for pytest."""
    parser.addoption(
        "--using",
        type=str,
        default=None,
        help="Hardware mode: board@sn1,sn2 (e.g., stm32@066DFF555051897267073723,0670FF494849897267154049)"
    )
    parser.addoption(
        "--n-samples",
        type=int,
        default=50,
        help="Number of seed samples for test_seed_entropy_sufficient (default: 50). "
             "Larger values give a tighter lower-bound estimate but require more resets. "
             "~200 needed to distinguish 5-bit from 3-bit sources; "
             "~5000 for a meaningful estimate of an 8-bit/byte source."
    )
    parser.addoption(
        "--ea-bin-dir",
        type=str,
        default=None,
        help="Directory containing the compiled ea_iid/ea_non_iid/ea_restart binaries "
             "from https://github.com/usnistgov/SP800-90B_EntropyAssessment (cpp/ after "
             "'make iid non_iid restart'). Defaults to libraries/SP800-90B_EntropyAssessment/cpp, "
             "or the EA_BIN_DIR environment variable."
    )
    parser.addoption(
        "--entropy-n-samples",
        type=int,
        default=1_000_000,
        help="Samples to collect per entropy source for the IID/non-IID assessment "
             "(default: 1,000,000, the SP800-90B minimum). Lower values run much faster "
             "over serial but the result is a dev sanity check only, not a valid claim."
    )
    parser.addoption(
        "--entropy-restarts",
        type=int,
        default=1000,
        help="Number of restarts for the entropy restart test (default: 1000, the SP800-90B default)."
    )
    parser.addoption(
        "--entropy-samples-per-restart",
        type=int,
        default=1000,
        help="Samples collected per restart for the entropy restart test (default: 1000, the SP800-90B default)."
    )
    parser.addoption(
        "--entropy-data-file",
        type=str,
        default=None,
        help="Path to a .bin capture (with same-named .json sidecar) previously written by "
             "TestEntropyCapture.test_capture_entropy_samples, e.g. testing/entropy_logs/"
             "20260705_120000_tm4c_iid_non_iid.bin. Used by test_entropy_analysis.py's "
             "test_entropy_sources_iid_or_non_iid (or pass --platform instead to use the "
             "latest capture for a platform)."
    )
    parser.addoption(
        "--entropy-restart-data-file",
        type=str,
        default=None,
        help="Path to a .bin capture (with same-named .json sidecar) previously written by "
             "TestEntropyCapture.test_capture_entropy_restart_samples. Used by "
             "test_entropy_analysis.py's test_entropy_sources_restart (or pass --platform "
             "instead to use the latest capture for a platform)."
    )
    # --platform and --entropy-skip-analysis exist only because pytest CLI options must be
    # registered from a conftest.py -- neither implies any hardware dependency. --platform is
    # consumed solely by test_entropy_analysis.py (pure file-lookup: which saved .bin/.json to
    # analyze), which never touches the deploy/hardware_config fixtures above.
    parser.addoption(
        "--platform",
        type=str,
        default=None,
        choices=["sim", "tm4c", "stm32"],
        help="Analyze the most recently written capture for this platform instead of passing "
             "an explicit --entropy-data-file/--entropy-restart-data-file path (see "
             "test_entropy_analysis.py). Raises if no matching capture exists under "
             "testing/entropy_logs/."
    )
    parser.addoption(
        "--entropy-skip-analysis",
        action="store_true",
        default=False,
        help="TestEntropyCapture's tests analyze what they just captured by default; pass "
             "this to only write the .bin/.json capture and skip that immediate analysis."
    )
    parser.addoption(
        "--run-birthday-bound-attack-full",
        action="store_true",
        default=False,
        help="Enable test_birthday_bound_attack_full (skipped by default): a full reproduction of "
             "the birthday-bound table/oracle attack against the car's nonce, rather than "
             "just the always-on quick cost estimate in test_birthday_bound_attack_quick_check."
    )
    parser.addoption(
        "--oracle-table-size",
        type=int,
        default=65536,
        help="Number of (nonce -> response) pairs test_birthday_bound_attack_full records before "
             "it stops adding new entries and starts watching for a repeat (default: 65536, "
             "i.e. sqrt(2**32), the classic birthday bound for a 32-bit nonce)."
    )
    parser.addoption(
        "--oracle-max-iter",
        type=int,
        default=0,
        help="Cap on how many further unlocks test_birthday_bound_attack_full watches for a nonce "
             "repeat after its table is built, before giving up (test passes if the cap is "
             "reached with no repeat found). Default: 0, meaning no cap - keep watching "
             "until a repeat is found."
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
    sim_envs = []

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
            """Deploy to simulation: build binaries and create SimulationEnvironment.

            A test may call this more than once (e.g. to pair a fob in one
            environment, then move its state to a fresh one) - each call gets
            its own SimulationEnvironment, and all of them are torn down at
            fixture teardown. A single nonlocal used to hold only the most
            recent environment, silently leaking every prior one's processes
            and relay threads; those non-daemon threads never exit, which is
            why the full suite would hang on exit after adding a test that
            deploys twice.
            """
            binary1 = build_binary(cfg1, "sim")
            binary2 = build_binary(cfg2, "sim") if cfg2 else None

            sim_env = SimulationEnvironment(binary1, binary2)
            sim_envs.append(sim_env)
            # SimulationEnvironment now returns DeployedDevice or tuple directly
            return sim_env.__enter__()

    yield deploy_fn

    # Cleanup - unified for both modes!
    if sim_envs:
        # Simulation: let each SimulationEnvironment handle its own cleanup
        for sim_env in sim_envs:
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
    if cfg.pairing_delay_ms is not None:
        cmd.append(f"pairing_delay_ms={cfg.pairing_delay_ms}")

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
