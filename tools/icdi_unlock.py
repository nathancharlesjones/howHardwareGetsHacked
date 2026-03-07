#!/usr/bin/env python3
"""
icdi_unlock.py - Send "debug unlock" to a TI ICDI over USB, bypassing OpenOCD.

Implements the GDB Remote Serial Protocol (RSP) qRcmd packet directly against
the TI ICDI USB endpoints, matching what OpenOCD's ti_icdi_usb.c would do if
it didn't abort during init when the target is locked.

The ICDI uses:
  VID 0x1cbe / PID 0x00fd
  Interface 2
  Bulk OUT EP 0x02  (host → ICDI)
  Bulk IN  EP 0x83  (ICDI → host)

After this script completes, power-cycle the LaunchPad to finish the recovery.
Flash and EEPROM will be mass-erased; non-volatile registers restored to defaults.

Usage:
  python3 icdi_unlock.py [--serial 0E236CE6] [--dry-run]

Dependencies:
  pip install pyusb
  # Linux also needs udev rules or root; run with sudo or add udev rule:
  # SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", ATTR{idProduct}=="00fd", MODE="0666"
"""

import argparse
import sys
import time

try:
    import usb.core
    import usb.util
    import usb.backend.libusb1
except ImportError:
    print("ERROR: pyusb not found. Install with: pip install pyusb")
    sys.exit(1)

# ICDI USB identifiers (from ti_icdi_usb.c)
ICDI_VID = 0x1cbe
ICDI_PID = 0x00fd
ICDI_INTERFACE = 2
ICDI_EP_OUT = 0x02
ICDI_EP_IN = 0x83
ICDI_TIMEOUT_MS = 5000
ICDI_MAX_PACKET = 4096


def gdb_checksum(data: bytes) -> int:
    """GDB RSP checksum: sum of bytes mod 256."""
    return sum(data) % 256


def build_qrcmd(cmd: str) -> bytes:
    """
    Build a GDB RSP $qRcmd,<hex_cmd>#XX packet.

    The command string is hex-encoded (ASCII hex of each byte), matching
    icdi_send_remote_cmd() in ti_icdi_usb.c.
    """
    hex_cmd = cmd.encode("ascii").hex()
    payload = f"qRcmd,{hex_cmd}".encode("ascii")
    chk = gdb_checksum(payload)
    return b"$" + payload + f"#{chk:02x}".encode("ascii")


def open_icdi(serial: str | None) -> usb.core.Device:
    """Find and open the ICDI device, detaching the kernel driver if needed."""
    devices = list(usb.core.find(idVendor=ICDI_VID, idProduct=ICDI_PID, find_all=True))
    if not devices:
        print("ERROR: No TI ICDI device found (VID 0x1cbe / PID 0x00fd).")
        print("  Is the LaunchPad plugged in?  Try running with sudo.")
        sys.exit(1)

    if serial:
        matched = [d for d in devices if usb.util.get_string(d, d.iSerialNumber) == serial]
        if not matched:
            found = [usb.util.get_string(d, d.iSerialNumber) for d in devices]
            print(f"ERROR: No ICDI with serial '{serial}'. Found: {found}")
            sys.exit(1)
        dev = matched[0]
    elif len(devices) > 1:
        serials = [usb.util.get_string(d, d.iSerialNumber) for d in devices]
        print(f"ERROR: Multiple ICDI devices found: {serials}")
        print("  Use --serial <SN> to select one.")
        sys.exit(1)
    else:
        dev = devices[0]

    sn = usb.util.get_string(dev, dev.iSerialNumber)
    print(f"Found ICDI device (serial: {sn})")

    # Detach kernel driver from interface 2 if it has claimed it
    if dev.is_kernel_driver_active(ICDI_INTERFACE):
        print(f"Detaching kernel driver from interface {ICDI_INTERFACE}...")
        dev.detach_kernel_driver(ICDI_INTERFACE)

    # The ICDI is a composite device; the kernel already configured it.
    # Calling set_configuration() on an active composite device raises EBUSY.
    # Just claim the interface we need directly.
    usb.util.claim_interface(dev, ICDI_INTERFACE)
    print(f"Claimed interface {ICDI_INTERFACE}")
    return dev


def usb_write(dev: usb.core.Device, data: bytes) -> None:
    n = dev.write(ICDI_EP_OUT, data, ICDI_TIMEOUT_MS)
    if n != len(data):
        raise IOError(f"Short write: sent {n} of {len(data)} bytes")


def usb_read(dev: usb.core.Device, length: int = ICDI_MAX_PACKET) -> bytes:
    return bytes(dev.read(ICDI_EP_IN, length, ICDI_TIMEOUT_MS))


def send_ack(dev: usb.core.Device) -> None:
    usb_write(dev, b"+")


