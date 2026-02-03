#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path

# Project configuration
AVAILABLE_ROLES = ["car", "paired_fob", "unpaired_fob", "all"]
AVAILABLE_PLATFORMS = ["stm32", "tm4c", "x86"]

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

################################################################################
##                                                                            ##
##  BUILD COMMAND                                                             ##
##                                                                            ##
################################################################################

def build_command(args):
    pass

def scons_command(args):
    # Validate arguments
    if args.verbose:
        print_info("Validating arguments")

    if args.role in ['car', 'paired_fob'] and args.id is None:
        print_error("Car ID is required when making a car or paired_fob")
        return 1

    if args.role == 'paired_fob' and args.pin is None:
        print_error("Pin is required when building a paired_fob")
        return 1

    # Determine build folder name
    if args.verbose:
        print_info("Creating build directory...")
    
    if args.role in ["car", "paired_fob"] and args.id:
        build_folder_name = f"{args.role}_{args.id}"
    else:
        build_folder_name = args.role
    
    # Create build folder
    build_folder = Path("hardware") / args.platform / "build" / build_folder_name
    build_folder.mkdir(parents=True, exist_ok=True)

    if args.verbose:
        print_info(f"...Build directory created: {build_folder}")

    # Prepare secret generation arguments
    if args.verbose:
        print_info(f"Generating secrets for {args.role}...")

    secret_file = Path("secrets") / "car_secrets.json"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    header_file = build_folder / "secrets.h"

    # Generate role secrets
    if args.role == "car":
        script = Path("tools") / "car_gen_secret.py"
        cmd = [
            sys.executable,
            str(script),
            "--car-id", str(args.id),
            "--secret-file", str(secret_file),
            "--header-file", str(header_file)
        ]
    elif args.role == "paired_fob":
        script = Path("tools") / "fob_gen_secret.py"
        cmd = [
            sys.executable,
            str(script),
            "--car-id", str(args.id),
            "--pair-pin", str(args.pin),
            "--secret-file", str(secret_file),
            "--header-file", str(header_file),
            "--paired"
        ]
    elif args.role == "unpaired_fob":
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
        print_error(f"Unknown role: {args.role}")
        return 1
    
    # Run secret generation script
    result = subprocess.run(cmd)

    if args.verbose:
        print_info(f"...Generated {header_file} using {script}")
    
    if result.returncode != 0:
        print_error(f"Secret generation failed for {args.role}")
        return result.returncode

    # Call scons
    cmd = ['scons', '-j5']
    cmd.extend([f'platform={args.platform}', f'role={args.role}', f'id={args.id}'])

    scons_args = args.scons_args
    if scons_args and scons_args[0] == "--":
        scons_args = scons_args[1:]
    cmd.extend(scons_args)

    if args.verbose:
        print_info(f"Running {' '.join(cmd)}")

    result = subprocess.run(cmd)
        
    if result.returncode != 0:
        print_error("Build failed!")
        return result.returncode
    
    if args.verbose:
        print_success("Build completed successfully!")

def car_id(value):
    this_id = int(value)
    if (this_id < 0) or (this_id > (2**32 - 1)):
        raise argparse.ArgumentTypeError(f"id must fit into a 32-bit unsigned integer")
    return this_id

def pin(value):
    if len(value) != 6:
        raise argparse.ArgumentTypeError(f"pin must be 6 digits")

    hex_chars = "0123456789abcdefABCDEF"
    if not all(char in hex_chars for char in value):
        raise argparse.ArgumentTypeError(f"pin must contain only hexadecmial digits ({hex_chars})")

    return value

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Project build and deployment orchestration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without doing it")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # BUILD
    build_parser = subparsers.add_parser("build", help="Build/clean project targets using SCons")
    build_parser.add_argument("--role", choices=AVAILABLE_ROLES, help=f"Target role")
    build_parser.add_argument("--platform", choices=AVAILABLE_PLATFORMS, help="Target platform")
    build_parser.add_argument("--id", type=car_id,
        help="Device ID (required for car and paired_fob)")
    build_parser.add_argument("--pin", type=pin,
        help="Device PIN (required for paired_fob)")
    build_parser.add_argument("scons_args", nargs=argparse.REMAINDER,
        help="Arguments passed directly to SCons. Run 'build -- -h' for more info.")
    build_parser.set_defaults(func=scons_command)

    # CLEAN

    # FLASH
    flash_parser = subparsers.add_parser("flash", help="Flash binary to hardware")

    # DEPLOY
    deploy_parser = subparsers.add_parser("deploy", help="Build and flash in one step")

    # DEBUG
    debug_parser = subparsers.add_parser("debug", help="Start openocd debug server and open gdbgui window")

    # Parse arguments
    args = parser.parse_args()
    
    # If no command specified, print help
    if not args.command:
        parser.print_help()
        exit(0)
    
    # Execute the command
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n" + Colors.WARNING + "Interrupted by user" + Colors.ENDC)
        exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        exit(1)