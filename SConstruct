AVAILABLE_PLATFORMS = ["stm32", "tm4c", "x86"]
AVAILABLE_ROLES = ["car", "paired_fob", "unpaired_fob"]
AVAILABLE_UI = ["console", "microui"]

# Build options
opts = Variables()
opts.Add(EnumVariable('platform', 'Target platform', None,
                      allowed_values=(AVAILABLE_PLATFORMS)))
opts.Add(EnumVariable('role', 'Device role', None,
                      allowed_values=(AVAILABLE_ROLES)))
opts.Add(EnumVariable('ui', 'UI type for x86 port', None,
                      allowed_values=(AVAILABLE_UI)))
opts.Add('id', 'Device ID (required for car and paired_fob)', '')
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
platform = app_env.get('platform')
role = app_env.get('role')
car_id = app_env.get('id')
ui = app_env.get('ui')

if 'all' in COMMAND_LINE_TARGETS or role in ['car', 'paired_fob']:
    if not car_id:
        print(f"Error: 'id' parameter is required when role={role}")
        print("Usage: scons platform=platform1 role=car id=12345")
        Exit(1)

if platform in ["stm32", "tm4c"] and ui != '':
    print("Error: ui option given for non-x86 platform")
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

import sys

def gen_secrets_action(target, source, env):
    secrets_h = str(target[0])

    if env['role'] == 'car':
        cmd = [
            sys.executable,
            'tools/car_gen_secret.py',
            '--car-id', env['id'],
            '--secret-file', 'secrets/car_secrets.json',
            '--header-file', secrets_h,
        ]
    elif env['role'] == 'paired_fob':
        cmd = [
            sys.executable,
            'tools/fob_gen_secret.py',
            '--car-id', env['id'],
            '--pair-pin', env['pin'],
            '--secret-file', 'secrets/car_secrets.json',
            '--header-file', secrets_h,
            '--paired'
        ]
    else:
        cmd = [
            sys.executable,
            'tools/fob_gen_secret.py',
            '--car-id', '0',
            '--pair-pin', '000000',
            '--secret-file', 'secrets/car_secrets.json',
            '--header-file', secrets_h,
            # No --paired flag for unpaired fob
        ]

Export('gen_secrets_action')


# List of all targets, one per platform/role combination
all_targets = []

for platform in AVAILABLE_PLATFORMS:
    for role in AVAILABLE_ROLES:
        e = app_env.Clone()
        e['role'] = role
        e['name'] = f"{role}_{e['id']}" if e['id'] else role
        e['build_dir'] = f"hardware/{platform}/build/{e['name']}"

        e.Append(CPPPATH=[f'#/{e["build_dir"]}'])   # secrets.h

        tgt = SConscript(
            f'hardware/{platform}/SConscript',
            variant_dir=e['build_dir'],
            duplicate=0,
            exports={'app_env': e}
        )

        all_targets.append(tgt)

# Build targets: all, stm32, tm4c, x86
Alias('all', all_targets)

for platform in ['stm32', 'tm4c', 'x86']:
    Alias(platform, [t for t in all_targets if platform in str(t)])

#Default(t for t in all_targets if (platform in str(t) and role in str(t)))

'''
# Print build configuration
print(f"-- Build configuration --")
print(f"  • Platform:       {env['platform']}")
if env['ui']:
    print(f"  • UI:             {env['ui']}")
print(f"  • Role:           {env['role']}")
if env['id']:
    print(f"  • ID:             {env['id']}")
print(f"  • Optimization:   -O{env['opt']}")
print(f"  • Debug:          {env['debug']}")
print(f"  • Test build:     {env['test']}")
if env['unlock_flag']:
    print(f"  • Unlock flag:    {env['unlock_flag']}")
if env['feature1_flag']:
    print(f"  • Feature 1 flag: {env['feature1_flag']}")
if env['feature2_flag']:
    print(f"  • Feature 2 flag: {env['feature2_flag']}")
if env['feature3_flag']:
    print(f"  • Feature 3 flag: {env['feature3_flag']}")
'''