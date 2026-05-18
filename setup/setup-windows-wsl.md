# Windows Development Setup (WSL2)

This guide will help you set up your Windows machine for embedded development using WSL2 (Windows Subsystem for Linux).

## Prerequisites

- Windows 10 version 2004+ (Build 19041+) or Windows 11
- Administrator access
- Internet connection

## Installing Environment Tools

### Install WSL2

#### Quick Install (Windows 11 or Windows 10 version 22H2+)

Open PowerShell or Command Prompt as Administrator and run:

```powershell
wsl --install -d Ubuntu-22.04
```

This will:
- Enable WSL2
- Install Ubuntu 22.04
- Set WSL2 as default version

Restart your computer when prompted.

#### Manual Install (Older Windows 10 versions)

If the quick install doesn't work:

1. Enable WSL:
   ```powershell
   dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
   ```

2. Enable Virtual Machine Platform:
   ```powershell
   dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
   ```

3. Restart your computer

4. Download and install the [WSL2 Linux kernel update package](https://aka.ms/wsl2kernel)

5. Set WSL2 as default:
   ```powershell
   wsl --set-default-version 2
   ```

6. Install Ubuntu from Microsoft Store (search "Ubuntu 22.04 LTS")

### First-Time WSL Setup

1. Launch Ubuntu from Start Menu
2. Create a username and password (doesn't have to match Windows credentials)
3. Update packages:
   ```bash
   sudo apt update
   sudo apt upgrade -y
   ```

## Installing Development Tools

Inside WSL (Ubuntu):

```bash
# Build essentials
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

## Setting Up USB Access to Devices

### Install USB Device Drivers (Windows Side)

#### ST-Link Drivers (for STM32 boards)

If you're using STM32 boards with ST-Link debuggers:

1. Download and install **STM32 ST-LINK Utility** from STMicroelectronics:
   - [https://www.st.com/en/development-tools/stsw-link004.html](https://www.st.com/en/development-tools/stsw-link004.html)
   - This installs the WinUSB drivers needed for ST-Link

**Alternative:** Install just the drivers without the utility:
   - Download from [https://www.st.com/en/development-tools/stsw-link009.html](https://www.st.com/en/development-tools/stsw-link009.html)

#### TM4C123 Drivers (for TI Tiva C Launchpad)

If you're using TI TM4C123 boards (EK-TM4C123GXL):

1. Download and install **Stellaris ICDI Drivers**:
   - Included in [TI's Tiva C Series Software](https://www.ti.com/tool/SW-TM4C)
   - Or install standalone ICDI drivers from Device Manager → Update Driver → Browse for the Stellaris ICDI

**Note:** The TM4C123 appears as two devices: a debugger (ICDI) and a virtual COM port. Both need drivers.

### Install USB/IP for USB Device Passthrough

#### On Windows Side

1. Install usbipd-win (USB/IP daemon for Windows):
   ```powershell
   winget install --interactive --exact dorssel.usbipd-win
   ```

   **Alternative:** Download installer from [https://github.com/dorssel/usbipd-win/releases](https://github.com/dorssel/usbipd-win/releases)

2. Restart your terminal (to refresh PATH)

#### On WSL Side

1. Install USB/IP tools and hardware utilities:
   ```bash
   sudo apt install linux-tools-generic hwdata
   sudo update-alternatives --install /usr/local/bin/usbip usbip /usr/lib/linux-tools/*-generic/usbip 20
   ```

### Configure Serial Port Permissions

```bash
# Add your user to dialout group (for serial port access)
sudo usermod -a -G dialout $USER

# Log out and log back in, or run:
newgrp dialout
```

### Attach USB Devices to WSL

Each time you connect a USB device (ST-Link, serial adapter, etc.):

#### On Windows (PowerShell as Administrator):

1. List USB devices:
   ```powershell
   usbipd list
   ```

   Example output:
   ```
   BUSID  VID:PID    DEVICE                                  STATE
   1-4    0483:374b  STMicroelectronics ST-LINK/V2.1         Not attached
   1-5    2341:0043  USB Serial Device (COM3)                Not attached
   ```

2. Attach device to WSL (replace `1-4` with your BUSID):
   ```powershell
   usbipd bind --busid 1-4
   usbipd attach --wsl --busid 1-4
   ```

   **Note:** You need to bind only once per device, but attach every time you reconnect it.

#### Inside WSL:

3. Verify device is visible:
   ```bash
   lsusb
   # Should show your ST-Link or serial device

   ls /dev/ttyACM*
   # Should show serial ports like /dev/ttyACM0
   ```

## Cloning or Downloading the Project

```bash
# Navigate to your project (WSL can access Windows files)
cd /mnt/c/Users/YourName/Documents/your-project
# Or clone fresh in WSL filesystem (faster - recommended):
cd ~
git clone https://github.com/nathancharlesjones/howHardwareGetsHacked
cd your-project
```

**Note:** Keep your project files in WSL filesystem (`~/projects/`) not Windows filesystem (`/mnt/c/`). WSL filesystem is much faster.

## Setting Up the Virtual Environment

**Python version:** Ubuntu 22.04 (installed above) ships Python 3.10, which is compatible with all project dependencies. If you used a different Ubuntu version and `python3 --version` shows 3.12 or newer, some dependencies (`gdbgui` → `gevent` → `greenlet`) may fail to build. In that case, install Python 3.11 via the deadsnakes PPA:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

```bash
# Create a Python virtual environment
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
./tools/openocd.py debug stm32 STLINKSERIAL

# In another terminal with venv activated
gdbgui -g "gdb-multiarch -ex 'target remote localhost:3333'" --args hardware/stm32/build/car_12345/car_12345.bin

# Opens browser at http://127.0.0.1:5000
# Connect to: localhost:3333
```

## Troubleshooting

### USB Device Not Appearing in WSL

**Problem:** `lsusb` doesn't show device after `usbipd attach`

**Solutions:**
- Verify device is attached: `usbipd list` (should show "Attached - WSL")
- Restart WSL: `wsl --shutdown` (in PowerShell), then relaunch Ubuntu
- Check WSL version: `wsl -l -v` (must be version 2)
- Try detaching and reattaching:
  ```powershell
  usbipd detach --busid 1-4
  usbipd attach --wsl --busid 1-4
  ```

### Permission Denied on Serial Port

**Problem:** `Permission denied` when accessing `/dev/ttyACM0`

**Solutions:**
```bash
# Verify you're in dialout group
groups
# Should include "dialout"

# If not, add yourself and restart WSL
sudo usermod -a -G dialout $USER
wsl --shutdown  # Run in PowerShell
# Then relaunch Ubuntu
```

### OpenOCD Can't Find ST-Link

**Problem:** `Error: unable to find CMSIS-DAP device`

**Solutions:**
- Ensure USB device is attached to WSL (see USB access section)
- Check device visibility: `lsusb | grep STM`
- Add udev rules:
  ```bash
  sudo nano /etc/udev/rules.d/99-openocd.rules
  ```
  Add:
  ```
  SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="374b", MODE="0666"
  ```
  Reload:
  ```bash
  sudo udevadm control --reload-rules
  sudo udevadm trigger
  ```

### Slow File Access

**Problem:** Git operations are slow

**Solution:** Keep your project files in WSL filesystem (`~/projects/`) not Windows filesystem (`/mnt/c/`). WSL filesystem is much faster.

### Windows Path Issues

**Problem:** Commands not found

**Solution:** WSL and Windows PATH are separate. Install tools in WSL, not Windows.

## Quick Reference

### USB Device Workflow

```powershell
# Windows (PowerShell as Admin) - every time you plug in device
usbipd list
usbipd attach --wsl --busid 1-4

# When done (optional - auto-detaches on disconnect)
usbipd detach --busid 1-4
```

### Access WSL Files from Windows

- Open File Explorer
- Type in address bar: `\\wsl$\Ubuntu-22.04\home\<username>`
- Or just: `\\wsl$\`

### Access Windows Files from WSL

```bash
cd /mnt/c/Users/YourName/Documents/
```
