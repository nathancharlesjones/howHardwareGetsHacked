# macOS Development Setup

This guide will help you set up your Mac for embedded development. macOS is Unix-based (POSIX-compliant), so most tools work natively without modifications.

## Prerequisites

- macOS 10.15 (Catalina) or newer recommended
- Administrator access
- Xcode Command Line Tools

## Step 1: Install Xcode Command Line Tools

Open Terminal and run:

```bash
xcode-select --install
```

Click "Install" in the dialog that appears. This provides essential build tools (git, make, clang, etc.).

## Step 2: Install Homebrew

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

## Step 3: Install Development Tools

```bash
# ARM cross-compiler toolchain
brew install --cask gcc-arm-embedded

# Alternative if cask doesn't work:
brew tap osx-cross/arm
brew install arm-gcc-bin

# OpenOCD (for programming/debugging STM32)
# Note: Project includes pyocd in venv, but openocd is useful as alternative
brew install openocd

# Python (if not already installed)
brew install python@3.11

# Git (usually already installed via Xcode CLI tools)
brew install git

# Serial port tools (optional - useful for manual debugging)
brew install minicom
```

**Note:** Python dependencies (SCons, pytest, pyserial, pyocd, etc.) are already provided in the project's virtual environment (`hhghVenv`). No need to install them separately!

## Step 4: Configure USB/Serial Port Access

macOS requires permission to access USB devices.

### Grant Terminal/IDE USB Permissions

1. Open **System Preferences** → **Security & Privacy** → **Privacy** tab
2. Select **Full Disk Access** (or **Files and Folders** on older versions)
3. Click the lock icon to make changes
4. Add **Terminal.app** (or your IDE like VSCode, PyCharm)

### Install USB Driver for ST-Link (if needed)

Modern macOS usually recognizes ST-Link automatically, but if not:

```bash
# Check if ST-Link is detected
system_profiler SPUSBDataType | grep -A 10 STM

# If not detected, install driver
brew install libusb
```

## Step 5: Clone and Set Up Your Project

```bash
# Navigate to where you want the project
cd ~/Documents  # or wherever you prefer

# Clone the repository
git clone <your-repo-url>
cd your-project

# Activate the virtual environment (IMPORTANT!)
source hhghVenv/bin/activate

# Your prompt should now show (hhghVenv) prefix
# This gives you access to SCons, pytest, pyserial, pyocd, etc.

# Build
scons car_id=1

# Flash device (with USB attached)
python tools/openocd.py --serial STLINKSERIAL --binary build/car/car_1.elf

# Run tests
pytest
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

## Step 6: Verify USB Device Access

### Check Serial Ports

Plug in your device and check available serial ports:

```bash
ls /dev/cu.*
# Should show something like:
# /dev/cu.usbmodem14101
# /dev/cu.usbserial-A12345
```

**Note:** macOS uses `/dev/cu.*` for serial devices (not `/dev/tty*` like Linux). The Python code should handle this automatically via pyserial.

### Check ST-Link Debugger

```bash
# With ST-Link connected
system_profiler SPUSBDataType | grep -i stm

# Should show something like:
# STMicroelectronics ST-LINK/V2.1:
#   Product ID: 0x374b
#   Vendor ID: 0x0483  (STMicroelectronics)
```

### Test OpenOCD

```bash
openocd --version
# Should show OpenOCD version info

# Test ST-Link detection
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "init; exit"
# Should detect your board
```

## Common Issues & Troubleshooting

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

Your Python code using `pyserial` should handle this automatically, but manual commands need the macOS device name.

## Platform-Specific Notes

### Serial Port Naming

```python
# Works cross-platform with pyserial
import serial
ser = serial.Serial('/dev/cu.usbmodem14101', 115200)  # macOS
# pyserial can also auto-detect ports
```

### File Paths

macOS uses forward slashes like Linux:
```bash
/Users/username/Documents/project  # macOS
/home/username/Documents/project   # Linux
```

Your project uses `pathlib`, which handles this automatically.

### Case Sensitivity

By default, macOS filesystem is case-insensitive (but case-preserving):
- `MyFile.txt` and `myfile.txt` refer to the same file
- This can cause issues with git if you rename files by case only

To check your filesystem:
```bash
diskutil info / | grep "Case"
```

Consider using case-sensitive APFS for development (advanced users only).

## Python Virtual Environment Notes

### What's Included

The project's `hhghVenv` virtual environment includes:
- **SCons** (build system)
- **pytest** (testing framework)
- **pyserial** (serial communication)
- **pyocd** (Python-based debugger, alternative to OpenOCD)
- **pylink-square** (J-Link support)
- **gdbgui** (web-based GDB debugger)
- And many other embedded development tools

### Recommended Additions (Optional)

Consider adding these tools to the venv for improved development experience:

```bash
source hhghVenv/bin/activate

