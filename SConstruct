import os
import sys
import subprocess
import string

AVAILABLE_PLATFORMS = ["stm32", "tm4c", "sim"]
AVAILABLE_ROLES = ["car", "paired_fob", "unpaired_fob"]
AVAILABLE_UI = ["console", "microui"]

# Build options
opts = Variables()
opts.Add(EnumVariable('platform', 'Target platform', None,
                      allowed_values=(AVAILABLE_PLATFORMS)))
opts.Add(EnumVariable('role', 'Device role', None,
                      allowed_values=(AVAILABLE_ROLES)))
opts.Add(EnumVariable('ui', 'UI type for simulation', None,
                      allowed_values=(AVAILABLE_UI)))
opts.Add('id', 'Device ID (required for car and paired_fob)', '')
opts.Add('pin', 'Pairing pin (required for paired_fob)', '')
opts.Add('opt', 'Optimization level', '2')
opts.Add(BoolVariable('debug', 'Debug build', False))
opts.Add(BoolVariable('test', 'Test build (enables test commands)', False))
opts.Add('pairing_delay_ms', 'Delay (ms) before checking pairing pin (anti-brute-force)', '750')
opts.Add('unlock_delay_ms', 'Delay (ms) before starting unlock sequence (anti-brute-force)', '750')

# Optional feature flags
opts.Add('unlock_flag', 'Custom unlock flag value', '')
opts.Add('feature1_flag', 'Custom feature 1 flag value', '')
opts.Add('feature2_flag', 'Custom feature 2 flag value', '')
opts.Add('feature3_flag', 'Custom feature 3 flag value', '')

app_env = Environment(variables=opts)
Help(opts.GenerateHelpText(app_env))

if GetOption('help'):
    Return()

# Validate inputs
single_build_mode = (len(COMMAND_LINE_TARGETS) == 0)
clean_mode = GetOption('clean')
plat = app_env.get('platform')
role = app_env.get('role')
car_id = app_env.get('id')
pin = app_env.get('pin')
ui = app_env.get('ui')

if single_build_mode:
    if not plat or not role:
        print("Error: single-build mode requires both 'platform' and 'role'")
        print("Usage: scons platform=stm32 role=car id=12345")
        Exit(1)

    if not car_id and role in ['car', 'paired_fob']:
        print("Error: 'id' parameter is required when building 'car' or 'paired_fob'")
        print("Usage: scons platform=platform1 role=car id=12345")
        print("    or scons stm32 id=12345 pin=123456")
        Exit(1)
    
    if ui and plat in ["stm32", "tm4c"]:
        print("Error: ui option given for simulation build")
        Exit(1)
else:
    if role or plat:
        print("Error: 'platform' and/or 'role' parameters given when building a collection of targets")
        print("Usage: scons platform=platform1 role=car id=12345  <-- Platform and role required")
        print("    or scons all id=12345 pin=123456               <-- No platform or role required")
        Exit(1)

    if not car_id:
        print("Error: 'id' parameter is required when building 'car' or 'paired_fob'")
        print("Usage: scons platform=platform1 role=car id=12345")
        print("    or scons stm32 id=12345 pin=123456")
        Exit(1)

if car_id:
    if not car_id.isdigit():
        print("Error: 'id' must be numeric")
        Exit(1)
    iCar_id = int(car_id)
    if (iCar_id < 0) or (iCar_id > (2**32-1)):
        print("Error: 'id' must fit within a 32-bit unsigned integer [0, 4'294'967'295]")
        Exit(1)

if not clean_mode:  # Validate pin
    if not pin and (not single_build_mode or (single_build_mode and role == 'paired_fob')):
        print("Error: 'pin' parameter is required when building 'paired_fob'")
        print("Usage: scons platform=platform1 role=paired_fob id=12345 pin=123456")
        print("    or scons stm32 id=12345 pin=123456")
        Exit(1)

    if pin:
        if not all(c in string.hexdigits for c in pin):
            print("Error: 'pin' must only contain hex digits")
            Exit(1)
        if len(pin) != 6:
            print("Error: 'pin' must be exactly 6 digits")
            Exit(1)

if not app_env['opt'].isdigit() or app_env['opt'] not in ['0', '1', '2', '3', 's']:
    print("Error: 'opt' must be one of: 0, 1, 2, 3, s")
    Exit(1)

if not app_env['pairing_delay_ms'].isdigit():
    print("Error: 'pairing_delay_ms' must be a non-negative integer")
    Exit(1)

if not app_env['unlock_delay_ms'].isdigit():
    print("Error: 'unlock_delay_ms' must be a non-negative integer")
    Exit(1)

FLAG_SIZE = 64
FLAG_DEFAULTS = {
    'unlock_flag':  'default_unlock',
    'feature1_flag': 'default_feature1',
    'feature2_flag': 'default_feature2',
    'feature3_flag': 'default_feature3',
}

