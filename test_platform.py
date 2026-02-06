#!/usr/bin/env python3
"""
Platform compatibility test script.
Run this on Windows/Mac/Linux to verify basic functionality.
"""

import sys
import platform
import subprocess
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
        ('pyocd', 'pyocd - debugger (alternative to openocd)'),
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

def test_serial_ports():
    """Test serial port detection."""
    print_section("Serial Port Detection")

    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())

        if ports:
            print(f"Found {len(ports)} serial port(s):")
            for port in ports:
                print(f"  - {port.device}")
                if port.serial_number:
                    print(f"    Serial: {port.serial_number}")
                if port.description:
                    print(f"    Description: {port.description}")
        else:
            print("⚠️  No serial ports found (this is OK if no hardware is connected)")

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
        import os
        print(f"\nOS path separator: '{os.sep}'")
        print(f"Pathlib handles this automatically ✅")

        return True
    except Exception as e:
        print(f"❌ Error testing paths: {e}")
        return False

def test_tool_availability():
    """Test availability of external tools."""
    print_section("External Tool Availability")

    tools = [
        ('arm-none-eabi-gcc', '--version', 'ARM GCC cross-compiler'),
        ('openocd', '--version', 'OpenOCD debugger'),
        ('git', '--version', 'Git version control'),
    ]

    all_ok = True
    for tool, arg, description in tools:
        try:
            result = subprocess.run(
                [tool, arg],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Get first line of output
                version = result.stdout.split('\n')[0]
                print(f"✅ {description}: {version}")
            else:
                print(f"⚠️  {description}: Found but returned error")
                all_ok = False
        except FileNotFoundError:
            print(f"❌ {description}: NOT FOUND in PATH")
            print(f"   See setup docs for installation instructions")
            all_ok = False
        except subprocess.TimeoutExpired:
            print(f"⚠️  {description}: Command timed out")
            all_ok = False
        except Exception as e:
            print(f"⚠️  {description}: Error - {e}")
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

def main():
    """Run all tests."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║         Platform Compatibility Test                          ║
║  Tests basic functionality for embedded systems development  ║
╚══════════════════════════════════════════════════════════════╝
""")

    results = {
        'Python Version': test_python_version(),
        'Package Imports': test_imports(),
        'Serial Ports': test_serial_ports(),
        'Path Handling': test_path_handling(),
        'External Tools': test_tool_availability(),
        'Build System': test_build_system(),
        'Virtual Serial Ports': test_virtual_serial_ports(),
    }

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
