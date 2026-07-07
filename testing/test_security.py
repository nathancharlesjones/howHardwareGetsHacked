import math
import time
import pytest
import struct
from collections import Counter
from conftest import RoleConfig
import protocol as proto
import secrets
import json
from pathlib import Path
import os

from package import create_feature_package, FeaturePackage


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

    def test_oracle_attack_fails(self, deploy):
        """An attacker with temporary physical access to a paired fob (the eCTF Car #2
        threat model) can record a table of (nonce -> response) pairs from real,
        legitimate unlocks while they have the fob. The car's response is a
        deterministic CMAC of the nonce under the shared key, so if the car ever
        reissues a nonce already in that table - after the attacker no longer has
        the fob - the old recorded response is still valid and can be replayed.

        This builds a table of TABLE_SIZE entries (the attacker's limited access
        window), then watches MAX_ITER further unlocks against that frozen table.
        Nonces seen only during the second window are never added to the table:
        a repeat entirely within that window wasn't in the attacker's table at the
        time they'd have needed it, so it isn't something they could have exploited."""
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        # Board message logs hold 15 entries = 3 unlocks worth (5 messages each), so
        # batch button presses 3 at a time before reading the log back.
        BATCH = 3
        # T=M=150000 -> ~99.5% chance of at least one collision against a 32-bit
        # nonce space (P = 1 - exp(-T*M/2**32)), at ~0.23ms/unlock -> ~70s total.
        TABLE_SIZE = 150000
        MAX_ITER = 150000

        def do_batch(total_done: int):
            for _ in range(BATCH):
                resp = proto.cmd_btn_press(fob)
                assert resp.success, f"Unlock failed after {total_done} unlocks: {resp.error}"
                total_done += 1

            log = proto.cmd_get_board_msg_log(car, role="car")
            nonce_entries = [e for e in log if e.tx and e.magic == proto.NONCE_MAGIC]
            response_entries = [e for e in log if not e.tx and e.magic == proto.RESPONSE_MAGIC]
            assert len(nonce_entries) == BATCH and len(response_entries) == BATCH, \
                "Did not capture the expected number of nonce/response pairs"
            return total_done, [(e1.payload, e2.payload) for e1, e2 in zip(nonce_entries, response_entries)]

        # Phase 1: attacker has the fob - build the table.
        mac_values = {}
        total_done = 0
        for _ in range(TABLE_SIZE // BATCH):
            total_done, pairs = do_batch(total_done)
            for nonce, response in pairs:
                mac_values[nonce] = response

        # Phase 2: attacker no longer has the fob - just watch for a repeat.
        collision_nonce = None
        collision_after = None
        for _ in range(MAX_ITER // BATCH):
            total_done, pairs = do_batch(total_done)
            for nonce, response in pairs:
                if nonce in mac_values:
                    collision_nonce = nonce
                    collision_after = total_done
                    break
            if collision_nonce is not None:
                break

        assert collision_nonce is None, (
            f"Nonce {collision_nonce.hex()} repeated one already in a {len(mac_values)}-entry "
            f"table after {collision_after} total unlocks - an attacker who recorded that table "
            f"during a temporary fob-access window could have replayed the old response and "
            f"unlocked the car without the fob"
        )



@pytest.mark.car2
@pytest.mark.car3
class TestNonceRandomness:
    """Tests that the challenge nonce PRNG is unpredictable.

    A weak PRNG (e.g. a fixed seed or a simple counter) lets an attacker who
    has observed past nonces predict future ones, defeating the challenge-response
    protocol entirely. These tests are designed to catch naive implementations.
    """

    def _capture_nonce(self, car, fob) -> bytes:
        """Perform one unlock and return the 4-byte nonce the car issued."""
        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Unlock failed: {resp.error}"
        log = proto.cmd_get_board_msg_log(car, role="car")
        entries = [e for e in log if e.tx and e.magic == proto.NONCE_MAGIC]
        assert entries, "No NONCE message found in board log"
        return bytes(entries[-1].payload[:4])

    def test_nonces_differ_across_reboots(self, deploy):
        """Catch fixed seeds: a PRNG seeded with a constant value produces the
        same nonce sequence on every boot, letting an attacker who observed one
        session predict every future session without knowing any secret."""
        N_BOOTS = 10
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        nonces = []
        for _ in range(N_BOOTS):
            proto.cmd_reset(car)
            nonces.append(self._capture_nonce(car, fob))

        assert len(set(nonces)) == N_BOOTS, \
            f"PRNG repeated a nonce across reboots: {[n.hex() for n in nonces]}"

    def test_nonces_not_sequential(self, deploy):
        """Catch counter-based PRNGs: state++ produces nonces with a constant
        difference of 1 between successive unlocks. An attacker who observes
        one nonce can immediately predict the next."""
        N_UNLOCKS = 8
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        nonces = []
        for _ in range(N_UNLOCKS):
            nonces.append(int.from_bytes(self._capture_nonce(car, fob), 'little'))

        diffs = [(nonces[i+1] - nonces[i]) & 0xFFFFFFFF for i in range(len(nonces) - 1)]
        assert len(set(diffs)) > 1, \
            f"Nonces follow a constant step of {diffs[0]}: {[hex(n) for n in nonces]}"

    def test_nonce_bit_distribution(self, deploy):
        """Sanity check: nonce bits should be roughly 50/50 across many samples.

        Note: this test alone is not a meaningful security gate — a sequential
        counter (state++) also produces balanced bits and would pass. Use this
        alongside test_nonces_not_sequential, not as a substitute for it."""
        N_UNLOCKS = 32
        car, fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        ones = 0
        total = 0
        for _ in range(N_UNLOCKS):
            for byte in self._capture_nonce(car, fob):
                for bit in range(8):
                    ones += (byte >> bit) & 1
                    total += 1

        ratio = ones / total
        assert 0.35 < ratio < 0.65, \
            f"Nonce bits strongly skewed: {ratio:.1%} ones (expected ~50%)"

@pytest.mark.car2
@pytest.mark.car5
class TestPairingPinAttacks:
    """Attacks that extract the pairing pin from a paired fob."""

    def test_brute_force_attack_on_pairing_pin(self, deploy):
        fob = deploy(RoleConfig("paired_fob", id="1337", pin="00000A"))

        pin_guess = 0
        start = time.perf_counter()
        for i in range(20):
            resp = proto.cmd_pair(fob, f"{pin_guess:06X}")
            if resp.success:
                break
            else:
                pin_guess += 1
        end = time.perf_counter()

        assert (end - start) > 5, f"Pairing attempts not sufficiently slow ({(end - start)/10} seconds per attempt)."

    @pytest.mark.hardware_only
    def test_timing_attack_on_pairing_pin(self, deploy):
        random_pin = secrets.token_hex(3)
        # Disable the anti-brute-force pairing delay for this fob build so the
        # ~768 memcmp timing samples (256 values x 3 byte positions) complete
        # in a reasonable amount of time. The delay itself is covered by
        # test_brute_force_attack_on_pairing_pin above.
        fob = deploy(RoleConfig("paired_fob", id="1337", pin=random_pin, pairing_delay_ms="1"))

        # memcmp leaks at the byte level (2 hex digits at a time), not the nibble
        # level, because hexToBytes() packs the pin into 3 binary bytes before
        # comparison. Iterate over all 256 byte values per byte position.
        guess_bytes = []
        for byte_pos in range(3):
            prefix = bytes(guess_bytes).hex().upper()
            suffix = "00" * (2 - byte_pos)

            memcmp_times = {}
            found = False
            for byte_val in range(256):
                candidate = prefix + f"{byte_val:02X}" + suffix
                resp = proto.cmd_pair(fob, candidate)
                if resp.success:
                    guess_bytes.append(byte_val)
                    found = True
                    break
                memcmp_times[byte_val] = proto.get_pair_memcmp_time(fob)

            if not found:
                best = max(memcmp_times, key=memcmp_times.get)
                guess_bytes.append(best)

            top3 = sorted(memcmp_times.items(), key=lambda x: -x[1])[:3]
            print(f"Byte {byte_pos}: top 3: {[(f'{v:02X}', t) for v, t in top3]}")

        guess = bytes(guess_bytes).hex().upper()
        print(f"Expected: {random_pin.upper()}, determined: {guess}")
        assert guess != random_pin.upper(), "Pairing pin was recoverable using a timing attack"

@pytest.mark.car5
class TestFeatureFile:
    """Tests that feature files cannot be forged."""

    def test_feature_file_cannot_be_modified_and_deployed(self, deploy):
        car, paired_fob = deploy(RoleConfig("car", id="1337"), RoleConfig("paired_fob", id="1337", pin="123456"))

        # Get enabled features
        flash = proto.get_flash_data(paired_fob)
        num_active_features = flash.feature_info.num_active
        active_features = [False, False, False]
        for i in range(num_active_features):
            active_features[flash.feature_info.features[i]-1] = True
        assert active_features[1] == False, "Fob started with Feature 2 active"

        # Package feature 1 (comes with Car #5)
        pkg = create_feature_package(flash.pair_info.car_id, 1)

        # Modify feature 1 to become feature 2, leaving the MAC (still over
        # feature 1) untouched, i.e. a forgery attempt
        forged = FeaturePackage.unpack(pkg)
        forged.feature = 2
        pkg = forged.pack()

        # Modified feature should be rejected
        resp = proto.cmd_enable(paired_fob, pkg)
        assert not resp.success, "Fob accepted forged Feature 2"

        # Feature 2 should not be enabled
        flash = proto.get_flash_data(paired_fob)
        num_active_features = flash.feature_info.num_active
        active_features = [False, False, False]
        for i in range(num_active_features):
            active_features[flash.feature_info.features[i]-1] = True
        assert active_features[1] == False, "Fob accepted forged Feature 2"

    @pytest.mark.hardware_only
    def test_timing_attack_on_feature_file_mac_comparison(self, deploy):
        car_id = "1337"
        fob = deploy(RoleConfig("paired_fob", id=car_id, pin="123456"))

        exp_pkg = create_feature_package(car_id, 1)

        # Make a real package, but then clear out the MAC to start fresh
        forged_pkg = FeaturePackage.unpack(exp_pkg)
        forged_pkg.mac = b'\x00'*8

        for byte_pos in range(8):            
            memcmp_times = {}
            found = False
            for byte_val in range(256):
                mac = bytearray(forged_pkg.mac)
                mac[byte_pos] = byte_val
                forged_pkg.mac = bytes(mac)

                resp = proto.cmd_enable(fob, forged_pkg.pack())
                if resp.success:
                    found = True
                    break
                memcmp_times[byte_val] = proto.get_feature_memcmp_time(fob)

            if not found:
                best = min(memcmp_times, key=memcmp_times.get) if byte_pos == 3 else max(memcmp_times, key=memcmp_times.get)
                mac = bytearray(forged_pkg.mac)
                mac[byte_pos] = best
                forged_pkg.mac = bytes(mac)

            top3 = sorted(memcmp_times.items(), key=lambda x: -x[1])[:3]
            print(f"Byte {byte_pos}: top 3: {[(f'{v:02X}', t) for v, t in top3]}")
            bottom3 = sorted(memcmp_times.items(), key=lambda x: x[1])[:3]
            print(f"Byte {byte_pos}: bottom 3: {[(f'{v:02X}', t) for v, t in bottom3]}")

        exp_mac = FeaturePackage.unpack(exp_pkg).mac
        print(f"Expected: {exp_mac}, determined: {forged_pkg.mac}")
        assert exp_mac != forged_pkg.mac, "Feature MAC was recoverable using a timing attack"