for key, default in FLAG_DEFAULTS.items():
    if not app_env[key]:
        app_env[key] = default

for key in FLAG_DEFAULTS:
    val = app_env[key]
    if len(val.encode('utf-8')) > FLAG_SIZE - 1:  # -1 to leave room for null terminator
        print(f"Error: '{key}' value is too long (max {FLAG_SIZE - 1} bytes, got {len(val.encode('utf-8'))})")
        Exit(1)

required_files = [
    'tools/car_gen_secret.py',
    'tools/fob_gen_secret.py',
]

for f in required_files:
    if not os.path.exists(f):
        print(f"Error: required file missing: {f}")
        Exit(1)

# Define flag values for sim.c (hardware targets read flags from flash/EEPROM at runtime)
app_env.Append(CPPDEFINES=[('UNLOCK_FLAG',   f'\\"{app_env["unlock_flag"]}\\"')])
app_env.Append(CPPDEFINES=[('FEATURE1_FLAG', f'\\"{app_env["feature1_flag"]}\\"')])
app_env.Append(CPPDEFINES=[('FEATURE2_FLAG', f'\\"{app_env["feature2_flag"]}\\"')])
app_env.Append(CPPDEFINES=[('FEATURE3_FLAG', f'\\"{app_env["feature3_flag"]}\\"')])
app_env.Append(CPPDEFINES=[('PAIRING_DELAY_MS', app_env['pairing_delay_ms'])])
app_env.Append(CPPDEFINES=[('UNLOCK_DELAY_MS', app_env['unlock_delay_ms'])])

# Common compiler flags
app_env.Append(CPPFLAGS=[f'-O{app_env["opt"]}', '-Wall', '-pedantic'])
if app_env['debug']:
    app_env.Append(CPPFLAGS=['-g', '-DDEBUG'])
if app_env['test']:
    app_env.Append(CPPDEFINES=['TEST_BUILD'])

# Include paths
app_env.Append(CPPPATH=[
    '#/hardware/include',         # platform.h, uart.h
    '#/application/include',      # messages.h, dataFormats.h
    '#/libraries/tiny-AES-c',     # aes.h
    '#/libraries/tiny-AES-CMAC-c' # aes_cmac.h
])

