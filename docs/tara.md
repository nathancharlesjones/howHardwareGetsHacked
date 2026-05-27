# Threat Analysis and Risk Assessment (TARA)
### eCTF Key Fob System — Illustrative Example per ISO/SAE 21434

---

## 1. Scope and Assets

**System:** Automotive key fob unlock system consisting of a car unit and one or more paired fobs communicating over a UART-based wireless link.

**Assets under protection:**

| Asset ID | Asset | Description |
|----------|-------|-------------|
| A-1 | Car flags | Unlock flag and feature flags stored in car flash (`FLAG_SIZE` = 64 bytes each) |
| A-2 | AES-128 car key | 16-byte symmetric key stored in fob flash (`PAIR_PACKET.key`); used to compute unlock MAC |
| A-3 | Pairing PIN | 7-character PIN stored in fob flash (`PAIR_PACKET.pin`); gates new fob pairing |
| A-4 | Unlock protocol integrity | Guarantee that only a legitimately paired fob can trigger a car unlock |
| A-5 | Feature packages | Manufacturer-signed packages that enable optional car features |

---

## 2. Threat Matrix

Impact ratings: **Critical** / **High** / **Medium** / **Low**
Attack feasibility: **High** (minimal equipment/expertise) → **Low** (lab/nation-state level)
Risk level: derived from impact × feasibility

| ID | Threat Scenario | Affected Asset(s) | Damage Scenario | Impact | Feasibility | Risk |
|----|----------------|-------------------|-----------------|--------|-------------|------|
| T-1 | Attacker reads flash memory over unlocked SWD/JTAG debug port | A-1, A-2, A-3 | All flags extracted directly; car key extracted, enabling message forgery; PIN extracted, enabling unauthorized fob pairing | Critical | **High** — requires only a $20 debug adapter and free software | **Critical** |
| T-2 | Attacker captures a valid unlock message over the air and retransmits it (replay attack) | A-4 | Car unlocked without an authorized fob present | High | **High** — requires only an SDR or UART tap; no crypto knowledge needed | **High** |
| T-3 | Attacker brute-forces the 6-digit pairing PIN to pair an unpaired fob | A-3 | Attacker gains a permanently paired fob, bypassing physical fob requirement | High | **Medium** — PIN space is 10^6; pairing requires physical proximity and a paired fob present | **Medium** |
| T-4 | Attacker analyzes power consumption during AES-CMAC computation to extract the car key (power side-channel) | A-2 | Car key extracted; attacker can forge valid unlock messages indefinitely | Critical | **Low** — requires oscilloscope, specialized expertise, and physical access to fob during operation | **Medium** |
| T-5 | Attacker uses voltage fault injection to bypass counter check or MAC verification | A-4 | Car unlocked without valid credentials | High | **Low** — requires specialized glitching hardware and significant expertise | **Medium** |
| T-6 | Attacker decapsulates MCU and reads memory values using scanning electron microscope (SEM) | A-1, A-2, A-3 | All secrets extracted; permanent compromise of any car paired with targeted fob | Critical | **Very Low** — nation-state / well-funded lab capability only; destructive to device | **Low** |
| T-7 | Attacker crafts a forged feature package to enable unpurchased features | A-5 | Unauthorized feature access; financial loss to manufacturer | Medium | **Medium** — requires knowledge of package format; CMAC prevents forgery without key | **Low** |
| T-8 | Attacker reuses a valid feature package from car A on car B | A-5 | Unauthorized feature enablement on unintended vehicle | Medium | **Low** — package embeds `car_id`; car validates match before accepting | **Low** |

---

## 3. Mitigation / Solution Table

| Threat | Treatment | Mitigation Implemented | Commit | Residual Risk | Status |
|--------|-----------|----------------------|--------|---------------|--------|
| T-1 | Reduce | Enable STM32 Read Protection (RDP Level 1) to disable SWD/JTAG readout | `d39462a` | Low — RDP Level 1 can be bypassed by RDP regression attack; Level 2 would eliminate this but permanently bricks device | **Mitigated** |
| T-2 | Reduce | Rolling counter + AES-128-CMAC on unlock message; car rejects any message with counter ≤ stored value for that fob ID | `(current)` | Low — counter window and rollover behavior require careful tuning (see pitfalls note in threat model) | **Mitigated** |
| T-3 | Reduce | *(Not yet implemented)* Rate-limit pairing attempts; require physical button press on paired fob within timeout | — | Medium | **Open** |
| T-4 | Accept / future | *(Not yet implemented)* Countermeasures include: randomized execution timing, hardware AES accelerator with built-in masking | — | Medium | **Accepted (out of scope for current series stage)** |
| T-5 | Accept / future | *(Not yet implemented)* Countermeasures include: redundant checks, supply voltage monitoring, glitch detection peripherals | — | Medium | **Accepted (out of scope for current series stage)** |
| T-6 | Accept | Attack cost vastly exceeds value of flags in a competition/demo context; no practical countermeasure at firmware level | — | Low (feasibility-limited) | **Out of Scope** |
| T-7 | Reduce | Package format embeds `car_id` and is validated by car firmware; AES-CMAC prevents forgery without manufacturer key | existing | Low | **Mitigated** |
| T-8 | Reduce | Car validates `car_id` field in feature package before enabling feature | existing | Low | **Mitigated** |

---

## 4. Notes on Limitations

This TARA reflects the system state as of the rolling-code + CMAC commit. It is a **point-in-time assessment** — if the firmware changes (new defenses, protocol modifications, new features), the attack feasibility ratings for open threats must be re-evaluated and any newly introduced attack surfaces must be added to Section 2.

Per ISO/SAE 21434, this document should be treated as a **living artifact** subject to update during:
- Any design change affecting assets or attack surfaces
- Discovery of new vulnerability classes applicable to the platform
- Post-deployment monitoring findings
