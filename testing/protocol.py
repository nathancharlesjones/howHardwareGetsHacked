"""
Protocol definitions for car/fob serial communication.

Commands are sent as "{cmd}\n" or "{cmd} {args}\n".
Responses are "OK\n", "OK: {value}\n", or "ERROR: {reason}\n".

Standard Commands (production firmware):
    Fob:
        enable <hex_feature_pkg>  - Enable a packaged feature
        pair <pin>                - Initiate pairing (paired fob sends this)

Test Commands (TEST_BUILD only):
    Both:
        sendBoardMsg              - Transmits a message over a device's board UART
        getBoardMsgLog            - Returns the last 15 messages sent or received over the board UART
        reset                     - Factory reset (clear state, restart)

    Fob:
        btnPress                  - Simulate button press, blocks until unlock completes
        isPaired                  - Returns OK: 1 or OK: 0
        getFlashData              - Get flash data as hex
        setFlashData <hex>        - Set flash data from hex (persists to flash)
        getPairMemcmpTime         - Returns OK: <n> cycle count of the last PIN memcmp
        getFeatureMemcmpTime      - Returns OK: <n> cycle count of the last feature MAC memcmp

    Car:
        isLocked                  - Returns OK: 1 or OK: 0
        getUnlockCount            - Returns OK: <n> (resets on power cycle)
        getPrngSeed               - Returns OK: <32 hex chars> (16 bytes from getPrngSeed())
        restart                   - Warm restart (state not cleared); real reboot on TM4C/STM32 (stub on sim) --
                                    on hardware, must be followed by wait_for_boot() before the next command
        getEntropyDescription     - Returns OK: <json>, {source_name: bytes_per_sample} for every entropy source
        getEntropySamples <n>     - Returns OK: <hex>, n rows (n<=255); each row is one sample from every
                                    entropy source back to back, in getEntropyDescription()'s key order
"""

import json
import time
from dataclasses import dataclass
from typing import Optional

ACK_MAGIC      = 0x54
PAIR_MAGIC     = 0x55
UNLOCK_MAGIC   = 0x56
START_MAGIC    = 0x57
NONCE_MAGIC    = 0x58
RESPONSE_MAGIC = 0x59

MAGIC_NAMES = {
  0x54: "ACK",
  0x55: "PAIR",
  0x56: "UNLOCK",
  0x57: "START",
  0x58: "NONCE",
  0x59: "RESPONSE"
}

ACK_SUCCESS  = 1
ACK_FAIL     = 0

MAX_LOG_ENTRIES = 15
LOG_ENTRY_SIZE = 65  # sizeof(bool) + MAX_MSG_LEN = 1 + 64

# =============================================================================
# Board message Parsing
# =============================================================================

@dataclass
class BoardMsgEntry:
    tx: bool          # True = sent by this device, False = received
    magic: int
    message_len: int
    payload: bytes    # first message_len bytes are valid
    role: str = None  # "fob" or "car"; unlocks directional labels

    def __str__(self):
        if self.role == "fob":
            direction = "Fob --> Car" if self.tx else "Car --> Fob"
        elif self.role == "car":
            direction = "Car --> Fob" if self.tx else "Fob --> Car"
        else:
            direction = "TX" if self.tx else "RX"
        magic_name = MAGIC_NAMES.get(self.magic, f"0x{self.magic:02x}")
        return f"{direction}, {magic_name:>6}, {self.message_len:02x}, {self.payload!r}"

def parse_board_msg_log(hex_str: str, role: str = None) -> list[BoardMsgEntry]:
      """Parse getBoardMsgLog hex output into a list of log entries."""
      raw = bytes.fromhex(hex_str)
      expected_len = MAX_LOG_ENTRIES * LOG_ENTRY_SIZE
      if len(raw) != expected_len:
          raise RuntimeError(
              f"getBoardMsgLog response truncated: got {len(raw)} bytes, "
              f"expected {expected_len}. Not a firmware bug - the firmware "
              f"always sends a fixed-size buffer. Most likely a short write "
              f"somewhere in the transport (e.g. a non-blocking write() that "
              f"silently drops bytes when a destination buffer is full)."
          )
      entries = []
      for i in range(MAX_LOG_ENTRIES):
          offset = i * LOG_ENTRY_SIZE
          entry_bytes = raw[offset:offset + LOG_ENTRY_SIZE]
          tx = bool(entry_bytes[0])
          magic = entry_bytes[1]
          message_len = entry_bytes[2]
          payload = entry_bytes[3:3 + message_len]
          entries.append(BoardMsgEntry(tx=tx, magic=magic, message_len=message_len, payload=payload, role=role))
      return entries

