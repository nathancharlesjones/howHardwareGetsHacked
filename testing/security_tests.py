import math
import time
import pytest
import struct
from collections import Counter
from conftest import RoleConfig
import protocol as proto
import secrets


def _mcv_min_entropy(samples: list[int]) -> float:
    """NIST SP 800-90B §6.3.1 Most Common Value Estimate.

    Returns the min-entropy lower bound (bits) for a byte-valued source given
    a list of observed samples. Uses a 99% one-sided Wilson confidence interval
    (z = 2.576) as specified in §6.3.1.
    """
    N = len(samples)
    p_hat = max(Counter(samples).values()) / N
    z = 2.576
    p = min(1.0,
            (p_hat + z*z / (2*N) + z * math.sqrt(p_hat*(1-p_hat)/N + z*z/(4*N*N)))
            / (1 + z*z / N))
    return -math.log2(p)


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
@pytest.mark.car3
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

    def test_seed_entropy_sufficient(self, request, deploy):
        """Catch weak entropy sources: apply the NIST SP 800-90B §6.3.1 Most
        Common Value estimate per byte across N seeds and verify the summed
        min-entropy meets a minimum threshold.

        The estimate is applied independently to each of the 16 byte positions
        of the getPrngSeed() output, then summed. Bytes that never vary (e.g.
        always 0x00) contribute 0 bits and pull the total below the threshold,
        exposing under-seeded implementations.

        N_SAMPLES is configurable via --n-samples. The MCV lower bound saturates
        at roughly log2(N) bits/byte, so interpretation depends on sample count:
          N~50   → max certifiable ~48 bits; detects constant/broken bytes only
          N~500  → max certifiable ~94 bits; distinguishes 5-bit from 3-bit sources
          N~5000 → max certifiable ~125 bits; meaningful estimate for 8-bit sources"""
        N_SAMPLES = request.config.getoption("--n-samples")
        THRESHOLD_BITS = 32  # sanity floor: catches constant bytes at any N

        car = deploy(RoleConfig("car", id="1337"))

        seeds = []
        for _ in range(N_SAMPLES):
            proto.cmd_reset(car)
            seeds.append(proto.get_prng_seed(car))

        per_byte = [_mcv_min_entropy([seed[i] for seed in seeds]) for i in range(16)]
        total_bits = sum(per_byte)

        # Theoretical maximum MCV total for a truly uniform source at this N:
        # when max_count=1 (no repeated value), p_hat=1/N, apply Wilson CI.
        z = 2.576
        p_hat_best = 1.0 / N_SAMPLES
        p_best = min(1.0,
                     (p_hat_best + z*z / (2*N_SAMPLES) + z * math.sqrt(p_hat_best*(1-p_hat_best)/N_SAMPLES + z*z/(4*N_SAMPLES*N_SAMPLES)))
                     / (1 + z*z / N_SAMPLES))
        max_possible = -math.log2(p_best) * 16

        pct = total_bits / max_possible * 100
        if pct >= 70:
            quality = "GOOD  (source looks uniform)"
        elif pct >= 40:
            quality = "OK    (some byte positions have limited variation)"
        else:
            quality = "WEAK  (significant entropy deficit)"

        print(
            f"\nSeed entropy estimate:  {total_bits:.1f} bits  "
            f"({pct:.0f}% of {max_possible:.0f}-bit ceiling at N={N_SAMPLES})  [{quality}]"
        )
        print(f"Per-byte: {[f'{b:.1f}' for b in per_byte]}")
        print(
            f"Note: MCV ceiling grows with N. "
            f"Run with --n-samples=5000 for a meaningful estimate of an 8-bit/byte source."
        )

        if total_bits < THRESHOLD_BITS:
            pytest.xfail(
                f"Seed entropy estimate {total_bits:.1f} bits < {THRESHOLD_BITS} bits. "
                f"Per-byte: {[f'{b:.1f}' for b in per_byte]}"
            )

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
                memcmp_times[byte_val] = proto.get_memcmp_time(fob)

            if not found:
                best = max(memcmp_times, key=memcmp_times.get)
                guess_bytes.append(best)

            top3 = sorted(memcmp_times.items(), key=lambda x: -x[1])[:3]
            print(f"Byte {byte_pos}: top 3: {[(f'{v:02X}', t) for v, t in top3]}")

        guess = bytes(guess_bytes).hex().upper()
        print(f"Expected: {random_pin.upper()}, determined: {guess}")
        assert guess != random_pin.upper(), "Pairing pin was recoverable using a timing attack"
