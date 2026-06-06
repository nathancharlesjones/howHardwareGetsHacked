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

        # Step 1: perform a legitimate unlock and capture the unlock message
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Legitimate unlock failed: {resp.error}"
        assert not proto.is_locked(car)

        log = proto.cmd_get_board_msg_log(car, role="car")
        for entry in log:
            if entry.magic != 0:
                print(entry)
        unlock_entries = [e for e in log if not e.tx and e.magic == proto.UNLOCK_MAGIC]
        assert unlock_entries, "Should have captured an UNLOCK message"
        captured_unlock_payload = unlock_entries[-1].payload

        unlock_count_before = proto.get_unlock_count(car)

        # Step 2: replay the captured UNLOCK message
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, captured_unlock_payload)
        time.sleep(0.05)

        # If the replay worked, the car accepted the UNLOCK and is now blocked waiting
        # for a START message; getUnlockCount will time out and the test will fail.
        # If the replay was rejected, the car is back in its main loop and we can
        # verify the unlock count is unchanged.
        assert proto.get_unlock_count(car) == unlock_count_before, "Replay attack should NOT unlock car"

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

        assert proto.is_locked(car_b), "Cross-car attack should NOT succeed"