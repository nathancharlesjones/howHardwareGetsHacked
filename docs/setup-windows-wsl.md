# Windows Development Setup (WSL2)

This guide will help you set up your Windows machine for embedded development using WSL2 (Windows Subsystem for Linux).

## Prerequisites

- Windows 10 version 2004+ (Build 19041+) or Windows 11
- Administrator access

## Step 1: Install WSL2

### Quick Install (Windows 11 or Windows 10 version 22H2+)

Open PowerShell or Command Prompt as Administrator and run:

```powershell
wsl --install -d Ubuntu-22.04
```

This will:
- Enable WSL2
- Install Ubuntu 22.04
- Set WSL2 as default version

Restart your computer when prompted.

### Manual Install (Older Windows 10 versions)

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

## Step 2: First-Time WSL Setup

1. Launch Ubuntu from Start Menu
2. Create a username and password (doesn't have to match Windows credentials)
3. Update packages:
   ```bash
   sudo apt update
   sudo apt upgrade -y
   ```

## Step 3: Install USB Device Drivers (Windows Side)

### ST-Link Drivers (for STM32 boards)

If you're using STM32 boards with ST-Link debuggers:

1. Download and install **STM32 ST-LINK Utility** from STMicroelectronics:
   - [https://www.st.com/en/development-tools/stsw-link004.html](https://www.st.com/en/development-tools/stsw-link004.html)
   - This installs the WinUSB drivers needed for ST-Link

**Alternative:** Install just the drivers without the utility:
   - Download from [https://www.st.com/en/development-tools/stsw-link009.html](https://www.st.com/en/development-tools/stsw-link009.html)

### TM4C123 Drivers (for TI Tiva C Launchpad)

If you're using TI TM4C123 boards (EK-TM4C123GXL):

1. Download and install **Stellaris ICDI Drivers**:
   - Included in [TI's Tiva C Series Software](https://www.ti.com/tool/SW-TM4C)
   - Or install standalone ICDI drivers from Device Manager → Update Driver → Browse for the Stellaris ICDI

**Note:** The TM4C123 appears as two devices: a debugger (ICDI) and a virtual COM port. Both need drivers.

## Step 4: Install USB/IP for USB Device Passthrough

### On Windows Side

1. Install usbipd-win (USB/IP daemon for Windows):
   ```powershell
   winget install --interactive --exact dorssel.usbipd-win
   ```

   **Alternative:** Download installer from [https://github.com/dorssel/usbipd-win/releases](https://github.com/dorssel/usbipd-win/releases)

2. Restart your terminal (to refresh PATH)

### On WSL Side

1. Install USB/IP tools and hardware utilities:
   ```bash
   sudo apt install linux-tools-generic hwdata
   sudo update-alternatives --install /usr/local/bin/usbip usbip /usr/lib/linux-tools/*-generic/usbip 20
   ```

## Step 5: Install Development Tools

### Inside WSL (Ubuntu)

```bash
# Build essentials
sudo apt install -y \
    build-essential \
    git \
    python3 \
    python3-pip \
    python3-venv

# ARM cross-compiler toolchain
sudo apt install -y gcc-arm-none-eabi

# OpenOCD (for programming/debugging STM32 and TM4C)
sudo apt install -y openocd

# X11 terminal emulator (required for x86 console simulator)
sudo apt install -y xterm

# Serial port tools (optional - useful for manual debugging)
sudo apt install -y \
    minicom \
    screen \
    picocom
```

**Note:** Python dependencies will be installed from `requirements.txt` into your virtual environment in a later step.

## Step 6: Configure USB Device Access

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

### Optional: GUI Tool for USB Attachment

For easier USB device management, use [wsl-usb-gui](https://gitlab.com/alelec/wsl-usb-gui):

1. Download from releases page
2. Run `wsl-usb-gui.exe` on Windows
3. Click devices to attach/detach from WSL

## Step 7: Set Up Serial Port Permissions

```bash
# Add your user to dialout group (for serial port access)
sudo usermod -a -G dialout $USER

# Log out and log back in, or run:
newgrp dialout
```

## Step 8: Clone and Set Up Your Project

```bash
# Navigate to your project (WSL can access Windows files)
cd /mnt/c/Users/YourName/Documents/your-project
# Or clone fresh in WSL filesystem (faster - recommended):
cd ~
git clone <your-repo-url>
cd your-project

# Create a Python virtual environment
python3 -m venv hhghVenv

# Activate the virtual environment (IMPORTANT!)
source hhghVenv/bin/activate

# Your prompt should now show (hhghVenv) prefix

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# This installs: SCons, pytest, pyserial, PyVirtualSerialPorts, gdbgui

# Build
scons platform=stm32 role=car id=1

# Flash device (with USB attached)
python tools/openocd.py --serial STLINKSERIAL --binary build/stm32/car_1/STM32.elf

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

## Step 9: IDE Setup (Optional but Recommended)

### Visual Studio Code with WSL Extension

1. Install [VS Code](https://code.visualstudio.com/) on Windows
2. Install "Remote - WSL" extension in VS Code
3. Open your project in WSL:
   ```bash
   # Inside WSL, in your project directory
   code .
   ```

This opens VS Code on Windows but runs all tools (git, python, compilers) inside WSL automatically.

## Common Issues & Troubleshooting

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
- Ensure USB device is attached to WSL (see Step 5)
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

## Resources

- [WSL Official Documentation](https://docs.microsoft.com/en-us/windows/wsl/)
- [usbipd-win GitHub](https://github.com/dorssel/usbipd-win)
- [WSL USB GUI](https://gitlab.com/alelec/wsl-usb-gui)
- [VS Code WSL Extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl)

## Python Virtual Environment Notes

### What's Included

The project's `requirements.txt` specifies these Python dependencies:
- **SCons** (build system)
- **pytest** (testing framework)
- **pyserial** (serial communication)
- **PyVirtualSerialPorts** (virtual serial ports for testing)
- **gdbgui** (web-based GDB debugger)

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
scons platform=stm32 role=car id=1  # Build firmware
pytest                              # Run tests
python tools/simulate.py            # Run simulator (optional)
```

**End of session:**
```bash
deactivate
```

**Pro tip:** Add to your `~/.bashrc` to auto-activate when entering project:
```bash
# Auto-activate venv when entering project directory
cd() {
    builtin cd "$@"
    if [ -f "hhghVenv/bin/activate" ]; then
        source hhghVenv/bin/activate
    fi
}
```

## Next Steps

Once setup is complete:
1. Review the main project README
2. Activate virtual environment: `source hhghVenv/bin/activate`
3. Build a test firmware: `scons platform=stm32 role=car id=1`
4. Flash to hardware with USB attached
5. Run test suite: `pytest`

Need help? Check the troubleshooting section or file an issue.
