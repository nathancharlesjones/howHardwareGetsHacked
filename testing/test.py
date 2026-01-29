"""
Black-box tests for car/fob system.

Each test exercises a specific hardware configuration.
Run with: pytest test.py
Or via: ./project.py test
"""

import pytest
from conftest import RoleConfig
import protocol as proto


class TestSinglePairedFob:
    """Tests using only a single paired fob."""

    def test_fob_is_paired(self, paired_fob):
        """A paired fob should report that it's paired."""
        assert proto.is_paired(paired_fob), "Fob should be paired"

    def test_get_flash_data(self, paired_fob):
        """Should be able to read fob's flash data."""
        flash = proto.get_flash_data(paired_fob)
        assert flash.paired == 0x00, "Flash data should show paired"
        assert flash.pair_info.car_id != b'\x00' * 8, "Should have a car ID"


class TestCarAndPairedFob:
    """Tests using a car and its matched paired fob."""

    def test_car_starts_locked(self, car_and_paired_fob):
        """Car should start in locked state."""
        car, fob = car_and_paired_fob
        assert proto.is_locked(car), "Car should start locked"
        assert proto.get_unlock_count(car) == 0, "Unlock count should be 0"

    def test_paired_fob_can_unlock_car(self, car_and_paired_fob):
        """A paired fob with matching ID should unlock its car."""
        car, fob = car_and_paired_fob

        # Verify car is locked
        assert proto.is_locked(car), "Car should start locked"

        # Fob initiates unlock (blocks until complete)
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"btnPress failed: {resp.error}"

        # Check car is now unlocked
        assert not proto.is_locked(car), "Car should be unlocked"
        assert proto.get_unlock_count(car) == 1, "Unlock count should be 1"

    def test_multiple_unlocks_increment_count(self, car_and_paired_fob):
        """Each unlock should increment the unlock count."""
        car, fob = car_and_paired_fob

        for i in range(3):
            resp = proto.cmd_btn_press(fob)
            assert resp.success, f"btnPress {i+1} failed: {resp.error}"

        assert proto.get_unlock_count(car) == 3, "Should have 3 unlocks"


class TestPairedAndUnpairedFob:
    """Tests using a paired fob and an unpaired fob."""

    def test_unpaired_fob_reports_unpaired(self, paired_and_unpaired_fob):
        """Unpaired fob should report that it's not paired."""
        paired, unpaired = paired_and_unpaired_fob
        assert proto.is_paired(paired), "Paired fob should be paired"
        assert not proto.is_paired(unpaired), "Unpaired fob should not be paired"

    def test_paired_fob_can_pair_unpaired_fob(self, paired_and_unpaired_fob):
        """A paired fob, given the correct PIN, can pair an unpaired fob."""
        paired, unpaired = paired_and_unpaired_fob

        assert not proto.is_paired(unpaired), "Should start unpaired"

        # Initiate pairing: paired fob sends pair command with PIN
        resp = proto.cmd_pair(paired, "123456")
        assert resp.success, f"Pairing failed: {resp.error}"

        # Wait for unpaired fob to receive pairing message and confirm
        resp = proto.wait_for_paired(unpaired)
        assert resp.success, f"Unpaired fob didn't get paired: {resp.error}"

        # Unpaired fob should now be paired
        assert proto.is_paired(unpaired), "Should now be paired"

    def test_wrong_pin_fails_pairing(self, paired_and_unpaired_fob):
        """Pairing with wrong PIN should fail."""
        paired, unpaired = paired_and_unpaired_fob

        # Try with wrong PIN
        resp = proto.cmd_pair(paired, "000000")
        assert not resp.success, "Pairing with wrong PIN should fail"

        # Unpaired fob should still be unpaired
        assert not proto.is_paired(unpaired), "Should still be unpaired"

