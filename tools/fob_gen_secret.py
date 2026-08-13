#!/usr/bin/python3 -u

# @file gen_secret
# @author Jake Grycel
# @brief Example script to generate header containing secrets for the fob
# @date 2023
#
# This source file is part of an example system for MITRE's 2023 Embedded CTF (eCTF).
# This code is being provided only for educational purposes for the 2023 MITRE eCTF
# competition, and may not meet MITRE standards for quality. Use this code at your
# own risk!
#
# @copyright Copyright (c) 2023 The MITRE Corporation

import json
import argparse
from pathlib import Path
import random


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--car-id", type=str)
    parser.add_argument("--pair-pin", type=str)
    parser.add_argument("--header-file", type=Path, required=True)
    parser.add_argument("--paired", action="store_true")
    parser.add_argument("--secrets-file", type=Path, required=True)
    args = parser.parse_args()

    # Open the secret file if it exists
    if args.secrets_file.exists():
        with open(args.secrets_file, "r") as fp:
            secrets = json.load(fp)
    else:
        secrets = {}

    secrets.setdefault("keys", {})

    if "feature_key" in secrets["keys"]:
        feature_key_array = secrets["keys"]["feature_key"]
    else:
        secrets["keys"]["feature_key"] = {}
        feature_key_array = list(random.randbytes(16))
        secrets["keys"]["feature_key"] = feature_key_array

    if args.paired:
        # Find car ID and matching key, if present
        if args.car_id in secrets["keys"]:
            unlock_key_array = secrets["keys"][args.car_id]["unlock"]

        # Else make a new key (and save it)
        else:
            secrets["keys"][args.car_id] = {}
            unlock_key_array = list(random.randbytes(16))
            secrets["keys"][args.car_id]["unlock"] = unlock_key_array

        # Write to header file
        with open(args.header_file, "w") as fp:
            fp.write("#ifndef __FOB_SECRETS__\n")
            fp.write("#define __FOB_SECRETS__\n\n")
            fp.write("#define PAIRED 1\n")
            fp.write(f'#define PAIR_PIN "{args.pair_pin}"\n')
            fp.write(f'#define CAR_ID "{args.car_id}"\n')
            fp.write('#define UNLOCK_KEY {')
            for i in range(15):
                fp.write(f'{unlock_key_array[i]}, ')
            fp.write(f'{unlock_key_array[15]}}}\n')
            fp.write('#define FEATURE_KEY {')
            for i in range(15):
                fp.write(f'{feature_key_array[i]}, ')
            fp.write(f'{feature_key_array[15]}}}\n')
            fp.write("\n#endif\n")
    else:
        # Write to header file
        with open(args.header_file, "w") as fp:
            fp.write("#ifndef __FOB_SECRETS__\n")
            fp.write("#define __FOB_SECRETS__\n\n")
            fp.write("#define PAIRED 0\n")
            fp.write('#define PAIR_PIN "000000"\n')
            fp.write('#define CAR_ID "000000"\n')
            fp.write("#define UNLOCK_KEY {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0}\n")
            fp.write('#define FEATURE_KEY {')
            for i in range(15):
                fp.write(f'{feature_key_array[i]}, ')
            fp.write(f'{feature_key_array[15]}}}\n')
            fp.write("\n#endif\n")

    # Save the new key
    args.secrets_file.parent.mkdir(parents=True, exist_ok=True)
    with open(args.secrets_file, "w") as fp:
        json.dump(secrets, fp, indent=4)

if __name__ == "__main__":
    main()
