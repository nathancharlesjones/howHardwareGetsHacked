import math
import statistics
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
from tqdm import trange, tqdm

from package import create_feature_package, FeaturePackage

from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms


def _expected_start_mac(car_id: str, feature_data: bytes) -> bytes:
    """
    Recompute the START message MAC unlockCar() (car.c) expects, straight
    from this car's start_key - so a timing-attack test can report exactly
    what it was trying to recover, not just whether it succeeded.

    start_key is per-car (unlike the fleet-wide feature_key in package.py),
    so this reads it out of the same secrets.json create_feature_package()
    uses (car_gen_secret.py writes both secrets.json and the build's
    secrets.h from the same key - secrets.json is just easier to parse than
    a generated C header).
    """
    secrets_file = os.environ.get("TEST_SECRETS_FILE", "secrets/secrets.json")
    with open(secrets_file, "r") as fp:
        keys = json.load(fp)["keys"]
    start_key = bytes(keys[car_id]["start"])

    # Mirrors car.c: AES_CMAC_digest() over [magic | length | feature_data],
    # i.e. everything in START_MSG_BUF up to (not including) the mac field.
    c = cmac.CMAC(algorithms.AES(start_key))
    c.update(bytes([proto.START_MAGIC, len(feature_data) + 8]) + feature_data)
    return c.finalize()[:8]


def _try_start_msg_mac_candidate(car, paired_fob, feature_data: bytes, guess_bytes: bytearray) -> tuple:
    """
    Stage guess_bytes as the START message MAC (via setStartMsg) and trigger
    one unlock attempt.

    Returns:
        (forged, memcmp_time): forged is True if car.c accepted the guess
        (feature 3 shows up in getFeatures()); memcmp_time is car.c's
        reported memcmp cycle count for that attempt (None if forged).
    """
    payload = feature_data + bytes(guess_bytes)
    resp = proto.cmd_set_start_msg(paired_fob, payload)
    assert resp.success, f"setStartMsg failed: {resp.error}"

    resp = proto.cmd_btn_press(paired_fob)
    assert resp.success, f"Unlock failed: {resp.error}"

    num_active, features = proto.get_features(car)
    if num_active == 1 and features[0] == 3:
        return True, None
    return False, proto.get_start_mac_memcmp_time(car)


FEATURE_DATA_SIZE = 15  # sizeof(FEATURE_DATA): car_id[11] + num_active[1] + features[3]

@pytest.mark.car1
@pytest.mark.car2
@pytest.mark.car3
@pytest.mark.car4
class TestSimpleReplayAttacks:
    """Basic replay attacks. Defenses against these apply to all eCTF car scenarios."""

    def test_replay_captured_unlock_fails(self, car_and_paired_fob):
        """An attacker who eavesdropped on one unlock can replay it to unlock again."""
        car, fob = car_and_paired_fob

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

