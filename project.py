#!/usr/bin/env python3
"""
Project Build and Deployment Orchestration Script

This script provides a unified interface for building, testing, flashing,
and managing your embedded project across multiple platforms and roles.
"""

import argparse
import sys
import os
import subprocess
from pathlib import Path
from typing import List, Optional


# Project configuration
AVAILABLE_PLATFORMS = ["stm32", "tm4c", "x86"]  # Update with your actual platforms
AVAILABLE_ROLES = ["car", "paired_fob", "unpaired_fob"]  # Update with your actual roles
HOST_TOOLS_DIR = Path("host_tools")  # Adjust to your project structure
#BUILD_DIR = Path(f"hardware/{args.platform}/build")  # Adjust to your build output directory


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_success(msg: str):
    print(f"{Colors.OKGREEN}✓ {msg}{Colors.ENDC}")


def print_error(msg: str):
    print(f"{Colors.FAIL}✗ {msg}{Colors.ENDC}", file=sys.stderr)


def print_warning(msg: str):
    print(f"{Colors.WARNING}⚠ {msg}{Colors.ENDC}")


def print_info(msg: str):
    print(f"{Colors.OKCYAN}ℹ {msg}{Colors.ENDC}")


def confirm(prompt: str) -> bool:
    """Ask user for confirmation"""
    response = input(f"{prompt} [y/N]: ").lower().strip()
    return response in ['y', 'yes']


def run_scons(build_configs: List[List[str]], clean: bool = False, dry_run: bool = False) -> int:
    """
    Run SCons with the given build configurations.
    
    Args:
        build_configs: List of argument lists, where each inner list is a complete
                      set of arguments for one SCons invocation
        clean: If True, add '-c' flag to clean instead of build
        dry_run: If True, add '-n' flag to show what would be done without doing it
    
    Returns:
        Return code from SCons (0 on success)
    """
    for config in build_configs:
        cmd = ["scons"]
        cmd.append("-j5")
        if clean:
            cmd.append("-c")
        if dry_run:
            cmd.append("-n")
        cmd.extend(config)
        
        print_info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd)
        
        if result.returncode != 0:
            return result.returncode
    
    return 0


def build_scons_args(platform: str, role: str, id_val: Optional[str] = None, 
                     pin: Optional[str] = None, unlock_flag: Optional[str] = None,
                     feature1_flag: Optional[str] = None, feature2_flag: Optional[str] = None,
                     feature3_flag: Optional[str] = None, test_build: bool = False) -> List[str]:
    """
    Build a list of SCons arguments for a single configuration.
    
    Args:
        platform: Target platform
        role: Target role
        id_val: Optional device ID
        pin: Optional device PIN
        unlock_flag: Optional custom unlock flag value
        feature1_flag: Optional custom feature 1 flag value
        feature2_flag: Optional custom feature 2 flag value
        feature3_flag: Optional custom feature 3 flag value
    
    Returns:
        List of argument strings for SCons
    """
    args = [f"platform={platform}", f"role={role}"]
    
    if id_val:
        args.append(f"id={id_val}")
    if pin:
        args.append(f"pin={pin}")
    
    # Add feature flags if provided
    if unlock_flag:
        args.append(f"unlock_flag={unlock_flag}")
    if feature1_flag:
        args.append(f"feature1_flag={feature1_flag}")
    if feature2_flag:
        args.append(f"feature2_flag={feature2_flag}")
    if feature3_flag:
        args.append(f"feature3_flag={feature3_flag}")
    if test_build:
        args.append("test=1")
    
    return args

