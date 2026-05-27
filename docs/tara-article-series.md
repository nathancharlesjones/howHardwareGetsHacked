# Threat Analysis and Risk Assessment (TARA)
### eCTF Key Fob System — Article Series Companion Document

> **Note on methodology:** TARA is a process defined in ISO/SAE 21434, an automotive cybersecurity standard. The standard specifies *what* a TARA must accomplish (identify assets, enumerate threats, rate risk, and document treatment decisions) but leaves the exact format to the practitioner. The layout and terminology below represent one reasonable interpretation. The companion document `tara.md` covers the full project; this document covers only the attacks and defenses depicted in the article series threat model diagram.

---

## 1. Scope and Assets

>  **Assets** are things worth protecting — data, functions, or capabilities whose loss, disclosure, or corruption would harm the system's security goals. Identifying them first gives every subsequent threat a concrete target: rather than asking "what could go wrong?", you ask "what could go wrong *with this specific thing*?"

**System:** Automotive key fob unlock system consisting of a car unit and one or more paired fobs communicating over a UART-based wireless link.

| Asset ID | Asset | Description |
|----------|-------|-------------|
| A-1 | Car flags | Unlock flag and feature flags stored in car flash memory. These are the competition's "crown jewels" — capturing one means an attacker has won that car's challenge. |
| A-2 | Unlock protocol integrity | The guarantee that a car only unlocks in response to a message from its legitimately paired fob. Compromising this lets an attacker unlock a car without physical possession of the fob. |

---

## 2. Threat Matrix

>  A **threat** is a possible action an attacker could take against an asset. The matrix below rates each threat on two independent axes — how bad the outcome is, and how hard it is to pull off — then combines them into an overall risk level.

**Impact** — How damaging is it if this threat is realized?

- **Critical**: Attacker achieves full objectives (e.g., all flags captured across all cars).
- **High**: Significant harm to most assets (e.g., flags captured for a subset of cars).
- **Medium**: Partial harm or harm requiring additional steps to exploit.
- **Low**: Minor or easily recoverable harm.

**Attack Feasibility** — How realistic is it that an attacker could carry this out?
- **High**: Requires only commodity hardware (≤$50) and publicly documented techniques. Achievable by a motivated hobbyist in an afternoon.
- **Medium**: Requires specialized knowledge or moderately expensive equipment, but no exotic capabilities.
- **Low**: Requires significant expertise, expensive lab equipment, or extended time.
- **Very Low**: Nation-state or well-funded research lab capability; likely destructive to the device.

>  **Risk** — Derived by combining Impact and Feasibility. A Critical impact with High feasibility is Critical risk; a Critical impact with Very Low feasibility may only be Low or Medium risk because so few attackers can realistically attempt it. There is no single universal formula — this is a judgment call informed by the ratings.

