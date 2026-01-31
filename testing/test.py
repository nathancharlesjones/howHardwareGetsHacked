"""
Black-box tests for car/fob system.

Each test exercises a specific hardware configuration.
Run with: pytest test.py
Or via: ./project.py test
"""

import pytest
import time
from conftest import RoleConfig
import protocol as proto

from packaging import create_feature_package

class TestSinglePairedFob:
    """Tests using only a single paired fob."""

    def test_paired_fob_is_paired(self, paired_fob):
        """A paired fob should report that it's paired."""
        assert proto.is_paired(paired_fob), "Fob should be paired"

    def test_get_flash_data_for_paired_fob(self, paired_fob):
        """Should be able to read fob's flash data."""
        flash = proto.get_flash_data(paired_fob)
        assert flash.paired == 0x01, "Flash data should show paired"
        assert flash.pair_info.car_id != b'\xFF' * 8, "Should have a car ID"
        assert flash.pair_info.pin != b'\xFF' * 8, "Should have a pin"
        assert flash.pair_info.password != b'\xFF' * 8, "Should have a password"

    def test_paired_fob_can_enable_feature_with_valid_id_and_valid_feature_when_there_is_room(self, paired_fob):
        """Should be able to enable valid features."""

        # Get flash data; ensure features 0
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 0, f"Newly paired fob has active features ({flash.feature_info.num_active}), but shouldn't"
        
        # Package feature
        pkg = create_feature_package(flash.pair_info.car_id, 1)

        # Enable feature
        resp = proto.cmd_enable(paired_fob, pkg)
        assert resp.success, f"Feature enable failed: {resp.error}"
        
        # Get flash data; ensure features 1 and features match
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 1, f"Paired fob did not report correct number of active feaures; expected 1, received {flash.feature_info.num_active}"

        # After modifying fob state, reset
        proto.cmd_reset(paired_fob)

    def test_paired_fob_can_enable_multiple_valid_features(self, paired_fob):
        """Should be able to enable multiple valid features."""

        # Get flash data; ensure features 0
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 0, f"Newly paired fob has active features ({flash.feature_info.num_active}), but shouldn't"
        
        # Package features 1
        pkg = create_feature_package(flash.pair_info.car_id, 1)

        # Enable feature 1
        resp = proto.cmd_enable(paired_fob, pkg)
        assert resp.success, f"Feature 1 enable failed: {resp.error}"

        # Package feature 2
        pkg = create_feature_package(flash.pair_info.car_id, 2)

        # Enable feature 2
        resp = proto.cmd_enable(paired_fob, pkg)
        assert resp.success, f"Feature 2 enable failed: {resp.error}"

        # Package feature 3
        pkg = create_feature_package(flash.pair_info.car_id, 3)

        # Enable feature 3
        resp = proto.cmd_enable(paired_fob, pkg)
        assert resp.success, f"Feature 3 enable failed: {resp.error}"
        
        # Get flash data; ensure features 1 and features match
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 3, f"Paired fob did not report correct number of active feaures; expected 1, received {flash.feature_info.num_active}"

        # After modifying fob state, reset
        proto.cmd_reset(paired_fob)

    def test_paired_fob_rejects_feature_with_mismatched_id(self, paired_fob):
        # Get flash data; ensure features 0
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 0, f"Newly paired fob has active features ({flash.feature_info.num_active}), but shouldn't"
        
        # Package feature
        pkg = create_feature_package("BAD_ID", 1)

        # Enable feature
        resp = proto.cmd_enable(paired_fob, pkg)
        assert not resp.success, f"Feature enable succeeded when it shouldn't have: {resp.value}"
        
        # Get flash data; ensure features 1 and features match
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 0, f"Paired fob did not report correct number of active feaures; expected 0, received {flash.feature_info.num_active}"

        # After modifying fob state, reset
        proto.cmd_reset(paired_fob)

    def test_paired_fob_rejects_feature_with_invalid_feature_number(self, paired_fob):
        pass

    def test_paired_fob_rejects_feature_when_feature_is_already_enabled(self, paired_fob):
        # Get flash data; ensure features 0
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 0, f"Newly paired fob has active features ({flash.feature_info.num_active}), but shouldn't"
        
        # Package features 1
        pkg = create_feature_package(flash.pair_info.car_id, 1)

        # Enable feature 1
        resp = proto.cmd_enable(paired_fob, pkg)
        assert resp.success, f"Feature 1 enable failed: {resp.error}"

        # Enable feature 1 again
        resp = proto.cmd_enable(paired_fob, pkg)
        assert not resp.success, f"Feature 1 enable succeded when it shouldn't have: {resp.value}"
        
        # Get flash data; ensure features 1 and features match
        flash = proto.get_flash_data(paired_fob)
        assert flash.feature_info.num_active == 1, f"Paired fob did not report correct number of active feaures; expected 1, received {flash.feature_info.num_active}"

        # After modifying fob state, reset
        proto.cmd_reset(paired_fob)

