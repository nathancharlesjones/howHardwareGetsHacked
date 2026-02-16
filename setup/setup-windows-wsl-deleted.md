# Removed Content from setup-windows-wsl.md

This file contains sections removed during the restructuring. Review to see if any content should be added back.

---

## Optional: GUI Tool for USB Attachment

For easier USB device management, use [wsl-usb-gui](https://gitlab.com/alelec/wsl-usb-gui):

1. Download from releases page
2. Run `wsl-usb-gui.exe` on Windows
3. Click devices to attach/detach from WSL

---

## IDE Setup (Optional but Recommended)

### Visual Studio Code with WSL Extension

1. Install [VS Code](https://code.visualstudio.com/) on Windows
2. Install "Remote - WSL" extension in VS Code
3. Open your project in WSL:
   ```bash
   # Inside WSL, in your project directory
   code .
   ```

This opens VS Code on Windows but runs all tools (git, python, compilers) inside WSL automatically.

---

## Resources

- [WSL Official Documentation](https://docs.microsoft.com/en-us/windows/wsl/)
- [usbipd-win GitHub](https://github.com/dorssel/usbipd-win)
- [WSL USB GUI](https://gitlab.com/alelec/wsl-usb-gui)
- [VS Code WSL Extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl)

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
pytest testing/test.py              # Run tests
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