# =============================================================================
# Response Parsing
# =============================================================================

@dataclass
class Response:
    success: bool
    value: Optional[str] = None
    error: Optional[str] = None
    
    def __bool__(self):
        return self.success


def parse_response(line: str) -> Response:
    """Parse a response line into a Response object."""
    if line is None or line == "":
        return Response(success=False, error="timeout")

    line = line.strip().lstrip('\x00')

    if line == "":
        return Response(success=False, error="timeout")

    if line.startswith("OK"):
        if line == "OK":
            return Response(success=True)
        elif line.startswith("OK: "):
            return Response(success=True, value=line[4:])

    if line.startswith("ERROR: "):
        return Response(success=False, error=line[7:])

    return Response(success=False, error=f"Unparseable: {line}")


# =============================================================================
# FLASH_DATA Structure Handling
# =============================================================================

# From dataFormats.h:
#   typedef struct __attribute__((aligned(4))) {
#     uint8_t paired;           // offset 0
#     PAIR_PACKET pair_info;    // offset 1:  car_id[11], key[16], pin[3]  = 30 bytes
#     FEATURE_DATA feature_info;// offset 31: car_id[11], num_active, features[3] = 15 bytes
#   } FOB_FLASH_DATA;           // 46 bytes content, padded to 48

FLASH_DATA_SIZE = 48  # sizeof(FOB_FLASH_DATA)

NUM_FEATURES = 3


@dataclass
class PairPacket:
    car_id: bytes   # 11 bytes
    key: bytes      # 16 bytes
    pin: bytes      # 3 bytes

    def pack(self) -> bytes:
        return self.car_id.ljust(11, b'\x00')[:11] + \
               self.key.ljust(16, b'\x00')[:16] + \
               self.pin.ljust(3, b'\x00')[:3]

    @classmethod
    def unpack(cls, data: bytes) -> 'PairPacket':
        return cls(
            car_id=data[0:11],
            key=data[11:27],
            pin=data[27:30]
        )


@dataclass
class FeatureData:
    car_id: bytes      # 11 bytes
    num_active: int    # 1 byte
    features: list     # 3 bytes (feature flags/indices)
    
    def pack(self) -> bytes:
        feat_bytes = bytes(self.features[:NUM_FEATURES]).ljust(NUM_FEATURES, b'\x00')
        return self.car_id.ljust(11, b'\x00')[:11] + \
               bytes([self.num_active]) + \
               feat_bytes
    
    @classmethod
    def unpack(cls, data: bytes) -> 'FeatureData':
        return cls(
            car_id=data[0:11],
            num_active=data[11],
            features=list(data[12:15])
        )


@dataclass
class FlashData:
    paired: int
    pair_info: PairPacket
    feature_info: FeatureData

    def pack(self) -> bytes:
        """Pack to bytes for setFlashData command."""
        data = bytes([self.paired]) + \
               self.pair_info.pack() + \
               self.feature_info.pack()
        return data.ljust(FLASH_DATA_SIZE, b'\x00')

    @classmethod
    def unpack(cls, data: bytes) -> 'FlashData':
        """Unpack from bytes received from getFlashData."""
        return cls(
            paired=data[0],
            pair_info=PairPacket.unpack(data[1:31]),
            feature_info=FeatureData.unpack(data[31:46])
        )

    @classmethod
    def from_hex(cls, hex_str: str) -> 'FlashData':
        """Parse from hex string (as returned by getFlashData)."""
        return cls.unpack(bytes.fromhex(hex_str))

    def to_hex(self) -> str:
        """Convert to hex string (for setFlashData command)."""
        return self.pack().hex()

    @classmethod
    def new_unpaired(cls) -> 'FlashData':
        """Create a fresh unpaired fob state."""
        return cls(
            paired=False,
            pair_info=PairPacket(b'\x00'*11, b'\x00'*16, b'\x00'*3),
            feature_info=FeatureData(b'\x00'*11, 0, [0, 0, 0])
        )

    @classmethod
    def new_paired(cls, car_id: bytes, key: bytes, pin: bytes) -> 'FlashData':
        """Create a paired fob state."""
        return cls(
            paired=True,
            pair_info=PairPacket(car_id, key, pin),
            feature_info=FeatureData(car_id, 0, [0, 0, 0])
        )


