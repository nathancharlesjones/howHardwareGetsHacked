"""
Build-budget tests: confirm flash/RAM footprint and worst-case stack depth
stay within each embedded target's hard limits.

Background: car.c's processHostCommand() briefly reserved ~7.7KB of TM4C's
fixed 7168-byte stack in a single frame - not from a VLA (the classic,
easy-to-spot case) but from an ordinary fixed-size local array
(getEntropySamples' samples[2550]+hex[5101]) that just happened to be huge.
GCC sizes a function's whole stack frame to the worst of its mutually-
exclusive branches, so *every* call into that function - not just the one
branch with the big array - was paying for it. Nothing about that was
visible from source alone without doing this arithmetic by hand.

SConstruct adds -fstack-usage to CPPFLAGS on its own whenever CC actually
accepts it (see compiler_accepts_flag() there) - no opt-in needed, since it
has no effect on the compiled output and no measurable compile-time cost.
When it's on, GCC emits one .su file per translation unit, reporting each
function's own stack frame size and whether it's statically known. That's
used two ways:

  1. Hard fail if any function reachable from main() has "dynamic"
     (unbounded, e.g. VLA/alloca) stack usage - the classic case.
  2. Best-effort worst-case *cumulative* stack depth along the call graph
     from main(), built from direct (bl/blx <symbol>) calls in the
     disassembly - the case that actually bit us, since a huge-but-fixed
     array doesn't set off check #1.

Check #2 is a lower bound, not a proof: it can't see through the couple of
function-pointer (blx <register>) calls in the AES-CMAC glue code, and
doesn't model interrupt stacking or the internals of prebuilt libc/libgcc
functions it didn't compile (and so has no .su data for). It's checked
against a fraction of the reserved stack budget (STACK_SAFETY_MARGIN)
rather than the raw size, specifically to absorb that slack - if it's
tripping, something has gotten large enough that the imprecision no longer
matters.

If CC doesn't accept -fstack-usage (a non-GCC/Clang toolchain), checks #1
and #2 above skip rather than fail or silently pass - there's no substitute
data source for either (arm-none-eabi-size's totals don't give per-function
frame sizes or a call graph to degrade to). Flash/RAM footprint, below,
needs none of this and always runs: checked separately (and exactly - no
margin, no model) via arm-none-eabi-size against each platform's own
linker-script region sizes, so a bloat regression shows up before the
linker's own hard failure would report the same overflow.

Run with `-v -s` to also get a box-drawing memory map (flash as
text/data/free, RAM as data/bss/heap/free/stack) printed per target - see
render_memory_map(). It's visualization only, built from the same numbers
the assertions above already check; -s is what makes pytest stop
swallowing the print().
"""

import re
import subprocess
from pathlib import Path

import pytest

from conftest import RoleConfig, build_binary, PROJECT_ROOT

ARM_SIZE = "arm-none-eabi-size"
ARM_OBJDUMP = "arm-none-eabi-objdump"

# Roles that share compiled code, one representative build per platform is
# enough to characterize them (paired_fob and unpaired_fob both build from
# fob.c - same functions, same .su data either way).
BUDGET_TARGETS = [
    ("tm4c", RoleConfig("car", id="900001")),
    ("tm4c", RoleConfig("paired_fob", id="900001", pin="123456")),
    ("stm32", RoleConfig("car", id="900002")),
    ("stm32", RoleConfig("paired_fob", id="900002", pin="123456")),
]

LD_SCRIPTS = {
    "tm4c": PROJECT_ROOT / "hardware/tm4c/libraries/tivaware/firmware.ld",
    "stm32": PROJECT_ROOT / "hardware/stm32/STM32F411XX_FLASH.ld",
}

# Neither platform's linker script carves out a dedicated stack region
# anymore (STM32 never really did either - see the comment on
# test_worst_case_stack_depth): SP starts at the true top of RAM and grows
# down through whatever .data/.bss/heap didn't claim. So "how much stack is
# actually available" isn't a linker-declared number to read - it's
# ram - data - bss, computed fresh per build below, same for both platforms.

