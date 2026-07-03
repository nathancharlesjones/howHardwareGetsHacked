# Session change log — macOS CI investigation (2026-07-01)

**Status: fixed and cleaned up.** Root cause was confirmed via a macOS CI
run against `d06d1ab` (passed). Cleanup below (reverts + reword) is done
and pushed as `ad13383`, `15cd2f0`, `71ddf9f`. Kept as a record of the
investigation; safe to delete once you're done referencing it.

Untracked scratch file, not meant to be committed. Lists every commit made
during this troubleshooting session on `main`, in order.

| # | SHA | Files | Purpose | Status |
|---|-----|-------|---------|--------|
| 1 | `a453a49` | `.github/workflows/multi-platform-test.yml` | Add `workflow_dispatch` so the multi-platform test can be run manually | Working as intended, keep |
| 2 | `796ba03` | `SConstruct`, `application/source/fob.c`, `docs/threat-model.md`, `hardware/*/SConscript`, `testing/conftest.py`, `testing/functional_tests.py`, `testing/security_tests.py`, `tools/fob_gen_secret.py` | Restore the 750ms anti-brute-force pairing delay as a build-time `pairing_delay_ms` param (fixed the Ubuntu brute-force test failure); fixed a bug where a `pairing_delay_ms=0` build turned into `UINT_MAX` after subtracting 1 in the timing-attack test | Working as intended, keep |
| 3 | `4451b58` | `testing/protocol.py` | Diagnosed truncated `getBoardMsgLog` responses as a possible host read-timeout; bumped `cmd_get_board_msg_log` timeout 2.0s→5.0s and turned silent truncation into a clear `RuntimeError` | Not the root cause, but the `RuntimeError` (clear message instead of a bare `IndexError`) and the longer timeout are still good defensive value. **Reword the message** — it currently says "Likely a slow/loaded host reading the serial response past its timeout rather than a firmware bug," which is now known to be wrong; it was a relay short-write bug (see #9) |
| 4 | `b852fe1` | `.github/workflows/multi-platform-test.yml` | Bumped `actions/checkout` v4→v7, `actions/setup-python` v5→v6, `actions/cache` v4→v6 (clears Node 20 deprecation warning); added `brew untap aws/tap` step (clears Homebrew untrusted-tap warning) | Unrelated to the truncation bug — cosmetic CI warning cleanup, keep |
| 5 | `f9f5869` | `tools/devices.py` | Replaced pyserial's byte-at-a-time `readline()` in `DeployedDevice.recv()` with a chunked read that extends its deadline on progress | Not the root cause (disproved the read-side timing theory). Still a generically more robust primitive than pyserial's default readline() — **recommend keeping** even though it wasn't the bug |
| 6 | `54cce0a` | `hardware/sim/source/uart_sim.c` | `uart_write()` now retries on `ENOBUFS`/`EINTR` in addition to `EAGAIN`/`EWOULDBLOCK` | Not the root cause — the diagnostic in #7/#8 proved this error path is never even hit. **Revert candidate**: harmless to keep (never fires in practice) but adds no value either since the real bug was never in our own `uart_write()` |
| 7 | `adb4d3d` | `hardware/sim/source/uart_sim.c` | Added `fprintf(stderr, "uart_write: errno=%d (%s), total_written=%u of %u\n", ...)` right before the existing `perror("uart_write")` in the non-retried error path | Diagnostic. Confirmed useful negative result: the branch never fired, which is what redirected the investigation away from `uart_write()` entirely. **Revert candidate** now that root cause is confirmed elsewhere, unless worth keeping as permanent defensive logging |
| 8 | `0f23bec` | `tools/simulate.py` | Stopped redirecting the sim binary's stderr to `/dev/null` in `_launch_device()` (stdout still redirected) | Diagnostic, and it worked as intended (would have shown #7's output had it fired). **Recommend keeping regardless** — visible firmware stderr is generally useful for future debugging, at basically no cost |
| 9 | `d06d1ab` | `tools/simulate.py` | Added `ReliableVirtualSerialPorts`/`_RetryWriteFile` wrapper around the third-party `PyVirtualSerialPorts` library: its relay loop calls `f.write(data)` on a non-blocking, unbuffered file object and never checks the return value, so a short write silently drops the untransmitted tail forever | **This is believed to be the actual root cause fix.** Awaiting a macOS CI run to confirm |

## Root cause (confirmed 2026-07-01, commit `d06d1ab`)

`PyVirtualSerialPorts==2.0.0` (pinned dependency, `setup/requirements.txt`,
not our code) opens each virtual port's master fd non-blocking and
unbuffered (`buffering=0`) in `VirtualSerialPorts.open()`. Its relay loop
(`VirtualSerialPorts.process()`) does `f.write(data)` to forward bytes
between ports **without checking the return value**. A non-blocking
`write()` can perform a **short write** — return fewer bytes written than
given — when the destination pty's kernel buffer is momentarily full; any
untransmitted remainder is silently, permanently dropped (no retry, no
error surfaced anywhere).

This explains every observed property of the bug:
- **True, permanent data loss**, not a delay — matches (nothing our own
  retry-happy read/write code in #5/#6 could have caught, since the loss
  happens inside the third-party relay between our writer and our reader)
- **Deterministic per run**, even though message *content* differs
  (different random nonces each run) — the *size* and *structure* of the
  ~1955-byte `getBoardMsgLog` response is always identical, so the same
  destination-buffer boundary gets hit at the same offset every time
- **macOS-only** — BSD/Darwin pty kernel buffers are classically smaller
  than Linux's; Linux's larger buffer never overflows for this payload size
- **Clean end-of-stream truncation** (not mid-stream corruption) — the
  captured log entries all decoded correctly on their 65-byte boundaries,
  confirming nothing shifted; only the always-zero-padded tail was short

Diagnosed by reading the installed library's source directly
(`hhghVenv/lib/python3.11/site-packages/virtualserialports.py`) after #7/#8
proved the loss wasn't happening in our own `uart_write()`, and after #5
proved it wasn't a host-side read timeout.

## Recommended cleanup once `d06d1ab` is confirmed fixed on macOS CI

- **Revert #6** (`54cce0a`) — adds retry-on-`ENOBUFS`/`EINTR` to a firmware
  error path that's now confirmed to never fire in this bug; no evidence it
  has value elsewhere either.
- **Revert #7** (`adb4d3d`) — the diagnostic `fprintf`, unless we decide
  permanent errno logging in `uart_write()`'s failure path is worth keeping
  generally (low cost either way).
- **Keep #8** (`0f23bec`) — visible firmware stderr is broadly useful for
  future debugging, not just this bug.
- **Keep #5** (`f9f5869`) — more robust than pyserial's default `readline()`
  even though it wasn't this bug's cause.
- **Reword #3's (`4451b58`) `RuntimeError` message** — it blames "a
  slow/loaded host reading past its timeout," which is now known to be
  wrong; should reference the relay short-write issue instead (or just be
  more neutral about the cause).
- **Keep #1, #2, #4, #9** — unrelated to each other, all working as
  intended.