# =============================================================================
# Standard Commands (Production)
# =============================================================================

def cmd_enable(device, feature_package: bytes, timeout: float = 5.0) -> Response:
    """
    Enable a packaged feature on the fob.
    
    Args:
        device: DeployedDevice (fob)
        feature_package: The packaged feature data
    
    Returns:
        Response with success/error
    """
    hex_data = feature_package.hex()
    return parse_response(device.send_recv(f"enable {hex_data}", timeout=timeout))


def cmd_pair(device, pin: str, timeout: float = 2.0) -> Response:
    """
    Initiate pairing from a paired fob.
    
    The paired fob validates the PIN and sends pairing data to the
    unpaired fob over the board UART.
    
    Args:
        device: DeployedDevice (paired fob)
        pin: 6-digit PIN string
    
    Returns:
        Response with success/error
    """
    return parse_response(device.send_recv(f"pair {pin}", timeout=timeout))


# =============================================================================
# Test Commands (TEST_BUILD only)
# =============================================================================

# --- Both Car and Fob ---

def cmd_send_board_msg(device, magic: int, payload: bytes, timeout: float = 2.0) -> Response:
    """Inject a raw board message via the sendBoardMsg test command."""
    raw = bytes([magic, len(payload)]) + payload
    return parse_response(device.send_recv(f"sendBoardMsg {raw.hex()}", timeout=timeout))

def cmd_get_board_msg_log(device, role: str = None, timeout: float = 5.0) -> list[BoardMsgEntry]:
    """Get and parse the board message log."""
    resp = parse_response(device.send_recv("getBoardMsgLog", timeout=timeout))
    if not resp.success:
        raise RuntimeError(f"getBoardMsgLog failed: {resp.error}")
    return parse_board_msg_log(resp.value, role=role)

def cmd_reset(device, timeout: float = 5.0) -> Response:
    """
    Factory reset - restore to initial factory state.

    For paired fob: restores original PIN/car_id credentials, clears features
    For unpaired fob: clears pair data, returns to unpaired state
    For car: resets unlock count, re-locks
    """
    return parse_response(device.send_recv("reset", timeout=timeout))


# --- Fob Only ---

def cmd_btn_press(device, timeout: float = 5.0) -> Response:
    """
    Simulate button press on fob to initiate unlock sequence.
    
    Blocks until unlock completes or fails.
    
    Args:
        device: DeployedDevice (fob)
        timeout: Max time to wait for unlock to complete
    
    Returns:
        Response: OK if car unlocked, ERROR: reason if failed
    """
    return parse_response(device.send_recv("btnPress", timeout=timeout))


def cmd_get_flash_data(device, timeout: float = 2.0) -> Response:
    """
    Get fob's FLASH_DATA as hex string.
    
    Returns:
        Response with value=hex string on success
    """
    return parse_response(device.send_recv("getFlashData", timeout=timeout))


def cmd_set_flash_data(device, flash_data: FlashData, timeout: float = 5.0) -> Response:
    """
    Set fob's FLASH_DATA and persist to flash.
    
    Args:
        device: DeployedDevice (fob)
        flash_data: FlashData object to write
    
    Returns:
        Response with success/error
    """
    hex_data = flash_data.to_hex()
    return parse_response(device.send_recv(f"setFlashData {hex_data}", timeout=timeout))


