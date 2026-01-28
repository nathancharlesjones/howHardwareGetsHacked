"""
Black-box tests for car/fob system.

Each test exercises a specific hardware configuration.
Run with: pytest test.py
Or via: ./project.py test
"""

import time
from conftest import RoleConfig


class TestSinglePairedFob:
    """Tests using only a single paired fob."""

    def test_fob_responds_to_ping(self, paired_fob):
        """A paired fob should respond to a basic command."""
        response = paired_fob.send_recv("ping")
        assert response, "Fob did not respond"


class TestCarAndPairedFob:
    """Tests using a car and its matched paired fob."""

    def test_paired_fob_can_unlock_car(self, car_and_paired_fob):
        """A paired fob with matching ID should unlock its car."""
        car, fob = car_and_paired_fob

        # Ensure car is locked
        car.send_recv("lock")
        status = car.send_recv("status")
        assert "locked" in status.lower(), f"Car should be locked, got: {status}"

        # Fob initiates unlock
        fob.send("unlock")
        time.sleep(0.5)

        # Check car is now unlocked
        status = car.send_recv("status")
        assert "unlocked" in status.lower(), f"Car should be unlocked, got: {status}"


class TestPairedAndUnpairedFob:
    """Tests using a paired fob and an unpaired fob."""

    def test_paired_fob_can_pair_unpaired_fob(self, paired_and_unpaired_fob):
        """A paired fob, given the correct PIN, can pair an unpaired fob."""
        paired, unpaired = paired_and_unpaired_fob

        # Unpaired fob should report unpaired status
        status = unpaired.send_recv("status")
        assert "unpaired" in status.lower(), f"Should be unpaired, got: {status}"

        # Initiate pairing: paired fob sends pair command with PIN
        paired.send("pair 123456")
        time.sleep(0.5)

        # Unpaired fob should now be paired
        status = unpaired.send_recv("status")
        assert "paired" in status.lower(), f"Should now be paired, got: {status}"


class TestCarPairedAndUnpaired:
    """Tests using car, paired fob, and unpaired fob together."""

    def test_unpaired_fob_cannot_unlock_car(self, car_paired_unpaired):
        """An unpaired fob should not be able to unlock the car."""
        car, paired, unpaired = car_paired_unpaired

        # Lock car
        car.send_recv("lock")

        # Unpaired fob tries to unlock (should fail)
        unpaired.send("unlock")
        time.sleep(0.5)

        # Car should still be locked
        status = car.send_recv("status")
        assert "locked" in status.lower(), f"Car should still be locked, got: {status}"

    def test_newly_paired_fob_can_unlock_car(self, car_paired_unpaired):
        """After pairing, a newly-paired fob should be able to unlock the car."""
        car, paired, unpaired = car_paired_unpaired

        # Lock car
        car.send_recv("lock")

        # Pair the unpaired fob
        paired.send("pair 123456")
        time.sleep(0.5)

        # Now the formerly-unpaired fob should be able to unlock
        unpaired.send("unlock")
        time.sleep(0.5)

        status = car.send_recv("status")
        assert "unlocked" in status.lower(), f"Car should be unlocked, got: {status}"


class TestCustomConfigurations:
    """Tests that deploy custom role configurations."""

    def test_mismatched_fob_cannot_unlock_car(self, deploy):
        """A fob paired to a different car ID should not unlock this car."""
        # Car with ID 1
        car = deploy(RoleConfig("car", id="1"))
        # Fob paired to car ID 2 (mismatched!)
        wrong_fob = deploy(RoleConfig("paired_fob", id="2", pin="654321"))

        car.send_recv("lock")

        # Wrong fob tries to unlock
        wrong_fob.send("unlock")
        time.sleep(0.5)

        # Should remain locked
        status = car.send_recv("status")
        assert "locked" in status.lower(), f"Car should reject mismatched fob, got: {status}"
