import time
import pytest
import struct
from conftest import RoleConfig
import protocol as proto


FEATURE_DATA_SIZE = 15  # sizeof(FEATURE_DATA): car_id[11] + num_active[1] + features[3]

@pytest.mark.car1
@pytest.mark.car2
@pytest.mark.car3
@pytest.mark.car4
class TestSimpleReplayAttacks:
    """Basic replay attacks. Defenses against these apply to all eCTF car scenarios."""

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
        response_entries = [e for e in log if not e.tx and e.magic == proto.RESPONSE_MAGIC]
        assert unlock_entries, "Should have captured an UNLOCK message"
        assert response_entries, "Should have captured a RESPONSE message"
        captured_unlock_payload = unlock_entries[-1].payload
        captured_response_payload = response_entries[-1].payload

        unlock_count_before = proto.get_unlock_count(car)

        # Step 2: replay the captured UNLOCK message
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, captured_unlock_payload)
        time.sleep(0.05)
        proto.cmd_send_board_msg(fob, proto.RESPONSE_MAGIC, captured_response_payload)

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

@pytest.mark.car2
class TestComplexReplayAttacks:
    """Advanced replay attacks that require temporary access to a paired fob (eCTF Car #2
    scenario). Defenses against these require a challenge-response protocol."""

    @pytest.mark.skip(reason="Car no longer implements a rolling counter")
    def test_rolljam_fails(self, deploy):
        """RollJam attack should be defeated: even if an attacker intercepts the unlock
        message before the car receives it (simulated by rewinding the car's stored
        counter by one), replaying it should be rejected."""
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        # Step 1: perform a legitimate unlock and capture the unlock message
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Legitimate unlock failed: {resp.error}"

        log = proto.cmd_get_board_msg_log(car, role="car")
        unlock_entries = [e for e in log if not e.tx and e.magic == proto.UNLOCK_MAGIC]
        assert unlock_entries, "Should have captured an UNLOCK message"
        captured_unlock_payload = unlock_entries[-1].payload

        # Step 2: rewind the car's counter for this fob by 1, simulating interception
        fob_id = captured_unlock_payload[0]
        car_flash = proto.get_car_flash_data(car)
        car_flash.fob_counter_values[fob_id] = (car_flash.fob_counter_values[fob_id] - 1) & 0xFFFF
        proto.cmd_set_car_flash_data(car, car_flash)

        unlock_count_before = proto.get_unlock_count(car)

        # Step 3: replay the captured UNLOCK — should be rejected
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, captured_unlock_payload)
        time.sleep(0.05)

        assert proto.get_unlock_count(car) == unlock_count_before, \
            "RollJam attack should NOT unlock the car"

    def test_forced_rollback_fails(self, deploy):
        """Forced rollback attack should be defeated: even if an attacker mass-erases
        the car's flash to reset its counter table (simulated by reset), replaying a
        previously captured unlock should be rejected."""
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        # Step 1: perform a legitimate unlock and capture the unlock message
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Legitimate unlock failed: {resp.error}"

        log = proto.cmd_get_board_msg_log(car, role="car")
        unlock_entries = [e for e in log if not e.tx and e.magic == proto.UNLOCK_MAGIC]
        response_entries = [e for e in log if not e.tx and e.magic == proto.RESPONSE_MAGIC]
        assert unlock_entries, "Should have captured an UNLOCK message"
        assert response_entries, "Should have captured a RESPONSE message"
        captured_unlock_payload = unlock_entries[-1].payload
        captured_response_payload = response_entries[-1].payload

        # Step 2: factory-reset the car, simulating mass erase / reflash
        proto.cmd_reset(car)
        unlock_count_before = proto.get_unlock_count(car)

        # Step 3: replay the captured UNLOCK — should be rejected
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, captured_unlock_payload)
        time.sleep(0.05)
        proto.cmd_send_board_msg(fob, proto.RESPONSE_MAGIC, captured_response_payload)

        assert proto.get_unlock_count(car) == unlock_count_before, \
            "Forced rollback attack should NOT unlock the car"

    @pytest.mark.skip(reason="Car no longer implements a rolling counter")
    def test_forced_rollover_fails(self, deploy):
        """Forced rollover attack should be defeated: even after UINT16_MAX-1 additional
        unlocks wrap the 16-bit counter so the captured value re-enters the acceptance
        window (simulated by directly advancing the car's stored counter), replaying the
        captured unlock should be rejected."""
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        # Step 1: perform a legitimate unlock and capture the unlock message
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Legitimate unlock failed: {resp.error}"

        log = proto.cmd_get_board_msg_log(car, role="car")
        unlock_entries = [e for e in log if not e.tx and e.magic == proto.UNLOCK_MAGIC]
        assert unlock_entries, "Should have captured an UNLOCK message"
        captured_unlock_payload = unlock_entries[-1].payload

        # Step 2: advance the car's counter by UINT16_MAX-1, simulating that many
        # additional unlocks having occurred since the message was captured
        fob_id = captured_unlock_payload[0]
        car_flash = proto.get_car_flash_data(car)
        car_flash.fob_counter_values[fob_id] = (car_flash.fob_counter_values[fob_id] + 0xFFFE) & 0xFFFF
        proto.cmd_set_car_flash_data(car, car_flash)

        unlock_count_before = proto.get_unlock_count(car)

        # Step 3: replay the captured UNLOCK — should be rejected
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, captured_unlock_payload)
        time.sleep(0.05)

        assert proto.get_unlock_count(car) == unlock_count_before, \
            "Forced rollover attack should NOT unlock the car"
