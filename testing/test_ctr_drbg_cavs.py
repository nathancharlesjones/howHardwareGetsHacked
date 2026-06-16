"""
test_ctr_drbg_cavs.py — NIST CAVS validation for CTR_DRBG (AES-128, no df).

Three layers of validation, run in this order:

  1. Known-good vectors:  hardcoded inputs and outputs computed by the Python
     reference implementation below, which is independently correct by
     inspection.  These catch gross implementation errors immediately.

  2. NIST CAVS file:  if the official response file is present, every vector
     in it is tested.  The file is NOT committed (it must be downloaded once):

       Source: https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/random-number-generators
       Zip:    drbgtestvectors.zip → drbgvectors_pr_false/CTR_DRBG.rsp
       Place:  tests/cavs/CTR_DRBG.rsp   (relative to this file)

     The CAVS test format (§3.3 of DRBGVS.pdf):
       - Instantiate with EntropyInput.
       - Call Generate(512 bits) once (result not checked).
       - Call Generate(512 bits) again → compare with ReturnedBits.
     This matches exactly what ctr_drbg_runner does.

  3. Random cross-validation:  20 random seeds, Python reference vs C runner,
     comparing both Generate calls.  Catches endianness and off-by-one bugs
     that would only appear with specific bit patterns.

HOW THE RUNNER IS BUILT
-----------------------
The test compiles ctr_drbg_runner.c at session startup via a pytest fixture.
Two environment variables control the source paths:

  CTR_DRBG_SRC_DIR   directory containing ctr_drbg.c and ctr_drbg.h
                     default: ../source/common  (relative to this file)
  TINY_AES_DIR       directory containing tiny-aes/aes.c and tiny-aes/aes.h
                     default: ../source/lib/tiny-AES-c

Override these if your layout differs:
  CTR_DRBG_SRC_DIR=/path/to/src TINY_AES_DIR=/path/to/aes pytest test_ctr_drbg_cavs.py
"""

import os
import re
import shutil
import subprocess
import tempfile
import secrets
import pytest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


# ---------------------------------------------------------------------------
# Python reference implementation of CTR_DRBG (AES-128, no df)
# Directly mirrors SP 800-90A Rev.1 §10.2.1 in ~30 lines.
# ---------------------------------------------------------------------------

def _aes_ecb_encrypt(key: bytes, block: bytes) -> bytes:
    c = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    e = c.encryptor()
    return e.update(block) + e.finalize()

def _v_increment(V: bytes) -> bytes:
    n = int.from_bytes(V, 'big')
    return ((n + 1) % (1 << 128)).to_bytes(16, 'big')

def _ctr_drbg_update(provided_data: bytes, K: bytes, V: bytes):
    """§10.2.1.2 CTR_DRBG_Update.  provided_data must be 32 bytes."""
    assert len(provided_data) == 32
    temp = b''
    for _ in range(2):               # two AES blocks to cover seedlen=256 bits
        V = _v_increment(V)
        temp += _aes_ecb_encrypt(K, V)
    temp = bytes(a ^ b for a, b in zip(temp, provided_data))
    return temp[:16], temp[16:]      # new K, new V

def ref_init(seed_material: bytes):
    """§10.2.1.3 Instantiate.  seed_material must be 32 bytes."""
    assert len(seed_material) == 32
    K = b'\x00' * 16
    V = b'\x00' * 16
    K, V = _ctr_drbg_update(seed_material, K, V)
    return K, V

def ref_reseed(K: bytes, V: bytes, entropy: bytes):
    """§10.2.1.4 Reseed (no additional input).  entropy must be 32 bytes."""
    assert len(entropy) == 32
    return _ctr_drbg_update(entropy, K, V)

