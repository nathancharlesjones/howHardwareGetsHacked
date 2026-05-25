import time
import pytest
import struct
from conftest import RoleConfig
import protocol as proto


FEATURE_DATA_SIZE = 15  # sizeof(FEATURE_DATA): car_id[11] + num_active[1] + features[3]

class TestReplayAttacks:
    """Replay a captured unlock sequence."""

    def test_replay_captured_unlock_fails(self, deploy):
        """An attacker who eavesdropped on one unlock can replay it to unlock again."""
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        # Step 1: perform a legitimate unlock and capture the messages
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Legitimate unlock failed: {resp.error}"
        assert not proto.is_locked(car)

        log = proto.cmd_get_board_msg_log(fob, role="fob")
        for entry in log:
            if entry.magic != 0:
                print(entry)
        unlock_entries = [e for e in log if e.tx and e.magic == proto.UNLOCK_MAGIC]
        start_entries  = [e for e in log if e.tx and e.magic == proto.START_MAGIC]
        assert unlock_entries, "Should have captured an UNLOCK message"
        assert start_entries,  "Should have captured a START message"

        captured_unlock_payload = unlock_entries[-1].payload
        captured_start_payload  = start_entries[-1].payload

        # Step 2: reset car (re-locks it)
        proto.cmd_reset(car)
        assert proto.is_locked(car), "Car should be locked again after reset"

        # Send UNLOCK
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, captured_unlock_payload)
        time.sleep(0.05)

        # Check ACK before sending START — models real attacker behavior
        log = proto.cmd_get_board_msg_log(fob)
        got_ack_success = any(
            not e.tx and e.magic == proto.ACK_MAGIC
            and len(e.payload) > 0 and e.payload[0] == proto.ACK_SUCCESS
            for e in log
        )

        if got_ack_success:
            proto.cmd_send_board_msg(fob, proto.START_MAGIC, captured_start_payload)
            time.sleep(0.05)

        # Flip these two assertions when security is implemented
        assert got_ack_success, "Replayed UNLOCK should be accepted (until fix is implemented)"
        assert not proto.is_locked(car), "Replay attack should unlock car (until fix is implemented)"
        #assert not got_ack_success, "Replayed UNLOCK should NOT be accepted"
        #assert proto.is_locked(car), "Replay attack should NOT unlock car"

    def test_fob_paired_to_different_car_cannot_unlock(self, deploy):
        """A fob paired to car A knows the global password. With knowledge of
        car B's ID, it can unlock car B by forging the START message's car_id."""
        # Fob is paired to car 1111; target is car 9999
        car_b, fob_a = deploy(
            RoleConfig("car", id="9999"),
            RoleConfig("paired_fob", id="1111", pin="111111"),
        )

        # Fob A's password is the global password — works on any car
        proto.cmd_btn_press(fob_a)
        time.sleep(0.05)

        assert not proto.is_locked(car_b), "Cross-car attack should succeed with global password (until fix is implemented)"