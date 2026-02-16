# Removed Content from setup-mac.md

This file contains sections removed during the restructuring. Review to see if any content should be added back.

---

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

---

## Python Virtual Environment Notes

### What's Included

The project's `requirements.txt` specifies these Python dependencies:
- **SCons** (build system)
- **pytest** (testing framework)
- **pyserial** (serial communication)
- **PyVirtualSerialPorts** (virtual serial ports for testing)
- **gdbgui** (web-based GDB debugger)

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

---

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

---

## USB Device Workflow

Unlike Windows/WSL, macOS devices are automatically available - no manual attachment needed!

```bash
# Just plug in your device and it appears
ls /dev/cu.*

# Use directly
python tools/openocd.py --serial <serial-number> --binary build/car/car_1.elf
```

---

## Resources

- [Homebrew Documentation](https://docs.brew.sh/)
- [OpenOCD macOS Guide](https://github.com/openocd-org/openocd)
- [macOS Serial Port Programming](https://developer.apple.com/library/archive/documentation/DeviceDrivers/Conceptual/WorkingWSerial/WWSerial_SerialDevs/SerialDevices.html)
- [pyserial Documentation](https://pyserial.readthedocs.io/)

---

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
