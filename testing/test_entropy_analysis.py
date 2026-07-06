"""
NIST SP 800-90B entropy assessment of previously captured samples.

Pure analysis, no hardware involved: every test here reads a .bin/.json
capture written by test_entropy.py's TestEntropyCapture and runs the NIST
statistics against it (no device fixtures, no --using flag needed -- similar
in spirit to test_ctr_drbg_cavs.py, and named test_*.py so a plain
`pytest testing/` sweep picks it up).

Each check is exposed two ways:
  - analyze_iid_or_non_iid() / analyze_restart(): plain functions taking a
    bin_path directly. test_entropy.py's capture tests import and call
    these right after writing a capture, so by default capturing and
    analyzing happen as a single pytest invocation (pass --entropy-skip-
    analysis there to capture without immediately analyzing).
  - test_entropy_sources_iid_or_non_iid() / test_entropy_sources_restart():
    pytest tests that resolve which capture to analyze from the command
    line, then call the same functions above. Resolution order:
      1. --entropy-data-file / --entropy-restart-data-file: analyze exactly
         this capture.
      2. --platform=<sim|tm4c|stm32>: analyze the most recently
         written capture for that platform (raises if none exists).
      3. neither given: skipped.

Common invocations:

    # Analyze the latest tm4c IID/non-IID + pairwise capture
    pytest test_entropy_analysis.py -k iid_or_non_iid --platform=tm4c

    # Analyze one specific capture
    pytest test_entropy_analysis.py -k iid_or_non_iid \\
        --entropy-data-file=testing/entropy_logs/<...>_iid_non_iid.bin

    # Analyze the latest restart capture for a platform
    pytest test_entropy_analysis.py -k entropy_sources_restart --platform=stm32

Requires the ea_iid/ea_non_iid/ea_restart tools from
https://github.com/usnistgov/SP800-90B_EntropyAssessment to be built; see the
module docstring in tools/entropy_assessment.py for build instructions and
CLI details. Analyses raise a clear error if the binaries can't be found
rather than skipping quietly, since a missing tool is a setup problem, not
an expected condition.

Every analysis run writes a timestamped .log file under testing/entropy_logs/
with the full ea_* stdout for later review, in addition to the terminal
summary (run pytest with -s to see it live).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from entropy_assessment import (
    assess_iid_or_non_iid,
    assess_restart,
    deinterleave,
    load_capture,
    pearson_correlation,
    mutual_information_bits,
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


def latest_capture(board: str, name: str) -> Path:
    """Most recently written `*_{board}_{name}.bin` capture under LOG_DIR."""
    matches = sorted(LOG_DIR.glob(f"*_{board}_{name}.bin"))
    if not matches:
        raise FileNotFoundError(
            f"No '{name}' capture found for board '{board}' under {LOG_DIR}"
        )
    return matches[-1]


def _resolve_capture_path(request, file_option: str, name: str, capture_test: str) -> Path:
    explicit = request.config.getoption(file_option)
    if explicit:
        return Path(explicit)
    platform = request.config.getoption("--platform")
    if platform:
        return latest_capture(platform, name)
    pytest.skip(f"Pass {file_option}=<path> or --platform=<sim|tm4c|stm32> to analyze a "
                f"capture (see TestEntropyCapture.{capture_test})")


def analyze_iid_or_non_iid(bin_path: Path, ea_bin_dir: Optional[str] = None) -> dict:
    """
    SP800-90B IID/non-IID assessment of each entropy source in a capture,
    plus a pairwise independence check across sources.

    Returns {source_name: EaResult}. Raises AssertionError if any source
    assesses at 0 bits of entropy per byte.
    """
    raw, meta = load_capture(bin_path)
    widths = meta["widths"]
    board = meta.get("board", "unknown")
    n_samples = meta.get("n_samples", "?")
    assert widths, f"{bin_path}: capture metadata has zero entropy sources"

    log_lines = [f"Entropy source IID/non-IID assessment - board={board}, n_samples={n_samples}, "
                 f"data_file={bin_path}"]

    raw_by_source = deinterleave(raw, widths)
    symbols_by_source = {
        name: _low_byte_symbols(raw_by_source[name], width) for name, width in widths.items()
    }

    # Each source's ea_iid/ea_non_iid run is independent of every other
    # source's, so run them concurrently (like `make -j`) instead of paying
    # for N sequential subprocess calls. Threads are sufficient here even
    # though the work is CPU-bound: the GIL is released for the duration of
    # each subprocess.run() call in entropy_assessment.py.
    with ThreadPoolExecutor(max_workers=len(symbols_by_source)) as pool:
        futures = {
            name: pool.submit(assess_iid_or_non_iid, symbols, BITS_PER_SYMBOL,
                               source_name=name, bin_dir=ea_bin_dir)
            for name, symbols in symbols_by_source.items()
        }
        results = {name: future.result() for name, future in futures.items()}

    for name in widths:
        result = results[name]
        perm = "n/a" if result.passed_iid_permutation is None else result.passed_iid_permutation
        summary = (f"[{name}] track={result.track} iid_permutation={perm} "
                   f"assessed_min_entropy={result.h_assessed:.3f} bits/byte "
                   f"({result.h_assessed / BITS_PER_SYMBOL * 100:.1f}% of {BITS_PER_SYMBOL}-bit ceiling)")
        print(summary)
        log_lines.append(summary)
        log_lines.append(result.stdout)

    # Pairwise independence check: two supposedly-independent entropy
    # sources that are actually correlated (e.g. sharing a physical driver
    # like board temperature) provide less combined entropy than naively
    # summing their individual estimates.
    #
    # Computed on the same low-byte-truncated symbols fed to
    # assess_iid_or_non_iid above (not the raw multi-byte samples) so this
    # correlation/MI is measuring the same random variable the h_assessed
    # values above describe -- correlation on the full raw samples could
    # differ substantially from correlation on just their low byte, and
    # mixing the two would make any H_a + H_b - I(a;b) combination invalid.
    names = list(widths.keys())
    if len(names) > 1:
        log_lines.append("\nPairwise source comparison:")
        print("\nPairwise source comparison:")
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                name_a, name_b = names[i], names[j]
                ints_a = list(symbols_by_source[name_a])
                ints_b = list(symbols_by_source[name_b])
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

    return results


def analyze_restart(bin_path: Path, ea_bin_dir: Optional[str] = None) -> dict:
    """
    SP800-90B restart test (Section 3.1.4) for each entropy source in a
    capture: confirms entropy doesn't collapse across power-on resets (e.g.
    an ADC or timer that always starts from the same state after boot).

    Returns {source_name: RestartResult}. Raises AssertionError if any
    source fails validation.
    """
    raw, meta = load_capture(bin_path)
    widths = meta["widths"]
    board = meta.get("board", "unknown")
    restarts = meta.get("restarts", "?")
    samples_per_restart = meta.get("samples_per_restart", "?")
    assert widths, f"{bin_path}: capture metadata has zero entropy sources"

    log_lines = [f"Entropy source restart assessment - board={board}, "
                 f"restarts={restarts}, samples_per_restart={samples_per_restart}, data_file={bin_path}"]

    raw_by_source = deinterleave(raw, widths)

    def _assess_source(name: str, width: int):
        symbols = _low_byte_symbols(raw_by_source[name], width)

        # H_I is derived from this same collection's flattened stream
        # (rather than depending on a separate test run's result) so this
        # analysis stays self-contained.
        initial = assess_iid_or_non_iid(symbols, BITS_PER_SYMBOL, source_name=name, bin_dir=ea_bin_dir)
        return assess_restart(
            symbols, BITS_PER_SYMBOL, initial.h_assessed,
            iid=(initial.track == "iid"), source_name=name, bin_dir=ea_bin_dir)

    # Each source's initial+restart assessment is independent of every other
    # source's, so run them concurrently (like `make -j`) instead of paying
    # for N sequential subprocess calls per source.
    with ThreadPoolExecutor(max_workers=len(widths)) as pool:
        futures = {name: pool.submit(_assess_source, name, width) for name, width in widths.items()}
        results = {}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except EntropyAssessmentError as e:
                pytest.fail(f"Source '{name}': {e}")

    for name, restart_result in results.items():
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
    return results


class TestEntropySourceQuality:
    """SP800-90B IID/non-IID assessment of each entropy source, plus a
    pairwise independence check across sources -- analyzes a capture written
    by test_entropy.py's TestEntropyCapture.test_capture_entropy_samples.
    Pass --entropy-data-file=<path> for a specific capture, or
    --platform=<sim|tm4c|stm32> for the latest one."""

    def test_entropy_sources_iid_or_non_iid(self, request):
        ea_bin_dir = request.config.getoption("--ea-bin-dir")
        bin_path = _resolve_capture_path(
            request, "--entropy-data-file", "iid_non_iid", "test_capture_entropy_samples")
        analyze_iid_or_non_iid(bin_path, ea_bin_dir=ea_bin_dir)


class TestEntropySourceRestart:
    """SP800-90B restart test (Section 3.1.4): confirms entropy doesn't
    collapse across power-on resets -- analyzes a capture written by
    test_entropy.py's TestEntropyCapture.test_capture_entropy_restart_samples.
    Pass --entropy-restart-data-file=<path> for a specific capture, or
    --platform=<sim|tm4c|stm32> for the latest one."""

    def test_entropy_sources_restart(self, request):
        ea_bin_dir = request.config.getoption("--ea-bin-dir")
        bin_path = _resolve_capture_path(
            request, "--entropy-restart-data-file", "restart", "test_capture_entropy_restart_samples")
        analyze_restart(bin_path, ea_bin_dir=ea_bin_dir)