def get_build_configs_for_target(args) -> List[List[str]]:
    """
    Generate SCons argument configurations based on command-line arguments.
    
    Valid patterns:
    1. id + pin (no role/platform) -> all roles for all platforms
    2. car + id + platform -> specific car build
    3. paired_fob + id + pin + platform -> specific paired_fob build
    4. unpaired_fob + platform -> specific unpaired_fob build
    5. No arguments (clean only) -> clean all
    
    Args:
        args: Parsed command-line arguments
    
    Returns:
        List of SCons argument lists, or None if invalid combination
    """
    configs = []
    
    # Extract feature flags if provided
    unlock_flag = getattr(args, 'unlock_flag', None)
    feature1_flag = getattr(args, 'feature1_flag', None)
    feature2_flag = getattr(args, 'feature2_flag', None)
    feature3_flag = getattr(args, 'feature3_flag', None)
    
    # Pattern 1: id + pin (no role/platform) -> all roles for all platforms
    if hasattr(args, 'id') and args.id and hasattr(args, 'pin') and args.pin and not args.role and not args.platform:
        for platform in AVAILABLE_PLATFORMS:
            for role in AVAILABLE_ROLES:
                if role == "paired_fob":
                    configs.append(build_scons_args(platform, role, args.id, args.pin,
                                                   unlock_flag, feature1_flag, feature2_flag, feature3_flag,
                                                   getattr(args, 'test_build', False)))
                elif role == "car":
                    configs.append(build_scons_args(platform, role, args.id, None,
                                                   unlock_flag, feature1_flag, feature2_flag, feature3_flag,
                                                   getattr(args, 'test_build', False)))
                else:  # unpaired_fob
                    configs.append(build_scons_args(platform, role, None, None,
                                                   unlock_flag, feature1_flag, feature2_flag, feature3_flag,
                                                   getattr(args, 'test_build', False)))
        return configs
    
    # Pattern 2: car + id + platform
    if args.role == "car" and hasattr(args, 'id') and args.id and args.platform:
        configs.append(build_scons_args(args.platform, "car", args.id, None,
                                       unlock_flag, feature1_flag, feature2_flag, feature3_flag,
                                       getattr(args, 'test_build', False)))
        return configs
    
    # Pattern 3: paired_fob + id + pin + platform
    if args.role == "paired_fob" and hasattr(args, 'id') and args.id and hasattr(args, 'pin') and args.pin and args.platform:
        configs.append(build_scons_args(args.platform, "paired_fob", args.id, args.pin,
                                       unlock_flag, feature1_flag, feature2_flag, feature3_flag,
                                       getattr(args, 'test_build', False)))
        return configs
    
    # Pattern 4: unpaired_fob + platform
    if args.role == "unpaired_fob" and args.platform:
        configs.append(build_scons_args(args.platform, "unpaired_fob", None, None,
                                       unlock_flag, feature1_flag, feature2_flag, feature3_flag,
                                       getattr(args, 'test_build', False)))
        return configs
    
    # Pattern 5: No arguments (clean only) -> clean all
    if not args.role and not args.platform and not (hasattr(args, 'id') and args.id):
        # For clean: delete all build folders
        # Return empty to signal "nuke everything"
        return None
    
    # Invalid combination
    return []


# ==============================================================================
# BUILD COMMAND
# ==============================================================================

def prepare_build_environment(platform: str, role: str, id_val: Optional[str], pin: Optional[str]) -> int:
    """
    Prepare the build environment by creating folders and generating secrets.
    
    Args:
        platform: Target platform
        role: Target role
        id_val: Device ID (for car/paired_fob)
        pin: Pair PIN (for paired_fob)
    
    Returns:
        0 on success, non-zero on failure
    """
    # Determine build folder name
    if role in ["car", "paired_fob"] and id_val:
        build_folder_name = f"{role}_{id_val}"
    else:
        build_folder_name = role
    
    # Create build folder
    build_folder = Path("hardware") / platform / "build" / build_folder_name
    build_folder.mkdir(parents=True, exist_ok=True)
    
    # Prepare secret generation arguments
    secret_file = Path("secrets") / "car_secrets.json"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    header_file = build_folder / "secrets.h"
    
    # Call appropriate secret generation script
    if role == "car":
        script = Path("tools") / "car_gen_secret.py"
        cmd = [
            sys.executable,
            str(script),
            "--car-id", str(id_val),
            "--secret-file", str(secret_file),
            "--header-file", str(header_file)
        ]
    elif role == "paired_fob":
        script = Path("tools") / "fob_gen_secret.py"
        cmd = [
            sys.executable,
            str(script),
            "--car-id", str(id_val),
            "--pair-pin", str(pin),
            "--secret-file", str(secret_file),
            "--header-file", str(header_file),
            "--paired"
        ]
    elif role == "unpaired_fob":
        script = Path("tools") / "fob_gen_secret.py"
        cmd = [
            sys.executable,
            str(script),
            "--car-id", "0",  # Dummy value for unpaired fob
            "--pair-pin", "000000",  # Dummy value for unpaired fob
            "--secret-file", str(secret_file),
            "--header-file", str(header_file)
            # No --paired flag for unpaired fob
        ]
    else:
        print_error(f"Unknown role: {role}")
        return 1
    
    # Run secret generation script
    print_info(f"Generating secrets for {role}...")
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print_error(f"Secret generation failed for {role}")
        return result.returncode
    
    print_success(f"Build environment prepared: {build_folder}")
    return 0


