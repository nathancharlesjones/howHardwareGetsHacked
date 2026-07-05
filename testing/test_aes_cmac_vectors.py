"""
test_aes_cmac_vectors.py — NIST/RFC validation for tiny-AES-CMAC-c (AES-128 CMAC).

Two layers of validation, run in this order:

  1. Known-good vectors: the four official AES-128 CMAC example vectors from
     NIST SP 800-38B, Appendix D.1 (identical to RFC 4493 §4).  These are the
     canonical NIST test vectors for AES-CMAC and cover Mlen = 0, 16, 40, and
     64 bytes (empty, one full block, a partial last block, and two full
     blocks) — i.e. every subkey/padding branch in AES_CMAC_digest.

  2. Random cross-validation: 30 random messages of random length (0-200
     bytes) with random keys, comparing the C library against Python's
     `cryptography` library CMAC implementation. Catches bugs that only
     appear at specific message lengths (e.g. off-by-one in the "is the last
     block complete" branch) that the four fixed vectors might not exercise.

HOW THE RUNNER IS BUILT
-----------------------
The test compiles aes_cmac_runner.c at session startup via a pytest fixture,
linking against tiny-AES-CMAC-c's aes_cmac.c and tiny-AES-c's aes.c (the CMAC
library takes a raw block-encrypt callback, so it needs a real AES
implementation to drive it).

Two environment variables control the source paths:

  AES_CMAC_DIR   directory containing aes_cmac.c and aes_cmac.h
                 default: ../libraries/tiny-AES-CMAC-c  (relative to this file)
  TINY_AES_DIR   directory containing aes.c and aes.h
                 default: ../libraries/tiny-AES-c

Override these if your layout differs:
  AES_CMAC_DIR=/path/to/cmac TINY_AES_DIR=/path/to/aes pytest test_aes_cmac_vectors.py
"""

import os
import random
import subprocess

import pytest

from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers import algorithms


