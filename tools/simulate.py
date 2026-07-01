#!/usr/bin/env python3

"""
Simulation environment for x86 testing.

Manages the wiring together of one or two x86 executables using virtual serial ports.
The environment opens a "board connection" shared between the two executables (if both
provided), and each device gets its own "host connection" for communication.

Architecture (two devices):
    Test <--[host1]--> exe1 <--[board]--> exe2 <--[host2]--> Test

Architecture (one device):
    Test <--[host1]--> exe1

Usage:
    with SimulationEnvironment(binary1, binary2=None) as env:
        dev1 = env.primary
        dev2 = env.secondary  # None if not provided
        # test or interact with devices
    # cleanup happens automatically
"""

import os
import time
import serial
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from virtualserialports import VirtualSerialPorts

from devices import DeployedDevice
from typing import Union


DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


class SimulationEnvironment:
    """
    Context manager for a simulation environment with one or two x86 devices.

    Usage (two devices):
        with SimulationEnvironment(binary1, binary2) as (dev1, dev2):
            # test code

    Usage (one device):
        with SimulationEnvironment(binary1) as dev1:
            # test code
    """

    def __init__(self, binary1: Path, binary2: Optional[Path] = None):
        """
        Initialize the environment with one or two binaries.

        Args:
            binary1: Path to first executable
            binary2: Path to second executable (optional)
        """
        self.binary1 = Path(binary1)
        self.binary2 = Path(binary2) if binary2 else None
        self.board_vsp: Optional[VirtualSerialPorts] = None
        self.dev1: Optional[DeployedDevice] = None
        self.dev2: Optional[DeployedDevice] = None
    
    def __enter__(self) -> Union[DeployedDevice, tuple[DeployedDevice, DeployedDevice]]:
        """
        Enter the simulation environment: launch binaries and wire them together.

        Returns:
            DeployedDevice if only binary1 provided, else tuple of two DeployedDevices
        """
        # Create board connection if we have two devices
        if self.binary2:
            self.board_vsp = VirtualSerialPorts(2)
            self.board_vsp.open()
            self.board_vsp.start()
            board_ports = self.board_vsp.ports
        else:
            board_ports = [None, None]

        # Deploy primary device
        self.dev1 = self._launch_device(self.binary1, board_ports[0])

        # Deploy secondary device if provided
        if self.binary2:
            self.dev2 = self._launch_device(self.binary2, board_ports[1])
            return self.dev1, self.dev2
        else:
            return self.dev1
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up all resources."""
        if self.dev1:
            self.dev1.close()
        if self.dev2:
            self.dev2.close()

        if self.board_vsp:
            self.board_vsp.stop()
            self.board_vsp.close()

        return False
    
    def _launch_device(self, binary: Path, board_port: Optional[str]) -> DeployedDevice:
        """
        Launch a single device and return its DeployedDevice.
        
        Args:
            binary: Path to the executable
            board_port: Virtual serial port for board communication (None if single device)
            
        Returns:
            DeployedDevice for communicating with the launched instance
        """
        binary = Path(binary)
        
        # Create host connection for this device
        host_vsp = VirtualSerialPorts(2)
        host_vsp.open()
        host_vsp.start()
        test_port, exe_host_port = host_vsp.ports
        
        # Open serial connection from test side
        ser = serial.Serial(test_port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
        ser.reset_input_buffer()
        
        # Build command line for executable
        cmd_args = [str(binary), f"host={exe_host_port}"]
        if board_port:
            cmd_args.append(f"board={board_port}")
        
        # Launch executable
        pid = os.fork()
        if pid == 0:
            # Child process: redirect stdout to /dev/null and exec the binary.
            # stderr is deliberately left inherited (not redirected) so that
            # firmware perror()/fprintf(stderr, ...) diagnostics surface in
            # pytest's "Captured stderr call" section instead of being
            # silently discarded - see SESSION_CHANGES.md #8.
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 1)  # redirect stdout
            os.close(devnull)

            # Child process: set up new session and exec the binary
            os.setsid()
            os.execv(cmd_args[0], cmd_args)
        
        # Parent continues here
        time.sleep(0.1)
        
        # Wait for "OK: started" message from the executable
        startup = ser.readline().decode('ascii', errors='replace').strip()
        if not startup.startswith("OK"):
            raise RuntimeError(f"Device didn't start properly, got: {startup}")
        
        # Create device object
        dev = DeployedDevice(ser, _pid=pid, _vsp=host_vsp)
        return dev


def main():
    """
    Command-line interface for running a simulation.
    
    Usage:
        python3 simulate.py binary1 [binary2]
    
    Examples:
        python3 simulate.py ./car              # Single device
        python3 simulate.py ./car ./fob        # Two devices
    """
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 simulate.py binary1 [binary2]")
        print("\nExamples:")
        print("  python3 simulate.py ./car              # Single device")
        print("  python3 simulate.py ./car ./fob        # Two devices")
        sys.exit(1)
    
    binary1 = Path(sys.argv[1])
    binary2 = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    
    # Validate files exist
    if not binary1.exists():
        print(f"Error: {binary1} not found")
        sys.exit(1)
    if binary2 and not binary2.exists():
        print(f"Error: {binary2} not found")
        sys.exit(1)
    
    try:
        with SimulationEnvironment(binary1, binary2) as result:
            # Print port information for the user
            print(f"Simulation running:")
            if isinstance(result, tuple):
                dev1, dev2 = result
                print(f"  Device 1 host port: {dev1.serial.port}")
                print(f"  Device 2 host port: {dev2.serial.port}")
            else:
                dev1 = result
                print(f"  Device 1 host port: {dev1.serial.port}")
            print("\nPress Ctrl-C to stop.\n")

            # Block until user interrupts
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
