#!/usr/bin/python3 -u

"""
Feature packaging utilities.

This module provides the core logic for creating feature packages.
Used by both tests (import directly) and CLI (via project.py).
"""

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms

CAR_ID_LEN = 11
MAC_LEN = 8
DEFAULT_SECRETS_FILE = "secrets/secrets.json"


@dataclass
class FeaturePackage:
    """
    On-the-wire layout of a feature-enable package sent to a fob:
    car_id (11 bytes, NUL-padded) + feature (1 byte) + MAC (16 bytes,
    AES-CMAC over the preceding 12 bytes, keyed with the car's key).
    """
    car_id: bytes
    feature: int
    mac: bytes

    def pack(self) -> bytes:
        return self.car_id + bytes([self.feature]) + self.mac

    @classmethod
    def unpack(cls, data: bytes) -> "FeaturePackage":
        expected_len = CAR_ID_LEN + 1 + MAC_LEN
        if len(data) != expected_len:
            raise ValueError(f"expected {expected_len} bytes, got {len(data)}")
        return cls(
            car_id=data[:CAR_ID_LEN],
            feature=data[CAR_ID_LEN],
            mac=data[CAR_ID_LEN + 1:],
        )


def create_feature_package(car_id: bytes, feature_number: int, secrets_file: str = None) -> bytes:
    """
    Create a feature package for enabling a feature on a fob.

    The package is authenticated with an AES-CMAC computed over the car ID
    and feature number, keyed with the fleet-wide feature key, so a fob can
    reject any package that was tampered with after packaging.

    Args:
        car_id: Car identifier (str, or bytes as returned by protocol flash reads)
        feature_number: Feature number (1-3)
        secrets_file: Path to secrets.json holding the fleet-wide feature key.
            Defaults to $TEST_SECRETS_FILE (set by the test suite) or
            secrets/secrets.json.

    Returns:
        bytes: The packaged feature data, ready to send to fob's enable command

    Raises:
        ValueError: If feature_number is out of range, or the feature key can't be found
    """
    if not 1 <= feature_number <= 3:
        raise ValueError(f"feature_number must be 1-3, got {feature_number}")

    if isinstance(car_id, bytes):
        car_id = car_id.rstrip(b'\x00').decode('ascii')
    car_id_padded = car_id.encode('ascii').ljust(CAR_ID_LEN, b'\x00')[:CAR_ID_LEN]

    secrets_file = secrets_file or os.environ.get("TEST_SECRETS_FILE", DEFAULT_SECRETS_FILE)
    try:
        with open(secrets_file, "r") as fp:
            secrets = json.load(fp)
            key = bytes(secrets["keys"]["feature_key"])
    except (OSError, KeyError, json.JSONDecodeError) as e:
        raise ValueError(
            f"Could not locate secrets file ({secrets_file}), or could not locate the fleet-wide feature key"
        ) from e

    c = cmac.CMAC(algorithms.AES(key))
    c.update(car_id_padded + bytes([feature_number]))
    mac = c.finalize()

    return FeaturePackage(car_id_padded, feature_number, mac[-8:]).pack()


def save_feature_package(filepath: str, car_id: bytes, feature_number: int, secrets_file: str = None) -> None:
    """
    Create a feature package and save it to a file.

    Args:
        filepath: Path to write the package file
        car_id: Car identifier
        feature_number: Feature number (1-3)
        secrets_file: Path to secrets.json holding the car's key
    """
    package_data = create_feature_package(car_id, feature_number, secrets_file)
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
        "--out", help="File path and name for feature, if not default", type=str, default=None
    )
    parser.add_argument(
        "--secrets-file", help="Path to secrets.json containing the car's key", type=Path,
        default=Path(os.environ.get("TEST_SECRETS_FILE", DEFAULT_SECRETS_FILE)),
    )

    args = parser.parse_args()

    save_feature_package(args.out, args.id, args.num, str(args.secrets_file))


if __name__ == "__main__":
    main()
