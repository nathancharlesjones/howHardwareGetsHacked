#!/usr/bin/env python3

import serial
import sys

DEFAULT_BAUD = 115200

def main():
	# Check if at least one argument (after the script name) is provided
	if len(sys.argv) < 2:
	    print("Usage: ./monitor.py <serial port to connect to>")
	    sys.exit(1) # Exit if no arguments are provided

	try:
		device = serial.Serial(sys.argv[1], DEFAULT_BAUD)
		print("Monitor program for eCTF devices. Enter 'q' to quit.")
		inStr = input(">> ")
		while inStr != 'q':
			# Check for enable command
			device.write(inStr.encode('utf-8'))
			print(device.readline().decode('utf-8').strip())
	except serial.SerialException as e:
	    print(f"Error opening serial port: {e}")

	finally:
	    # --- Close the port ---
	    if 'device' in locals() and device.is_open:
	        device.close()
	        print("Serial port closed.")

if __name__ == "__main__":
    main()