# See module docstring: check #2 is a lower-bound model (misses
# function-pointer calls, interrupt stacking, and library-internal frames),
# so it's compared against a fraction of the reserved stack rather than all
# of it. This is a knob for that imprecision, not a "real" utilization
# target - if a legitimate change trips it, re-derive rather than just
# raising the number.
STACK_SAFETY_MARGIN = 0.5

# Flat per-call estimate for functions with no .su data of our own - almost
# always a leaf call into prebuilt libc (memset/memcpy/strncmp/atoi/...).
# Deliberately conservative for what this codebase actually calls; revisit
# if a call to something stack-heavier (e.g. float snprintf) shows up.
UNKNOWN_FUNC_STACK_BYTES = 32

# Reachability probe for the memory-map visualization's heap figure: this
# codebase never calls malloc() itself (see hardware/tm4c/source/syscalls.c),
# so "heap used" is 0 by construction, not by measurement - there's no
# tracked high-water mark to report. Rather than silently print a
# possibly-false 0 forever, check whether any of these ever become
# reachable from main() and say "unmeasured" instead if so.
HEAP_ALLOC_FUNCS = {"malloc", "_malloc_r", "calloc", "_calloc_r", "realloc", "_realloc_r"}


# =============================================================================
# Linker-script parsing (single source of truth for the budgets)
# =============================================================================

def _parse_size_literal(token):
    """'0x00008000' / '128K' / '32768' -> int bytes."""
    m = re.match(r'^(0[xX][0-9a-fA-F]+|\d+)\s*([KkMm]?)$', token.strip())
    if not m:
        raise RuntimeError(f"unrecognized linker-script size literal: {token!r}")
    value = int(m.group(1), 0)
    multiplier = {'': 1, 'k': 1024, 'm': 1024 * 1024}[m.group(2).lower()]
    return value * multiplier


def parse_ld_budget(platform):
    """Pull FLASH/RAM region sizes straight out of the platform's own linker
    script, so this test can't silently drift from what the linker itself
    enforces."""
    text = LD_SCRIPTS[platform].read_text()

    def region(name):
        m = re.search(rf'\b{name}\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*[^,]+,\s*LENGTH\s*=\s*([^\s,;]+)', text)
        if not m:
            raise RuntimeError(f"couldn't find {name} region in {LD_SCRIPTS[platform]}")
        return _parse_size_literal(m.group(1))

    return {
        "flash": region("FLASH"),
        "ram": region("RAM"),
    }


# =============================================================================
# arm-none-eabi-size (flash/RAM footprint)
# =============================================================================

def read_footprint(elf_path):
    """(text, data, bss) in bytes, from arm-none-eabi-size --format=berkeley."""
    out = subprocess.run(
        [ARM_SIZE, "--format=berkeley", str(elf_path)],
        capture_output=True, text=True, check=True,
    ).stdout
    # Header line, then "  text    data     bss     dec     hex filename"
    fields = out.splitlines()[1].split()
    text, data, bss = (int(fields[i]) for i in range(3))
    return text, data, bss


# =============================================================================
# .su parsing (per-function stack usage)
# =============================================================================

def parse_su_files(build_dir):
    """{function_name: (frame_bytes, qualifier)} from every .su under build_dir.
    qualifier is 'static' (known fixed size), or contains 'dynamic' (VLA/alloca -
    frame_bytes is GCC's best-effort estimate, not a real bound)."""
    usage = {}
    for su_path in Path(build_dir).rglob("*.su"):
        for line in su_path.read_text().splitlines():
            parts = line.split()
            if len(parts) != 3:
                continue  # tolerate stray/malformed lines rather than crash the test
            location, byte_str, qualifier = parts
            func = location.rsplit(":", 1)[-1]
            usage[func] = (int(byte_str), qualifier)
    return usage


# =============================================================================
# objdump-derived call graph (direct calls only - see module docstring)
# =============================================================================

_FUNC_HEADER_RE = re.compile(r'^[0-9a-fA-F]+\s+<([^>]+)>:$')
# Any branch mnemonic (b, bl, blx, and condition-coded forms like beq/bne/bcc),
# optionally .w/.n width-suffixed, landing on a resolved <symbol>.
_BRANCH_RE = re.compile(r'\bb\w*(?:\.[nw])?\s+[0-9a-fA-F]+\s+<([^>+]+)(?:\+0x[0-9a-fA-F]+)?>')
_INDIRECT_CALL_RE = re.compile(r'\bblx?\s+(?:r\d+|ip|lr|pc|sp)\b')


