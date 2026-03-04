import os
import sys
import subprocess

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
        if not pin.isdigit():
            print("Error: 'pin' must be numeric")
            Exit(1)
        if len(pin) != 6:
            print("Error: 'pin' must be exactly 6 digits")
            Exit(1)

if not app_env['opt'].isdigit() or app_env['opt'] not in ['0', '1', '2', '3', 's']:
    print("Error: 'opt' must be one of: 0, 1, 2, 3, s")
    Exit(1)

required_files = [
    'tools/car_gen_secret.py',
    'tools/fob_gen_secret.py',
]

for f in required_files:
    if not os.path.exists(f):
        print(f"Error: required file missing: {f}")
        Exit(1)

# Add feature flag defines if provided
if app_env['unlock_flag']:
    app_env.Append(CPPDEFINES=[('UNLOCK_FLAG', f'\\"{app_env["unlock_flag"]}\\"')])
if app_env['feature1_flag']:
    app_env.Append(CPPDEFINES=[('FEATURE1_FLAG', f'\\"{app_env["feature1_flag"]}\\"')])
if app_env['feature2_flag']:
    app_env.Append(CPPDEFINES=[('FEATURE2_FLAG', f'\\"{app_env["feature2_flag"]}\\"')])
if app_env['feature3_flag']:
    app_env.Append(CPPDEFINES=[('FEATURE3_FLAG', f'\\"{app_env["feature3_flag"]}\\"')])

# Common compiler flags
app_env.Append(CPPFLAGS=[f'-O{app_env["opt"]}', '-Wall'])
if app_env['debug']:
    app_env.Append(CPPFLAGS=['-g', '-DDEBUG'])
if app_env['test']:
    app_env.Append(CPPDEFINES=['TEST_BUILD'])

# Include paths
app_env.Append(CPPPATH=[
    '#/hardware/include',     # platform.h, uart.h
    '#/application/include',  # messages.h, dataFormats.h
])

def gen_secrets_action(target, source, env):
    secrets_h = str(target[0])

    if env['role'] == 'car':
        cmd = [
            sys.executable,
            'tools/car_gen_secret.py',
            '--car-id', env['id'],
            '--header-file', secrets_h,
        ]
    elif env['role'] == 'paired_fob':
        cmd = [
            sys.executable,
            'tools/fob_gen_secret.py',
            '--car-id', env['id'],
            '--pair-pin', env['pin'],
            '--header-file', secrets_h,
            '--paired'
        ]
    else:
        cmd = [
            sys.executable,
            'tools/fob_gen_secret.py',
            '--car-id', '0',
            '--pair-pin', '000000',
            '--header-file', secrets_h,
            # No --paired flag for unpaired fob
        ]

    subprocess.run(cmd, check=True)

Export('gen_secrets_action')

if single_build_mode:
    app_env['name'] = f"{app_env['role']}_{app_env['id']}" if app_env['role'] in ['car', 'paired_fob'] else app_env['role']
    app_env['build_dir'] = f"hardware/{app_env['platform']}/build/{app_env['name']}"
    app_env.Append(CPPPATH=[f'#/{app_env["build_dir"]}'])   # secrets.h

    app = SConscript(
        f"hardware/{app_env['platform']}/SConscript",
        variant_dir=app_env['build_dir'],
        duplicate=0,
        exports={'app_env': app_env}
    )
    Default(app)

else:
    # List of all targets, one per platform/role combination
    all_targets = []

    for platform in AVAILABLE_PLATFORMS:
        for role in AVAILABLE_ROLES:
            e = app_env.Clone()
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

    # Build targets: all, stm32, tm4c, simulation
    Alias('all', all_targets)

    for platform in AVAILABLE_PLATFORMS:
        Alias(platform, [t for t in all_targets if platform in str(t)])