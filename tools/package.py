#!/usr/bin/python3 -u

"""
Feature packaging utilities.

This module provides the core logic for creating feature packages.
Used by both tests (import directly) and CLI (via project.py).
"""

import argparse

def create_feature_package(car_id: bytes, feature_number: int) -> bytes:
    """
    Create a feature package for enabling a feature on a fob.
    
    Args:
        car_id: 8-byte car identifier (will be padded/truncated to 8 bytes)
        feature_number: Feature number (1-3)
    
    Returns:
        bytes: The packaged feature data, ready to send to fob's enable command
    
    Raises:
        ValueError: If feature_number is out of range
    """
    if not 1 <= feature_number <= 3:
        raise ValueError(f"feature_number must be 1-3, got {feature_number}")
    
    # Ensure car_id is exactly 11 bytes
    if isinstance(car_id, str):
        car_id = car_id.encode('ascii')
    car_id_padded = car_id.ljust(11, b'\x00')[:11]
    
    return car_id_padded + bytes([feature_number])


def save_feature_package(filepath: str, car_id: bytes, feature_number: int) -> None:
    """
    Create a feature package and save it to a file.
    
    Args:
        filepath: Path to write the package file
        car_id: 8-byte car identifier
        feature_number: Feature number (1-3)
    """
    package_data = create_feature_package(car_id, feature_number)
    if filepath is None:
        filepath = f"application/packages/{car_id}_{feature_number}"
    with open(filepath, 'wb') as f:
        f.write(package_data)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--id", help="Car ID the feature is being built for", type=str, required=True,
    )
    parser.add_argument(
        "--num", help="Feature number to be packaged", type=int, required=True,
    )
    parser.add_argument(
        "--out", help="File path and name, if not default", type=str, default=None
    )

    args = parser.parse_args()

    save_feature_package(args.out, args.id, args.num)


if __name__ == "__main__":
    main()