| ID | Threat Scenario | Affected Asset(s) | Damage Scenario | Impact | Feasibility | Risk |
|----|----------------|-------------------|-----------------|--------|-------------|------|
| T-1 | Attacker connects a debug adapter to the SWD/JTAG pins and reads flash contents directly | A-1, A-2 | All flags extracted from car flash; car key extracted, enabling arbitrary unlock message forgery | Critical | **High** — $20 debug adapter, free OpenOCD toolchain, ~30 minutes | **Critical** |
| T-2 | Attacker taps the fob-to-car UART link, captures a valid unlock message, and retransmits it (replay attack) | A-2, A-1 (partial) | Car unlocked without authorized fob; unlock flags captured for any car the attacker observed in operation (Cars #1–4) | High | **High** — UART tap or SDR; no cryptographic knowledge required | **High** |
| T-3 | Attacker physically decapsulates the MCU and reads memory cell values using a scanning electron microscope (SEM) | A-1, A-2 | All secrets and flags extracted; permanent compromise of any car paired with the targeted fob | Critical | **Very Low** — requires specialized lab, is destructive to the device, and costs thousands of dollars | **Low** |
| T-4 | Attacker brute-forces the 128-bit car key used for AES-CMAC | A-2, A-1 (partial) | Car key recovered; attacker can forge valid unlock messages for Cars #1–4 indefinitely | Critical | **Very Low** — AES-128 has 2¹²⁸ possible keys; exhaustive search is computationally infeasible with any known hardware | **Low** |
| T-5 | Attacker observes three consecutive car keys generated at provisioning time and reverses the key generation algorithm to predict or recover the key | A-2, A-1 (partial) | Car key recovered for Cars #1–4 without breaking AES itself | Critical | **Low** — requires access to multiple provisioning outputs and knowledge of a weakness in the key generation process; not feasible if a cryptographically secure RNG is used | **Low–Medium** |

---

## 3. Mitigation / Solution Table

For each threat, a **treatment decision** is made. The four standard options are:

- **Reduce**: Implement a control that lowers the impact or feasibility of the threat. This is the most common choice.
- **Avoid**: Redesign or remove the functionality that enables the threat entirely.
- **Share**: Transfer the risk to another party (e.g., insurance, outsourcing to a certified subsystem). Rare in embedded firmware.
- **Accept**: Formally acknowledge the risk and decide not to act on it. Acceptable when feasibility is very low, cost of mitigation is disproportionate, or the asset value does not justify the investment. An acceptance decision should be documented and reviewed periodically.

The **Status** column reflects the current state of the treatment:
- **Mitigated**: A control has been implemented and is active in the current firmware.
- **Open**: The threat is in scope but no mitigation has been implemented yet.
- **Accepted (Out of Scope)**: The risk has been formally accepted; no mitigation is planned within this project.

> **Residual Risk** is the risk that remains *after* a mitigation is in place. No mitigation is perfect. A "Low" residual risk means the mitigation significantly reduces the threat; remaining risk is acknowledged but considered acceptable. A "Medium" residual risk means the mitigation helps but notable weaknesses remain.

| Threat | Treatment | Mitigation Implemented | Commit | Residual Risk | Status |
|--------|-----------|----------------------|--------|---------------|--------|
| T-1 | Reduce | Enable STM32 Read Protection Level 1 (RDP1) via OpenOCD at provisioning time. RDP1 disables SWD/JTAG readout of flash and SRAM; re-enabling it requires a full chip erase that destroys all stored secrets. | `d39462a` | Low — **Pitfalls:** (1) Distributing plaintext `.bin` files allows offline extraction without the debug port. (2) Repurposing SWD pins as GPIO does not disable the debug subsystem. **Alternatives that further reduce residual risk:** RDP Level 2 (permanent, bricks device), PCROP/FMPRE (per-sector read protection), MPU (runtime access control), or selecting an MCU with a hardware secure enclave. | **Mitigated** |
| T-2 | Reduce | Rolling counter + AES-128-CMAC on unlock messages. The fob increments a counter with each transmission and includes a MAC over `{fob_id, counter}`. The car rejects any message whose counter is not strictly greater than the last accepted value for that fob, and verifies the MAC before acting. | `(current)` | Medium — **Pitfalls:** (1) Using an unvetted ("home grown") CMAC implementation. (2) Embedding the car key in source code or binary. (3) Integer rollover of the counter. (4) Writing the updated counter to flash *after* sending the flag (creates a replay window on restart). (5) Counter acceptance window that is too large (allows many replays) or too small (causes lockout on message loss). **Alternatives:** Rolling code + encryption (KeeLoq), binding unlock messages to the car ID, using an MCU with a hardware AES peripheral or secure key enclave. | **Mitigated** |
| T-3 | Accept | Physical decapsulation and SEM-level readout is beyond the threat model for this competition and article series. Attack cost and lab requirements vastly exceed the value of the competition flags. | — | Low (feasibility-limited) | **Accepted (Out of Scope)** |
| T-4 | Accept | AES-128 brute force is computationally infeasible against a randomly chosen key. No firmware-level countermeasure is needed as long as keys are generated correctly (see T-5). | — | Low | **Accepted (Out of Scope)** |
| T-5 | Accept | Feasibility is Low when a cryptographically secure RNG (e.g., Python `secrets` module) is used during provisioning. If key generation is weak or deterministic, this threat re-escalates. Currently accepted on the assumption that provisioning uses a secure RNG. | — | Low–Medium (depends on provisioning RNG quality) | **Accepted (Out of Scope)** |

---

## 4. Notes on Limitations

> This document covers only the five attacks explicitly depicted in the article series threat model diagram. Additional threats exist against this system (PIN brute force, power side-channel analysis, voltage fault injection, cross-car feature reuse) and are catalogued in the full project TARA (`tara.md`).

The threat model — and therefore this document — reflects the system state at a specific point in the article series. Each defense implemented changes the attack surface: closing one path may raise the relative severity of a previously lower-priority path, or reveal a new one. **This document should be treated as a snapshot tied to a specific firmware version, not a permanent security assessment.**

In a production system, ISO/SAE 21434 requires this assessment to be maintained as a living document throughout the product lifecycle, revisited whenever the design changes or new vulnerability classes are identified.