def build_command(args):
    """Handle the build subcommand"""
    print_info("Building project...")
    
    # Generate build configurations
    configs = get_build_configs_for_target(args)
    
    # Check for invalid combinations
    if configs is None:
        print_error("Invalid build command: cannot build 'all' - you must specify id and pin")
        return 1
    
    if not configs:
        print_error("Invalid build arguments. Valid patterns:")
        print("  • build                     --id ID --pin PIN (builds all roles for all platforms)")
        print("  • build --role car          --id ID           --platform PLATFORM")
        print("  • build --role paired_fob   --id ID --pin PIN --platform PLATFORM")
        print("  • build --role unpaired_fob                   --platform PLATFORM")
        return 1
    
    # Prepare build environments for each configuration
    if not args.dry_run:
        for config in configs:
            # Parse the config to extract platform, role, id, pin
            platform = None
            role = None
            id_val = None
            pin = None
            
            for arg in config:
                if arg.startswith("platform="):
                    platform = arg.split("=", 1)[1]
                elif arg.startswith("role="):
                    role = arg.split("=", 1)[1]
                elif arg.startswith("id="):
                    id_val = arg.split("=", 1)[1]
                elif arg.startswith("pin="):
                    pin = arg.split("=", 1)[1]
            
            # Prepare this build environment
            result = prepare_build_environment(platform, role, id_val, pin)
            if result != 0:
                return result
    
    # Show what we're building
    if len(configs) == 1:
        config_str = ' '.join(configs[0])
        print_info(f"Building: {config_str}")
    else:
        print_info(f"Building {len(configs)} configurations...")
        if args.verbose:
            for config in configs:
                print(f"  • {' '.join(config)}")
    
    result = run_scons(configs, clean=False, dry_run=args.dry_run)
    
    if result == 0:
        print_success("Build completed successfully!")
    else:
        print_error("Build failed!")
    
    return result


# ==============================================================================
# CLEAN COMMAND
# ==============================================================================

