# Linux Development Setup

This guide will help you set up your Linux machine for embedded development. Linux is the most straightforward platform for embedded development with native tool support.

## Prerequisites

- Ubuntu 20.04+ (or equivalent Debian-based distribution)
- Other distributions (Fedora, Arch, etc.) will work with package manager adjustments
- Administrator access (sudo)
- Internet connection

## Installing Development Tools

### For Ubuntu/Debian-based distributions:

```bash
# Essential build tools
sudo apt update
sudo apt install -y \
    build-essential \
    git \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev

# ARM cross-compiler toolchain
sudo apt install -y gcc-arm-none-eabi

# OpenOCD (for programming/debugging STM32 and TM4C)
sudo apt install -y openocd

# X11 terminal emulator (required for x86 console simulator)
sudo apt install -y xterm

# GDB for ARM debugging (optional but recommended)
sudo apt install -y gdb-multiarch

# OPTIONAL: Serial port tools (useful for manual debugging; only need one)
sudo apt install -y \
    minicom \
    screen \
    picocom
```

**Note:** Python project dependencies will be installed from `requirements.txt` into your virtual environment in a later step.

### For Fedora/RHEL-based distributions:

```bash
sudo dnf install -y \
    gcc gcc-c++ make \
    git \
    python3 python3-pip python3-virtualenv \
    arm-none-eabi-gcc-cs \
    openocd \
    xterm \
    gdb-multiarch \
    minicom screen
```

### For Arch Linux:

```bash
sudo pacman -S \
    base-devel \
    git \
    python python-pip python-virtualenv \
    arm-none-eabi-gcc \
    openocd \
    xterm \
    gdb-multiarch \
    minicom screen
```

## Setting Up USB Access to Devices

### Configure USB Permissions

Linux requires permission to access USB devices. Add your user to the `dialout` group:

```bash
# Add your user to dialout group (for serial port access)
sudo usermod -a -G dialout $USER

# Log out and log back in for group changes to take effect
# Or run this to apply immediately in current shell:
newgrp dialout
```

### Install USB Device Drivers

#### ST-Link (for STM32 boards)

Modern Linux kernels include ST-Link drivers by default. Verify detection:

```bash
# With ST-Link connected
lsusb | grep STM
# Should show: STMicroelectronics ST-LINK/V2.1

# Check serial devices
ls /dev/ttyACM*
# Should show: /dev/ttyACM0 (or similar)
```

If OpenOCD can't access the device, add udev rules:

```bash
# Create udev rules file
sudo nano /etc/udev/rules.d/99-openocd.rules
```

Add the following:

```
# ST-Link V2
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="3748", MODE="0666"
# ST-Link V2.1
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="374b", MODE="0666"
# ST-Link V3
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="374e", MODE="0666"
```

Reload udev rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### TM4C123 (for TI Tiva C Launchpad)

The TI TM4C123 (EK-TM4C123GXL) should work automatically:

```bash
# Check if TM4C123 ICDI is detected
lsusb | grep -i "texas\|stellaris\|tm4c"

# Check serial devices
ls /dev/ttyACM*
```

The TM4C123 appears as two devices:
- **Stellaris ICDI** - debugger interface (for OpenOCD)
- **Virtual COM port** - appears as `/dev/ttyACM0` or `/dev/ttyACM1`

If needed, add udev rules:

```bash
sudo nano /etc/udev/rules.d/99-openocd.rules
```

Add:

```
# TI Stellaris ICDI
SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", ATTR{idProduct}=="00fd", MODE="0666"
```

Reload:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Cloning or Downloading the Project

```bash
# Navigate to where you want the project
cd ~/Documents  # or wherever you prefer

# Clone the repository
git clone https://github.com/nathancharlesjones/howHardwareGetsHacked
cd your-project
```

## Setting Up the Virtual Environment

**Python version:** This project requires Python 3.11. Newer versions (3.12+) may fail to build some dependencies (`gdbgui` → `gevent` → `greenlet`). If your system Python is newer, install 3.11 via the deadsnakes PPA:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

Then create the venv with `python3.11` explicitly (see below).

```bash
# Create a Python virtual environment (use python3.11 if your system Python is newer)
python3.11 -m venv hhghVenv

# Activate the virtual environment (IMPORTANT!)
source hhghVenv/bin/activate

# Your prompt should now show (hhghVenv) prefix

# Install Python dependencies
pip install --upgrade pip
pip install -r setup/requirements.txt

# This installs: SCons, pytest, pyserial, PyVirtualSerialPorts, gdbgui
```

