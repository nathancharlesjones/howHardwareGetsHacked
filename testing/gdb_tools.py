"""
Shared OpenOCD/gdb debug-session helpers for the buffer-overflow test suite:
starting a real gdbserver session against a deployed board and waiting for
it to actually come up, extracted out of test_stack_overflow_poc.py (which
originated this pattern) so Stage 3/4's tests in test_overflow_derivation.py
don't duplicate it a second and third time - see that file's module
docstring for how each stage uses this.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import openocd  # noqa: E402


def start_openocd_gdbserver(platform: str, probe_serial: str, gdb_port: int,
                             telnet_port: int = 44490) -> subprocess.Popen:
    """Start an OpenOCD gdbserver session for `probe_serial` in the
    background - does NOT flash or touch the target's running state, only
    attaches. Caller must terminate it (see stop_openocd()).

    Non-default gdb_port/telnet_port: OpenOCD binds 3333/4444 by default,
    which flash()/reset() elsewhere use transiently (they shut down when
    done) - a concurrent debug session needs its own ports to avoid
    colliding with those, or with another concurrent session's use of this
    same rig."""
    board_config = openocd.BOARD_CONFIG[platform]["config_file"]
    return subprocess.Popen(
        ["openocd", "-f", board_config, "-c", f"adapter serial {probe_serial}",
         "-c", f"gdb_port {gdb_port}", "-c", f"telnet_port {telnet_port}", "-c", "tcl_port disabled"],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def stop_openocd(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    """Terminate a start_openocd_gdbserver() session, killing it if it
    doesn't exit cleanly within `timeout`."""
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for_gdbserver(elf: Path, gdb_port: int, timeout: float = 10.0) -> None:
    """Poll until OpenOCD's gdbserver on gdb_port actually accepts a
    connection, rather than a fixed sleep - it can take a variable amount of
    time to come up (or contend with another concurrent OpenOCD/probe use)."""
    deadline = time.monotonic() + timeout
    last_output = ""
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["gdb-multiarch", "-batch",
             "-ex", f"target extended-remote localhost:{gdb_port}",
             "-ex", "detach",
             str(elf)],
            capture_output=True, text=True, timeout=5,
        )
        last_output = result.stdout + result.stderr
        if "Remote communication error" not in last_output and "Connection refused" not in last_output:
            return
        time.sleep(0.5)
    raise RuntimeError(f"OpenOCD gdbserver on port {gdb_port} never came up:\n{last_output}")


def run_breakpoint_probe(elf: Path, gdb_port: int, reentry_addr: int, tmp_path: Path,
                          trigger_fn, gdb_timeout: float = 20.0) -> str:
    """Set a one-shot breakpoint at reentry_addr, call trigger_fn() to cause
    it to be hit, then delete the breakpoint and resume so whatever's on the
    other side of it runs to completion undisturbed. Returns gdb's captured
    stdout for the caller to check with assert_breakpoint_hit() below.

    Assumes an OpenOCD gdbserver is already up on gdb_port (see
    start_openocd_gdbserver()/wait_for_gdbserver()). trigger_fn is called
    once gdb has had a moment to attach and issue `continue` (so it's
    genuinely waiting), and its return value is ignored - it exists purely
    for its side effect (e.g. a real unlock, or a crafted wire payload) of
    causing the target to reach reentry_addr. If it never does, gdb's
    `continue` just blocks until gdb_timeout, at which point the process is
    killed and whatever partial output exists is returned - letting
    assert_breakpoint_hit() report a clear "never fired" failure rather than
    this function hanging the test indefinitely.

    Shared by test_overflow_derivation.py's Stage 3 (trigger_fn = a real
    proto.cmd_btn_press unlock) and Stage 4a (trigger_fn = delivering the
    crafted overflow payload over the wire) - same mechanics, different
    trigger."""
    gdb_script = tmp_path / "breakpoint.gdb"
    gdb_script.write_text(f"""\
target extended-remote localhost:{gdb_port}
break *{reentry_addr:#x}
continue
print/x $pc
delete
continue
detach
""")
    gdb_proc = subprocess.Popen(
        ["gdb-multiarch", "-batch", "-x", str(gdb_script), str(elf)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        time.sleep(1.0)  # let gdb connect, set the breakpoint, and reach
                          # `continue` (now genuinely waiting) before trigger_fn
        trigger_fn()
        try:
            gdb_stdout, _ = gdb_proc.communicate(timeout=gdb_timeout)
        except subprocess.TimeoutExpired:
            gdb_proc.kill()
            gdb_stdout, _ = gdb_proc.communicate()
    finally:
        if gdb_proc.poll() is None:
            gdb_proc.kill()
    return gdb_stdout


def assert_breakpoint_hit(gdb_stdout: str, expected_addr: int) -> None:
    """Assert run_breakpoint_probe()'s captured output shows the breakpoint
    fired at exactly expected_addr - not just that something happened."""
    assert "Breakpoint 1," in gdb_stdout, (
        f"Breakpoint never fired at {expected_addr:#x}.\ngdb output:\n{gdb_stdout}"
    )
    m = re.search(r"\$1 = (0x[0-9a-f]+)", gdb_stdout)
    assert m, f"Breakpoint fired but couldn't parse the printed $pc:\n{gdb_stdout}"
    hit_addr = int(m.group(1), 16)
    assert hit_addr == expected_addr, (
        f"Breakpoint fired at {hit_addr:#x}, not the expected {expected_addr:#x}"
    )
