#!/usr/bin/env python3

from serial.tools.list_ports import comports

def list_devices():
	ports = comports()
	devices = [device for item in ports if item.description != "n/a"]
	return devices


if __name__ == "__main__":
    devices = list_devices()
    if len(devices) == 0:
    	print("No attached devices")
    else:
    	for dev in devices:
    		print(device.description)
    		print(f"  SN: {device.serial_number}")
    		print(f"  Port: {device.device}")