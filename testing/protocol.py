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
        restart                   - Software reset (re-run main, state persists)
        reset                     - Factory reset (clear state, restart)
    
    Fob:
        btnPress                  - Simulate button press, blocks until unlock completes
        getFlashData              - Get FLASH_DATA as hex
        setFlashData <hex>        - Set FLASH_DATA from hex (persists to flash)
        isPaired                  - Returns OK: 1 or OK: 0
    
    Car:
        isLocked                  - Returns OK: 1 or OK: 0
        getUnlockCount            - Returns OK: <n> (resets on power cycle)
"""

from dataclasses import dataclass
from typing import Optional


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
    line = line.strip()
    
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
#   typedef struct {
#     uint8_t paired;
#     PAIR_PACKET pair_info;    // car_id[8], password[8], pin[8]
#     FEATURE_DATA feature_info; // car_id[8], num_active, features[3]
#   } FLASH_DATA;
#
# Total: 1 + 24 + 12 = 37 bytes (but aligned to 4, so likely 40 bytes)

FLASH_DATA_SIZE = 40  # Adjust based on actual sizeof(FLASH_DATA)

NUM_FEATURES = 3


@dataclass
class PairPacket:
    car_id: bytes      # 8 bytes
    password: bytes    # 8 bytes
    pin: bytes         # 8 bytes
    
    def pack(self) -> bytes:
        return self.car_id.ljust(8, b'\x00')[:8] + \
               self.password.ljust(8, b'\x00')[:8] + \
               self.pin.ljust(8, b'\x00')[:8]
    
    @classmethod
    def unpack(cls, data: bytes) -> 'PairPacket':
        return cls(
            car_id=data[0:8],
            password=data[8:16],
            pin=data[16:24]
        )


@dataclass
class FeatureData:
    car_id: bytes      # 8 bytes
    num_active: int    # 1 byte
    features: list     # 3 bytes (feature flags/indices)
    
    def pack(self) -> bytes:
        feat_bytes = bytes(self.features[:NUM_FEATURES]).ljust(NUM_FEATURES, b'\x00')
        return self.car_id.ljust(8, b'\x00')[:8] + \
               bytes([self.num_active]) + \
               feat_bytes
    
    @classmethod
    def unpack(cls, data: bytes) -> 'FeatureData':
        return cls(
            car_id=data[0:8],
            num_active=data[8],
            features=list(data[9:12])
        )


@dataclass
class FlashData:
    paired: bool
    pair_info: PairPacket
    feature_info: FeatureData
    
    def pack(self) -> bytes:
        """Pack to bytes for setFlashData command."""
        data = bytes([1 if self.paired else 0]) + \
               self.pair_info.pack() + \
               self.feature_info.pack()
        # Pad to aligned size
        return data.ljust(FLASH_DATA_SIZE, b'\x00')
    
    @classmethod
    def unpack(cls, data: bytes) -> 'FlashData':
        """Unpack from bytes received from getFlashData."""
        return cls(
            paired=data[0] != 0,
            pair_info=PairPacket.unpack(data[1:25]),
            feature_info=FeatureData.unpack(data[25:37])
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
            pair_info=PairPacket(b'\x00'*8, b'\x00'*8, b'\x00'*8),
            feature_info=FeatureData(b'\x00'*8, 0, [0, 0, 0])
        )
    
    @classmethod
    def new_paired(cls, car_id: bytes, password: bytes, pin: bytes) -> 'FlashData':
        """Create a paired fob state."""
        return cls(
            paired=True,
            pair_info=PairPacket(car_id, password, pin),
            feature_info=FeatureData(car_id, 0, [0, 0, 0])
        )


# =============================================================================
# Standard Commands (Production)
# =============================================================================

def cmd_enable(device, feature_package: bytes) -> Response:
    """
    Enable a packaged feature on the fob.
    
    Args:
        device: DeployedDevice (fob)
        feature_package: The packaged feature data
    
    Returns:
        Response with success/error
    """
    hex_data = feature_package.hex()
    return parse_response(device.send_recv(f"enable {hex_data}"))


def cmd_pair(device, pin: str) -> Response:
    """
    Initiate pairing from a paired fob.
    
    The paired fob validates the PIN and sends pairing data to the
    unpaired fob (which is blocking, waiting for PAIR_MAGIC).
    
    After this succeeds, the unpaired fob will send "OK: paired" on its
    host UART. Use wait_for_paired() to consume that message.
    
    Args:
        device: DeployedDevice (paired fob)
        pin: 6-digit PIN string
    
    Returns:
        Response with success/error
    """
    return parse_response(device.send_recv(f"pair {pin}"))


def wait_for_paired(device, timeout: float = 2.0) -> Response:
    """
    Wait for an unpaired fob to receive pairing and become paired.
    
    After the paired fob sends the pairing message (via cmd_pair),
    the unpaired fob will send "OK: paired" when it receives it.
    
    Args:
        device: DeployedDevice (unpaired fob that was awaiting pairing)
        timeout: Max time to wait
    
    Returns:
        Response: Should be OK with value="paired"
    """
    return parse_response(device.recv(timeout=timeout))


# =============================================================================
# Test Commands (TEST_BUILD only)
# =============================================================================

# --- Both Car and Fob ---

def cmd_restart(device, timeout: float = 2.0) -> Response:
    """
    Software reset - re-run main, state persists.
    
    On STM32/TM4C: NVIC_SystemReset()
    On x86: re-exec or longjmp to main
    
    The device will reset and send "OK: started" when ready.
    """
    device.send("restart")
    # Wait for the device to restart and send its ready message
    resp = device.recv(timeout=timeout)
    return parse_response(resp)


def cmd_reset(device) -> Response:
    """
    Factory reset - clear all state and restart.
    
    For fob: clears FLASH_DATA (becomes unpaired)
    For car: resets unlock count, re-locks
    """
    return parse_response(device.send_recv("reset"))


# --- Fob Only ---

def cmd_btn_press(device, timeout: float = 2.0) -> Response:
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


def cmd_get_flash_data(device) -> Response:
    """
    Get fob's FLASH_DATA as hex string.
    
    Returns:
        Response with value=hex string on success
    """
    return parse_response(device.send_recv("getFlashData"))


def cmd_set_flash_data(device, flash_data: FlashData) -> Response:
    """
    Set fob's FLASH_DATA and persist to flash.
    
    Args:
        device: DeployedDevice (fob)
        flash_data: FlashData object to write
    
    Returns:
        Response with success/error
    """
    hex_data = flash_data.to_hex()
    return parse_response(device.send_recv(f"setFlashData {hex_data}"))


def cmd_is_paired(device) -> Response:
    """
    Check if fob is paired.
    
    Returns:
        Response with value="1" if paired, "0" if not
    """
    return parse_response(device.send_recv("isPaired"))


def get_flash_data(device) -> FlashData:
    """
    Convenience: get and parse FLASH_DATA.
    
    Raises:
        RuntimeError: if command fails
    """
    resp = cmd_get_flash_data(device)
    if not resp.success:
        raise RuntimeError(f"getFlashData failed: {resp.error}")
    return FlashData.from_hex(resp.value)


def is_paired(device) -> bool:
    """Convenience: check if fob is paired."""
    resp = cmd_is_paired(device)
    if not resp.success:
        raise RuntimeError(f"isPaired failed: {resp.error}")
    return resp.value == "1"


# --- Car Only ---

def cmd_is_locked(device) -> Response:
    """
    Check if car is locked.
    
    Returns:
        Response with value="1" if locked, "0" if unlocked
    """
    return parse_response(device.send_recv("isLocked"))


def cmd_get_unlock_count(device) -> Response:
    """
    Get number of successful unlocks since boot.
    
    This value resets on power cycle (not persisted).
    
    Returns:
        Response with value=count as string
    """
    return parse_response(device.send_recv("getUnlockCount"))


def is_locked(device) -> bool:
    """Convenience: check if car is locked."""
    resp = cmd_is_locked(device)
    if not resp.success:
        raise RuntimeError(f"isLocked failed: {resp.error}")
    return resp.value == "1"


def get_unlock_count(device) -> int:
    """Convenience: get unlock count as int."""
    resp = cmd_get_unlock_count(device)
    if not resp.success:
        raise RuntimeError(f"getUnlockCount failed: {resp.error}")
    return int(resp.value)