def send_packet(dev: usb.core.Device, packet: bytes, label: str = "") -> str:
    """
    Send a GDB RSP packet, handle ACK/NAK, and return the reply body.

    Protocol (from ti_icdi_usb.c icdi_send_packet / icdi_usb_read_mem):
      1. Write the packet bytes to EP OUT.
      2. Read EP IN — first byte(s) may be the ACK ('+' or '-').
      3. If the response also contains '$..#xx', parse it as the reply packet.
      4. Send '+' ACK for the reply.
    """
    if label:
        print(f"  TX [{label}]: {packet.decode('ascii', errors='replace')}")

    usb_write(dev, packet)
    time.sleep(0.05)

    # Read response — may include the '+' ACK and the reply packet together
    raw = usb_read(dev)
    if label:
        print(f"  RX [{label}]: {raw.decode('ascii', errors='replace')!r}")

    if not raw:
        raise IOError("Empty response from ICDI")

    # Strip leading ACK/NAK bytes
    i = 0
    while i < len(raw) and raw[i:i+1] in (b"+", b"-"):
        if raw[i:i+1] == b"-":
            raise IOError("ICDI sent NAK — packet rejected")
        i += 1

    reply_raw = raw[i:]
    if not reply_raw:
        # ACK only — no packet yet; read again
        reply_raw = usb_read(dev)
        if label:
            print(f"  RX2[{label}]: {reply_raw.decode('ascii', errors='replace')!r}")

    # Parse $<body>#XX
    if reply_raw.startswith(b"$"):
        hash_pos = reply_raw.rfind(b"#")
        if hash_pos != -1:
            body = reply_raw[1:hash_pos].decode("ascii", errors="replace")
            # Send ACK for the reply packet
            send_ack(dev)
            return body
        else:
            # Incomplete packet
            return reply_raw.decode("ascii", errors="replace")
    else:
        return reply_raw.decode("ascii", errors="replace")


def main():
    parser = argparse.ArgumentParser(description="Send 'debug unlock' to TI ICDI via USB")
    parser.add_argument("--serial", help="ICDI serial number (e.g. 0E236CE6)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Open device and send 'version' only — do not send unlock")
    args = parser.parse_args()

    print("=" * 60)
    print(" TM4C123GH6PM ICDI Debug Unlock")
    print(" Sends qRcmd,'debug unlock' directly via USB (pyusb)")
    print("=" * 60)
    print()

    if args.dry_run:
        print("DRY-RUN MODE: will only send 'version' command, not 'debug unlock'")
        print()

    dev = open_icdi(args.serial)
    print()

    try:
        # Step 1: Send 'version' to verify the ICDI USB channel is up.
        # On a locked device the ICDI firmware itself is still alive — it just
        # can't reach the target debug port.  The version command is handled
        # entirely in the ICDI MCU, so it should succeed regardless.
        print("Step 1: Querying ICDI version...")
        pkt = build_qrcmd("version")
        try:
            reply = send_packet(dev, pkt, label="version")
            # Reply body is hex-encoded ASCII text
            try:
                decoded = bytes.fromhex(reply).decode("ascii", errors="replace")
            except ValueError:
                decoded = reply
            print(f"  Version reply: {decoded!r}")
        except Exception as e:
            print(f"  WARNING: version query failed ({e})")
            print("  Continuing anyway — the unlock command may still work.")
        print()

        if args.dry_run:
            print("Dry-run complete. Exiting without sending unlock.")
            return

        # Step 2: Send 'debug unlock'.
        # This is the same string that OpenOCD's stellaris_handle_recover_command
        # passes to hla_command(), which calls icdi_send_remote_cmd() internally.
        print("Step 2: Sending 'debug unlock'...")
        print("  WARNING: This will MASS ERASE flash and EEPROM. No undo.")
        print()
        pkt = build_qrcmd("debug unlock")
        try:
            reply = send_packet(dev, pkt, label="debug unlock")
            try:
                decoded = bytes.fromhex(reply).decode("ascii", errors="replace")
            except ValueError:
                decoded = reply
            print(f"  Reply: {decoded!r}")
            if "OK" in reply.upper() or "ok" in decoded.lower():
                print("  => ICDI acknowledged the unlock command.")
            else:
                print("  => Reply received (see above). The ICDI may have")
                print("     accepted the command even without an explicit OK.")
        except Exception as e:
            print(f"  ERROR during unlock: {e}")
            print("  The command may have been partially processed.")
            print("  Power-cycle and try connecting normally before giving up.")

        print()
        print("=" * 60)
        print("DONE.  Now POWER-CYCLE the LaunchPad (unplug USB, replug).")
        print()
        print("After power-cycle:")
        print("  - Flash and EEPROM will have been mass-erased")
        print("  - Non-volatile registers restored to factory defaults")
        print("  - Normal OpenOCD/flashing will work again")
        print("=" * 60)

    finally:
        usb.util.release_interface(dev, ICDI_INTERFACE)
        usb.util.dispose_resources(dev)
        print()
        print("USB interface released.")


if __name__ == "__main__":
    main()
