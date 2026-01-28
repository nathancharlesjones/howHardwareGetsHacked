"""
Protocol definitions and helpers for car/fob serial communication.

This module defines the serial protocol used to communicate with car and fob
devices. In addition to the standard production commands, TEST_BUILD firmware
responds to additional diagnostic commands that enable black-box testing.

Protocol Overview:
- Text-based commands terminated by newline
- Binary payloads are hex-encoded in the command string
- Responses are text with optional hex-encoded binary data
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import re

# Protocol constants
MAX_COMMAND_LEN = 256
MAX_RESPONSE_LEN = 512
CHALLENGE_LEN = 16
RESPONSE_LEN = 16
KEY_LEN = 16

CMD_TERMINATOR = b'\n'

# Response prefixes
RESP_OK = "OK"
RESP_ERROR = "ERROR"
RESP_CHALLENGE = "CHALLENGE"


# =============================================================================
# Standard Commands (Production + Test builds)
# =============================================================================

# ----- FOB Commands -----
CMD_FOB_UNLOCK = "unlock"
CMD_FOB_ENABLE = "enable"
CMD_FOB_DISABLE = "disable"

# ----- CAR Commands -----
CMD_CAR_STATUS = "status"
CMD_CAR_LOCK = "lock"


# =============================================================================
# Test/Diagnostic Commands (TEST_BUILD only)
# =============================================================================

# ----- Universal Test Commands -----
CMD_VERSION = "version"
CMD_RESET = "reset"
CMD_ECHO = "echo"

# ----- FOB Test Commands -----
CMD_FOB_BTN_PRESS = "btnPress"
CMD_FOB_LAST_UNLOCK = "lastUnlockResult"
CMD_FOB_GET_CHALLENGE = "getChallenge"
CMD_FOB_INJECT_CHALLENGE = "injectChallenge"
CMD_FOB_GET_RESPONSE = "getResponse"
CMD_FOB_DUMP_KEY = "dumpKey"
CMD_FOB_SET_KEY = "setKey"

# ----- CAR Test Commands -----
CMD_CAR_LAST_UNLOCK = "lastUnlockAttempt"
CMD_CAR_LAST_CHALLENGE = "lastChallenge"
CMD_CAR_EXPECTED_RESPONSE = "expectedResponse"
CMD_CAR_INJECT_RESPONSE = "injectResponse"
CMD_CAR_START_CHALLENGE = "startChallenge"
CMD_CAR_SET_TIMEOUT = "setTimeout"
CMD_CAR_UNLOCK_COUNT = "unlockCount"
CMD_CAR_DUMP_KEY = "dumpKey"
CMD_CAR_SET_KEY = "setKey"


# =============================================================================
# Response Dataclass
# =============================================================================

@dataclass
class Response:
    """Parsed response from a device."""
    raw: str
    ok: bool
    data: Optional[str] = None
    error_reason: Optional[str] = None
    
    @property
    def data_bytes(self) -> Optional[bytes]:
        """Decode hex data to bytes, if present."""
        if self.data:
            try:
                return decode_hex(self.data)
            except ValueError:
                return None
        return None


# =============================================================================
# Parsing Functions
# =============================================================================

def parse_response(response: str) -> Response:
    """
    Parse a response string into a Response object.
    
    Examples:
        "OK: unlocked" -> Response(ok=True, data="unlocked")
        "OK: 0123456789ABCDEF" -> Response(ok=True, data="0123456789ABCDEF")
        "ERROR: invalid key" -> Response(ok=False, error_reason="invalid key")
        "OK" -> Response(ok=True, data=None)
    """
    response = response.strip()
    
    if response.startswith("OK"):
        if response == "OK":
            return Response(raw=response, ok=True)
        elif response.startswith("OK: "):
            return Response(raw=response, ok=True, data=response[4:])
        elif response.startswith("OK:"):
            return Response(raw=response, ok=True, data=response[3:].strip())
        else:
            return Response(raw=response, ok=True, data=response[2:].strip())
    
    elif response.startswith("ERROR"):
        if response == "ERROR":
            return Response(raw=response, ok=False, error_reason="unknown")
        elif response.startswith("ERROR: "):
            return Response(raw=response, ok=False, error_reason=response[7:])
        elif response.startswith("ERROR:"):
            return Response(raw=response, ok=False, error_reason=response[6:].strip())
        else:
            return Response(raw=response, ok=False, error_reason=response[5:].strip())
    
    else:
        # Unknown format - treat as OK with the whole thing as data
        return Response(raw=response, ok=True, data=response)


def is_ok(response: str) -> bool:
    """Check if a response string indicates success."""
    return response.strip().startswith("OK")


def is_error(response: str) -> bool:
    """Check if a response string indicates an error."""
    return response.strip().startswith("ERROR")


# =============================================================================
# Hex Encoding/Decoding
# =============================================================================

def encode_hex(data: bytes) -> str:
    """Encode binary data as uppercase hex string."""
    return data.hex().upper()


def decode_hex(hex_str: str) -> bytes:
    """
    Decode a hex string to binary data.
    
    Raises:
        ValueError: If the string is not valid hex
    """
    # Remove any whitespace
    hex_str = hex_str.replace(" ", "").replace("\n", "").replace("\t", "")
    
    # Handle odd-length strings by prepending 0
    if len(hex_str) % 2 == 1:
        hex_str = "0" + hex_str
    
    return bytes.fromhex(hex_str)


# =============================================================================
# Command Building
# =============================================================================

def build_command(cmd: str, payload: Optional[bytes] = None) -> bytes:
    """
    Build a command string with optional hex payload.
    
    Args:
        cmd: Command name (e.g., "setKey")
        payload: Optional binary payload to hex-encode
        
    Returns:
        Complete command as bytes, with newline terminator
    """
    if payload is not None:
        return f"{cmd} {encode_hex(payload)}\n".encode('ascii')
    else:
        return f"{cmd}\n".encode('ascii')


def build_set_key_command(key: bytes) -> bytes:
    """Build a setKey command with the given key."""
    if len(key) != KEY_LEN:
        raise ValueError(f"Key must be {KEY_LEN} bytes, got {len(key)}")
    return build_command(CMD_FOB_SET_KEY, key)


def build_inject_challenge_command(challenge: bytes) -> bytes:
    """Build an injectChallenge command."""
    if len(challenge) != CHALLENGE_LEN:
        raise ValueError(f"Challenge must be {CHALLENGE_LEN} bytes, got {len(challenge)}")
    return build_command(CMD_FOB_INJECT_CHALLENGE, challenge)


def build_inject_response_command(response: bytes) -> bytes:
    """Build an injectResponse command."""
    if len(response) != RESPONSE_LEN:
        raise ValueError(f"Response must be {RESPONSE_LEN} bytes, got {len(response)}")
    return build_command(CMD_CAR_INJECT_RESPONSE, response)


# =============================================================================
# Response Data Extraction
# =============================================================================

def extract_hex_data(response: str) -> Optional[bytes]:
    """
    Extract hex-encoded binary data from a response.
    
    Looks for hex data after "OK: " prefix.
    Returns None if no valid hex data found.
    """
    parsed = parse_response(response)
    if parsed.ok and parsed.data:
        # Check if data looks like hex (only hex chars)
        if re.match(r'^[0-9A-Fa-f]+$', parsed.data):
            try:
                return decode_hex(parsed.data)
            except ValueError:
                pass
    return None


def extract_status(response: str) -> Optional[str]:
    """
    Extract status string from a response.
    
    For responses like "OK: locked" or "OK: unlocked", returns "locked"/"unlocked".
    """
    parsed = parse_response(response)
    if parsed.ok and parsed.data:
        return parsed.data.lower()
    return None


def extract_count(response: str) -> Optional[int]:
    """
    Extract a count/integer from a response.
    
    For responses like "OK: 5", returns 5.
    """
    parsed = parse_response(response)
    if parsed.ok and parsed.data:
        try:
            return int(parsed.data)
        except ValueError:
            pass
    return None


# =============================================================================
# Validation
# =============================================================================

def is_valid_key(key: bytes) -> bool:
    """Check if a key has valid length."""
    return len(key) == KEY_LEN


def is_valid_challenge(challenge: bytes) -> bool:
    """Check if a challenge has valid length."""
    return len(challenge) == CHALLENGE_LEN


def is_valid_response(response: bytes) -> bool:
    """Check if a response has valid length."""
    return len(response) == RESPONSE_LEN
