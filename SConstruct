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

env = Environment(variables=opts)
Help(opts.GenerateHelpText(env))

if GetOption('help'):
    Return()

# Validate inputs
platform = env.get('platform')
role = env.get('role')
car_id = env.get('id')
ui = env.get('ui')

if 'all' in COMMAND_LINE_TARGETS or role in ['car', 'paired_fob']:
    if not car_id:
        print(f"Error: 'id' parameter is required when role={role}")
        print("Usage: scons platform=platform1 role=car id=12345")
        Exit(1)

if platform in ["stm32", "tm4c"] and ui != '':
    print("Error: ui option given for non-x86 platform")
    Exit(1)

# Common compiler flags
env.Append(CPPFLAGS=[f'-O{env["opt"]}', '-Wall'])
if env['debug']:
    env.Append(CPPFLAGS=['-g', '-DDEBUG'])
if env['test']:
    env.Append(CPPDEFINES=['TEST_BUILD'])

# Add feature flag defines if provided
if env['unlock_flag']:
    env.Append(CPPDEFINES=[('UNLOCK_FLAG', f'\\"{env["unlock_flag"]}\\"')])
if env['feature1_flag']:
    env.Append(CPPDEFINES=[('FEATURE1_FLAG', f'\\"{env["feature1_flag"]}\\"')])
if env['feature2_flag']:
    env.Append(CPPDEFINES=[('FEATURE2_FLAG', f'\\"{env["feature2_flag"]}\\"')])
if env['feature3_flag']:
    env.Append(CPPDEFINES=[('FEATURE3_FLAG', f'\\"{env["feature3_flag"]}\\"')])

# Include paths
env.Append(CPPPATH=[
    '#/hardware/include',     # platform.h, uart.h
    '#/application/include',  # messages.h, dataFormats.h
])

stm32_drivers = SConscript(
    'hardware/stm32/Drivers/SConscript',
    exports={'env': env}
)

tm4c_drivers = SConscript(
    'hardware/tm4c/libraries/SConscript',
    exports={'env': env}
)

# List of all targets, one per platform/role combination
all_targets = []

for platform in AVAILABLE_PLATFORMS:
    for role in AVAILABLE_ROLES:
        e = env.Clone()
        e['platform'] = platform
        e['role'] = role

        drivers = None

        # Platform-specific toolchain configuration
        if platform in ['stm32', 'tm4c']:
            # ARM toolchain
            e.Replace(CC='arm-none-eabi-gcc')
            e.Replace(AR='arm-none-eabi-ar')
            e.Replace(AS='arm-none-eabi-as')
            e["arch_flags"] = [
                '-mcpu=cortex-m4',
                '-mthumb'
            ]
            e.Append(CPPFLAGS = [
                '-ffunction-sections',
                '-fdata-sections',
                '-Wall',
                '-c',
                '-g'
            ])
            drivers = stm32_drivers if platform == 'stm32' else tm4c_drivers

        e['name'] = f'{role}_{e["id"]}' if e['id'] else role
        e['build_dir'] = f'hardware/{platform}/build/{e["name"]}'

        e.Append(CPPPATH=[f'#/{e["build_dir"]}'])   # secrets.h

        tgt = SConscript(
            f'hardware/{platform}/SConscript',
            variant_dir=e['build_dir'],
            duplicate=0,
            exports={'env': e, 'drivers' : drivers}
        )

        all_targets.append(tgt)

# Build targets: all, stm32, tm4c, x86
Alias('all', all_targets)

for platform in ['stm32', 'tm4c', 'x86']:
    Alias(platform, [t for t in all_targets if platform in str(t)])

Default(t for t in all_targets if (platform in str(t) and role in str(t)))

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