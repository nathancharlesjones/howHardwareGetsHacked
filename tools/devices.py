"""
Represents a deployed device (car or fob) on either hardware or simulation.

Each device manages its own resources:
- Serial port for host communication
- Process ID (x86 simulation only)
- Host-side virtual serial port (x86 simulation only)

The device cleans up its resources when closed.
"""

import os
import signal
import time
import serial
from typing import Optional
from dataclasses import dataclass


@dataclass
class DeployedDevice:
    """
    Represents a deployed device instance.
    
    Attributes:
        serial: Serial port connection for communication
        _pid: Process ID (x86 simulation only)
        _vsp: Virtual serial ports object (x86 simulation only)
    """
    serial: serial.Serial
    _pid: Optional[int] = None
    _vsp: Optional[object] = None

    def send(self, data: str) -> None:
        """Send data to device, automatically appending newline if needed."""
        if not data.endswith('\n'):
            data += '\n'
        self.serial.write(data.encode('ascii'))
        self.serial.flush()

    def recv(self, timeout: Optional[float] = None) -> str:
        """Receive one line from device, optionally with custom timeout.

        Reads in chunks and extends the deadline on progress, rather than
        using pyserial's default readline() (which reads one byte at a time,
        each independently subject to the timeout). On a loaded host, a long
        response can have hundreds of individual per-byte reads; if any single
        one of them is delayed past the timeout by scheduling jitter, the
        default readline() silently returns a truncated line. Chunked reads
        cut the number of at-risk syscalls from one-per-byte to a handful.
        """
        read_timeout = timeout if timeout is not None else self.serial.timeout
        old_timeout = self.serial.timeout
        self.serial.timeout = 0.1  # poll interval; overall budget enforced below
        buf = bytearray()
        deadline = time.monotonic() + read_timeout
        try:
            while time.monotonic() < deadline:
                chunk = self.serial.read(max(1, self.serial.in_waiting))
                if chunk:
                    buf += chunk
                    if b'\n' in chunk:
                        break
                    deadline = time.monotonic() + read_timeout  # reset on progress
        finally:
            self.serial.timeout = old_timeout
        return buf.decode('ascii', errors='replace').strip()

    def send_recv(self, data: str, timeout: Optional[float] = None) -> str:
        """Send data and receive response in one call."""
        self.send(data)
        return self.recv(timeout)

    def close(self):
        """Clean up device resources: serial port, process, and virtual serial ports."""
        self.serial.close()
        if self._pid:
            try:
                os.kill(self._pid, signal.SIGTERM)
                time.sleep(0.05)
                os.kill(self._pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except OSError:
                pass
        if self._vsp:
            self._vsp.stop()
            self._vsp.close()
