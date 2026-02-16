# macOS Development Setup

This guide will help you set up your Mac for embedded development. macOS is Unix-based (POSIX-compliant), so most tools work natively without modifications.

## Prerequisites

- macOS 10.15 (Catalina) or newer recommended
- Administrator access
- Internet connection

## Installing Environment Tools

### Install Xcode Command Line Tools

Open Terminal and run:

```bash
xcode-select --install
```

Click "Install" in the dialog that appears. This provides essential build tools (git, make, clang, etc.).

### Install Homebrew

Homebrew is the macOS package manager, similar to apt on Linux.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen instructions. After installation, you may need to add Homebrew to your PATH:

```bash
# For Apple Silicon (M1/M2/M3)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
eval "$(/opt/homebrew/bin/brew shellenv)"

# For Intel Macs
echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zshrc
eval "$(/usr/local/bin/brew shellenv)"
```

Restart your terminal or run `source ~/.zshrc`.

## Installing Development Tools

```bash
# ARM cross-compiler toolchain
brew install --cask gcc-arm-embedded

# Alternative if cask doesn't work:
brew tap osx-cross/arm
brew install arm-gcc-bin

# OpenOCD (for programming/debugging STM32 and TM4C)
brew install openocd

# Python (if not already installed)
brew install python@3.11

# Git (usually already installed via Xcode CLI tools)
brew install git

# X11 support and terminal emulator (required for x86 console simulator)
brew install --cask xquartz
brew install xterm

# Serial port tools (optional - useful for manual debugging)
brew install minicom
```

**Note:** Python project dependencies will be installed from `requirements.txt` into your virtual environment in a later step.

## Setting Up USB Access to Devices

### Grant Terminal/IDE USB Permissions

1. Open **System Preferences** → **Security & Privacy** → **Privacy** tab
2. Select **Full Disk Access** (or **Files and Folders** on older versions)
3. Click the lock icon to make changes
4. Add **Terminal.app** (or your IDE like VSCode, PyCharm)

### Install USB Drivers

#### ST-Link (for STM32 boards)

Modern macOS usually recognizes ST-Link automatically via built-in drivers, but you may need libusb:

```bash
# Check if ST-Link is detected
system_profiler SPUSBDataType | grep -A 10 STM

# Install libusb for USB device support
brew install libusb
```

#### TM4C123 (for TI Tiva C Launchpad)

The TI TM4C123 (EK-TM4C123GXL) should work automatically on macOS:

```bash
# Check if TM4C123 ICDI is detected
system_profiler SPUSBDataType | grep -i "stellaris\|icdi\|tm4c"
```

If not detected, ensure libusb is installed (see above). The TM4C123 appears as two devices:
- **Stellaris ICDI** - debugger interface
- **Serial port** - appears as `/dev/cu.usbmodem*`

**Note:** macOS uses `/dev/cu.*` for serial devices (not `/dev/tty*` like Linux).

## Cloning or Downloading the Project

```bash
# Navigate to where you want the project
cd ~/Documents  # or wherever you prefer

# Clone the repository
git clone https://github.com/nathancharlesjones/howHardwareGetsHacked
cd your-project
```

## Setting Up the Virtual Environment

```bash
# Create a Python virtual environment
python3 -m venv hhghVenv

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

### Using arm-none-eabi-gdb

The ARM GDB debugger **should be included** with the Homebrew `gcc-arm-embedded` cask. Verify it's installed:

```bash
which arm-none-eabi-gdb
# Should show: /opt/homebrew/bin/arm-none-eabi-gdb (Apple Silicon)
#          or: /usr/local/bin/arm-none-eabi-gdb (Intel)
```

If not found, you can install the full toolchain from [ARM's website](https://developer.arm.com/downloads/-/gnu-rm).

Usage:

```bash
# Debug ARM firmware
arm-none-eabi-gdb hardware/stm32/build/car_12345/car_12345.bin

# Connect to OpenOCD (running in another terminal)
(gdb) target remote localhost:3333
(gdb) monitor reset halt
(gdb) break main
(gdb) continue
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

### Permission Denied on Serial Port

**Problem:** `Permission denied` when accessing `/dev/cu.usbmodem*`

**Solutions:**
1. Add your user to `_dialout` group (usually automatic on macOS)
2. Check System Preferences → Security & Privacy → Full Disk Access
3. Give Terminal (or your IDE) permission

### OpenOCD Can't Find ST-Link

**Problem:** `Error: unable to find CMSIS-DAP device`

**Solutions:**
```bash
# Verify USB device is connected
system_profiler SPUSBDataType | grep -i stm

# Check OpenOCD permissions
brew reinstall openocd

# Try with sudo (not ideal, but for testing)
sudo openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "init; exit"
```

### ARM Toolchain Not Found

**Problem:** `arm-none-eabi-gcc: command not found`

**Solutions:**
```bash
# Verify installation
which arm-none-eabi-gcc

# If not found, check Homebrew cask
brew list --cask | grep arm

# Reinstall if needed
brew reinstall --cask gcc-arm-embedded

# Add to PATH manually if needed (Apple Silicon)
echo 'export PATH="/opt/homebrew/opt/gcc-arm-embedded/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# For Intel Macs
echo 'export PATH="/usr/local/opt/gcc-arm-embedded/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Rosetta Issues (Apple Silicon M1/M2/M3)

**Problem:** Some tools don't run on Apple Silicon

**Solutions:**
```bash
# Install Rosetta 2 for x86_64 compatibility
softwareupdate --install-rosetta --agree-to-license

# Run specific tools under Rosetta
arch -x86_64 arm-none-eabi-gcc --version
```

Most modern tools are now compiled for ARM64, but older versions may need Rosetta.

### Serial Port Device Not Found

**Problem:** Can't find `/dev/ttyACM0` (Linux device name)

**Solution:** macOS uses different naming:
- Linux: `/dev/ttyUSB0`, `/dev/ttyACM0`
- macOS: `/dev/cu.usbmodem*`, `/dev/cu.usbserial*`

Your Python code using `pyserial` should handle this automatically.

### Check Serial Ports

Plug in your device and check available serial ports:

```bash
ls /dev/cu.*
# Should show something like:
# /dev/cu.usbmodem14101
# /dev/cu.usbserial-A12345
```

### Test OpenOCD Connection

```bash
openocd --version
# Should show OpenOCD version info

# Test ST-Link detection
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "init; exit"
# Should detect your board
```