def compiler_accepts_flag(cc, flag):
    """Best-effort, compiler-agnostic probe: does invoking `cc` with `flag`
    on a trivial compile succeed, rather than being rejected as an
    unrecognized option? Tried directly against whatever CC actually is for
    a given platform, instead of assuming a GCC/Clang-family compiler -
    some future platform's CC might be neither."""
    try:
        result = subprocess.run(
            [cc, flag, '-c', '-x', 'c', '-o', os.devnull, '-'],
            input='int main(void) { return 0; }',
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def configure_env(p, env):
    if p in ['stm32', 'tm4c']:
        env.Replace(CC='arm-none-eabi-gcc')
        env.Replace(AR='arm-none-eabi-ar')
        env.Replace(AS='arm-none-eabi-as')
        if p == 'tm4c':
            env.Replace(LINK='arm-none-eabi-ld')
        env['arch_flags'] = ['-mcpu=cortex-m4', '-mthumb']
        if p == 'stm32':
            env['arch_flags'] += ['-mfpu=fpv4-sp-d16', '-mfloat-abi=hard']
        env.Append(CPPFLAGS=env['arch_flags'] + ['-ffunction-sections', '-fdata-sections'])
    # sim: system gcc, no overrides needed

    # -fstack-usage costs nothing when supported (see testing/test_build_budgets.py's
    # docstring for what it's used for) - no measurable compile-time or
    # artifact-size effect, since it only ever adds a .su side-output next
    # to each .o. On by default whenever CC actually accepts it; otherwise
    # left off rather than assumed, since CC isn't guaranteed to be GCC or
    # Clang for every platform this project might ever target.
    if compiler_accepts_flag(env['CC'], '-fstack-usage'):
        env.Append(CPPFLAGS=['-fstack-usage'])

    lib_dir = f'hardware/{p}/build/libraries'
    env['platform_libs'] = (
        env.StaticLibrary(
            target=f'{lib_dir}/tiny-AES-c/aes',
            source=[env.Object(
                target=f'{lib_dir}/tiny-AES-c/aes.o',
                source='#/libraries/tiny-AES-c/aes.c'
            )]
        ),
        env.StaticLibrary(
            target=f'{lib_dir}/tiny-AES-CMAC-c/aes_cmac',
            source=[env.Object(
                target=f'{lib_dir}/tiny-AES-CMAC-c/aes_cmac.o',
                source='#/libraries/tiny-AES-CMAC-c/aes_cmac.c'
            )]
        )
    )
    env['platform_common_obj'] = env.Object(
        target=f'hardware/{p}/build/platform_common.o',
        source='#/hardware/source/platform_common.c'
    )

SECRETS_JSON_PATH = os.environ.get('TEST_SECRETS_FILE', 'secrets/secrets.json')

GEN_SECRET_SCRIPT = {
    'car':          'tools/car_gen_secret.py',
    'paired_fob':   'tools/fob_gen_secret.py',
    'unpaired_fob': 'tools/fob_gen_secret.py',
}

def gen_secrets_action(target, source, env):
    secrets_h = str(target[0])
    secrets_json = SECRETS_JSON_PATH
    gen_script = GEN_SECRET_SCRIPT[env['role']]

    if env['role'] == 'car':
        cmd = [
            sys.executable,
            gen_script,
            '--car-id', env['id'],
            '--header-file', secrets_h,
            '--secrets-file', secrets_json
        ]
    elif env['role'] == 'paired_fob':
        cmd = [
            sys.executable,
            gen_script,
            '--car-id', env['id'],
            '--pair-pin', env['pin'],
            '--header-file', secrets_h,
            '--secrets-file', secrets_json,
            '--paired'
        ]
    else:
        cmd = [
            sys.executable,
            gen_script,
            '--header-file', secrets_h,
            '--secrets-file', secrets_json
            # No --paired flag for unpaired fob
        ]

    subprocess.run(cmd, check=True)

def secrets_h_sources(env):
    """
    Sources that should force secrets.h to regenerate. role/id are deliberately
    excluded: they're already baked into the build directory path, so a
    different role/id is always a different secrets.h target, never a staleness
    case. pin is NOT reflected in the path (paired_fob's dir is role_id only),
    so it must be tracked explicitly.
    """
    sources = [env.Value(env.get('pin', '')), f'#/{GEN_SECRET_SCRIPT[env["role"]]}']
    if os.path.exists(SECRETS_JSON_PATH):
        secrets_json_node = SECRETS_JSON_PATH if os.path.isabs(SECRETS_JSON_PATH) else f'#/{SECRETS_JSON_PATH}'
        sources.append(secrets_json_node)
    return sources

Export('gen_secrets_action', 'secrets_h_sources')

def gen_flags_bin_action(target, source, env):
    # Binary layout (FLAG_SIZE bytes each): feature3, feature2, feature1, unlock
    # This order matches the TM4C EEPROM address layout (lowest address first).
    flag_order = ['feature3_flag', 'feature2_flag', 'feature1_flag', 'unlock_flag']
    buf = bytearray(len(flag_order) * FLAG_SIZE)
    for i, key in enumerate(flag_order):
        val = env[key].encode('utf-8')
        buf[i * FLAG_SIZE : i * FLAG_SIZE + len(val)] = val
    with open(str(target[0]), 'wb') as f:
        f.write(buf)

if single_build_mode:
    app_env['name'] = f"{app_env['role']}_{app_env['id']}" if app_env['role'] in ['car', 'paired_fob'] else app_env['role']
    app_env['build_dir'] = f"hardware/{app_env['platform']}/build/{app_env['name']}"
    app_env.Append(CPPPATH=[f'#/{app_env["build_dir"]}'])   # secrets.h
    configure_env(app_env['platform'], app_env)

    app = SConscript(
        f"hardware/{app_env['platform']}/SConscript",
        variant_dir=app_env['build_dir'],
        duplicate=0,
        exports={'app_env': app_env}
    )
    Default(app)

    if app_env['role'] == 'car':
        flags_bin = app_env.Command(
            f'{app_env["build_dir"]}/flags.bin',
            [],
            gen_flags_bin_action
        )
        Default(flags_bin)

else:
    # List of all targets, one per platform/role combination
    all_targets = []

    for platform in AVAILABLE_PLATFORMS:
        base_e = app_env.Clone()
        configure_env(platform, base_e)

        for role in AVAILABLE_ROLES:
            e = base_e.Clone()
            e['role'] = role
            e['name'] = f"{role}_{e['id']}" if role in ['car', 'paired_fob'] else role
            e['build_dir'] = f"hardware/{platform}/build/{e['name']}"

            e.Append(CPPPATH=[f'#/{e["build_dir"]}'])   # secrets.h

            tgt = SConscript(
                f'hardware/{platform}/SConscript',
                variant_dir=e['build_dir'],
                duplicate=0,
                exports={'app_env': e}
            )

            all_targets.append(tgt)

            if role == 'car':
                flags_bin = e.Command(
                    f'{e["build_dir"]}/flags.bin',
                    [],
                    gen_flags_bin_action
                )
                all_targets.append(flags_bin)

    # Build targets: all, stm32, tm4c, simulation
    Alias('all', all_targets)

    for platform in AVAILABLE_PLATFORMS:
        Alias(platform, [t for t in all_targets if platform in str(t)])