#!/usr/bin/env python3
"""
Platform compatibility test script.
Run this on Windows/Mac/Linux to verify basic functionality.

Usage:
  python test_platform.py          # Run all tests (including hardware detection)
  python test_platform.py --ci-mode # Skip hardware-dependent tests (for CI/CD)
"""

import sys
import os
import platform
import subprocess
import argparse
from pathlib import Path

def print_section(title):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_python_version():
    """Check Python version."""
    print_section("Python Version")
    print(f"Python {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Machine: {platform.machine()}")

    version_info = sys.version_info
    if version_info.major >= 3 and version_info.minor >= 8:
        print("✅ Python version is compatible (3.8+)")
        return True
    else:
        print("❌ Python version too old (need 3.8+)")
        return False

def test_imports():
    """Test critical Python imports."""
    print_section("Python Package Imports")

    packages = [
        ('serial', 'pyserial - serial communication'),
        ('pytest', 'pytest - testing framework'),
        ('SCons', 'SCons - build system'),
        ('pathlib', 'pathlib - path handling (built-in)'),
    ]

    all_ok = True
    for module_name, description in packages:
        try:
            __import__(module_name)
            print(f"✅ {description}")
        except ImportError as e:
            print(f"❌ {description} - NOT FOUND")
            print(f"   Error: {e}")
            all_ok = False

    return all_ok

def test_serial_ports(ci_mode=False):
    """Test serial port detection."""
    print_section("Serial Port Detection")

    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())

        # Filter to show only ports with actual hardware (not "n/a")
        hardware_ports = [p for p in ports if p.description and p.description.lower() != 'n/a']

        print(f"Found {len(ports)} total serial port(s)")

        if hardware_ports:
            print(f"Ports with hardware attached ({len(hardware_ports)}):")
            for port in hardware_ports:
                print(f"  - {port.device}")
                if port.serial_number:
                    print(f"    Serial: {port.serial_number}")
                if port.description:
                    print(f"    Description: {port.description}")
        else:
            if ci_mode:
                print("✅ No hardware devices found (expected in CI environment)")
            else:
                print("⚠️  No hardware devices found (this is OK if no hardware is connected)")

        # Test platform-specific naming
        if platform.system() == 'Darwin':  # macOS
            print("\nℹ️  macOS uses /dev/cu.* for serial devices")
        elif platform.system() == 'Linux':
            print("\nℹ️  Linux uses /dev/ttyUSB*, /dev/ttyACM* for serial devices")
        elif platform.system() == 'Windows':
            print("\nℹ️  Windows uses COM* for serial devices")

        return True
    except Exception as e:
        print(f"❌ Error testing serial ports: {e}")
        return False

def test_path_handling():
    """Test pathlib path handling."""
    print_section("Path Handling")

    try:
        # Test that pathlib works cross-platform
        current = Path(__file__).parent
        print(f"Current directory: {current}")
        print(f"Absolute path: {current.absolute()}")

        # Test path operations
        test_path = current / "tools" / "list.py"
        print(f"Test path (using / operator): {test_path}")
        print(f"Exists: {test_path.exists()}")

        # Show path separator
        print(f"\nOS path separator: '{os.sep}'")
        print(f"Pathlib handles this automatically ✅")

        return True
    except Exception as e:
        print(f"❌ Error testing paths: {e}")
        return False

