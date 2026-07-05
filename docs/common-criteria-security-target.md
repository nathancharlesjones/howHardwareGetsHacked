# Security Target (ST)
### eCTF Key Fob System — Illustrative Example per Common Criteria v3.1 Rev. 5

> **Note:** A Security Target describes how a *specific product* meets its security requirements. A related document, the **Protection Profile (PP)**, would define the same requirements for an entire *class* of products (e.g., "automotive proximity key systems") without naming a specific implementation. This document is a Security Target.

---

## 1. ST Introduction

### 1.1 ST Reference

| Field | Value |
|-------|-------|
| ST Title | eCTF Key Fob System Security Target |
| ST Version | 1.0 |
| ST Date | 2026 |
| TOE Reference | eCTF Key Fob Firmware, commit `(current)` |

### 1.2 TOE Overview

The **Target of Evaluation (TOE)** is the firmware running on the car unit and paired fob units of the eCTF key fob system. The TOE implements authentication and access control for the car unlock and feature enablement functions. It does not include the physical hardware, the wireless channel, or the host tools used during manufacturing.

**TOE boundary:** Firmware executing on STM32F411 or TM4C123 microcontrollers (or x86 simulation). Secrets are provisioned at build time and stored in internal flash. Communication between car and fob occurs over a UART-based board link.

### 1.3 TOE Description

The system consists of three roles:
- **Car**: Validates unlock requests, stores flags and a rolling counter table indexed by fob ID.
- **Paired Fob**: Holds a car ID, AES-128 key, and rolling counter in flash; sends authenticated unlock messages on button press.
- **Unpaired Fob**: Holds no secrets; becomes a paired fob only after a successful pairing exchange initiated by a paired fob with a valid PIN.

---

## 2. Conformance Claims

This ST makes no claim of conformance to a registered Protection Profile. It targets **EAL2** (Structurally Tested) — appropriate for a competition/educational device with moderate assurance requirements and no formal mathematical proof of security.

---

## 3. Security Problem Definition

### 3.1 Threats

The following threats are addressed by the TOE. (These map to T-1 through T-8 in the companion TARA document.)

| Threat ID | Threat Name | Description |
|-----------|-------------|-------------|
| T.DEBUG_READOUT | Debug port memory extraction | An attacker with physical access uses the SWD/JTAG debug interface to read flash contents, extracting flags, the AES key, or the pairing PIN. |
| T.REPLAY | Unlock message replay | An attacker captures a valid unlock message in transit and retransmits it to unlock the car without possessing a paired fob. |
| T.PIN_BRUTE | Pairing PIN brute force | An attacker submits repeated pairing attempts with guessed PINs to pair an unauthorized fob. |
| T.SIDE_CHANNEL | Power side-channel key extraction | An attacker analyzes fob power consumption during cryptographic operations to recover the AES-128 key. |
| T.FORGERY | Feature package forgery | An attacker crafts a fraudulent feature package to enable a feature that was not purchased or authorized by the manufacturer. |
| T.CROSS_CAR | Cross-car feature reuse | An attacker reuses a valid feature package from one car on a different car. |

### 3.2 Assumptions

| Assumption ID | Description |
|---------------|-------------|
| A.MANUFACTURER | The manufacturer's build environment is trusted. Secrets are correctly provisioned into firmware at build time and are not leaked through the build toolchain. |
| A.PHYSICAL_FOB | A paired fob in an attacker's physical possession is treated as a compromised fob. Revoking physical access (e.g., confiscating the fob) is the primary mechanism for revoking unlock ability. |
| A.NO_SEM | Attacks requiring physical decapsulation of the MCU die (e.g., SEM readout) are outside scope. The cost and destructiveness of such attacks exceed the value of the protected assets in this context. |
| A.CHANNEL | The wireless board-link channel is assumed to be observable by an adversary (i.e., passive eavesdropping is possible). Active injection of messages is considered in threat T.REPLAY. |

### 3.3 Organizational Security Policies

| OSP ID | Policy |
|--------|--------|
| OSP.UNIQUE_KEY | Each car is provisioned with a unique AES-128 key. No two cars share a key. |
| OSP.CAR_BOUND | Feature packages are bound to a specific car ID and cannot be transferred between cars. |
| OSP.PAIR_PIN | Pairing a new fob requires both a physically present paired fob and knowledge of the pairing PIN. |

---

## 4. Security Objectives

### 4.1 Objectives for the TOE

| Objective ID | Description |
|--------------|-------------|
| O.AUTH_UNLOCK | The TOE shall ensure that a car only unlocks in response to an authenticated message from a legitimately paired fob. Authentication shall be cryptographically verified and replay-resistant. |
| O.DEBUG_PROTECT | The TOE shall disable the hardware debug interface (SWD/JTAG) to prevent unauthorized readout of flash memory on production devices. |
| O.ROLLING_CODE | The TOE shall reject any unlock message whose counter value is not strictly greater than the most recently accepted counter value for that fob ID. |
| O.PACKAGE_AUTH | The TOE shall reject any feature package that does not carry a valid manufacturer-issued authentication tag, or whose car ID does not match the receiving car. |
| O.PAIR_CONTROL | The TOE shall require both physical presence of a paired fob and a valid PIN before accepting a pairing request from an unpaired fob. |

