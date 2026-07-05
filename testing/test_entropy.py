"""
Collects real entropy-source samples from a car (getEntropyDescription /
getEntropySamples) and writes them to a timestamped .bin/.json capture under
testing/entropy_logs/ for NIST SP800-90B assessment.

By default, each capture test immediately analyzes what it just wrote, by
importing and calling the same functions test_entropy_analysis.py's
standalone tests use -- see that file for the actual NIST statistics and for
re-running analysis later against a saved capture without a live device.
Pass --entropy-skip-analysis to only capture.

    TestEntropyCapture.test_capture_entropy_samples
        -> analyzed by test_entropy_analysis.analyze_iid_or_non_iid
    TestEntropyCapture.test_capture_entropy_restart_samples  (hardware_only)
        -> analyzed by test_entropy_analysis.analyze_restart

Common invocations:

    # Capture + analyze in one shot (writes .bin/.json, then immediately
    # runs the NIST IID/non-IID + pairwise assessment on it)
    pytest test_entropy.py -k test_capture_entropy_samples

    # Capture + analyze the restart test (hardware only)
    pytest test_entropy.py -k test_capture_entropy_restart_samples --using board@sn1,sn2

    # Capture only, analyze later (see test_entropy_analysis.py for how,
    # including --platform to avoid re-typing the saved filename)
    pytest test_entropy.py -k test_capture_entropy_samples --entropy-skip-analysis
"""

from datetime import datetime
from pathlib import Path

import pytest

from conftest import RoleConfig
import protocol as proto
from entropy_assessment import save_capture
from test_entropy_analysis import analyze_iid_or_non_iid, analyze_restart

LOG_DIR = Path(__file__).parent / "entropy_logs"


def _timestamped_path(name: str, board: str, suffix: str) -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return LOG_DIR / f"{timestamp}_{board}_{name}{suffix}"


class TestEntropyCapture:
    """Pulls real samples from a device, saves them to disk, and (unless
    --entropy-skip-analysis is passed) immediately analyzes the capture --
    see test_entropy_analysis.py to re-run analysis later without a live
    device."""

    def test_capture_entropy_samples(self, deploy, request, hardware_config):
        n_samples = request.config.getoption("--entropy-n-samples")
        board = hardware_config.board if hardware_config else "sim"

        car = deploy(RoleConfig("car", id="1337"))

        widths = proto.get_entropy_description(car)
        assert widths, "Device reports zero entropy sources"

        # One interleaved collection: each row is one sample from every
        # source, read back to back on the device, so row i is a genuine
        # same-instant reading across sources once deinterleaved later.
        print(f"\nCollecting {n_samples} interleaved rows from {len(widths)} source(s) "
              f"({', '.join(f'{name}:{w}B' for name, w in widths.items())})...")
        raw = proto.collect_entropy_samples(car, n_samples, show_progress=True)

        bin_path = _timestamped_path("iid_non_iid", board, ".bin")
        save_capture(bin_path, raw, widths, n_samples=n_samples, board=board)
        print(f"\nSaved capture: {bin_path}\nSaved metadata: {bin_path.with_suffix('.json')}")

        if request.config.getoption("--entropy-skip-analysis"):
            print(f"Analyze later with: pytest test_entropy_analysis.py -k iid_or_non_iid "
                  f"--entropy-data-file={bin_path}")
            return

        analyze_iid_or_non_iid(bin_path, ea_bin_dir=request.config.getoption("--ea-bin-dir"))

    @pytest.mark.hardware_only
    def test_capture_entropy_restart_samples(self, deploy, request, hardware_config):
        """
        Hardware-only: restart() triggers a real warm reset on STM32/TM4C
        (NVIC_SystemReset() / SysCtlReset()), which this capture needs to
        collect genuinely independent post-boot samples. In simulation
        restart() remains an empty stub -- there's no real boot sequence to
        re-run and process restart isn't viable here (see
        hardware/sim/source/sim.c) -- so simulation mode is skipped outright
        rather than produce a misleadingly-passing capture.
        """
        restarts = request.config.getoption("--entropy-restarts")
        samples_per_restart = request.config.getoption("--entropy-samples-per-restart")
        board = hardware_config.board

        car = deploy(RoleConfig("car", id="1337"))

        widths = proto.get_entropy_description(car)
        assert widths, "Device reports zero entropy sources"

        # One interleaved collection per restart cycle: every source's
        # post-restart rows come from the same physical reboot, instead of
        # each source separately looping through its own `restarts` restarts
        # (which would let source A's restart #5 and source B's restart #5
        # be two different, unrelated reboots).
        print(f"\nCollecting {restarts}x{samples_per_restart} interleaved restart rows from "
              f"{len(widths)} source(s) ({', '.join(f'{name}:{w}B' for name, w in widths.items())})...")

        rows = bytearray()
        for r in range(restarts):
            rows += proto.collect_entropy_samples(car, samples_per_restart)
            proto.cmd_restart(car)
            # restart() really reboots on hardware; drain the unprompted
            # "OK: started" boot banner now, or the next loop iteration's
            # collect_entropy_samples() would read it instead of real data.
            proto.wait_for_boot(car)
            frac = (r + 1) / restarts
            bar = "#" * int(frac * 30) + "-" * (30 - int(frac * 30))
            print(f"\r  [{bar}] {r + 1}/{restarts} restarts", end="", flush=True)
        print()

        bin_path = _timestamped_path("restart", board, ".bin")
        save_capture(bin_path, bytes(rows), widths, restarts=restarts,
                     samples_per_restart=samples_per_restart, board=board)
        print(f"\nSaved capture: {bin_path}\nSaved metadata: {bin_path.with_suffix('.json')}")

        if request.config.getoption("--entropy-skip-analysis"):
            print(f"Analyze later with: pytest test_entropy_analysis.py -k entropy_sources_restart "
                  f"--entropy-restart-data-file={bin_path}")
            return

        analyze_restart(bin_path, ea_bin_dir=request.config.getoption("--ea-bin-dir"))