def clean_command(args):
    """Handle the clean subcommand"""
    print_info("Cleaning build artifacts...")
    
    # Generate configurations for what to clean
    configs = get_build_configs_for_target(args)
    
    # Pattern 5: "nuke" - clean all build folders
    if configs is None:
        print_warning("This will delete ALL build artifacts for ALL platforms!")
        if not args.dry_run and not confirm("Continue?"):
            print_info("Clean cancelled.")
            return 0
        
        # Delete all hardware/PLATFORM/build folders
        for platform in AVAILABLE_PLATFORMS:
            build_path = Path("hardware") / platform / "build"
            if build_path.exists():
                if args.dry_run:
                    print_info(f"Would remove: {build_path}")
                else:
                    print_info(f"Removing: {build_path}")
                    result = subprocess.run(["rm", "-rf", str(build_path)])
                    if result.returncode != 0:
                        print_error(f"Failed to remove {build_path}")
                        return result.returncode
        
        if not args.dry_run:
            print_success("All build artifacts cleaned!")
        return 0
    
    # Invalid combination
    if not configs:
        print_error("Invalid clean arguments. Valid patterns:")
        print("  • clean (removes all build folders - 'nuke')")
        print("  • clean --role car --id ID --platform PLATFORM")
        print("  • clean --role paired_fob --id ID --pin PIN --platform PLATFORM")
        print("  • clean --role unpaired_fob --platform PLATFORM")
        return 1
    
    # Show what we're cleaning
    count = len(configs)
    if count > 1:
        print_warning(f"This will clean {count} program(s):")
        for config in configs[:10]:
            config_str = ' '.join(config)
            print(f"  • {config_str}")
        if count > 10:
            print(f"  ... and {count - 10} more")
        
        if not args.dry_run and not confirm("Continue?"):
            print_info("Clean cancelled.")
            return 0
    elif count == 1:
        config_str = ' '.join(configs[0])
        print_info(f"Cleaning: {config_str}")
    
    # Clean using SCons
    result = run_scons(configs, clean=True, dry_run=args.dry_run)
    
    if result == 0:
        print_success("Clean completed successfully!")
    else:
        print_error("Clean failed!")
    
    return result


# ==============================================================================
# FLASH COMMAND
# ==============================================================================

def flash_command(args):
    """Handle the flash subcommand"""
    if not args.role or not args.platform:
        print_error("flash requires --role and --platform arguments")
        return 1
    
    print_info(f"Flashing {args.role} to {args.platform}...")
    
    # TODO: Implement actual flashing logic
    # This might involve:
    # 1. Finding the built executable
    # 2. Detecting or using specified serial port
    # 3. Calling appropriate flash tool (avrdude, openocd, etc.)
    
    flash_cmd = ["echo", "Flash command not yet implemented"]
    if args.port:
        flash_cmd.append(f"(port: {args.port})")
    
    result = subprocess.run(flash_cmd)
    
    if result.returncode == 0:
        print_success(f"Successfully flashed {args.role} to {args.platform}")
    else:
        print_error("Flash failed!")
    
    return result.returncode


# ==============================================================================
# RUN COMMAND
# ==============================================================================

def run_command(args):
    """Handle the run subcommand"""
    
    if args.target == "tests":
        print_info("Running unit tests...")
        
        # TODO: Implement test execution
        # Find and run test executables
        test_cmd = ["echo", "Test execution not yet implemented"]
        if args.test_name:
            test_cmd.append(f"(test: {args.test_name})")
        
        result = subprocess.run(test_cmd)
        return result.returncode
    
    elif args.target == "sim":
        print_info("Starting x86 simulation...")
        
        # TODO: Implement simulator launch
        sim_cmd = ["echo", "Simulator not yet implemented"]
        if args.debug:
            sim_cmd.append("(debug mode)")
        
        result = subprocess.run(sim_cmd)
        return result.returncode
    
    else:
        print_error(f"Unknown run target: {args.target}")
        return 1


# ==============================================================================
# PACKAGE COMMAND
# ==============================================================================