# ---------------------------------------------------------------------------
# Build fixture: compile aes_cmac_runner once per session.
# ---------------------------------------------------------------------------

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope='session')
def runner_binary(tmp_path_factory):
    """Compile aes_cmac_runner.c and return the path to the binary."""
    build_dir = tmp_path_factory.mktemp('aes_cmac_build')

    # Source locations — override via environment variables if needed.
    cmac_dir = os.environ.get('AES_CMAC_DIR',
                               os.path.join(THIS_DIR, '..', 'libraries', 'tiny-AES-CMAC-c'))
    tiny_aes = os.environ.get('TINY_AES_DIR',
                               os.path.join(THIS_DIR, '..', 'libraries', 'tiny-AES-c'))
    runner_src = os.path.join(THIS_DIR, 'aes_cmac_runner.c')

    # Resolve so errors are readable.
    cmac_dir = os.path.realpath(cmac_dir)
    tiny_aes = os.path.realpath(tiny_aes)

    binary = str(build_dir / 'aes_cmac_runner')

    result = subprocess.run(
        [
            'gcc', '-O2', '-Wall', '-Wextra', '-Werror',
            f'-I{cmac_dir}',
            f'-I{tiny_aes}',
            runner_src,
            os.path.join(cmac_dir, 'aes_cmac.c'),
            os.path.join(tiny_aes, 'aes.c'),
            '-o', binary,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Failed to compile aes_cmac_runner:\n"
            f"  cmac_dir = {cmac_dir}\n"
            f"  tiny_aes = {tiny_aes}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return binary


def run_runner(binary: str, key_hex: str, msg_hex: str) -> str:
    """Feed a key and message to the runner; return the CMAC tag as hex."""
    inp = key_hex.lower() + '\n' + msg_hex.lower() + '\n'
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
    assert len(lines) == 1, \
        f"Expected 1 output line, got {len(lines)}: {result.stdout!r}"
    return lines[0]


# ---------------------------------------------------------------------------
# Test 1: Known-good vectors — NIST SP 800-38B Appendix D.1 / RFC 4493 §4.
#
# All four vectors share the same key:
#   K = 2b7e151628aed2a6abf7158809cf4f3c
# and message bytes are drawn as a prefix of the same 64-byte plaintext used
# throughout the SP 800-38A/-38B examples. Each (Mlen, tag) pair below was
# independently re-verified against Python's `cryptography` CMAC
# implementation before being hardcoded here.
# ---------------------------------------------------------------------------

CMAC_KEY = '2b7e151628aed2a6abf7158809cf4f3c'

_PLAINTEXT = (
    '6bc1bee22e409f96e93d7e117393172a'
    'ae2d8a571e03ac9c9eb76fac45af8e51'
    '30c81c46a35ce411e5fbc1191a0a52ef'
    'f69f2445df4f9b17ad2b417be66c3710'
)

# (Mlen in bytes, expected tag)
KNOWN_GOOD_VECTORS = [
    (0, 'bb1d6929e95937287fa37d129b756746'),  # Example 1
    (16, '070a16b46b4d4144f79bdd9dd04a287c'), # Example 2
    (40, 'dfa66747de9ae63030ca32611497c827'), # Example 3
    (64, '51f0bebf7e3b9d92fc49741779363cfe'), # Example 4
]


@pytest.mark.parametrize('mlen, expected_tag', KNOWN_GOOD_VECTORS,
                          ids=[f'Mlen={m}' for m, _ in KNOWN_GOOD_VECTORS])
def test_known_good_python_reference(mlen, expected_tag):
    """Python's `cryptography` CMAC must reproduce the hardcoded NIST tag."""
    msg = bytes.fromhex(_PLAINTEXT)[:mlen]
    c = CMAC(algorithms.AES(bytes.fromhex(CMAC_KEY)))
    c.update(msg)
    assert c.finalize().hex() == expected_tag, 'tag mismatch in Python reference'


@pytest.mark.parametrize('mlen, expected_tag', KNOWN_GOOD_VECTORS,
                          ids=[f'Mlen={m}' for m, _ in KNOWN_GOOD_VECTORS])
def test_known_good_c_runner(runner_binary, mlen, expected_tag):
    """tiny-AES-CMAC-c must reproduce the official NIST/RFC 4493 tag."""
    msg_hex = _PLAINTEXT[:2 * mlen]
    got_tag = run_runner(runner_binary, CMAC_KEY, msg_hex)
    assert got_tag.lower() == expected_tag, \
        f'tag mismatch:\n  exp {expected_tag}\n  got {got_tag.lower()}'


# ---------------------------------------------------------------------------
# Test 2: Random cross-validation (Python `cryptography` CMAC vs C runner)
#
# 30 random keys/messages of random length (0-200 bytes, spanning several
# block boundaries). Catches length-dependent bugs — e.g. errors in the
# "complete last block" vs. "needs padding" branch — that four fixed-length
# vectors might not trigger.
# ---------------------------------------------------------------------------

def _random_case(rng: random.Random):
    key = bytes(rng.randrange(256) for _ in range(16))
    length = rng.randrange(0, 201)
    msg = bytes(rng.randrange(256) for _ in range(length))
    return key, msg


_RNG = random.Random(0xA35CE4)
_RANDOM_CASES = [_random_case(_RNG) for _ in range(30)]


@pytest.mark.parametrize('key, msg', _RANDOM_CASES,
                          ids=[f'rand{i:02d}_len{len(m)}' for i, (_, m) in enumerate(_RANDOM_CASES)])
def test_random_cross_validation(runner_binary, key, msg):
    """C runner and Python `cryptography` CMAC must agree for random inputs."""
    c = CMAC(algorithms.AES(key))
    c.update(msg)
    expected_tag = c.finalize().hex()

    got_tag = run_runner(runner_binary, key.hex(), msg.hex())
    assert got_tag.lower() == expected_tag, \
        f'tag mismatch for key={key.hex()} msg_len={len(msg)}:\n' \
        f'  exp {expected_tag}\n  got {got_tag.lower()}'