### 4.2 Objectives for the Operational Environment

| Objective ID | Description |
|--------------|-------------|
| OE.SECRET_PROV | The operational environment (build system, manufacturing process) shall provision secrets correctly and protect them from unauthorized disclosure during manufacturing. |
| OE.KEY_UNIQUE | The operational environment shall generate a distinct AES-128 key for each car at provisioning time. |

---

## 5. Security Functional Requirements (SFRs)

The following requirements use abbreviated Common Criteria class notation. Descriptions are paraphrased for readability.

| SFR ID | CC Class | Requirement | Satisfied By |
|--------|----------|-------------|--------------|
| FCS_COP.1/CMAC | Cryptographic Operation | The TOE shall perform AES-128-CMAC to authenticate unlock messages. | `tiny-AES-CMAC-c` library; `UNLOCK_PACKET.mac[8]` field |
| FDP_ACC.1 | Subset Access Control | The TOE shall enforce an access control policy that restricts the unlock function to authenticated, rolling-code-validated messages. | Car firmware MAC verification and counter comparison in `car.c` |
| FDP_ACF.1 | Security Attribute Based Access Control | Access decisions shall be based on: (a) valid CMAC over `{fob_id, counter}`, (b) counter > stored value for `fob_id`, (c) `fob_id` present in car's pairing table. | `CAR_FLASH_DATA.fob_counter_values[256]` rolling counter table |
| FIA_UAU.2 | User Authentication | The TOE shall authenticate the fob before performing any unlock action. | MAC verification must pass before `car.c` toggles unlock state |
| FPT_PHP.1 | Passive Detection of Physical Attack | The TOE shall disable the hardware debug interface to resist passive readout of protected memory. | STM32 RDP Level 1 configured via OpenOCD at provisioning; `openocd.py lock_cmds` |
| FDP_ITC.1 | Import of User Data Without Security Attributes | The TOE shall validate the `car_id` field of any feature package before enabling the associated feature. | Feature package validation in car firmware |

---

## 6. Security Assurance Requirements (SARs)

This ST targets **EAL2**, comprising:

| SAR | Description |
|-----|-------------|
| ADV_ARC.1 | Security architecture description |
| ADV_FSP.2 | Security-enforcing functional specification |
| AGD_OPE.1 | Operational user guidance |
| AGD_PRE.1 | Preparative procedures |
| ATE_COV.1 | Evidence of coverage (tests exist for security functions) |
| ATE_FUN.1 | Functional testing |
| AVA_VAN.2 | Vulnerability analysis |

The automated test suite (`testing/test_functional.py`) provides evidence for ATE_COV.1 and ATE_FUN.1, covering unlock authentication, replay rejection, pairing PIN validation, and feature package acceptance/rejection.

---

## 7. TOE Summary Specification

### 7.1 Cryptographic Authentication (satisfies FCS_COP.1/CMAC, FIA_UAU.2, FDP_ACC.1)

The fob constructs an `UNLOCK_PACKET` containing `fob_id`, the current `rolling_counter`, and an 8-byte truncated AES-128-CMAC over those fields using the car's shared key. The car verifies the CMAC before taking any action. If verification fails, the unlock attempt is silently dropped.

### 7.2 Replay Prevention (satisfies FDP_ACF.1)

The car maintains a 256-entry table (`CAR_FLASH_DATA.fob_counter_values`) indexed by `fob_id`. Upon receiving an unlock message, the car accepts it only if `packet.counter > stored_value[fob_id]`, then updates the stored value. The table is persisted to flash so that power cycles do not reset replay protection.

### 7.3 Debug Port Protection (satisfies FPT_PHP.1)

At provisioning time, STM32 Read Protection Level 1 (RDP1) is enabled via the `openocd.py` lock command. RDP1 disables SWD/JTAG readout of flash and SRAM contents. A full chip erase is required before RDP can be lowered, which destroys all secrets.

### 7.4 Feature Package Validation (satisfies FDP_ITC.1)

Feature packages embed a `car_id` field. The car firmware checks that this field matches its own ID before enabling the feature. Packages without a valid manufacturer-issued credential are rejected.

---

## 8. Threats Outside TOE Scope

The following threats were evaluated and explicitly accepted or deferred:

| Threat | Rationale |
|--------|-----------|
| T.SEM (physical decap) | Attack cost and destructiveness exceed asset value in this deployment context. No firmware-level countermeasure is practical. Accepted per assumption A.NO_SEM. |
| T.SIDE_CHANNEL | Countermeasures (timing randomization, hardware AES with masking) are deferred to a future revision. Residual risk is accepted at current assurance level. |
| T.FAULT_INJECT | Voltage fault injection countermeasures are deferred. Residual risk is accepted at current assurance level. |

---

*This document describes the security posture of a specific firmware version. Any change to the firmware that affects assets, attack surfaces, or security mechanisms requires this Security Target to be reviewed and updated.*