def package_command(args):
    """Handle the package subcommand"""
    if not args.package_name or not args.car_id or args.feature_number is None:
        print_error("package requires --package-name, --car-id, and --feature-number arguments")
        return 1
    
    print_info(f"Creating package '{args.package_name}'...")
    
    package_tool = HOST_TOOLS_DIR / "package_tool.py"
    
    if not package_tool.exists():
        print_error(f"Package tool not found at {package_tool}")
        return 1
    
    cmd = [
        sys.executable,
        str(package_tool),
        "--package-name", args.package_name,
        "--car-id", args.car_id,
        "--feature-number", str(args.feature_number)
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print_success(f"Package '{args.package_name}' created successfully!")
    else:
        print_error("Package creation failed!")
    
    return result.returncode


# ==============================================================================
# ENABLE COMMAND
# ==============================================================================

def enable_command(args):
    """Handle the enable subcommand"""
    if not args.package_name or not args.port:
        print_error("enable requires --package-name and --port arguments")
        return 1
    
    print_info(f"Enabling package '{args.package_name}' on {args.port}...")
    
    enable_tool = HOST_TOOLS_DIR / "enable_tool.py"
    
    if not enable_tool.exists():
        print_error(f"Enable tool not found at {enable_tool}")
        return 1
    
    cmd = [
        sys.executable,
        str(enable_tool),
        "--package-name", args.package_name,
        "--port", args.port
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print_success(f"Package '{args.package_name}' enabled successfully!")
    else:
        print_error("Enable failed!")
    
    return result.returncode


# ==============================================================================
# MONITOR COMMAND
# ==============================================================================

def monitor_command(args):
    """Handle the monitor/serial subcommand"""
    if not args.port:
        print_error("monitor requires --port argument")
        return 1
    
    print_info(f"Opening serial monitor on {args.port} at {args.baudrate} baud...")
    print_info("Press Ctrl+] to exit")
    
    # Use pyserial's miniterm or similar tool
    # You might want to use: python -m serial.tools.miniterm
    cmd = [
        sys.executable,
        "-m", "serial.tools.miniterm",
        args.port,
        str(args.baudrate)
    ]
    
    try:
        result = subprocess.run(cmd)
        return result.returncode
    except FileNotFoundError:
        print_error("pyserial not installed. Install with: pip install pyserial")
        print_info("Alternatively, use any serial terminal of your choice.")
        return 1


# ==============================================================================
# LIST COMMAND
# ==============================================================================

def list_command(args):
    """Handle the list subcommand"""
    
    if args.list_type == "platforms":
        print_info("Available platforms:")
        for platform in AVAILABLE_PLATFORMS:
            print(f"  • {platform}")
    
    elif args.list_type == "roles":
        print_info("Available roles:")
        for role in AVAILABLE_ROLES:
            print(f"  • {role}")
    
    elif args.list_type == "devices":
        print_info("Connected devices:")
        # TODO: Implement device detection
        # Could use pyserial.tools.list_ports
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            if ports:
                for port in ports:
                    print(f"  • {port.device}: {port.description}")
            else:
                print("  (no devices found)")
        except ImportError:
            print_warning("Install pyserial to detect devices: pip install pyserial")
    
    elif args.list_type == "builds":
        print_info("Build configurations:")
        # TODO: List available/built configurations
        if BUILD_DIR.exists():
            builds = list(BUILD_DIR.glob("*"))
            if builds:
                for build in builds:
                    print(f"  • {build.name}")
            else:
                print("  (no builds found)")
        else:
            print("  (build directory does not exist)")
    
    else:
        # List everything
        print_info("Project Information:")
        print(f"\n{Colors.BOLD}Platforms:{Colors.ENDC}")
        for platform in AVAILABLE_PLATFORMS:
            print(f"  • {platform}")
        
        print(f"\n{Colors.BOLD}Roles:{Colors.ENDC}")
        for role in AVAILABLE_ROLES:
            print(f"  • {role}")
        
        print(f"\n{Colors.BOLD}Connected Devices:{Colors.ENDC}")
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            if ports:
                for port in ports:
                    print(f"  • {port.device}: {port.description}")
            else:
                print("  (no devices found)")
        except ImportError:
            print("  (install pyserial to detect devices)")
    
    return 0


# ==============================================================================
# DEPLOY COMMAND
# ==============================================================================

def deploy_command(args):
    """Handle the deploy subcommand (build + flash)"""
    if not args.role or not args.platform:
        print_error("deploy requires --role and --platform arguments")
        return 1
    
    print_info(f"Deploying {args.role} to {args.platform}...")
    
    # First, build
    print_info("Step 1: Building...")
    build_result = build_command(args)
    
    if build_result != 0:
        print_error("Build failed, aborting deployment")
        return build_result
    
    # Then, flash
    print_info("Step 2: Flashing...")
    flash_result = flash_command(args)
    
    if flash_result == 0:
        print_success(f"Successfully deployed {args.role} to {args.platform}!")
    else:
        print_error("Deployment failed at flash stage")
    
    return flash_result


# ==============================================================================
# CONFIGURE COMMAND
# ==============================================================================

def configure_command(args):
    """Handle the configure subcommand"""
    print_info("Project configuration...")
    
    # TODO: Implement configuration
    # This could:
    # - Set up toolchain paths
    # - Configure default ports
    # - Set project-wide settings
    # - Create/edit a config file
    
    config_file = Path(".project_config")
    
    if args.show:
        if config_file.exists():
            print_info(f"Current configuration ({config_file}):")
            with open(config_file, 'r') as f:
                print(f.read())
        else:
            print_info("No configuration file found")
        return 0
    
    # Interactive configuration or specific setting
    print_warning("Configuration setup not yet implemented")
    print_info("Future options might include:")
    print("  • Toolchain paths")
    print("  • Default serial ports")
    print("  • Build optimization levels")
    print("  • Default IDs/PINs")
    
    return 0


# ==============================================================================
# DEBUG COMMAND
# ==============================================================================

def debug_command(args):
    """Handle the debug subcommand"""
    if not args.platform:
        print_error("debug requires --platform argument")
        return 1
    
    print_info(f"Starting debugger for {args.platform}...")
    
    # TODO: Implement debugger launch
    # This would launch GDB, OpenOCD, or other debugger based on platform
    
    if args.platform == "x86":
        debugger = "gdb"
    elif args.platform == "arm":
        debugger = "arm-none-eabi-gdb"
    elif args.platform == "avr":
        debugger = "avr-gdb"
    else:
        debugger = "gdb"
    
    print_info(f"Debugger: {debugger}")
    print_warning("Debug launch not yet implemented")
    
    # Example implementation might be:
    # cmd = [debugger, executable_path]
    # if args.port:
    #     cmd.extend(["--remote", args.port])
    # subprocess.run(cmd)
    
    return 0


# ==============================================================================
# MAIN ARGUMENT PARSER
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Project build and deployment orchestration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Global options
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without doing it")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # BUILD
    build_parser = subparsers.add_parser("build", help="Build project targets")
    build_parser.add_argument("--platform", choices=AVAILABLE_PLATFORMS,
                             help="Target platform")
    build_parser.add_argument("--role", choices=AVAILABLE_ROLES,
                             help="Target role")
    build_parser.add_argument("--id", type=str,
                             help="Device ID (required for car and paired_fob)")
    build_parser.add_argument("--pin", type=str,
                             help="Device PIN (required for paired_fob)")

    # Optional feature flags
    build_parser.add_argument("--unlock-flag", type=str, dest="unlock_flag",
                             help="Custom unlock flag value")
    build_parser.add_argument("--feature1-flag", type=str, dest="feature1_flag",
                             help="Custom feature 1 flag value")
    build_parser.add_argument("--feature2-flag", type=str, dest="feature2_flag",
                             help="Custom feature 2 flag value")
    build_parser.add_argument("--feature3-flag", type=str, dest="feature3_flag",
                             help="Custom feature 3 flag value")
    build_parser.add_argument("--test-build", action="store_true", dest="test_build",
                             help="Enable test commands in firmware")
    build_parser.set_defaults(func=build_command)
    
    # CLEAN (with 'nuke' alias)
    clean_parser = subparsers.add_parser("clean", aliases=["nuke"], 
                                         help="Clean build artifacts (use 'nuke' with no args to delete all)")
    clean_parser.add_argument("--platform", choices=AVAILABLE_PLATFORMS,
                             help="Target platform")
    clean_parser.add_argument("--role", choices=AVAILABLE_ROLES,
                             help="Target role")
    clean_parser.add_argument("--id", type=str,
                             help="Device ID (for car/paired_fob builds)")
    clean_parser.add_argument("--pin", type=str,
                             help="Device PIN (for paired_fob builds)")
    clean_parser.set_defaults(func=clean_command)
    
    # FLASH
    flash_parser = subparsers.add_parser("flash", help="Flash program to hardware")
    flash_parser.add_argument("--platform", choices=AVAILABLE_PLATFORMS,
                             required=True, help="Target platform")
    flash_parser.add_argument("--role", choices=AVAILABLE_ROLES,
                             required=True, help="Target role")
    flash_parser.add_argument("--port", type=str,
                             help="Serial port (auto-detect if not specified)")
    flash_parser.set_defaults(func=flash_command)
    
    # RUN
    run_parser = subparsers.add_parser("run", help="Run tests or simulation")
    run_parser.add_argument("target", choices=["tests", "sim"],
                           help="What to run")
    run_parser.add_argument("--test-name", type=str,
                           help="Specific test to run (for 'tests' target)")
    run_parser.add_argument("--debug", action="store_true",
                           help="Run in debug mode (for 'sim' target)")
    run_parser.set_defaults(func=run_command)
    
    # PACKAGE
    package_parser = subparsers.add_parser("package", help="Create feature package")
    package_parser.add_argument("--package-name", type=str, required=True,
                               help="Name of the package")
    package_parser.add_argument("--car-id", type=str, required=True,
                               help="Car ID")
    package_parser.add_argument("--feature-number", type=int, required=True,
                               help="Feature number")
    package_parser.set_defaults(func=package_command)
    
    # ENABLE
    enable_parser = subparsers.add_parser("enable", help="Enable feature package")
    enable_parser.add_argument("--package-name", type=str, required=True,
                              help="Name of the package to enable")
    enable_parser.add_argument("--port", type=str, required=True,
                              help="Serial port")
    enable_parser.set_defaults(func=enable_command)
    
    # MONITOR
    monitor_parser = subparsers.add_parser("monitor", help="Open serial monitor")
    monitor_parser.add_argument("--port", type=str, required=True,
                               help="Serial port")
    monitor_parser.add_argument("--baudrate", type=int, default=115200,
                               help="Baud rate (default: 115200)")
    monitor_parser.set_defaults(func=monitor_command)
    
    # LIST
    list_parser = subparsers.add_parser("list", help="List available options")
    list_parser.add_argument("list_type", nargs="?",
                            choices=["platforms", "roles", "devices", "builds"],
                            help="What to list (omit to list everything)")
    list_parser.set_defaults(func=list_command)
    
    # DEPLOY
    deploy_parser = subparsers.add_parser("deploy", help="Build and flash in one step")
    deploy_parser.add_argument("--platform", choices=AVAILABLE_PLATFORMS,
                              required=True, help="Target platform")
    deploy_parser.add_argument("--role", choices=AVAILABLE_ROLES,
                              required=True, help="Target role")
    deploy_parser.add_argument("--id", type=str,
                              help="Device ID (required for car and paired_fob)")
    deploy_parser.add_argument("--pin", type=str,
                              help="Device PIN (required for paired_fob)")
    deploy_parser.add_argument("--port", type=str,
                              help="Serial port (auto-detect if not specified)")
    deploy_parser.set_defaults(func=deploy_command)
    
    # CONFIGURE
    configure_parser = subparsers.add_parser("configure", help="Configure project settings")
    configure_parser.add_argument("--show", action="store_true",
                                 help="Show current configuration")
    configure_parser.set_defaults(func=configure_command)
    
    # DEBUG
    debug_parser = subparsers.add_parser("debug", help="Launch debugger")
    debug_parser.add_argument("--platform", choices=AVAILABLE_PLATFORMS,
                             required=True, help="Target platform")
    debug_parser.add_argument("--role", choices=AVAILABLE_ROLES,
                             help="Target role")
    debug_parser.add_argument("--port", type=str,
                             help="Debug port/interface")
    debug_parser.set_defaults(func=debug_command)
    
    # Parse arguments
    args = parser.parse_args()
    
    # If no command specified, print help
    if not args.command:
        parser.print_help()
        return 0
    
    # Execute the command
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n" + Colors.WARNING + "Interrupted by user" + Colors.ENDC)
        return 130
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())