def cmd_is_paired(device, timeout: float = 2.0) -> Response:
    """
    Check if fob is paired.
    
    Returns:
        Response with value="1" if paired, "0" if not
    """
    return parse_response(device.send_recv("isPaired", timeout=timeout))


def get_flash_data(device, timeout: float = 2.0) -> FlashData:
    """
    Convenience: get and parse FLASH_DATA.

    Raises:
        RuntimeError: if command fails
    """
    resp = cmd_get_flash_data(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getFlashData failed: {resp.error}")
    return FlashData.from_hex(resp.value)


def is_paired(device, timeout: float = 2.0) -> bool:
    """Convenience: check if fob is paired."""
    resp = cmd_is_paired(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"isPaired failed: {resp.error}")
    return resp.value == "1"


def wait_until_paired(device, timeout: float = 5.0, interval: float = 0.25) -> bool:
    """Poll isPaired until true or timeout expires. Returns True if paired, False if timed out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if is_paired(device):
                return True
        except RuntimeError:
            pass  # device busy (e.g. mid-saveFobState); keep polling
        time.sleep(interval)
    return False


def cmd_get_pair_memcmp_time(device, timeout: float = 2.0) -> Response:
    """
    Get the cycle count of the most recent PIN memcmp in pairFob().

    Returns:
        Response with value=cycle count as decimal string
    """
    return parse_response(device.send_recv("getPairMemcmpTime", timeout=timeout))


def get_pair_memcmp_time(device, timeout: float = 2.0) -> int:
    """Convenience: get the last PIN memcmp cycle count as an int."""
    resp = cmd_get_pair_memcmp_time(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getPairMemcmpTime failed: {resp.error}")
    return int(resp.value)


def cmd_get_feature_memcmp_time(device, timeout: float = 2.0) -> Response:
    """
    Get the cycle count of the most recent feature MAC memcmp in enableFeature().

    Returns:
        Response with value=cycle count as decimal string
    """
    return parse_response(device.send_recv("getFeatureMemcmpTime", timeout=timeout))


def get_feature_memcmp_time(device, timeout: float = 2.0) -> int:
    """Convenience: get the last feature MAC memcmp cycle count as an int."""
    resp = cmd_get_feature_memcmp_time(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getFeatureMemcmpTime failed: {resp.error}")
    return int(resp.value)


# --- Car Only ---

def cmd_is_locked(device, timeout: float = 2.0) -> Response:
    """
    Check if car is locked.
    
    Returns:
        Response with value="1" if locked, "0" if unlocked
    """
    return parse_response(device.send_recv("isLocked", timeout=timeout))


def cmd_get_unlock_count(device, timeout: float = 2.0) -> Response:
    """
    Get number of successful unlocks since boot.
    
    This value resets on power cycle (not persisted).
    
    Returns:
        Response with value=count as string
    """
    return parse_response(device.send_recv("getUnlockCount", timeout=timeout))


def is_locked(device, timeout: float = 2.0) -> bool:
    """Convenience: check if car is locked."""
    resp = cmd_is_locked(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"isLocked failed: {resp.error}")
    return resp.value == "1"


def get_unlock_count(device, timeout: float = 2.0) -> int:
    """Convenience: get unlock count as int."""
    resp = cmd_get_unlock_count(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getUnlockCount failed: {resp.error}")
    return int(resp.value)



def cmd_get_prng_seed(device, timeout: float = 2.0) -> Response:
    """Get 16 bytes of seed material from getPrngSeed() as a 32-char hex string."""
    return parse_response(device.send_recv("getPrngSeed", timeout=timeout))


def get_prng_seed(device, timeout: float = 2.0) -> bytes:
    """Convenience: get getPrngSeed() output as bytes."""
    resp = cmd_get_prng_seed(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getPrngSeed failed: {resp.error}")
    return bytes.fromhex(resp.value)


def cmd_restart(device, timeout: float = 5.0) -> Response:
    """
    Warm-restart the device (unlike cmd_reset, does not clear persisted state).

    Sends "OK\\n" then reboots on TM4C/STM32 (SysCtlReset()/NVIC_SystemReset());
    sim's restart() remains an empty stub and does not reboot. On hardware,
    callers MUST follow this with wait_for_boot() before sending another
    command -- the reboot prints an unprompted "OK: started" banner (the same
    one deploy() waits for after flashing), and if it isn't drained first it
    sits in the serial buffer and gets misread as the response to whatever
    command is sent next.
    """
    print("DEBUG cmd_restart: about to send_recv('restart')")
    result = parse_response(device.send_recv("restart", timeout=timeout))
    print(f"DEBUG cmd_restart: got {result!r}")
    return result


def wait_for_boot(device, timeout: float = 5.0) -> None:
    """
    Block until the device's post-boot "OK: started" banner arrives.

    Must be called after cmd_restart() on hardware, before sending any other
    command -- see cmd_restart()'s docstring for why.
    """
    print("DEBUG wait_for_boot: about to recv()")
    line = device.recv(timeout=timeout)
    print(f"DEBUG wait_for_boot: got {line!r}")
    if "OK: started" not in line:
        raise RuntimeError(f"Device didn't report a clean restart, got: '{line}'")


# --- Car Only: entropy source sampling ---

def cmd_get_entropy_description(device, timeout: float = 2.0) -> Response:
    """Get the JSON description of hardware entropy sources on this platform."""
    return parse_response(device.send_recv("getEntropyDescription", timeout=timeout))


def get_entropy_description(device, timeout: float = 2.0) -> dict:
    """
    Convenience: get an ordered {source_name: bytes_per_sample} mapping.

    Key order matches the byte layout getEntropySamples() actually writes --
    each "row" is one sample from every source, back to back, in this same
    order (see getEntropyDescription()/getEntropySamples() in
    hardware/*/source/*.c). Needed to split a raw row stream back into
    per-source sequences; see entropy_assessment.deinterleave().
    """
    resp = cmd_get_entropy_description(device, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getEntropyDescription failed: {resp.error}")
    return json.loads(resp.value)


def cmd_get_entropy_samples(device, num_samples: int, timeout: float = 5.0) -> Response:
    """
    Get `num_samples` rows, hex-encoded; each row is one sample from every
    entropy source back to back (see get_entropy_description() for order/widths).

    num_samples is capped at 255 by the firmware's uint8_t parameter; use
    get_entropy_samples() (single call) or collect_entropy_samples() (chunked,
    for large collections) instead of calling this directly with num_samples > 255.
    """
    return parse_response(device.send_recv(f"getEntropySamples {num_samples}", timeout=timeout))


def get_entropy_samples(device, num_samples: int, timeout: float = 5.0) -> bytes:
    """Convenience: get raw interleaved row bytes for one command (num_samples must be 0-255)."""
    if not (0 <= num_samples <= 255):
        raise ValueError("num_samples must be 0-255 per call; see collect_entropy_samples()")
    resp = cmd_get_entropy_samples(device, num_samples, timeout=timeout)
    if not resp.success:
        raise RuntimeError(f"getEntropySamples failed: {resp.error}")
    return bytes.fromhex(resp.value) if resp.value else b""


def collect_entropy_samples(device, count: int, timeout: float = 5.0,
                             show_progress: bool = False) -> bytes:
    """
    Collect `count` consecutive interleaved rows (one sample from every
    entropy source per row), chunked into <=255-row requests to stay within
    the firmware's uint8_t parameter.

    With show_progress=True, renders a single self-overwriting progress bar
    line (needs pytest -s) instead of printing one line per chunk -- a
    1,000,000-row collection is ~3900 chunks, too many to print separately.

    Returns the raw concatenated row bytes (row_width * count bytes total).
    """
    out = bytearray()
    remaining = count
    collected = 0
    while remaining > 0:
        chunk = min(remaining, 255)
        out += get_entropy_samples(device, chunk, timeout=timeout)
        remaining -= chunk
        collected += chunk
        if show_progress:
            frac = collected / count
            bar = "#" * int(frac * 30) + "-" * (30 - int(frac * 30))
            print(f"\r  [{bar}] {collected}/{count}", end="", flush=True)
    if show_progress:
        print()
    return bytes(out)