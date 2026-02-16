# Removed Content from setup-linux.md

This file contains sections removed during the restructuring. Review to see if any content should be added back.

---

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

---

## IDE Setup (Optional)

### Visual Studio Code

1. Install VS Code:
   ```bash
   # Via snap
   sudo snap install code --classic

   # Or download .deb from https://code.visualstudio.com/
   ```

2. Install extensions:
   - Python extension (ms-python.python)
   - C/C++ extension (ms-vscode.cpptools)

3. Open project:
   ```bash
   code ~/your-project
   ```

4. Select Python interpreter: Ctrl+Shift+P → "Python: Select Interpreter" → Choose `./hhghVenv/bin/python`

### CLion / PyCharm

1. Open project in IDE
2. Configure Python interpreter:
   - **Settings** → **Project** → **Python Interpreter**
   - Click gear icon → **Add** → **Existing Environment**
   - Select `./hhghVenv/bin/python`

---

## Platform Comparison

For reference, here are the main differences between Linux and other platforms:

| Feature | Linux | macOS | Windows (WSL) |
|---------|-------|-------|---------------|
| **Package Manager** | apt, dnf, pacman | Homebrew | apt (in WSL) |
| **Serial Devices** | `/dev/ttyUSB*`, `/dev/ttyACM*` | `/dev/cu.usbmodem*` | `/dev/ttyACM*` |
| **USB Auto-detection** | Usually works | Usually works | Requires usbipd |
| **Development Experience** | Native, fastest | Native | Good via WSL2 |
| **GDB Support** | gdb-multiarch | arm-none-eabi-gdb | gdb-multiarch |

---

## Resources

- [OpenOCD Documentation](http://openocd.org/documentation/)
- [ARM GNU Toolchain Downloads](https://developer.arm.com/downloads/-/gnu-rm)
- [pyserial Documentation](https://pyserial.readthedocs.io/)
- [GDB Documentation](https://sourceware.org/gdb/documentation/)
- [Linux USB Device Permissions](https://www.freedesktop.org/software/systemd/man/udev.html)