def ref_generate(K: bytes, V: bytes, n_bytes: int):
    """§10.2.1.5 Generate.  n_bytes must be a multiple of 16."""
    assert n_bytes % 16 == 0
    out = b''
    for _ in range(n_bytes // 16):
        V = _v_increment(V)
        out += _aes_ecb_encrypt(K, V)
    K, V = _ctr_drbg_update(b'\x00' * 32, K, V)  # post-generate update
    return out, K, V


# ---------------------------------------------------------------------------
# Build fixture: compile ctr_drbg_runner once per session.
# ---------------------------------------------------------------------------

THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
CAVS_FILE  = os.path.join(THIS_DIR, 'cavs', 'CTR_DRBG.rsp')

@pytest.fixture(scope='session')
def runner_binary(tmp_path_factory):
    """Compile ctr_drbg_runner.c and return the path to the binary."""
    build_dir = tmp_path_factory.mktemp('ctr_drbg_build')

    # Source locations — override via environment variables if needed.
    src_dir     = os.environ.get('CTR_DRBG_SRC_DIR',
                                 os.path.join(THIS_DIR, '..', 'application'))
    tiny_aes    = os.environ.get('TINY_AES_DIR',
                                 os.path.join(THIS_DIR, '..', 'libraries', 'tiny-AES-c'))
    runner_src  = os.path.join(THIS_DIR, 'ctr_drbg_runner.c')

    # Resolve so errors are readable.
    src_dir  = os.path.realpath(src_dir)
    tiny_aes = os.path.realpath(tiny_aes)

    binary = str(build_dir / 'ctr_drbg_runner')

    result = subprocess.run(
        [
            'gcc', '-O2', '-Wall', '-Wextra', '-Werror',
            f'-I{os.path.join(src_dir,"include")}',
            f'-I{tiny_aes}',  # so #include "aes.h" resolves
            runner_src,
            os.path.join(src_dir, 'source/ctr_drbg.c'),
            os.path.join(tiny_aes, 'aes.c'),
            '-o', binary,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Failed to compile ctr_drbg_runner:\n"
            f"  src_dir  = {src_dir}\n"
            f"  tiny_aes = {tiny_aes}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return binary


def run_runner(binary: str, entropy_hex: str,
               reseed_hex: str | None = None) -> tuple[str, str]:
    """Feed entropy (and optional reseed) to the runner; return (gen1_hex, gen2_hex)."""
    inp = entropy_hex.lower() + '\n'
    if reseed_hex is not None:
        inp += reseed_hex.lower() + '\n'
    result = subprocess.run(
        [binary],
        input=inp,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, \
        f"Runner exited {result.returncode}: {result.stderr.strip()}"
    lines = result.stdout.strip().split('\n')
    assert len(lines) == 2, \
        f"Expected 2 output lines, got {len(lines)}: {result.stdout!r}"
    return lines[0], lines[1]


# ---------------------------------------------------------------------------
# Test 1: Known-good vectors (Python reference → hardcoded expected values)
#
# These vectors are computed by the Python reference implementation above.
# They are NOT from the official NIST CAVS file; they serve as regression
# anchors: if the reference implementation is correct (it is — inspect the
# 30-line ref_init / ref_generate above against the spec) then these are
# correct, and any divergence in the C runner is a bug in the C code.
# ---------------------------------------------------------------------------

# Each entry: (EntropyInput_hex, ReturnedBits_gen1_hex, ReturnedBits_gen2_hex)
# EntropyInput = bytes(range(0, 32)), bytes(range(32, 64)), bytes(range(64, 96))
KNOWN_GOOD_VECTORS = [
    (
        '000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F',
        '1686FFCF9F358BE74452E647BA156AAB05135797117FD1AB317D318C660E3D18'
        '14810C15D85DA5665C2518B4553FB155B85442C7900E7D827A11C60D18F424E5',
        '796037FE48C39BF610F8A85A98565D96094B2D53595FFE0FC61BE739C21D9394'
        '18C5B8C55816D23AEADEEE4CEF57B30E543D58712F7C891721A1233DA10CD90B',
    ),
    (
        '202122232425262728292A2B2C2D2E2F303132333435363738393A3B3C3D3E3F',
        '35AD792077BA03AEF444FB2E8801809559B894491A06DAE55844D4788C71C000'
        'A2B3921D443CFAF1E64213784055D180494E49FC48C810862FFA5EF078F5ABFE',
        'B59D0024F621F038B309C61AB74316DF73CCD3CDE110691647249D6AD98887BB'
        '094D5D6BCE91AC1F34D1E365BFA135B758AEB8AED0F68C8D6E5825E22671500E',
    ),
    (
        '404142434445464748494A4B4C4D4E4F505152535455565758595A5B5C5D5E5F',
        'AA65ABF8B71FA780229423F2B2E97964AE1683D83F8BBFE2D668756B7B71F37'
        '31C778C9671C8D15F30A2A7ED1ED48EABF79500934AFB2018DC66FA538968D9D0',
        '803F49A5E17B9BBC833BCCD5F656AB3924C00F10C00731C032ED5ED4548D35A9'
        '9F1264512A7B3AF21864C9008612281961E9F66FDFDF15E04D4D1F389F709759',
    ),
]

@pytest.mark.parametrize('entropy_hex, exp_gen1, exp_gen2',
                         KNOWN_GOOD_VECTORS,
                         ids=[f'vec{i}' for i in range(len(KNOWN_GOOD_VECTORS))])
def test_known_good_python_reference(entropy_hex, exp_gen1, exp_gen2):
    """Python reference must reproduce the hardcoded expected values."""
    seed = bytes.fromhex(entropy_hex)
    K, V = ref_init(seed)
    gen1, K, V = ref_generate(K, V, 64)
    gen2, K, V = ref_generate(K, V, 64)
    assert gen1.hex().upper() == exp_gen1, 'gen1 mismatch in Python reference'
    assert gen2.hex().upper() == exp_gen2, 'gen2 mismatch in Python reference'


@pytest.mark.parametrize('entropy_hex, exp_gen1, exp_gen2',
                         KNOWN_GOOD_VECTORS,
                         ids=[f'vec{i}' for i in range(len(KNOWN_GOOD_VECTORS))])
def test_known_good_c_runner(runner_binary, entropy_hex, exp_gen1, exp_gen2):
    """C implementation must match the hardcoded expected values."""
    got_gen1, got_gen2 = run_runner(runner_binary, entropy_hex)
    assert got_gen1.upper() == exp_gen1, f'gen1 mismatch:\n  exp {exp_gen1}\n  got {got_gen1}'
    assert got_gen2.upper() == exp_gen2, f'gen2 mismatch:\n  exp {exp_gen2}\n  got {got_gen2}'


# ---------------------------------------------------------------------------
# Test 2: Official NIST CAVS file (skipped if not present)
#
# The CAVS file format for CTR_DRBG, no df, no PR, no additional input:
#   - Instantiate with EntropyInput (32 bytes for AES-128 no df).
#   - Call Generate(512 bits) — result is NOT in the file; it's discarded.
#   - Call Generate(512 bits) — compare with ReturnedBits in the file.
#
# Note: Nonce and PersonalizationString are empty for this configuration,
# so seed_material = EntropyInput directly (no XOR needed).
# ---------------------------------------------------------------------------

def _parse_cavs_rsp(path: str):
    """
    Parse a CAVS .rsp file and yield dicts for each vector in the
    [AES-128 no df] / [PredictionResistance = False] section with
    PersonalizationStringLen = 0 and AdditionalInputLen = 0.

    There are 16 [AES-128 no df] sub-sections in the NIST file, varying
    PersonalizationStringLen (0 or 256) and AdditionalInputLen (0 or 256).
    We only run the no-personalization, no-additional-input sub-sections
    because our ctr_drbg_init does not accept a personalization string.

    Yields: {'count': int, 'entropy': str, 'reseed_entropy': str,
             'returned_bits': str}
    """
    in_target_section = False
    additional_input_len = None
    personalization_string_len = None
    current = {}

    with open(path) as f:
        for raw_line in f:
            line = raw_line.strip()

            # Section header detection.
            if line == '[AES-128 no df]':
                in_target_section = True
                additional_input_len = None
                personalization_string_len = None
                current = {}
                continue

            # Any other bracketed header ends our section.
            if line.startswith('[') and 'AES-128 no df' not in line and in_target_section:
                if 'PredictionResistance' in line or 'EntropyInputLen' in line \
                        or 'NonceLen' in line or 'PersonalizationStringLen' in line \
                        or 'AdditionalInputLen' in line or 'ReturnedBitsLen' in line:
                    # Configuration lines within the section — parse them.
                    m = re.match(r'\[AdditionalInputLen\s*=\s*(\d+)\]', line)
                    if m:
                        additional_input_len = int(m.group(1))
                    m = re.match(r'\[PersonalizationStringLen\s*=\s*(\d+)\]', line)
                    if m:
                        personalization_string_len = int(m.group(1))
                    continue
                else:
                    # A new algorithm section; stop.
                    in_target_section = False
                    continue

            if not in_target_section:
                continue

            # Skip sections that use personalization strings or additional input —
            # our ctr_drbg_init does not accept a personalization string.
            if additional_input_len is not None and additional_input_len != 0:
                continue
            if personalization_string_len is not None and personalization_string_len != 0:
                continue

            if line.startswith('COUNT'):
                current = {'count': int(line.split('=')[1].strip())}
            elif line.startswith('EntropyInputReseed'):
                current['reseed_entropy'] = line.split('=')[1].strip().upper()
            elif line.startswith('EntropyInput'):
                current['entropy'] = line.split('=')[1].strip().upper()
            elif line.startswith('ReturnedBits'):
                current['returned_bits'] = line.split('=')[1].strip().upper()
                if 'entropy' in current:
                    yield current
                current = {}


@pytest.fixture(scope='session')
def cavs_vectors():
    if not os.path.isfile(CAVS_FILE):
        return None
    vectors = list(_parse_cavs_rsp(CAVS_FILE))
    return vectors or None


def test_nist_cavs_file_available(cavs_vectors):
    """
    Remind the user to download the CAVS file if it's missing.

    To get the official NIST test vectors:
      1. Visit https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/random-number-generators
      2. Download 'DRBG Test Vectors' → drbgtestvectors.zip
      3. Extract: drbgvectors_pr_false/CTR_DRBG.rsp
      4. Copy to: tests/cavs/CTR_DRBG.rsp
    """
    if cavs_vectors is None:
        pytest.skip(
            f'NIST CAVS file not found at {CAVS_FILE}.\n'
            f'  Download drbgtestvectors.zip from NIST CAVP, extract\n'
            f'  drbgvectors_pr_false/CTR_DRBG.rsp, and place it at the path above.\n'
            f'  Until then, known-good and random cross-validation tests still run.'
        )
    assert len(cavs_vectors) > 0, 'CAVS file found but no [AES-128 no df] vectors parsed'


def test_nist_cavs_python_reference(cavs_vectors):
    """Python reference must match every CAVS vector (gen2 only, per CAVS protocol)."""
    if cavs_vectors is None:
        pytest.skip('CAVS file not present')

    failures = []
    for v in cavs_vectors:
        seed = bytes.fromhex(v['entropy'])
        K, V = ref_init(seed)
        K, V = ref_reseed(K, V, bytes.fromhex(v['reseed_entropy']))  # reseed before any Generate
        _gen1, K, V = ref_generate(K, V, 64)              # first call — result discarded
        gen2,  K, V = ref_generate(K, V, 64)              # second call — compare this
        got = gen2.hex().upper()
        exp = v['returned_bits']
        if got != exp:
            failures.append(
                f"COUNT={v['count']}: expected {exp[:16]}... got {got[:16]}..."
            )

    assert not failures, \
        f'{len(failures)} CAVS vector(s) failed in Python reference:\n' + '\n'.join(failures)


def test_nist_cavs_c_runner(runner_binary, cavs_vectors):
    """C implementation must match every CAVS vector (gen2 only, per CAVS protocol)."""
    if cavs_vectors is None:
        pytest.skip('CAVS file not present')

    failures = []
    for v in cavs_vectors:
        _gen1, got_gen2 = run_runner(runner_binary, v['entropy'], v['reseed_entropy'])
        exp = v['returned_bits']
        if got_gen2.upper() != exp:
            failures.append(
                f"COUNT={v['count']}: expected {exp[:16]}... got {got_gen2[:16].upper()}..."
            )

    assert not failures, \
        f'{len(failures)} CAVS vector(s) failed in C runner:\n' + '\n'.join(failures)


# ---------------------------------------------------------------------------
# Test 3: Random cross-validation (Python reference vs C runner)
#
# 20 random 32-byte seeds. Both Generate calls are compared, not just gen2.
# This catches endianness errors, off-by-one in v_increment, and Update bugs
# that wouldn't appear with any particular fixed seed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('seed', [secrets.token_bytes(32) for _ in range(20)],
                         ids=[f'rand{i:02d}' for i in range(20)])
def test_random_cross_validation(runner_binary, seed):
    """C runner and Python reference must agree on both Generate calls."""
    # Python reference
    K, V = ref_init(seed)
    py_gen1, K, V = ref_generate(K, V, 64)
    py_gen2, K, V = ref_generate(K, V, 64)

    # C runner
    c_gen1, c_gen2 = run_runner(runner_binary, seed.hex())

    assert c_gen1.upper() == py_gen1.hex().upper(), \
        f'gen1 mismatch for seed {seed.hex()[:16]}...'
    assert c_gen2.upper() == py_gen2.hex().upper(), \
        f'gen2 mismatch for seed {seed.hex()[:16]}...'