def build_call_graph(elf_path):
    """({caller: {callees}}, {caller: indirect_call_count}) from the disassembly.

    Treats any branch (not just bl/blx) landing on a *different* function's
    symbol as a call-graph edge, not just bl/blx. -O2 routinely rewrites a
    call in tail position (nothing left to do after it returns but return)
    into a plain `b`/`b.w` straight to the callee instead of `bl` - it's
    still every bit as much a call for stack-budgeting purposes (this is
    exactly how the two-part processHostCommand -> processHostCommand.part.0
    split, and separately its tail-call into a factored-out handler, both
    show up in the disassembly). A branch to an address *inside the current
    function* (ordinary loops/if-else) is excluded by requiring the target's
    resolved symbol to differ from the caller - it's intra-function control
    flow, not a call.
    """
    out = subprocess.run(
        [ARM_OBJDUMP, "-d", str(elf_path)],
        capture_output=True, text=True, check=True,
    ).stdout

    graph = {}
    indirect = {}
    current = None

    for line in out.splitlines():
        header = _FUNC_HEADER_RE.match(line)
        if header:
            current = header.group(1)
            graph.setdefault(current, set())
            continue
        if current is None:
            continue
        m = _BRANCH_RE.search(line)
        if m:
            target = m.group(1)
            if target != current:
                graph[current].add(target)
        elif _INDIRECT_CALL_RE.search(line):
            indirect[current] = indirect.get(current, 0) + 1

    return graph, indirect


# =============================================================================
# Worst-case cumulative stack depth
# =============================================================================

def reachable_from(call_graph, root):
    seen = set()
    stack = [root]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        stack.extend(call_graph.get(f, ()))
    return seen


def worst_case_stack_path(call_graph, su_usage, root="main", unknown_bytes=UNKNOWN_FUNC_STACK_BYTES):
    """Memoized DFS: max cumulative stack bytes along any direct-call chain
    from root, through OUR OWN compiled code only. A function with no .su
    entry is prebuilt library code (no source, no per-function data, and
    -O2'd library internals can have real mutual-tail-call cycles that
    aren't recursion in any meaningful sense but would trip cycle detection
    anyway) - it's charged one flat unknown_bytes fee as a leaf and not
    traversed into. Raises on a call cycle within our own code (recursion
    isn't safe to budget this way, and this codebase shouldn't have any)."""
    memo = {}
    visiting = set()

    def dfs(func):
        if func in memo:
            return memo[func]
        info = su_usage.get(func)
        if info is None:
            # Boundary of our own compiled code - don't traverse further.
            return unknown_bytes, [func]
        if func in visiting:
            raise RuntimeError(
                f"call cycle detected at {func!r} - recursion on a fixed-size "
                f"embedded stack can't be budgeted by summing frame sizes"
            )
        visiting.add(func)
        best_extra, best_tail = 0, []
        for callee in call_graph.get(func, ()):
            extra, tail = dfs(callee)
            if extra > best_extra:
                best_extra, best_tail = extra, tail
        visiting.discard(func)
        result = (info[0] + best_extra, [func] + best_tail)
        memo[func] = result
        return result

    return dfs(root)


# =============================================================================
# Memory-map visualization (printed under `-v -s`; doesn't assert anything -
# the numbers it renders are the same ones test_flash_and_ram_footprint and
# test_worst_case_stack_depth already check)
# =============================================================================

MAP_BAR_WIDTH = 60


def _bar_row(segments, total, width=MAP_BAR_WIDTH):
    """One box-drawing bar row: each (letter, bytes) segment gets a
    proportional run of `letter`, in segment order, sized so the whole row
    is exactly `width` columns wide.

    Byte counts almost never divide evenly into `width` columns, so this
    uses largest-remainder rounding (award each segment its floor share,
    then hand the columns lost to truncation to whichever segments had the
    biggest fractional remainder) rather than plain int() truncation - that
    keeps the row's total width exact without visibly shortchanging
    whichever segment happens to round down.
    """
    nonzero = [(letter, count) for letter, count in segments if count > 0]
    if not nonzero:
        return "." * width
    exact = [count * width / total for _, count in nonzero]
    cols = [int(w) for w in exact]
    remainder = width - sum(cols)
    order = sorted(range(len(nonzero)), key=lambda i: exact[i] - cols[i], reverse=True)
    for i in order[:remainder]:
        cols[i] += 1
    return "".join(letter * n for (letter, _), n in zip(nonzero, cols))


