#!/usr/bin/env python3

import serial
import sys
import os

DEFAULT_BAUD = 115200

def main():
    # Check if at least one argument (after the script name) is provided
    if len(sys.argv) < 2:
        print("Usage: ./monitor.py <serial port to connect to>")
        sys.exit(1) # Exit if no arguments are provided

    try:
        device = serial.Serial(sys.argv[1], DEFAULT_BAUD, timeout=0.05)
        device.reset_input_buffer()
        print("Monitor program for eCTF devices. Enter 'q' to quit.")

        inStr = input(">> ")
        while inStr != 'q':
            # Special handling for: enable <path>
            if inStr.startswith("enable "):
                path = inStr[len("enable "):].strip()

                if not os.path.isfile(path):
                    print(f"Error: '{path}' is not a valid file")
                    continue

                try:
                    with open(path, "rb") as f:
                        feature_data = f.read().hex()

                    payload = f"enable {feature_data}\n"
                    device.write(bytes(payload, "utf-8"))

                except OSError as e:
                    print(f"Failed to read feature file: {e}")
                    continue
            else:
                # Normal text command
                device.write((inStr+'\n').encode('utf-8'))

            old_timeout = device.timeout
            device.timeout = 2.0
            while True:
                line = device.readline()
                if not line:  # Timeout with no data means we're done
                    break
                try:
                    print(line.decode('utf-8').strip())
                except UnicodeDecodeError:
                    # Try stripping first byte (often 0xFF from UART reset glitch)
                    if len(line) > 1:
                        try:
                            print(line[1:].decode('utf-8').strip())
                        except UnicodeDecodeError:
                            print(f"[Binary data: {line.hex()}]")
                    else:
                        print(f"[Binary data: {line.hex()}]")
                device.timeout = old_timeout
            
            inStr = input(">> ")
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")

    finally:
        # --- Close the port ---
        if 'device' in locals() and device.is_open:
            device.close()
            print("Serial port closed.")

if __name__ == "__main__":
    main()