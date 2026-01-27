# Build options
opts = Variables()
opts.Add(EnumVariable('platform', 'Target platform', '',
                      allowed_values=('stm32', 'tm4c', 'x86')))
opts.Add(EnumVariable('role', 'Device role', '',
                      allowed_values=('car', 'paired_fob', 'unpaired_fob')))
opts.Add('id', 'Device ID (required for car and paired_fob)', '')
opts.Add('opt', 'Optimization level', '2')
opts.Add(BoolVariable('debug', 'Debug build', False))

# Optional feature flags
opts.Add('unlock_flag', 'Custom unlock flag value', '')
opts.Add('feature1_flag', 'Custom feature 1 flag value', '')
opts.Add('feature2_flag', 'Custom feature 2 flag value', '')
opts.Add('feature3_flag', 'Custom feature 3 flag value', '')

env = Environment(variables=opts)
Help(opts.GenerateHelpText(env))

# Validate that id is provided when required
if env['role'] in ['car', 'paired_fob']:
    if not env['id']:
        print(f"Error: 'id' parameter is required when ROLE={env['ROLE']}")
        print("Usage: scons platform=platform1 ROLE=car id=12345")
        Exit(1)

# Platform-specific toolchain configuration
if env['platform'] in ['stm32', 'tm4c']:
    # ARM toolchain
    env.Replace(CC='arm-none-eabi-gcc')
    env.Replace(AR='arm-none-eabi-ar')
    env.Replace(AS='arm-none-eabi-as')
    env["arch_flags"] = [
        '-mcpu=cortex-m4',
        '-mthumb'
    ]
    env.Append(CPPFLAGS = [
        '-ffunction-sections',
        '-fdata-sections',
        '-Wall',
        '-c',
        '-g'
    ])
elif env['platform'] == 'x86':
    # x86 toolchain (use defaults)
    pass  # env already has gcc/ar

# Common compiler flags
env.Append(CPPFLAGS=[f'-O{env["opt"]}', '-Wall'])
if env['debug']:
    env.Append(CPPFLAGS=['-g', '-DDEBUG'])

# Add feature flag defines if provided
if env['unlock_flag']:
    env.Append(CPPDEFINES=[('UNLOCK_FLAG', f'\\"{env["unlock_flag"]}\\"')])
if env['feature1_flag']:
    env.Append(CPPDEFINES=[('FEATURE1_FLAG', f'\\"{env["feature1_flag"]}\\"')])
if env['feature2_flag']:
    env.Append(CPPDEFINES=[('FEATURE2_FLAG', f'\\"{env["feature2_flag"]}\\"')])
if env['feature3_flag']:
    env.Append(CPPDEFINES=[('FEATURE3_FLAG', f'\\"{env["feature3_flag"]}\\"')])

if env['role'] in ['car', 'paired_fob']:
    env['name'] = f'{env["role"]}_{env["id"]}'
else:
    env['name'] = f'{env["role"]}'

env['build_dir'] = f'hardware/{env["platform"]}/build/{env["name"]}'

# Include paths
env.Append(CPPPATH=[
    '#/hardware/include',     # platform.h, uart.h
    '#/application/include',  # messages.h, dataFormats.h
    f'#/{env["build_dir"]}'   # secrets.h
])

# Export environment for the driver build script
Export('env')

# Just build the application - it will handle its own dependencies
app_binary = SConscript(
    f'hardware/{env["platform"]}/SConscript',
    variant_dir=env["build_dir"],
    duplicate=0
)

Default(app_binary)

print(f"\nBuild configuration:")
print(f"  Platform: {env['platform']}")
print(f"  Role: {env['role']}")
if env['id']:
    print(f"  ID: {env['id']}")
print(f"  Optimization: -O{env['opt']}")
print(f"  Debug: {env['debug']}")