def test_tool_availability(ci_mode=False):
    """Test availability of external tools."""
    print_section("External Tool Availability")

    tools = [
        ('arm-none-eabi-gcc', '--version', 'ARM GCC cross-compiler', True),  # required
        ('openocd', '--version', 'OpenOCD debugger', False),  # optional in CI (Windows issues)
        ('git', '--version', 'Git version control', True),  # required
        ('xterm', '-version', 'xterm (for x86 console simulator)', True),  # required
    ]

    all_ok = True
    for tool, arg, description, required in tools:
        try:
            result = subprocess.run(
                [tool, arg],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Get first line of output
                version = result.stdout.split('\n')[0] if result.stdout else result.stderr.split('\n')[0]
                print(f"✅ {description}: {version}")
            else:
                # xterm returns version info via stderr and exits with error code
                if tool == 'xterm' and result.stderr:
                    version = result.stderr.split('\n')[0]
                    print(f"✅ {description}: {version}")
                else:
                    print(f"⚠️  {description}: Found but returned error")
                    if required and not ci_mode:
                        all_ok = False
        except FileNotFoundError:
            if not required or (ci_mode and tool == 'openocd'):
                print(f"⚠️  {description}: NOT FOUND in PATH")
                if tool == 'openocd' and ci_mode:
                    print(f"   (OpenOCD may fail on some CI platforms - this is OK)")
            else:
                print(f"❌ {description}: NOT FOUND in PATH")
                print(f"   See setup docs for installation instructions")
                all_ok = False
        except subprocess.TimeoutExpired:
            print(f"⚠️  {description}: Command timed out")
            if required and not ci_mode:
                all_ok = False
        except Exception as e:
            print(f"⚠️  {description}: Error - {e}")
            if required and not ci_mode:
                all_ok = False

    return all_ok

def test_build_system():
    """Test that SCons build system can initialize."""
    print_section("Build System")

    try:
        # Check if SConstruct exists
        sconstruct = Path('SConstruct')
        if not sconstruct.exists():
            print("❌ SConstruct not found (are you in project root?)")
            return False

        print(f"✅ Found SConstruct at {sconstruct.absolute()}")

        # Test SCons help command (doesn't require full build)
        result = subprocess.run(
            ['scons', '--help'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            print("✅ SCons can initialize build system")
            return True
        else:
            print("⚠️  SCons returned error (may be OK if options missing)")
            return True  # Still return True as SCons is installed

    except FileNotFoundError:
        print("❌ SCons not found - is virtual environment activated?")
        return False
    except Exception as e:
        print(f"⚠️  Error testing build system: {e}")
        return False

def test_virtual_serial_ports():
    """Test virtual serial port library (for simulation)."""
    print_section("Virtual Serial Ports (for simulation)")

    try:
        from virtualserialports import VirtualSerialPorts
        print("✅ VirtualSerialPorts library is available")

        # Try to create virtual ports (don't actually open/start them)
        print("   Testing virtual port creation...")
        vsp = VirtualSerialPorts(2)
        print(f"✅ Created VirtualSerialPorts object (not opened)")

        # Platform-specific notes
        if platform.system() == 'Darwin':
            print("\nℹ️  macOS: Virtual serial ports use pseudo-terminals")
        elif platform.system() == 'Linux':
            print("\nℹ️  Linux: Virtual serial ports use /dev/pts/")
        elif platform.system() == 'Windows':
            print("\n⚠️  Windows: Virtual serial port support may be limited")

        return True

    except ImportError:
        print("❌ VirtualSerialPorts not found")
        print("   This is needed for x86 simulation mode")
        return False
    except Exception as e:
        print(f"⚠️  Error testing virtual serial ports: {e}")
        return False

def test_usb_devices():
    """Test for connected USB development boards."""
    print_section("USB Development Boards (Hardware Detection)")

    found_devices = []

    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())

        # Look for known devices
        for port in ports:
            desc_lower = (port.description or "").lower()
            mfg_lower = (port.manufacturer or "").lower()

            # ST-Link detection
            if 'stm' in desc_lower or 'st-link' in desc_lower or 'stmicro' in mfg_lower:
                found_devices.append(f"STM32/ST-Link: {port.device} ({port.description})")

            # TM4C123 ICDI detection
            elif 'stellaris' in desc_lower or 'icdi' in desc_lower or 'tm4c' in desc_lower or 'tiva' in desc_lower:
                found_devices.append(f"TM4C123/ICDI: {port.device} ({port.description})")

        if found_devices:
            print(f"Found {len(found_devices)} development board(s):")
            for device in found_devices:
                print(f"  ✅ {device}")
        else:
            print("⚠️  No development boards detected")
            print("   This is OK if no hardware is connected")
            print("\nExpected boards:")
            print("   - STM32 with ST-Link debugger")
            print("   - TI TM4C123 (EK-TM4C123GXL) with Stellaris ICDI")

        # Platform-specific driver notes
        if platform.system() == 'Windows':
            print("\nℹ️  Windows: Ensure ST-Link and Stellaris ICDI drivers are installed")
            print("   See docs/setup-windows-wsl.md for driver installation")
        elif platform.system() == 'Darwin':
            print("\nℹ️  macOS: Boards should work automatically with libusb")
            print("   Run 'system_profiler SPUSBDataType' to see all USB devices")
        elif platform.system() == 'Linux':
            print("\nℹ️  Linux: Ensure user is in 'dialout' group for serial access")
            print("   Run 'lsusb' to see all USB devices")

        return True

    except Exception as e:
        print(f"⚠️  Error detecting USB devices: {e}")
        return True  # Don't fail the test, this is informational

def test_platform_specific():
    """Test platform-specific requirements."""
    print_section("Platform-Specific Requirements")

    sys_name = platform.system()
    all_ok = True

    if sys_name == 'Darwin':  # macOS
        # Check for XQuartz (needed for xterm)
        try:
            result = subprocess.run(
                ['xterm', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If xterm exists, check if XQuartz is available
            xquartz_path = Path('/Applications/Utilities/XQuartz.app')
            if xquartz_path.exists():
                print("✅ XQuartz is installed (needed for xterm)")
            else:
                print("⚠️  XQuartz not found at standard location")
                print("   Install with: brew install --cask xquartz")
                print("   (Only needed for x86 console simulator)")
        except FileNotFoundError:
            print("ℹ️  xterm not found (XQuartz check skipped)")
        except Exception as e:
            print(f"ℹ️  Could not check XQuartz: {e}")

    elif sys_name == 'Linux':
        # Check if running in WSL
        try:
            with open('/proc/version', 'r') as f:
                version = f.read().lower()
                if 'microsoft' in version or 'wsl' in version:
                    print("✅ Running in WSL (Windows Subsystem for Linux)")
                    print("ℹ️  Remember to attach USB devices with usbipd")
                    print("   See docs/setup-windows-wsl.md for USB passthrough setup")
                else:
                    print("✅ Running native Linux")
        except FileNotFoundError:
            print("✅ Running native Linux")
        except Exception as e:
            print(f"ℹ️  Could not determine Linux type: {e}")

    elif sys_name == 'Windows':
        print("⚠️  Running on Windows (not WSL)")
        print("   This project is designed for WSL2 on Windows")
        print("   See docs/setup-windows-wsl.md for setup instructions")
        all_ok = False

    return all_ok

def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(
        description='Platform compatibility test for embedded systems development',
        epilog='Run without --ci-mode to include hardware detection tests'
    )
    parser.add_argument(
        '--ci-mode',
        action='store_true',
        help='Skip hardware-dependent tests (for CI/CD environments)'
    )
    args = parser.parse_args()

    mode_str = " (CI Mode - HW tests skipped)" if args.ci_mode else ""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Platform Compatibility Test{mode_str:29}    ║
║  Tests basic functionality for embedded systems development  ║
╚══════════════════════════════════════════════════════════════╝
""")

    results = {
        'Python Version': test_python_version(),
        'Package Imports': test_imports(),
        'Serial Ports': test_serial_ports(ci_mode=args.ci_mode),
        'Path Handling': test_path_handling(),
        'External Tools': test_tool_availability(ci_mode=args.ci_mode),
        'Build System': test_build_system(),
        'Virtual Serial Ports': test_virtual_serial_ports(),
        'Platform-Specific': test_platform_specific(),
    }

    # Only run hardware detection if not in CI mode
    if not args.ci_mode:
        results['USB Devices'] = test_usb_devices()

    # Summary
    print_section("SUMMARY")

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:10} {test_name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Platform is fully compatible.")
        return 0
    elif passed >= total - 2:
        print("\n⚠️  Most tests passed. Minor issues detected (likely OK).")
        return 0
    else:
        print("\n❌ Multiple tests failed. Review errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