def _map_legend_lines(rows, region_total):
    lines = []
    label_width = max(len(label) for _, label, _ in rows)
    for letter, label, n in rows:
        if n is None:
            lines.append(f"   {letter} {label:<{label_width}}          unmeasured (reachable, no tracked high-water mark)")
            continue
        pct = 100 * n / region_total
        lines.append(f"   {letter} {label:<{label_width}}  {n:>8,} B  ({pct:5.1f}%)")
    return lines


def render_memory_map(label, flash_budget, ram_budget, text, data, bss,
                       stack_used, heap_used):
    """Two stacked box-drawing bars (flash, then RAM) plus a byte/percentage
    legend under each - flash as text+data+free, RAM as data+bss+heap+
    free+stack (address order: heap grows up from _end, stack grows down
    from the true top of RAM, whatever's unclaimed between them is free -
    see firmware.ld / STM32F411XX_FLASH.ld). heap_used=None means "can't
    measure, but confirmed unreachable" territory doesn't apply here -
    render_memory_map is only called once malloc IS reachable, so None
    always means print "unmeasured" instead of a number."""
    flash_free = flash_budget - text - data
    ram_free = ram_budget - data - bss - (heap_used or 0) - stack_used

    flash_bar = _bar_row([("T", text), ("D", data), (".", flash_free)], flash_budget)
    ram_bar = _bar_row(
        [("D", data), ("B", bss), ("H", heap_used or 0), (".", ram_free), ("S", stack_used)],
        ram_budget,
    )

    lines = [
        "",
        "=" * (MAP_BAR_WIDTH + 2),
        f" {label} memory map",
        "=" * (MAP_BAR_WIDTH + 2),
        "",
        f" FLASH  {flash_budget:,} B budget",
        "┌" + "─" * MAP_BAR_WIDTH + "┐",
        "│" + flash_bar + "│",
        "└" + "─" * MAP_BAR_WIDTH + "┘",
    ]
    lines += _map_legend_lines(
        [("T", "text", text), ("D", "data", data), (".", "free", flash_free)],
        flash_budget,
    )
    lines += [
        "",
        f" RAM    {ram_budget:,} B budget",
        "┌" + "─" * MAP_BAR_WIDTH + "┐",
        "│" + ram_bar + "│",
        "└" + "─" * MAP_BAR_WIDTH + "┘",
    ]
    lines += _map_legend_lines(
        [
            ("D", "data", data),
            ("B", "bss", bss),
            ("H", "heap", heap_used),
            (".", "free", ram_free),
            ("S", "stack (worst-case)", stack_used),
        ],
        ram_budget,
    )
    return "\n".join(lines)


# =============================================================================
# Fixture: build once per (platform, role), shared by both checks below
# =============================================================================

@pytest.fixture(scope="module")
def built(request):
    platform, cfg = request.param
    elf_path = build_binary(cfg, platform)
    build_dir = elf_path.parent
    return platform, elf_path, build_dir


def _target_id(val):
    platform, cfg = val
    return f"{platform}-{cfg.role}"


# =============================================================================
# Tests
# =============================================================================