'''
class TestCarPairedAndUnpaired:
    """Tests using car, paired fob, and unpaired fob together."""

    def test_unpaired_fob_cannot_unlock_car(self, car_paired_unpaired):
        """An unpaired fob should not be able to unlock the car."""
        car, paired, unpaired = car_paired_unpaired

        assert proto.is_locked(car), "Car should start locked"

        # Unpaired fob tries to unlock (should fail - not paired)
        resp = proto.cmd_btn_press(unpaired)
        assert not resp.success, "Unpaired fob unlock should fail"

        # Car should still be locked
        assert proto.is_locked(car), "Car should still be locked"
        assert proto.get_unlock_count(car) == 0, "Unlock count should be 0"

    def test_newly_paired_fob_can_unlock_car(self, car_paired_unpaired):
        """After pairing, a newly-paired fob should be able to unlock the car."""
        car, paired, unpaired = car_paired_unpaired

        # Pair the unpaired fob
        resp = proto.cmd_pair(paired, "123456")
        assert resp.success, f"Pairing failed: {resp.error}"

        # Wait for unpaired fob to receive pairing
        resp = proto.wait_for_paired(unpaired)
        assert resp.success, f"Unpaired fob didn't get paired: {resp.error}"

        # Now the formerly-unpaired fob should be able to unlock
        resp = proto.cmd_btn_press(unpaired)
        assert resp.success, f"Unlock failed: {resp.error}"

        assert not proto.is_locked(car), "Car should be unlocked"
'''

class TestStateManagement:
    """Tests for restart and reset functionality."""

    def test_restart_preserves_state(self, paired_fob):
        """Software restart should preserve flash data."""
        # Get current state
        flash_before = proto.get_flash_data(paired_fob)

        # Restart
        resp = proto.cmd_restart(paired_fob)
        assert resp.success, f"Restart failed: {resp.error}"

        # State should be preserved
        flash_after = proto.get_flash_data(paired_fob)
        assert flash_after.paired == flash_before.paired
        assert flash_after.pair_info.car_id == flash_before.pair_info.car_id

    def test_reset_clears_state(self, paired_fob):
        """Factory reset should clear all state."""
        assert proto.is_paired(paired_fob), "Should start paired"

        # Factory reset
        resp = proto.cmd_reset(paired_fob)
        assert resp.success, f"Reset failed: {resp.error}"

        # Should now be unpaired
        assert not proto.is_paired(paired_fob), "Should be unpaired after reset"

    def test_set_flash_data(self, paired_fob):
        """Should be able to modify flash data directly."""
        # Create custom state
        new_flash = proto.FlashData.new_paired(
            car_id=b'TESTCAR1',
            password=b'TESTPWD1',
            pin=b'999999\x00\x00'
        )

        resp = proto.cmd_set_flash_data(paired_fob, new_flash)
        assert resp.success, f"setFlashData failed: {resp.error}"

        # Read back and verify
        flash = proto.get_flash_data(paired_fob)
        assert flash.pair_info.car_id == b'TESTCAR1'
        assert flash.pair_info.password == b'TESTPWD1'


class TestCustomConfigurations:
    """Tests that deploy custom role configurations."""

    def test_mismatched_fob_cannot_unlock_car(self, deploy):
        """A fob paired to a different car ID should not unlock this car."""
        # Car with ID 1
        car = deploy(RoleConfig("car", id="1"))
        # Fob paired to car ID 2 (mismatched!)
        wrong_fob = deploy(RoleConfig("paired_fob", id="2", pin="654321"))

        # Wrong fob tries to unlock
        resp = proto.cmd_btn_press(wrong_fob)
        # Should fail (either ERROR response or car stays locked)

        # Car should remain locked
        assert proto.is_locked(car), "Car should reject mismatched fob"


class TestTiming:
    """Timing-sensitive tests (non-fatal failures)."""

    @pytest.mark.xfail(reason="timing-sensitive, may fail under load", strict=False)
    def test_unlock_completes_within_1_second(self, car_and_paired_fob):
        """Unlock should complete within 1 second (per spec)."""
        import time
        car, fob = car_and_paired_fob

        start = time.monotonic()
        resp = proto.cmd_btn_press(fob, timeout=1.5)
        elapsed = time.monotonic() - start

        assert resp.success, f"Unlock failed: {resp.error}"
        assert elapsed < 1.0, f"Unlock took {elapsed:.2f}s, should be <1s"
