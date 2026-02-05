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
        """Receive one line from device, optionally with custom timeout."""
        old_timeout = self.serial.timeout
        if timeout is not None:
            self.serial.timeout = timeout
        try:
            return self.serial.readline().decode('ascii', errors='replace').strip()
        finally:
            self.serial.timeout = old_timeout

    def send_recv(self, data: str, timeout: Optional[float] = None) -> str:
        """Send data and receive response in one call."""
        self.send(data)
        return self.recv(timeout)

    def close(self):
        """Clean up device resources: serial port, process, and virtual serial ports."""
        # Close serial port first to unblock any pending reads/writes
        self.serial.close()

        # Terminate process and wait for it to die
        if self._pid:
            try:
                # Try graceful termination first
                os.kill(self._pid, signal.SIGTERM)

                # Wait for up to 0.5 seconds for graceful shutdown
                for _ in range(10):
                    try:
                        pid, status = os.waitpid(self._pid, os.WNOHANG)
                        if pid != 0:  # Process exited
                            break
                    except ChildProcessError:  # Already reaped
                        break
                    time.sleep(0.05)
                else:
                    # Process didn't die gracefully, force kill
                    try:
                        os.kill(self._pid, signal.SIGKILL)
                        os.waitpid(self._pid, 0)  # Block until it dies
                    except (OSError, ChildProcessError):
                        pass
            except (OSError, ChildProcessError):
                pass

        # Now that process is dead, clean up VSP
        if self._vsp:
            self._vsp.stop()
            self._vsp.close()