@pytest.mark.parametrize("built", BUDGET_TARGETS, indirect=True, ids=_target_id)
class TestBuildBudgets:

    def test_flash_and_ram_footprint(self, built):
        """.data/.bss must physically fit in RAM - the bare precondition for
        there to be any stack space left over at all. How much stack itself
        is needed, and whether what's left is enough, is a separate,
        measured question - see test_worst_case_stack_depth."""
        platform, elf_path, _ = built
        budget = parse_ld_budget(platform)
        text, data, bss = read_footprint(elf_path)

        flash_used = text + data
        ram_used = data + bss

        assert flash_used <= budget["flash"], (
            f"{platform}: flash usage {flash_used}B (text={text}+data={data}) "
            f"exceeds {budget['flash']}B available"
        )
        assert ram_used <= budget["ram"], (
            f"{platform}: RAM usage {ram_used}B (data={data}+bss={bss}) "
            f"exceeds {budget['ram']}B available"
        )

    def test_no_unbounded_stack_functions(self, built):
        """Fail if anything reachable from main() has GCC-reported
        'dynamic' stack usage (VLA/alloca) - unbounded by construction, so
        no numeric budget check can vouch for it. This is what would have
        caught the original getBoardMsgLog VLA directly."""
        platform, elf_path, build_dir = built
        su_usage = parse_su_files(build_dir)
        if not su_usage:
            pytest.skip(
                f"{platform}: no .su files found - CC doesn't accept "
                f"-fstack-usage (see compiler_accepts_flag() in SConstruct), "
                f"so there's no per-function stack data to check here. "
                f"test_flash_and_ram_footprint still covers the flash/RAM "
                f"totals regardless."
            )
        call_graph, _ = build_call_graph(elf_path)

        reachable = reachable_from(call_graph, "main")
        offenders = sorted(
            f for f in reachable
            if f in su_usage and "dynamic" in su_usage[f][1]
        )
        assert not offenders, (
            f"{platform}: function(s) with unbounded stack usage reachable from "
            f"main(): {offenders} (qualifiers: "
            f"{[su_usage[f][1] for f in offenders]}) - replace the VLA/alloca "
            f"with a fixed-size or static buffer"
        )

    def test_worst_case_stack_depth(self, built):
        platform, elf_path, build_dir = built
        budget = parse_ld_budget(platform)
        su_usage = parse_su_files(build_dir)
        if not su_usage:
            pytest.skip(
                f"{platform}: no .su files found - CC doesn't accept "
                f"-fstack-usage (see compiler_accepts_flag() in SConstruct), "
                f"so there's no per-function stack data to compute a "
                f"worst-case depth from. arm-none-eabi-size alone (what "
                f"test_flash_and_ram_footprint uses) has no substitute for "
                f"this - it reports totals, not per-function frame sizes or "
                f"a call graph, so there's nothing to degrade to here."
            )
        call_graph, indirect = build_call_graph(elf_path)
        text, data, bss = read_footprint(elf_path)

        # Neither platform's linker script reserves a fixed stack region:
        # SP starts at the true top of RAM on both and grows down through
        # whatever .data/.bss/heap left unclaimed. So the real available
        # stack isn't a linker-declared constant to read - it's this, computed
        # fresh per build (and per role: fob's much smaller .bss than car's
        # leaves it correspondingly more headroom here, not a fixed number
        # sized for the worse case of the two).
        available_stack = budget["ram"] - data - bss

        worst_bytes, path = worst_case_stack_path(call_graph, su_usage)
        limit = available_stack * STACK_SAFETY_MARGIN

        # See HEAP_ALLOC_FUNCS: this codebase has no tracked heap high-water
        # mark, so "0 used" is only trustworthy while malloc/calloc/realloc
        # stay unreachable from main() - checked fresh per build rather than
        # asserted once, since that's exactly the kind of thing a future
        # change could quietly falsify.
        reachable = reachable_from(call_graph, "main")
        heap_used = None if reachable & HEAP_ALLOC_FUNCS else 0

        print(render_memory_map(
            f"{platform}/{elf_path.stem}", budget["flash"], budget["ram"],
            text, data, bss, worst_bytes, heap_used,
        ))

        indirect_on_path = [f for f in path if indirect.get(f)]
        note = (
            f" (NOTE: {indirect_on_path} make function-pointer calls this "
            f"model can't see through - the true worst case may be higher)"
            if indirect_on_path else ""
        )

        assert worst_bytes <= limit, (
            f"{platform}: worst-case stack depth from main() is ~{worst_bytes}B "
            f"along {' -> '.join(path)}, over the {STACK_SAFETY_MARGIN:.0%} "
            f"safety margin of the {available_stack}B available stack "
            f"({limit:.0f}B){note}"
        )