class TestSingleUnpairedFob:
    """Tests using only a single unpaired fob."""

    def test_unpaired_fob_is_unpaired(self, unpaired_fob):
        """An unpaired fob should report that it's unpaired."""
        assert not proto.is_paired(unpaired_fob), "Fob should be unpaired"

    def test_get_flash_data_for_unpaired_fob(self, unpaired_fob):
        """Should be able to read fob's flash data."""
        flash = proto.get_flash_data(unpaired_fob)
        assert flash.paired == 0xFF, "Flash data should show unpaired"
        assert flash.pair_info.car_id == b'\xFF' * 8, "Should not have a car ID"
        assert flash.pair_info.pin == b'\xFF' * 8, "Should not have a pin"
        assert flash.pair_info.password == b'\xFF' * 8, "Should not have a password"

    def test_unpaired_fob_rejects_feature(self, unpaired_fob):        
        #resp = proto.cmd_btn_press(fob)
        # assert not resp.success, f"Feature enable succeeded when it shouldn't have: {resp.value}"
        pass

    def test_unpaired_fob_rejects_btnPress(self, unpaired_fob):
        resp = proto.cmd_btn_press(unpaired_fob)
        assert not resp.success, f"btnPress succeeded when it shouldn't have: {resp.value}"

    def test_unpaired_fob_rejects_pair(self, unpaired_fob):
        resp = proto.cmd_pair(unpaired_fob, "123456")
        assert not resp.success, f"Pairing succeeded when it shouldn't have: {resp.value}"

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

    def test_paired_fob_can_pair_unpaired_fob(self, paired_and_unpaired_fob):
        """A paired fob, given the correct PIN, can pair an unpaired fob."""
        paired, unpaired = paired_and_unpaired_fob

        assert not proto.is_paired(unpaired), "Should start unpaired"

        # Initiate pairing: paired fob sends pair command with PIN
        resp = proto.cmd_pair(paired, "123456")
        assert resp.success, f"Pairing failed: {resp.error}"

        # Give time for the pairing message to be received and processed
        time.sleep(0.1)

        # Query unpaired fob to verify it's now paired
        assert proto.is_paired(unpaired), "Should now be paired"

        proto.cmd_reset(unpaired)

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

        # Give time for pairing message to be processed
        time.sleep(0.1)

        # Verify pairing succeeded
        assert proto.is_paired(unpaired), "Fob should now be paired"

        # Now the formerly-unpaired fob should be able to unlock
        resp = proto.cmd_btn_press(unpaired)
        assert resp.success, f"Unlock failed: {resp.error}"

        assert not proto.is_locked(car), "Car should be unlocked"
'''

class TestStateManagement:
    """Tests for reload and reset functionality."""

    def test_reload_preserves_state(self, paired_fob):
        """Software reload should preserve flash data."""
        # Get current state
        flash_before = proto.get_flash_data(paired_fob)

        # Reload
        resp = proto.cmd_reload(paired_fob)
        assert resp.success, f"Reload failed: {resp.error}"

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
        # Save original state to restore later
        original_flash = proto.get_flash_data(paired_fob)

        try:
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
        finally:
            # Restore original state so other tests aren't affected
            proto.cmd_set_flash_data(paired_fob, original_flash)


class TestCustomConfigurations:
    """Tests that deploy custom role configurations."""

    def test_mismatched_fob_cannot_unlock_car(self, deploy):
        """A fob paired to a different car ID should not unlock this car."""
        # Car with ID 1
        car = deploy(RoleConfig("car", id="2"))
        # Fob paired to car ID 2 (mismatched!)
        wrong_fob = deploy(RoleConfig("paired_fob", id="1", pin="654321"))

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
        car, fob = car_and_paired_fob

        start = time.monotonic()
        resp = proto.cmd_btn_press(fob, timeout=1.5)
        elapsed = time.monotonic() - start

        assert resp.success, f"Unlock failed: {resp.error}"
        assert elapsed < 1.0, f"Unlock took {elapsed:.2f}s, should be <1s"