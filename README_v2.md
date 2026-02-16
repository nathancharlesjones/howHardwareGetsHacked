# eCTF Hardware Hacking Demo

> **Companion code for:** "How Hardware Gets Hacked" article series on Maker.io [link to Part 1](https://www.digikey.com/en/maker/blogs/2025/how-hardware-gets-hacked-part-1)

This project demonstrates iterative attacks and defenses for embedded systems using the 2023 MITRE eCTF competition as a foundation. Built from scratch to support multi-platform development (STM32, TM4C, x86), automated testing, and x86 simulation without Docker dependencies.

**Article Series:**
- [Part 1: Introduction to the 2023 MITRE eCTF](https://www.digikey.com/en/maker/blogs/2025/how-hardware-gets-hacked-part-1)
- [Part 2: On-boarding](link)
- [Part 3: Adopting the Attacker Mindset](link)

## Project Structure

```
./
├── application/          # Platform-independent firmware
│   ├── source/           # car.c, fob.c, messages.c
│   ├── include/          # Shared headers
│   ├── packages/         # Feature package definitions
│   └── SConscript        # Application build rules
│
├── hardware/             # Platform-specific implementations
│   ├── include/          # platform.h and uart.h (abstraction layer)
│   ├── stm32/            # STM32F4 HAL & drivers
│   ├── tm4c/             # TM4C123 drivers
│   └── x86/              # Desktop simulation layer
│
├── tools/                # Python utilities
│   ├── simulate.py       # x86 simulation environment
│   ├── openocd.py        # Flash & debug wrapper
│   ├── monitor.py        # Serial monitor
│   ├── list.py           # Device enumeration
│   ├── package.py        # Package a car feature
│   └── enable.py         # Feature enablement
│
├── testing/              # Automated test suite
│   ├── test.py           # Protocol & security tests
│   ├── conftest.py       # pytest fixtures & device mgmt
│   └── protocol.py       # Test message helpers
│
├── setup/                # Platform setup guides
├── secrets/              # Secret generation & storage
└── SConstruct            # Build system entry point
```

### Hardware Abstraction

The project uses a clean abstraction layer (`hardware/include/platform.h` and `hardware/include/uart.h`) that allows the same application code to run on multiple platforms:

![Hardware Abstraction](docs/images/hwAbstraction.png)

```c
// platform.h defines the non-UART interface
void initHardware_car(int argc, char **argv);
void initHardware_fob(int argc, char **argv);
void setLED(led_color_t color);
bool buttonPressed(void);
// ... etc.

// uart.h defines the UART interface
void uart_init(hw_uart_t uart, int argc, char ** argv);
uint32_t uart_readline(hw_uart_t uart, uint8_t *buf);
void uart_writeb(hw_uart_t uart, uint8_t data);
// ... etc.
```

Each platform implements these functions differently:
- **STM32**: Uses ST HAL library (GPIO, UART, flash APIs)
- **TM4C**: Uses TivaWare drivers
- **x86**: Software simulation (ncurses UI, virtual serial ports)

## The 2023 eCTF Challenge

The [MITRE eCTF](https://ectf.mitre.org/) is an embedded security competition where teams design secure car key fob systems. The challenge: build a system where paired fobs can unlock cars and enable features, while preventing unauthorized access.

**Key components:**
- **Car**: Stores secrets, validates unlock requests
- **Paired Fob**: Pre-configured with car ID and PIN, can unlock car and pair an unpaired fob
- **Unpaired Fob**: Factory-fresh fob that pairs at runtime

**Security goals:**
- Prevent code/secret extraction
- Prevent replay attacks
- Protect against fault injection
- Secure pairing protocol

For detailed protocol flows and security architecture, see [`application/README.md`](application/README.md).

## Threat Model

This repository is organized around progressive security improvements. Each defense corresponds to an attack demonstrated in the article series.

Sample set of links to be included later, as the other articles are written:

**Development roadmap:**

1. **[Baseline project](commit-link)** - Basic unlock/pairing without security
2. **[Defending against code readout](commit-link)** - Read protection, debug disable
3. **[Defending against replay attacks](commit-link)** - Challenge-response with nonces
4. **[Defending against glitching](commit-link)** - Fault detection and recovery
5. **[Defending against side channels](commit-link)** - Constant-time crypto

> **Note:** If you're following the articles, start with the baseline commit and progress through each defense as you read about the corresponding attack.

## Usage

### Setup

- **Windows + WSL2**: See [`setup/setup-windows-wsl.md`](setup/setup-windows-wsl.md)
- **macOS**: See [`setup/setup-mac.md`]((setup/setup-mac.md))
- **Linux**: See [`setup/setup-linux.md`]((setup/setup-linux.md))

### Development Workflow

![Development Pipeline](images/pipeline.png)

For a guided introduction to building, flashing, and testing the firmware, see [Part 2: On-boarding](link)

### Building

Use SCons to build firmware for any platform/role combination:

```bash
scons -j8 <TARGET> [id=<#>] [pin=<#>]
```

`TARGET` can be:
- `platform={stm32|tm4c|x86} role={car|paired_fob|unpaired_fob}` (build a specific role for a specific platform)
    - `car` requires `id`
    - `paired_fob` requires `id` and `pin`
    - `unpaired_fob` requires neither
- `x86` / `stm32` / `tm4c` (build all roles for a specific platform; requires `id` and `pin`)
- `all` (build all roles for all platforms; requires `id` and `pin`)

**Output location:** Binaries are placed in `hardware/{platform}/build/{role}_{id}/` (or `hardware/{platform}/build/unpaired_fob` for unpaired fobs)

**Build options:**
- `debug=1` - Enable debug symbols
- `test=1` - Enable test commands via HOST_UART
- `opt=0` - Set optimization level (0-3,s)
- `ui=console` - Use console UI for x86
- Feature flags: Supports single words or quoted strings
    - `unlock_flag=`
    - `feature1_flag=`
    - `feature2_flag=`
    - `feature3_flag=`

Examples:

```bash
# Builds the firmware for a paired fob with id "1357" and pin "123456" for the STM32
scons -j8 platform=stm32 role=paired_fob id=1357 pin=123456

# Build all roles for x86 with feature flags (embedded in car firmware)
scons -j8 x86 id=12345 pin=987654 \
    unlock_flag="FLAG{car_unlocked}" \
    feature1_flag="FLAG{heated_seats}"

# Build all targets with test commands
scons -j8 all id=12345 pin=123456 test=1

# Clean build artifacts (must specify a unique build)
scons -j8 -c platform=stm32 role=paired_fob id=1357
scons -j8 x86 id=12345
scons -j8 all id=12345
```

### Flashing & Running

**For physical hardware (STM32/TM4C):**

```bash
# Use list.py to find connected devices
./tools/list.py

# Flash using OpenOCD wrapper
./tools/openocd.py flash stm32 <SERIAL_NUMBER> <PATH_TO_BIN>

# Monitor device output
./tools/monitor.py <SERIAL_PORT>
```

**For x86 simulation:**

```bash
# Run simulation (launches both car and fob)
./tools/simulate.py \
    hardware/x86/build/car_12345/firmware \
    hardware/x86/build/paired_fob_12345/firmware

# Press 'b' in fob console window to simulate button press

# Simulation opens virtual serial ports - use monitor.py to interact
# In another terminal:
./tools/monitor.py /dev/pts/3  # Car's HOST_UART
./tools/monitor.py /dev/pts/5  # Fob's HOST_UART
```

**HOST UART Interaction**

```
Commands are sent as "{cmd}\n" or "{cmd} {args}\n".
Responses are "OK\n", "OK: {value}\n", or "ERROR: {reason}\n".

Standard Commands (production firmware):
    Fob:
        enable <hex_feature_pkg>  - Enable a packaged feature
        pair <pin>                - Initiate pairing (paired fob sends this)
```

### Testing & Debugging

The testing framework supports both hardware and simulation:

![Testing Setup](images/testSetup.png)

**Running tests:**

```bash
# Run full test suite on simulated firmware
pytest testing/test.py

# Run single test on simulated firmware
pytest testing/test.py::TestSinglePairedFob::test_unlock_valid_fob

# Run test on real hardware
pytest testing/test.py --using stm32@<SERIAL_NUMBER_1>,<SERIAL_NUMBER_2>
```

**Useful pytest flags:**
- `-v` - Verbose output
- `-x` - Halt on first failing test
- `-s` - Don't suppress print output

**Interactive debugging:**

```bash
# Launch GDB session via OpenOCD
./tools/openocd.py debug stm32 <SERIAL_NUMBER>

# In another terminal, connect GDB:
arm-none-eabi-gdb hardware/stm32/build/car_12345/firmware.elf
(gdb) target remote localhost:3333
(gdb) monitor reset halt
(gdb) b main
(gdb) c

# or

gdbgui -g "gdb-multiarch -ex 'target remote localhost:3333'" --args hardware/stm32/build/paired_fob_2345/paired_fob_2345.bin
```

**Test commands (with `test=1` build):**

When built with `test=1`, devices accept additional commands for debugging:

```
Commands are sent as "{cmd}\n" or "{cmd} {args}\n".
Responses are "OK\n", "OK: {value}\n", or "ERROR: {reason}\n".

Test Commands (TEST_BUILD only):
    Both:
        reset                     - Factory reset (clear state, restart)
    
    Fob:
        reload                    - Reload flash data, state persists
        btnPress                  - Simulate button press, blocks until unlock completes
        getFlashData              - Get FLASH_DATA as hex
        setFlashData <hex>        - Set FLASH_DATA from hex (persists to flash)
        isPaired                  - Returns OK: 1 or OK: 0
    
    Car:
        isLocked                  - Returns OK: 1 or OK: 0
        getUnlockCount            - Returns OK: <n> (resets on power cycle)
```

Send commands via `monitor.py` or another terminal of choice (screen, minicom, PuTTY, etc).

## Adding New Tests

Tests are written using pytest and the `DeployedDevice` abstraction (see `testing/conftest.py`).

**Basic test structure:**

```python
def test_my_security_check(single_paired_fob):
    """Test description"""
    fob, car = single_paired_fob

    # Send command to fob
    fob.send_command("unlock")

    # Check car response
    response = car.read_until(b"OK", timeout=2.0)
    assert b"FLAG{unlocked}" in response
```

**Available fixtures:**
- `single_paired_fob` - One fob + one car (same ID)
- `single_unpaired_fob` - Unpaired fob + one car
- `two_paired_fobs` - Two fobs + one car (all same ID)
- `mismatched_fob` - Fob with ID `1234`, car with ID `5678`

**Adding a new fixture:**

1. Edit `testing/conftest.py`
2. Define fixture using `deploy()` helper:

```python
@pytest.fixture
def my_custom_setup(request):
    """Custom test setup"""
    car = deploy(platform="x86", role="car", car_id="9999")
    fob1 = deploy(platform="x86", role="paired_fob", car_id="9999", pin="111111")
    fob2 = deploy(platform="stm32", role="paired_fob", car_id="9999", pin="222222")

    yield (car, fob1, fob2)

    # Cleanup happens automatically
```

**Test organization:**
- `TestSinglePairedFob` - Basic unlock/feature tests
- `TestSecurityValidation` - Attack/defense tests
- `TestCustomConfigurations` - Multi-device scenarios

## Adding a New Platform

To add support for a new microcontroller or simulator:

### 1. Create Hardware Directory Structure

```bash
mkdir -p hardware/newplatform/{source,include,build}
cd hardware/newplatform
```

### 2. Implement Platform Abstraction (`platform.h` and `uart.h`)

Create implementations for all functions in `hardware/include/platform.h`:

```c
// hardware/newplatform/source/newplatform.c

#include "platform.h"
#include <newplatform_hal.h>  // Your platform's HAL

void initHardware_car(int argc, char **argv) {
    // Initialize clocks, GPIO, UART, flash
    // Set up LED as output
    // Set up button as input with interrupt
}

void uart_write(uart_port_t port, const uint8_t *data, size_t len) {
    // Write to UART (HOST_UART or BOARD_UART)
}

// ... implement all other platform.h functions
```

**Required functions:**
- Hardware init: `initHardware_car()`, `initHardware_fob()`
- UART: `uart_write()`, `uart_read()`, `uart_avail()`
- Flash: `loadFobState()`, `saveFobState()`, `loadFlag()`
- GPIO: `setLED()`, `buttonPressed()`

### 3. Integrate with SCons

Create `hardware/newplatform/SConscript`:

```python
Import('app_env role car_id pin')

# Clone environment for platform-specific settings
env = app_env.Clone()

# Set compiler and flags
env['CC'] = 'newplatform-gcc'
env['CCFLAGS'] = ['-mcpu=cortex-m4', '-mthumb', ...]
env['LINKFLAGS'] = ['-Tnewplatform.ld', ...]

# Add platform sources
platform_sources = Glob('source/*.c')

# Build firmware
firmware = env.Program(
    target=f'build/{role}_{car_id}/firmware.elf',
    source=[platform_sources, app_sources]
)

# Generate binary
env.Command(
    f'build/{role}_{car_id}/firmware.bin',
    firmware,
    'newplatform-objcopy -O binary $SOURCE $TARGET'
)
```

Add platform to `SConstruct`:

```python
AVAILABLE_PLATFORMS = ["stm32", "tm4c", "x86", "newplatform"]
```

### 4. Integrate with `openocd.py`

Add OpenOCD configuration in `tools/openocd.py`:

```python
PLATFORM_CONFIGS = {
    # ... existing platforms ...
    'newplatform': {
        'interface': 'cmsis-dap.cfg',  # Or your debugger interface
        'target': 'newplatform_device.cfg',
        'flash_bank': 'newplatform.flash',
    }
}
```

If OpenOCD doesn't support your platform, you'll need to create custom flash/debug scripts:

```python
def flash_newplatform(serial, binary):
    """Custom flash implementation"""
    # Use manufacturer's programming tool
    subprocess.run([
        'newplatform-flash',
        '--serial', serial,
        '--write', binary
    ])
```

### 5. Integrate with `list.py`

Add device detection in `tools/list.py`:

```python
def detect_devices():
    devices = []
    ports = serial.tools.list_ports.comports()

    for port in ports:
        # ... existing detection ...

        # Add newplatform detection
        if 'newplatform' in port.description.lower():
            devices.append({
                'platform': 'newplatform',
                'serial': port.serial_number,
                'port': port.device
            })

    return devices
```

### 6. Integrate with `conftest.py`

Update pytest fixtures to support the new platform:

```python
# testing/conftest.py

def deploy(platform, role, car_id, pin=None):
    """Deploy a device for testing"""

    # Build firmware
    build_firmware(platform, role, car_id, pin)

    if platform == 'newplatform':
        # Flash to hardware
        devices = list_devices(platform='newplatform')
        if not devices:
            pytest.skip(f"No {platform} devices connected")

        device = devices[0]
        flash_device(platform, device['serial'], binary_path)

        # Open serial connection
        ser = serial.Serial(device['port'], 115200, timeout=1.0)
        return DeployedDevice(ser, platform='newplatform')

    # ... handle other platforms ...
```

**Key considerations:**
- **Serial ports**: Does your platform expose two UARTs (HOST + BOARD)?
- **Flash persistence**: How do you emulate EEPROM/flash storage?
- **Button/LED**: Can you map to GPIO or simulate them?
- **Debugging**: Does OpenOCD support your device, or do you need a custom solution?

### 7. Test the Integration

```bash
# Build for new platform
scons platform=newplatform role=car id=12345

# List detected devices
python tools/list.py

# Flash and test
python tools/openocd.py flash newplatform <SERIAL> hardware/newplatform/build/car_12345/firmware.bin
pytest testing/test.py --using newplatform@<SERIAL>
```

---

**Need help?** Open an issue or see the existing platform implementations for reference:
- Simple example: `hardware/x86/` (software simulation)
- Complex example: `hardware/stm32/` (full HAL integration)
