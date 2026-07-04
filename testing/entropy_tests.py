"""
NIST SP 800-90B entropy assessment of the car's hardware entropy sources
(getEntropySourceCount / getEntropySourceName / getEntropySourceSamples).

Requires the ea_iid/ea_non_iid/ea_restart tools from
https://github.com/usnistgov/SP800-90B_EntropyAssessment to be built; see the
module docstring in tools/entropy_assessment.py for build instructions and
CLI details. Tests here raise a clear error if the binaries can't be found
rather than skipping quietly, since a missing tool is a setup problem, not
an expected condition.

Every run writes a timestamped .log file under testing/entropy_logs/ with
the full ea_* stdout for later review, in addition to the terminal summary
(run pytest with -s to see it live).
"""

from datetime import datetime
from pathlib import Path

import pytest

from conftest import RoleConfig
import protocol as proto
from entropy_assessment import (
    assess_iid_or_non_iid,
    assess_restart,
    pearson_correlation,
    mutual_information_bits,
    bytes_to_ints,
    EntropyAssessmentError,
)

LOG_DIR = Path(__file__).parent / "entropy_logs"

# Each raw reading is packed into an 8-bit symbol using the reading's low
# byte. The ADC channels are 12-bit and the jitter/timer channel is wider
# still; SP800-90B's tools only accept <=8-bit symbols, so multi-byte
# readings are truncated to their low byte rather than split across several
# symbols. This is a conservative choice: it can only under-count entropy
# that happens to live in the upper bits, never over-count it.
BITS_PER_SYMBOL = 8


def _low_byte_symbols(raw: bytes, width: int) -> bytes:
    """Extract the low byte of each `width`-byte little-endian reading."""
    return raw if width == 1 else bytes(raw[i] for i in range(0, len(raw), width))


def _write_log(name: str, board: str, lines: list) -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{timestamp}_{board}_{name}.log"
    log_path.write_text("\n".join(lines))
    return log_path


class TestEntropySourceQuality:
    """SP800-90B IID/non-IID assessment of each entropy source, plus a
    pairwise independence check across sources."""

    def test_entropy_sources_iid_or_non_iid(self, deploy, request, hardware_config):
        n_samples = request.config.getoption("--entropy-n-samples")
        ea_bin_dir = request.config.getoption("--ea-bin-dir")
        board = hardware_config.board if hardware_config else "sim"

        car = deploy(RoleConfig("car", id="1337"))

        source_count = proto.get_entropy_source_count(car)
        assert source_count > 0, "Device reports zero entropy sources"

        log_lines = [f"Entropy source IID/non-IID assessment - board={board}, n_samples={n_samples}"]
        results = {}
        raw_by_source = {}

        for source_num in range(source_count):
            name = proto.get_entropy_source_name(car, source_num)
            width = proto.entropy_source_sample_width(car, source_num)
            print(f"\nCollecting {n_samples} samples from source {source_num} "
                  f"({name}, {width} bytes/sample)...")
            raw = proto.collect_entropy_source_samples(
                car, source_num, n_samples, show_progress=True)
            raw_by_source[name] = (raw, width)

            symbols = _low_byte_symbols(raw, width)
            result = assess_iid_or_non_iid(symbols, BITS_PER_SYMBOL, source_name=name, bin_dir=ea_bin_dir)
            results[name] = result

            perm = "n/a" if result.passed_iid_permutation is None else result.passed_iid_permutation
            summary = (f"[{name}] track={result.track} iid_permutation={perm} "
                       f"assessed_min_entropy={result.h_assessed:.3f} bits/byte "
                       f"({result.h_assessed / BITS_PER_SYMBOL * 100:.1f}% of {BITS_PER_SYMBOL}-bit ceiling)")
            print(summary)
            log_lines.append(summary)
            log_lines.append(result.stdout)

        # Pairwise independence check: two supposedly-independent entropy
        # sources that are actually correlated (e.g. sharing a physical
        # driver like board temperature) provide less combined entropy than
        # naively summing their individual estimates.
        names = list(raw_by_source.keys())
        if len(names) > 1:
            log_lines.append("\nPairwise source comparison:")
            print("\nPairwise source comparison:")
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    name_a, name_b = names[i], names[j]
                    raw_a, width_a = raw_by_source[name_a]
                    raw_b, width_b = raw_by_source[name_b]
                    ints_a = bytes_to_ints(raw_a, width_a)
                    ints_b = bytes_to_ints(raw_b, width_b)
                    corr = pearson_correlation(ints_a, ints_b)
                    mi = mutual_information_bits(ints_a, ints_b)
                    line = f"  {name_a} <-> {name_b}: pearson_r={corr:+.4f}, mutual_info~={mi:.4f} bits"
                    print(line)
                    log_lines.append(line)
                    if abs(corr) > 0.3:
                        warning = "    WARNING: |r| > 0.3 - investigate before treating these as independent sources"
                        print(warning)
                        log_lines.append(warning)

        log_path = _write_log("iid_non_iid", board, log_lines)
        print(f"\nFull log: {log_path}")

        for name, result in results.items():
            assert result.h_assessed > 0, f"Source '{name}' assessed at 0 bits of entropy per byte"