# Code formatting
pip install black isort

# Linting
pip install ruff  # Modern, fast linter (recommended)
# Or traditional linters:
pip install pylint flake8

# Type checking
pip install mypy

# Better Python REPL
pip install ipython

# If you need HTTP requests
pip install requests
```

### Session Workflow

**Start of each work session:**
```bash
cd ~/your-project
source hhghVenv/bin/activate
```

**During work:**
```bash
scons car_id=1          # Build
pytest                  # Run tests
python tools/simulate.py  # Run simulator
```

**End of session:**
```bash
deactivate
```

**Pro tip:** Add to your `~/.zshrc` to auto-activate when entering project:
```bash
# Auto-activate venv when entering project directory
cd() {
    builtin cd "$@"
    if [ -f "hhghVenv/bin/activate" ]; then
        source hhghVenv/bin/activate
    fi
}
```

## IDE Setup (Optional)

### Visual Studio Code

1. Install [VS Code](https://code.visualstudio.com/)
2. Install Python extension
3. Open project: `code ~/your-project`
4. Select Python interpreter: Cmd+Shift+P → "Python: Select Interpreter" → Choose `./hhghVenv/bin/python`

VS Code will automatically use the venv for all Python operations.

### PyCharm

1. Open project in PyCharm
2. Go to **Preferences** → **Project** → **Python Interpreter**
3. Click gear icon → **Add** → **Existing Environment**
4. Select `./hhghVenv/bin/python`

## Quick Reference

### Common Commands

```bash
# Activate venv (always first!)
source hhghVenv/bin/activate

# Build for specific car
scons car_id=1

# Build for specific fob
scons fob_id=1

# Clean build
scons -c

# List serial devices
ls /dev/cu.*

# Monitor serial output
screen /dev/cu.usbmodem14101 115200
# Press Ctrl+A then K to exit screen

# Alternative: use minicom
minicom -D /dev/cu.usbmodem14101 -b 115200
```

### USB Device Workflow

Unlike Windows/WSL, macOS devices are automatically available - no manual attachment needed!

```bash
# Just plug in your device and it appears
ls /dev/cu.*

# Use directly
python tools/openocd.py --serial <serial-number> --binary build/car/car_1.elf
```

## Resources

- [Homebrew Documentation](https://docs.brew.sh/)
- [OpenOCD macOS Guide](https://github.com/openocd-org/openocd)
- [macOS Serial Port Programming](https://developer.apple.com/library/archive/documentation/DeviceDrivers/Conceptual/WorkingWSerial/WWSerial_SerialDevs/SerialDevices.html)
- [pyserial Documentation](https://pyserial.readthedocs.io/)

## Next Steps

Once setup is complete:
1. Review the main project README
2. Activate virtual environment: `source hhghVenv/bin/activate`
3. Build a test firmware: `scons car_id=1`
4. Flash to hardware
5. Run test suite: `pytest`

Need help? Check the troubleshooting section or file an issue.

## Differences from Linux

For reference, here are the main differences between macOS and Linux development:

| Feature | Linux | macOS |
|---------|-------|-------|
| **Package Manager** | apt, yum | Homebrew |
| **Serial Devices** | `/dev/ttyUSB*`, `/dev/ttyACM*` | `/dev/cu.usbmodem*`, `/dev/cu.usbserial*` |
| **USB Auto-detection** | Usually works | Usually works (better than Windows) |
| **POSIX Compliance** | Full | Full (certified Unix) |
| **Shell** | bash (or zsh) | zsh (default since Catalina) |
| **Case Sensitivity** | Yes (by default) | No (by default, but configurable) |

Most of your Python code should work identically on both platforms thanks to `pathlib` and `pyserial`.