@pytest.mark.car1
@pytest.mark.car2
@pytest.mark.car3
@pytest.mark.car4
@pytest.mark.car5
class TestUnlockBufferOverflow:
    """car.c's unlockCar() reads the first board message of an unlock attempt
    (UNLOCK_MAGIC) into a fixed 64-byte stack buffer, before any nonce/CMAC
    exchange happens - i.e. fully pre-auth. The receive path
    (messages.c: receive_board_message) does:

        message->message_len = uart_readb(BOARD_UART);       // attacker-controlled, 0-255
        uart_read(BOARD_UART, message->buffer, message->message_len);

    with no check that message_len fits the 64-byte buffer it's about to fill.
    Declaring a length larger than the buffer overflows it, corrupting
    unlockCar()'s saved registers and return address. On real Cortex-M
    hardware (no stack protector in this build - see SConstruct, no
    -fstack-protector* flag anywhere in the ARM build config) this is full
    control-flow hijack; see testing/test_stack_overflow_poc.py for a working
    proof-of-concept that turns it into arbitrary code execution and flag
    exfiltration on real STM32 hardware. Here on sim, gcc's own stack
    protector (glibc canary between the locals and the saved return address)
    independently catches the corruption and aborts the process - so this
    test demonstrates the underlying bug (an oversized message_len reaches
    and corrupts the return address) via that crash, without needing to
    reproduce the RCE mechanism itself."""

    def test_oversized_unlock_message_crashes_car(self, car_and_paired_fob):
        # Deliberately a *paired* fob, not unpaired, even though pairing state
        # is irrelevant to this pre-auth attack: an unpaired fob's main loop
        # reacts to any unsolicited board-UART byte by calling
        # receivePairData() (fob.c), which itself blocks waiting for a
        # PAIR_MAGIC message. The car's own unsolicited NONCE_MAGIC reply to
        # our forged UNLOCK would trigger exactly that, hanging the fob and
        # making it look like the attack "worked" (no response) regardless of
        # whether the car actually crashed. A paired fob only reacts to
        # buttonPressed(), so it never touches unsolicited board bytes and
        # can't produce that false positive.
        car, fob = car_and_paired_fob
        assert proto.is_locked(car), "Sanity check failed before attack"

        # 200 bytes is comfortably past car.c's 64-byte buffer and reaches
        # into the saved return address; sendBoardMsg's own decode buffer
        # (TEST_SENDBOARDMSG_BUF_LEN, see car.c/fob.c) is sized to carry this
        # for real, so message_len here matches the real number of bytes
        # actually placed on the wire - this models a real attacker exactly,
        # no test-harness workaround needed.
        proto.cmd_send_board_msg(fob, proto.UNLOCK_MAGIC, b"A" * 200)
        time.sleep(0.05)

        # unlockCar() won't reach its own return (and thus won't touch the
        # corrupted saved return address) until the RESPONSE_MAGIC receive
        # unblocks - the attacker doesn't have the CMAC key, so the actual
        # bytes here don't matter, only that the memcmp is reached and fails.
        proto.cmd_send_board_msg(fob, proto.RESPONSE_MAGIC, b"\x00" * 8)
        time.sleep(0.2)

        # A correctly-guarded car would still be alive: the memcmp mismatch
        # is expected (this isn't a real fob), so it should just send an ACK
        # failure and return to its main loop. Instead, the corrupted return
        # address/canary takes it down entirely, and it never responds to
        # anything again.
        #
        # NOTE: once message_len is validated against the buffer size (the
        # actual fix), this assertion is the one that should start failing -
        # flip it to `assert resp.success` at that point.
        resp = proto.cmd_is_locked(car, timeout=2.0)
        assert not resp.success, (
            "Car responded normally after an oversized UNLOCK message - expected "
            "it to have crashed (unbounded uart_read() into a fixed stack buffer, "
            "corrupting the saved return address / stack canary)."
        )