@pytest.mark.hardware_only
class TestEntropySourceRestart:
    """SP800-90B restart test (Section 3.1.4): confirms entropy doesn't
    collapse across power-on resets (e.g. an ADC or timer that always starts
    from the same state after boot).

    Hardware-only: restart() triggers a real warm reset on STM32/TM4C
    (NVIC_SystemReset() / SysCtlReset()), which this test needs to collect
    genuinely independent post-boot samples. In simulation restart() remains
    an empty stub -- there's no real boot sequence to re-run and process
    restart isn't viable here (see hardware/sim/source/sim.c) -- so
    simulation mode is skipped outright rather than produce a misleadingly-
    passing result.
    """

    def test_entropy_sources_restart(self, deploy, request, hardware_config):
        restarts = request.config.getoption("--entropy-restarts")
        samples_per_restart = request.config.getoption("--entropy-samples-per-restart")
        ea_bin_dir = request.config.getoption("--ea-bin-dir")
        board = hardware_config.board

        car = deploy(RoleConfig("car", id="1337"))

        source_count = proto.get_entropy_source_count(car)
        log_lines = [f"Entropy source restart assessment - board={board}, "
                     f"restarts={restarts}, samples_per_restart={samples_per_restart}"]

        for source_num in range(source_count):
            name = proto.get_entropy_source_name(car, source_num)
            width = proto.entropy_source_sample_width(car, source_num)
            print(f"\nCollecting {restarts}x{samples_per_restart} restart samples from source "
                  f"{source_num} ({name}, {width} bytes/sample)...")

            rows = bytearray()
            for r in range(restarts):
                rows += proto.collect_entropy_source_samples(car, source_num, samples_per_restart)
                proto.cmd_restart(car)
                frac = (r + 1) / restarts
                bar = "#" * int(frac * 30) + "-" * (30 - int(frac * 30))
                print(f"\r  [{bar}] {r + 1}/{restarts} restarts", end="", flush=True)
            print()

            raw = bytes(rows)
            symbols = _low_byte_symbols(raw, width)

            # H_I is derived from this same collection's flattened stream
            # (rather than depending on a separate test run's result) so this
            # test stays self-contained.
            initial = assess_iid_or_non_iid(symbols, BITS_PER_SYMBOL, source_name=name, bin_dir=ea_bin_dir)

            try:
                restart_result = assess_restart(
                    symbols, BITS_PER_SYMBOL, initial.h_assessed,
                    iid=(initial.track == "iid"), source_name=name, bin_dir=ea_bin_dir)
            except EntropyAssessmentError as e:
                pytest.fail(f"Source '{name}': {e}")

            if restart_result.validation_passed:
                summary = (f"[{name}] PASSED: H_r={restart_result.h_r:.3f} H_c={restart_result.h_c:.3f} "
                           f"H_I={restart_result.h_i:.3f} -> assessed={restart_result.h_assessed:.3f} bits/byte")
            else:
                summary = f"[{name}] FAILED: {restart_result.failure_reason}"
            print(summary)
            log_lines.append(summary)
            log_lines.append(restart_result.stdout)

            assert restart_result.validation_passed, (
                f"Source '{name}' failed the SP800-90B restart validation test: {restart_result.failure_reason}"
            )

        log_path = _write_log("restart", board, log_lines)
        print(f"\nFull log: {log_path}")
