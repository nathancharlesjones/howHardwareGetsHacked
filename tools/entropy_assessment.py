"""
Wrapper around the NIST SP 800-90B EntropyAssessment C++ tools (ea_iid,
ea_non_iid, ea_restart), plus a few pure-Python pairwise statistics for
comparing multiple entropy sources against each other.

Get and build the tools from:
    https://github.com/usnistgov/SP800-90B_EntropyAssessment

    sudo apt-get install libbz2-dev libdivsufsort-dev libjsoncpp-dev \
                         libssl-dev libmpfr-dev libgmp-dev
    git clone https://github.com/usnistgov/SP800-90B_EntropyAssessment.git \
        libraries/SP800-90B_EntropyAssessment
    cd libraries/SP800-90B_EntropyAssessment/cpp
    make iid non_iid restart

This produces ea_iid, ea_non_iid, ea_restart directly in that cpp/ directory
(not a bin/ subfolder - bin/ in the repo only holds sample test vectors).
Point EA_BIN_DIR (or --ea-bin-dir) at that cpp/ directory if it isn't at the
default location resolved below.

NOTE on -v: ea_iid and ea_non_iid only *compute* (not just print) the final
"Assessed min entropy" value once verbose > 2 (i.e. two or more -v flags).
Below verbose>2, the tool still exits 0 and still writes a plausible-looking
number, but for ea_iid specifically that number is left at its uninitialized
default (bits_per_symbol) rather than the real computed estimate. So -v -v is
mandatory here, not just extra logging - dropping it silently produces wrong
(too high) IID entropy numbers.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


class EntropyAssessmentError(RuntimeError):
    """Raised when an ea_* tool can't be found, or exits abnormally for a
    reason other than an expected validation/sanity-check failure."""


_DEFAULT_BIN_DIR = Path(__file__).parent.parent / "libraries" / "SP800-90B_EntropyAssessment" / "cpp"

_MIN_ENTROPY_RE = re.compile(r"Assessed min entropy:\s*([0-9.eE+-]+)")
_IID_PERM_RE = re.compile(r"IID permutation tests:\s*(Passed|Failed)")
_RESTART_RESULT_RE = re.compile(r"min\(H_r, H_c, H_I\):\s*([0-9.eE+-]+)")
_RESTART_HR_RE = re.compile(r"^H_r:\s*([0-9.eE+-]+)", re.M)
_RESTART_HC_RE = re.compile(r"^H_c:\s*([0-9.eE+-]+)", re.M)


def _find_binary(name: str, bin_dir: Optional[str] = None) -> Path:
    search_dirs = []
    if bin_dir:
        search_dirs.append(Path(bin_dir))
    env_dir = os.environ.get("EA_BIN_DIR")
    if env_dir:
        search_dirs.append(Path(env_dir))
    search_dirs.append(_DEFAULT_BIN_DIR)

    for d in search_dirs:
        candidate = d / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    raise EntropyAssessmentError(
        f"Could not find '{name}' in any of: {[str(d) for d in search_dirs]}\n"
        f"Build https://github.com/usnistgov/SP800-90B_EntropyAssessment (cpp/, 'make iid non_iid restart') "
        f"and pass --ea-bin-dir=<path to cpp/> or set EA_BIN_DIR."
    )


def _run(binary: Path, args: list) -> tuple:
    """Run binary, returning (stdout, returncode). Never raises on nonzero
    exit - callers decide which nonzero exits are expected failures vs. real
    tool errors."""
    result = subprocess.run([str(binary), *args], capture_output=True, text=True)
    return result.stdout + result.stderr, result.returncode


@dataclass
class AssessmentResult:
    source_name: str
    track: str                    # "iid" or "non_iid"
    passed_iid_permutation: Optional[bool]  # None when the non-IID track was used directly
    h_assessed: float             # bits of min-entropy per symbol
    bits_per_symbol: int
    n_samples: int
    stdout: str


@dataclass
class RestartAssessmentResult:
    source_name: str
    validation_passed: bool
    h_r: Optional[float]
    h_c: Optional[float]
    h_i: float
    h_assessed: Optional[float]   # min(H_r, H_c, H_I); None if validation failed
    failure_reason: Optional[str]
    stdout: str


def assess_iid_or_non_iid(samples: bytes, bits_per_symbol: int, source_name: str = "",
                           bin_dir: Optional[str] = None) -> AssessmentResult:
    """
    Run the standard SP800-90B initial entropy estimate workflow:

      1. Run ea_iid. If its IID permutation tests pass, that's the estimate.
      2. Otherwise, fall back to ea_non_iid (the conservative estimators that
         don't assume independence) on the same data.

    `samples` should be >= 1,000,000 bytes to meet SP800-90B's minimum sample
    count; shorter inputs still run (useful in development) but the result
    isn't a certifiable claim.
    """
    if len(samples) < 1_000_000:
        print(f"WARNING [{source_name}]: {len(samples)} samples < 1,000,000 minimum required "
              f"by SP800-90B. Treat this result as a development sanity check only.")

    with tempfile.TemporaryDirectory() as td:
        data_path = Path(td) / "samples.bin"
        data_path.write_bytes(samples)

        ea_iid = _find_binary("ea_iid", bin_dir)
        stdout, rc = _run(ea_iid, ["-i", "-v", "-v", str(data_path), str(bits_per_symbol)])
        if rc != 0:
            raise EntropyAssessmentError(f"ea_iid exited {rc} for source '{source_name}':\n{stdout}")

        perm_match = _IID_PERM_RE.search(stdout)
        if not perm_match:
            raise EntropyAssessmentError(f"Could not find IID permutation test result in ea_iid output:\n{stdout}")
        passed_iid = perm_match.group(1) == "Passed"

        h_match = _MIN_ENTROPY_RE.search(stdout)
        if not h_match:
            raise EntropyAssessmentError(f"Could not parse ea_iid output:\n{stdout}")
        h_iid = float(h_match.group(1))

        if passed_iid:
            return AssessmentResult(source_name, "iid", True, h_iid, bits_per_symbol, len(samples), stdout)

        ea_non_iid = _find_binary("ea_non_iid", bin_dir)
        stdout_ni, rc_ni = _run(ea_non_iid, ["-i", "-v", "-v", str(data_path), str(bits_per_symbol)])
        if rc_ni != 0:
            raise EntropyAssessmentError(f"ea_non_iid exited {rc_ni} for source '{source_name}':\n{stdout_ni}")

        h_match_ni = _MIN_ENTROPY_RE.search(stdout_ni)
        if not h_match_ni:
            raise EntropyAssessmentError(f"Could not parse ea_non_iid output:\n{stdout_ni}")
        h_non_iid = float(h_match_ni.group(1))
        return AssessmentResult(source_name, "non_iid", False, h_non_iid, bits_per_symbol, len(samples),
                                 stdout + "\n" + stdout_ni)


def assess_restart(samples: bytes, bits_per_symbol: int, h_i: float, iid: bool, source_name: str = "",
                    bin_dir: Optional[str] = None) -> RestartAssessmentResult:
    """
    Run the SP800-90B restart test (Section 3.1.4) on a "row dataset":
    `samples` must be exactly restarts * samples_per_restart bytes, laid out
    row-major (all samples from restart 0, then all samples from restart 1,
    ...). The tool's built-in default is 1000 restarts x 1000 samples.

    `h_i` is the initial entropy estimate for this same source from an
    independent (non-restart) collection, e.g. via assess_iid_or_non_iid().
    `iid` should be the `track == "iid"` value from that same result.
    """
    if len(samples) < 1_000_000:
        print(f"WARNING [{source_name}]: {len(samples)} samples < the 1000x1000 minimum required "
              f"by SP800-90B restart testing. Treat this result as a development sanity check only.")

    with tempfile.TemporaryDirectory() as td:
        data_path = Path(td) / "restart_samples.bin"
        data_path.write_bytes(samples)

        ea_restart = _find_binary("ea_restart", bin_dir)
        flag = "-i" if iid else "-n"
        stdout, rc = _run(ea_restart, [flag, str(data_path), str(bits_per_symbol), str(h_i)])

        if "Restart Sanity Check Failed" in stdout:
            return RestartAssessmentResult(source_name, False, None, None, h_i, None,
                                            "Restart sanity check failed (Section 3.1.4.3): "
                                            "row/column counts exceed the expected collision bound.",
                                            stdout)
        if "Validation Testing Failed" in stdout:
            hr_match = _RESTART_HR_RE.search(stdout)
            hc_match = _RESTART_HC_RE.search(stdout)
            return RestartAssessmentResult(
                source_name, False,
                float(hr_match.group(1)) if hr_match else None,
                float(hc_match.group(1)) if hc_match else None,
                h_i, None,
                "min(H_r, H_c) < H_I/2 (Section 3.1.4.2): entropy across restarts is "
                "inconsistent with the non-restart estimate.",
                stdout)

        if rc != 0:
            raise EntropyAssessmentError(f"ea_restart exited {rc} for source '{source_name}':\n{stdout}")

        result_match = _RESTART_RESULT_RE.search(stdout)
        hr_match = _RESTART_HR_RE.search(stdout)
        hc_match = _RESTART_HC_RE.search(stdout)
        if not result_match:
            raise EntropyAssessmentError(f"Could not parse ea_restart output:\n{stdout}")

        return RestartAssessmentResult(
            source_name, True,
            float(hr_match.group(1)) if hr_match else None,
            float(hc_match.group(1)) if hc_match else None,
            h_i, float(result_match.group(1)), None, stdout)


# =============================================================================
# Pairwise source comparison (not part of the NIST tool - a lightweight check
# that no two "independent" entropy sources are secretly correlated, which
# would mean their combined entropy is less than the sum of their individual
# estimates).
# =============================================================================

def pearson_correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson correlation coefficient of two equal-length numeric sequences."""
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    denom = (var_a * var_b) ** 0.5
    return cov / denom if denom else 0.0


def mutual_information_bits(a: Sequence[int], b: Sequence[int], bins: int = 16) -> float:
    """
    Rough mutual information estimate (bits) between two equal-length integer
    sequences, via histogram binning. Not a substitute for a real statistical
    test - intended only to flag "these two sources look related, go look
    closer" during development.
    """
    import math
    from collections import Counter

    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    lo_a, hi_a = min(a[:n]), max(a[:n])
    lo_b, hi_b = min(b[:n]), max(b[:n])
    span_a = max(hi_a - lo_a, 1)
    span_b = max(hi_b - lo_b, 1)

    def bin_of(x, lo, span):
        return min(bins - 1, int((x - lo) * bins / (span + 1)))

    joint = Counter()
    marg_a = Counter()
    marg_b = Counter()
    for x, y in zip(a[:n], b[:n]):
        bx, by = bin_of(x, lo_a, span_a), bin_of(y, lo_b, span_b)
        joint[(bx, by)] += 1
        marg_a[bx] += 1
        marg_b[by] += 1

    mi = 0.0
    for (bx, by), count in joint.items():
        p_xy = count / n
        p_x = marg_a[bx] / n
        p_y = marg_b[by] / n
        mi += p_xy * math.log2(p_xy / (p_x * p_y))
    return mi


def bytes_to_ints(data: bytes, width: int, signed: bool = False) -> list:
    """Unpack a raw sample byte-stream into a list of little-endian ints of `width` bytes each."""
    return [int.from_bytes(data[i:i + width], "little", signed=signed)
            for i in range(0, len(data) - width + 1, width)]