@pytest.mark.car2
class TestComplexReplayAttacks:
    """Advanced replay attacks that require temporary access to a paired fob (eCTF Car #2
    scenario). Defenses against these require a challenge-response protocol."""

    def test_forced_rollback_fails(self, car_and_paired_fob):
        """Forced rollback attack should be defeated: even if an attacker mass-erases
        the car's flash to reset its counter table (simulated by reset), replaying a
        previously captured unlock should be rejected."""
        car, fob = car_and_paired_fob

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

    def test_birthday_bound_attack_quick_check(self, car_and_paired_fob):
        """Fast, always-on cost estimate for the birthday-bound table/oracle attack
        (see test_oracle_attack_full for an actual reproduction, skipped by default).

        An attacker with temporary physical access to a paired fob (the eCTF Car #2
        threat model) can record a table of (nonce -> response) pairs from real,
        legitimate unlocks while they have the fob. The car's response is a
        deterministic CMAC of the nonce under the shared key, so if the car ever
        reissues a nonce already in that table - after the attacker no longer has
        the fob - the old recorded response is still valid and can be replayed.

        Nonce width isn't something that needs statistical inference: it's a fixed,
        wire-visible protocol parameter, so a single real unlock is enough to read
        it directly and project the attack's cost analytically. The projection uses
        the wire time computed straight from the observed board-bus message sizes
        (not the host-command bytes used to trigger this test's own button press,
        and not our own getBoardMsgLog bookkeeping overhead) - a real attacker
        sniffing the car<->fob bus doesn't pay either of those costs."""
        car, fob = car_and_paired_fob

        resp = proto.cmd_btn_press(fob)
        assert resp.success, f"Unlock failed: {resp.error}"

        log = proto.cmd_get_board_msg_log(car, role="car")
        unlock_entries = [e for e in log if not e.tx and e.magic == proto.UNLOCK_MAGIC]
        nonce_entries = [e for e in log if e.tx and e.magic == proto.NONCE_MAGIC]
        response_entries = [e for e in log if not e.tx and e.magic == proto.RESPONSE_MAGIC]
        ack_entries = [e for e in log if e.tx and e.magic == proto.ACK_MAGIC]
        start_entries = [e for e in log if not e.tx and e.magic == proto.START_MAGIC]
        assert unlock_entries and nonce_entries and response_entries and ack_entries and start_entries, \
            "Did not capture a full unlock exchange"

        nonce_bits = len(nonce_entries[-1].payload) * 8
        nonce_space = 2 ** nonce_bits

        # Wire time for one full unlock exchange, from the observed board-bus message
        # sizes (each message is a 2-byte magic+len prefix plus its payload) at the
        # board's baud rate.
        BAUD = 115200
        byte_time = 10 / BAUD  # 8N1: start + 8 data + stop bits
        msg_bytes = sum(2 + len(e.payload) for e in (
            unlock_entries[-1], nonce_entries[-1], response_entries[-1],
            ack_entries[-1], start_entries[-1],
        ))
        unlock_time_s = msg_bytes * byte_time

        # Symmetric two-phase birthday attack (build a table of T entries, then watch
        # M more unlocks for a repeat): T=M=sqrt(nonce_space * ln(2)) gives ~50% odds.
        table_size = math.sqrt(nonce_space * math.log(2))
        projected_attack_s = 2 * table_size * unlock_time_s

        # 1 hour - a realistic bar, not a generous one. A valet (or anyone else
        # who can plausibly borrow a fob for ~30-60 minutes) can build the table
        # during that window and keep attacking afterward; if the combined
        # attack fits inside that same order of magnitude, it doesn't take a
        # decade-scale adversary to pull off, just an ordinary opportunistic one.
        CONCERNING_THRESHOLD_S = 1 * 3600

        print(f"\nObserved nonce width: {nonce_bits} bits ({nonce_space:,} possible values)")
        print(f"Observed wire time per unlock: {unlock_time_s * 1000:.3f} ms")
        print(f"Projected birthday-bound table attack (~50% odds): ~{table_size:,.0f} unlocks "
              f"each way, ~{projected_attack_s:,.1f}s (~{projected_attack_s / 86400:.2f} days)")

        assert projected_attack_s >= CONCERNING_THRESHOLD_S, (
            f"A birthday-bound table/oracle attack against this {nonce_bits}-bit nonce "
            f"could plausibly succeed in as little as ~{projected_attack_s:,.1f}s "
            f"(~{projected_attack_s / 86400:.2f} days) of continuous unlock attempts at "
            f"the protocol's own wire rate - too low to be comfortable. Pass "
            f"--run-oracle-attack-full to reproduce this directly."
        )

    @pytest.mark.birthday_bound_attack_full
    def test_birthday_bound_attack_full(self, car_and_paired_fob, request):
        """Full reproduction of the birthday-bound table/oracle attack (skipped by
        default - pass --run-oracle-attack-full to enable; see
        test_oracle_attack_quick_check for a fast, always-on cost estimate of this
        same vulnerability that doesn't require actually reproducing it).

        Builds a table of --oracle-table-size (nonce -> response) pairs from real
        unlocks (modeling an attacker's limited fob-access window), then keeps
        unlocking - up to --oracle-max-iter more times, or indefinitely if not
        given - watching for a nonce to repeat one already in that frozen table.
        Nonces seen only during the second window are never added to the table:
        a repeat entirely within that window wasn't in the attacker's table at the
        time they'd have needed it, so it isn't something they could have exploited."""
        car, fob = car_and_paired_fob

        TABLE_SIZE = request.config.getoption("--oracle-table-size")
        MAX_ITER = request.config.getoption("--oracle-max-iter")  # 0 => no cap, run until found

        # Board message logs hold 15 entries = 3 unlocks worth (5 messages each), so
        # batch button presses 3 at a time before reading the log back.
        BATCH = 3

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
        for _ in trange(TABLE_SIZE // BATCH, desc="Phase 1: building table", unit="batch", unit_scale=BATCH):
            total_done, pairs = do_batch(total_done)
            for nonce, response in pairs:
                mac_values[nonce] = response
        print(f"\nBuilt a table of {len(mac_values)} (nonce -> response) pairs from {total_done} unlocks.")

        # Phase 2: attacker no longer has the fob - just watch for a repeat, up to
        # MAX_ITER further unlocks (or indefinitely if MAX_ITER is 0).
        collision_nonce = None
        collision_after = None
        monitored = 0
        monitor_bar = (
            trange(MAX_ITER // BATCH, desc="Phase 2: watching for a repeat", unit="batch", unit_scale=BATCH)
            if MAX_ITER
            else tqdm(desc="Phase 2: watching for a repeat", unit="batch", unit_scale=BATCH)
        )
        try:
            while MAX_ITER == 0 or monitored < MAX_ITER:
                total_done, pairs = do_batch(total_done)
                monitored += BATCH
                monitor_bar.update(1)
                for nonce, response in pairs:
                    if nonce in mac_values:
                        collision_nonce = nonce
                        collision_after = total_done
                        break
                if collision_nonce is not None:
                    break
        finally:
            monitor_bar.close()

        assert collision_nonce is None, (
            f"Nonce {collision_nonce.hex()} repeated one already in a {len(mac_values)}-entry "
            f"table after {collision_after} total unlocks ({monitored} monitoring unlocks) - an "
            f"attacker who recorded that table during a temporary fob-access window could have "
            f"replayed the old response and unlocked the car without the fob"
        )


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

    def test_nonces_differ_across_reboots(self, car_and_paired_fob):
        """Catch fixed seeds: a PRNG seeded with a constant value produces the
        same nonce sequence on every boot, letting an attacker who observed one
        session predict every future session without knowing any secret."""
        N_BOOTS = 10
        car, fob = car_and_paired_fob

        nonces = []
        for _ in range(N_BOOTS):
            proto.cmd_reset(car)
            nonces.append(self._capture_nonce(car, fob))

        assert len(set(nonces)) == N_BOOTS, \
            f"PRNG repeated a nonce across reboots: {[n.hex() for n in nonces]}"

    def test_nonces_not_sequential(self, car_and_paired_fob):
        """Catch counter-based PRNGs: state++ produces nonces with a constant
        difference of 1 between successive unlocks. An attacker who observes
        one nonce can immediately predict the next."""
        N_UNLOCKS = 8
        car, fob = car_and_paired_fob

        nonces = []
        for _ in range(N_UNLOCKS):
            nonces.append(int.from_bytes(self._capture_nonce(car, fob), 'little'))

        diffs = [(nonces[i+1] - nonces[i]) & 0xFFFFFFFF for i in range(len(nonces) - 1)]
        assert len(set(diffs)) > 1, \
            f"Nonces follow a constant step of {diffs[0]}: {[hex(n) for n in nonces]}"

    def test_nonce_bit_distribution(self, car_and_paired_fob):
        """Sanity check: nonce bits should be roughly 50/50 across many samples.

        Note: this test alone is not a meaningful security gate — a sequential
        counter (state++) also produces balanced bits and would pass. Use this
        alongside test_nonces_not_sequential, not as a substitute for it."""
        N_UNLOCKS = 32
        car, fob = car_and_paired_fob

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

    def test_feature_file_cannot_be_modified_and_deployed(self, car_and_paired_fob):
        car, paired_fob = car_and_paired_fob

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
    def test_timing_attack_on_feature_file_mac_comparison(self, paired_fob):
        car_id = "1337"
        fob = paired_fob

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
                # byte_pos == 3 is special-cased to min() rather than max()
                # because of how newlib-nano's memcmp compares this
                # particular pair of pointers: ENABLE_PACKET.mac happens to
                # land 4-byte aligned (offsetof == 12), so memcmp takes a
                # word-at-a-time fast path and the timing signal inverts at
                # the first word boundary it hits inside the 8-byte MAC (see
                # test_timing_attack_on_start_msg_mac_comparison below, where
                # the equivalent struct's mac field is *not* 4-byte aligned,
                # the fast path never triggers, and no inversion happens at
                # all). That means this hardcoded "byte 3" is an artifact of
                # this exact struct layout/compiler/libc - not something the
                # attack can assume in general. A more robust version of this
                # test wouldn't hardcode which byte(s) invert; it would
                # detect the inversion programmatically, e.g. by noticing
                # that all 256 candidates at some byte position clock in at
                # the same time (a sign every guess is equally wrong, because
                # the true differentiator was actually at the *previous*
                # byte and got picked incorrectly) and backtracking to retry
                # that earlier byte with the opposite selection rule.
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

    def test_mitm_attack_on_start_msg(self, car_and_paired_fob):
        """unlockCar() authenticates the UNLOCK/NONCE/RESPONSE challenge-response
        exchange with a CMAC, but once that passes it just trusts whatever
        FEATURE_DATA arrives in the following START message: it only checks
        car_id (car.c: `strcmp(car_id, feature_info->car_id)`), never a MAC
        over num_active/features. A fob only ever sends its own feature_info
        here, so this is unreachable through the fob's normal control flow -
        but the START message travels in the clear over the same board bus as
        everything else, so a MITM attacker sitting on that bus (no key
        material needed) can rewrite it in transit to claim any feature,
        including ones never purchased/paired. setStartMsg simulates exactly
        that interception: it lets us splice a forged FEATURE_DATA payload
        into the fob's *next* outgoing START message in place of its real one.
        """
        car, paired_fob = car_and_paired_fob

        # Unlock once, legitimately, to learn the wire format of a real START
        # message (car_id + this fob's actual, unmodified feature_info).
        resp = proto.cmd_btn_press(paired_fob)
        assert resp.success, f"Legitimate unlock failed: {resp.error}"

        # Get last valid start msg
        log = proto.cmd_get_board_msg_log(car, role="car")
        start_entries = [e for e in log if not e.tx and e.magic == proto.START_MAGIC]
        assert start_entries, "Should have captured a START message"
        captured_start = proto.FeatureData.unpack(start_entries[-1].payload)

        # This fob wasn't paired with any features enabled - confirm the
        # captured message reflects that before we tamper with it.
        assert captured_start.num_active == 0, "Fob unexpectedly started with an active feature"

        # Modify start msg to make feature 2 active. The car_id is left
        # untouched, so the one check unlockCar() does still passes.
        forged_start = proto.FeatureData(
            car_id=captured_start.car_id,
            num_active=1,
            features=[2, 0, 0],
        )

        # Set start msg - stored for exactly one send by attemptUnlock()
        resp = proto.cmd_set_start_msg(paired_fob, forged_start.pack())
        assert resp.success, f"setStartMsg failed: {resp.error}"

        # Check that getFeatures has no active features: the car hasn't
        # unlocked again yet, so it should still reflect the first, real
        # unlock's feature data, not the forged one just staged on the fob.
        num_active, features = proto.get_features(car)
        assert num_active == 0, "Car's feature record changed before the forged START was ever sent"

        # Unlock: the challenge-response exchange succeeds as normal (it's
        # untouched by this attack), then attemptUnlock() sends the forged
        # START message in place of the fob's real feature_info.
        resp = proto.cmd_btn_press(paired_fob)
        assert resp.success, f"Unlock failed: {resp.error}"

        # Check that getFeatures has feature 2 active: the car accepted the
        # forged feature data outright, with no MAC/signature ever required
        # over num_active/features - a MITM attacker who never had the
        # feature-package signing key (see TestFeatureFile above) can still
        # grant themselves any feature this way.
        num_active, features = proto.get_features(car)
        assert num_active != 1 and 2 not in features[:num_active], (
            f"Expected the forged START message to fail, got "
            f"num_active={num_active}, features={features}"
        )

    @pytest.mark.hardware_only
    def test_timing_attack_on_start_msg_mac_comparison(self, car_and_paired_fob):
        """The START message MAC check added in unlockCar() (car.c) guards
        against forgery (see test_mitm_attack_on_start_msg above), but a plain
        memcmp() leaks byte-by-byte timing information the same way the
        pairing PIN and feature-file MAC checks used to (see
        test_timing_attack_on_pairing_pin / test_timing_attack_on_feature_file_
        mac_comparison). An attacker who can get the fob to send arbitrary
        START message bytes over the board bus - exactly the setStartMsg
        primitive test_mitm_attack_on_start_msg uses - can forge a MAC one
        byte at a time by watching how long car.c's memcmp() takes to reject
        each guess, without ever knowing start_key.
        """
        car_id = "1337"
        car, paired_fob = car_and_paired_fob

        # A distinctive feature payload (num_active=1, feature 3 active) so a
        # successful forgery is unambiguous: getFeatures() will only ever
        # reflect it if car.c's memcmp() accepted our forged MAC, since this
        # fob was never paired with any real features to begin with.
        feature_data = proto.FeatureData(car_id=car_id.encode(), num_active=1, features=[3, 0, 0]).pack()

        # memcmp leaks at the byte level. Guess the 8 MAC bytes one at a time,
        # timing car.c's rejection of each candidate via getStartMacMemcmpTime.
        #
        # A single sample per candidate is noisy enough on real hardware that
        # an unrelated spike can occasionally beat the real signal (a wrong
        # candidate reads *slower* than the correct one, purely by chance -
        # this struct isn't 4-byte aligned the way ENABLE_PACKET.mac is in
        # test_timing_attack_on_feature_file_mac_comparison, so that test's
        # byte-3 word-boundary quirk doesn't reproduce here the same way). So
        # instead of trusting one sample, re-sample only the loudest few
        # candidates several more times each and pick by median.
        #
        # That said, "this struct happens not to be 4-byte aligned" is itself
        # just as much a layout artifact as the other test's "byte 3 happens
        # to invert" - it's true for this exact struct/compiler/libc, not a
        # general property of the attack. A more robust version of both this
        # test and test_timing_attack_on_feature_file_mac_comparison
        # shouldn't assume an alignment/inversion story up front at all; it
        # should detect it programmatically. E.g. if every one of the 256
        # candidates at some byte position comes back with (statistically)
        # the same time, that's a sign the true differentiator was actually
        # at the *previous* byte and got guessed wrong there - the fob is
        # bailing out at the same earlier byte every time regardless of what
        # we send here - so the test should backtrack, retry the previous
        # byte with the next-best candidate (or the opposite selection rule),
        # and only then move forward again.
        RESAMPLE_TOP_N = 3
        RESAMPLE_COUNT = 4

        guess_bytes = bytearray(8)
        for byte_pos in range(8):
            memcmp_times = {}
            found = False
            for byte_val in range(256):
                guess_bytes[byte_pos] = byte_val
                forged, t = _try_start_msg_mac_candidate(car, paired_fob, feature_data, guess_bytes)
                if forged:
                    found = True
                    break
                memcmp_times[byte_val] = t

            if not found:
                top_candidates = sorted(memcmp_times, key=memcmp_times.get, reverse=True)[:RESAMPLE_TOP_N]
                medians = {}
                for candidate in top_candidates:
                    guess_bytes[byte_pos] = candidate
                    samples = [memcmp_times[candidate]]
                    for _ in range(RESAMPLE_COUNT):
                        forged, t = _try_start_msg_mac_candidate(car, paired_fob, feature_data, guess_bytes)
                        if forged:
                            found = True
                            break
                        samples.append(t)
                    if found:
                        break
                    medians[candidate] = statistics.median(samples)

                if not found:
                    guess_bytes[byte_pos] = max(medians, key=medians.get)
                    print(f"Byte {byte_pos}: resampled medians: {[(f'{v:02X}', t) for v, t in sorted(medians.items(), key=lambda x: -x[1])]}")

            top3 = sorted(memcmp_times.items(), key=lambda x: -x[1])[:3]
            print(f"Byte {byte_pos}: top 3 (first pass): {[(f'{v:02X}', t) for v, t in top3]}")

        num_active, features = proto.get_features(car)
        forged = (num_active == 1 and features[0] == 3)
        expected_mac = _expected_start_mac(car_id, feature_data)
        print(f"Expected MAC: {expected_mac.hex()}, determined: {guess_bytes.hex()}, forgery succeeded: {forged}")
        assert bytes(guess_bytes) != expected_mac, "START message MAC was recoverable using a timing attack"