**Important:** Always activate the virtual environment before working:

```bash
cd ~/your-project
source hhghVenv/bin/activate
```

To deactivate when done:

```bash
deactivate
```

## Confirming Everything Worked

### Run Platform Tests

```bash
# Activate venv first
source hhghVenv/bin/activate

# Run platform compatibility tests
./setup/test_platform.py

# Should show all tools installed and working
```

### Build and Test

```bash
# Build x86 console version (no hardware needed)
scons -j8 x86 id=1337 pin=123456 ui=console test=1

# Begin simulation
./tools/simulate.py hardware/x86/build/paired_fob_1337/paired_fob_1337 hardware/x86/build/car_1337/car_1337

# Attach to HOST serial ports. In separate terminals:
./tools/monitor.py {fob port; first port printed by simulate tool}
./tools/monitor.py {car port; second port printed by simulate tool}

# Run test commands
## In car monitor window:
>> isLocked  # Should return "OK: 1" (the car is locked)
## In fob console window, press 'b'. Car LED should turn green.
## In car monitor window:
>> isLocked  # Should return "OK: 0" (the car is now UNlocked)

# Run software tests
pytest testing/test.py
```

## Optional: Debugging with GDB

### Using gdb-multiarch

The `gdb-multiarch` tool can debug multiple architectures (ARM, x86, etc.) from a single GDB installation:

```bash
# Debug ARM firmware
gdb-multiarch hardware/stm32/build/car_12345/car_12345.bin

# Connect to OpenOCD (running in another terminal)
(gdb) target remote localhost:3333
(gdb) monitor reset halt
(gdb) break main
(gdb) continue
```

### Note about arm-none-eabi-gdb

**Important:** The Ubuntu/Debian `gcc-arm-none-eabi` package does **NOT** include `arm-none-eabi-gdb`. Use `gdb-multiarch` instead (installed in the development tools step).

If you downloaded the toolchain directly from ARM's website, it would include `arm-none-eabi-gdb`, which works the same way:

```bash
# Only if you installed from ARM's website:
arm-none-eabi-gdb hardware/stm32/build/car_12345/car_12345.bin
(gdb) target remote localhost:3333
```

### Using gdbgui (Web-based GUI)

The project includes `gdbgui` in requirements.txt for a web-based debugging interface:

```bash
# Start OpenOCD in one terminal
./tools/openocd.py degub stm32 STLINKSERIAL

# In another terminal with venv activated
gdbgui -g "gdb-multiarch -ex 'target remote localhost:3333'" --args hardware/stm32/build/car_12345/car_12345.bin

# Opens browser at http://127.0.0.1:5000
# Connect to: localhost:3333
```

## Troubleshooting

### Permission Denied on Serial Port

**Problem:** `Permission denied` when accessing `/dev/ttyACM0`

**Solutions:**

```bash
# Verify you're in dialout group
groups
# Should include "dialout"

# If not, add yourself
sudo usermod -a -G dialout $USER

# Log out and back in, or restart session
```

### OpenOCD Can't Find ST-Link

**Problem:** `Error: unable to find CMSIS-DAP device`

**Solutions:**

```bash
# Verify USB device is connected
lsusb | grep STM

# Check permissions
ls -l /dev/ttyACM0

# Add udev rules (see USB access section)
sudo nano /etc/udev/rules.d/99-openocd.rules

# Reload rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Unplug and replug the device
```

### ARM Toolchain Version Issues

**Problem:** Wrong ARM toolchain version or conflicts

**Solutions:**

```bash
# Check version
arm-none-eabi-gcc --version

# Ubuntu 20.04+ provides version 9.x or 10.x which works fine
# If you need a specific version, download from ARM:
# https://developer.arm.com/downloads/-/gnu-rm

# Remove old version (optional)
sudo apt remove gcc-arm-none-eabi

# Install manually (example)
wget https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2
tar -xjf gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2
sudo mv gcc-arm-none-eabi-10.3-2021.10 /opt/
echo 'export PATH="/opt/gcc-arm-none-eabi-10.3-2021.10/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### xterm Not Found or Display Issues

**Problem:** `xterm: command not found` or X11 display errors

**Solutions:**

```bash
# Install xterm
sudo apt install xterm

# For SSH connections, enable X11 forwarding
ssh -X user@remote-host

# Or set DISPLAY variable
export DISPLAY=:0
```
