# Application Code

## Competition requirements

In the 2023 MITRE eCTF, teams were asked to provide firmware for a simulated car and key fob system. Their final deliverable needed to be able to build three images:
- Car
- Paired fob (comes "from the manufacturer" ready to unlock an associated car)
- Unpaired fob

![Build process](../docs/images/buildProcess.png)

These devices (along with, possibly, any custom host-side tools), were required to be able to do three things:

### Unlock a car

With a car, paired fob, and computer connected as shown below, pressing the on-board button should cause the car to send the "unlock" flag to the computer, along with the flags for any features that have been been enabled on the fob.

![Unlocking](../docs/images/unlockSetup.png)

### Pair an unpaired fob

With a paired fob, unpaired fob, and computer connected as shown below, sending `pair <PIN>\n` to the paired fob should cause it to send the necessary information to the unpaired fob to let it unlock the associated car. The paired fob does not transfer its enabled features.

![Pairing](../docs/images/pairFobSetup.png)

### Package and subsequently enable a new feature

Running the "package tool" results in a binary feature file.

![Packaging](../docs/images/packageFeatureSetup.png)

With a paired fob and computer connected as shown below, sending `enable <BIN>\n` results in the fob enabling that feature. Subsequent unlock attempts with that fob will cause the car to send the associated feature flag to the attached computer.

`<BIN>` represents the contents of the previously-packaged binary feature file, encoded as ASCII hex digits (i.e. `\xA5` [`0b10100101`] would be sent as ASCII `A` `5` [`0b01000001 0b00110101`]).

![Enabling](../docs/images/enableFeatureSetup.png)

## The current firmware

### Fob

#### Main flowchart

![](https://img.plantuml.biz/plantuml/png/RP0n3eCm34NtdC9RuGhjKA0CR5GK3X0bHaI594fCgzw-1YenbCcM_lVpryyYoK3pD8fr4G4zIX80feUaGNNIKDMF5fIR9cdrDGKQq4BomPYo2-3iWrCOO-KYtJPJabvOGgjD_mFTfGbuSBnenKpaBFZ0a2CFlv14E7dgxEZKSwFlV1mZGcBTJjnYQqaI65pKULD2bpVj8JkWGlF29M795t_qTMwjm7im8_-YC6FAVJalCjQvl2y0)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
repeat
  if (Rec'd HOST command?) then (yes)
    :processHostCommand();
  endif
  if (Paired?) then (yes)
    if (Button pressed?) then (yes)
      :attemptUnlock();
    endif
  else (no)
    if (Rec'd data on BOARD UART?) then (yes)
      :receivePairData();
    endif
  endif
repeat while (true)
stop
@enduml
```
</details>

#### Flowchart for processHostCommand()

![](https://img.plantuml.biz/plantuml/png/VOv13eCm30JlVeN5oVa25Ied_X7AeaOA2OhDeR-leQUgKc_MxEx8erfiTcoPheFIolBO5Xu6xb3YdD7T0ziJXUK53SJSV_Y4Q4U3X9ipjReJieAbr40eIrg_N7jCxTTqqgdEVnozL9yqTezww-gC7ld7Rm00)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
if (cmd == "enable"?) then (yes)
  :enableFeature();
  stop
else (no)
endif
if (cmd == "pair"?) then (yes)
  :pairFob();
  stop
else (no)
endif
:(other cmds);
stop
@enduml
```
</details>

#### Flowchart for enableFeature()

![](https://img.plantuml.biz/plantuml/png/bP7D2i9038Jl-nHpipru46zAjL8HF0ZY6qIJui9sM_P7yErTAuWYIhqbPBwPa9G-a0knCQelbAwHxKaxuMMES1QBpBQv0dneEoN62xAh-5o9PLttyeESHWoJf8i2OkbevDuDvgkswM8GncvLeIYG_4HV7lqtZqyJSjYkFJmrCZXv8nIYIzjg7r17OvvaBtn3xrwVf8qDjCTaFFqxb8mJuYk8-UNOlu9dAsRK3tokUacP9kbvDm00)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
if (Paired?) then (no)
  stop
else (yes)
endif
if (Rec'd len >= enable len?) then (no)
  stop
else (yes)
endif
if (Computed MAC == Received MAC) then (no)
  stop
else  (yes)
endif
if (Car IDs same?) then (no)
  stop
else (yes)
endif
if (Feature list full?) then (yes)
  stop
else (no)
endif
if (Feature num is 1-3?) then (no)
  stop
else (yes)
endif
if (Feature already added?) then (yes)
  stop
else (no)
endif
:Add feature;
stop
@enduml
```
</details>

#### Flowchart for pairFob()

![](https://img.plantuml.biz/plantuml/png/SoWkIImgAStDuG8pk3BJ53G24ZEBKbFiDHLACbBp53JoyZMv51IAI_8Bk59pYbCLD2fJYpMvKlDICjF0oeDIazLJ508y_HHoWCfjRM5CCWo0Q2PAerKma5O8SFGCKl0DThVc0gjo08e1_G80)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
if (Paired?) then (no)
  stop
else (yes)
endif
if (Rec'd PIN len == PIN len?) then (no)
  stop
else (yes)
endif
if (Rec'd PIN == PIN?) then (no)
  stop
else (yes)
endif
:Send PAIR MSG;
stop
@enduml
```
</details>

#### Flowchart for attemptUnlock()

![](https://img.plantuml.biz/plantuml/png/FO_D2eCm48JlUOgzrHpw0lLGGmWzMAEuUYwYAmre51CBVVl67thQOTcP_IPnlbdyEWvi5ypq41MDMQYxS_1liX3PYJC0vwUPqU08eYyvpiXsfcSt31Dg_Snb2Xa-OdOhgINp8T2vbkhSoMcSLqyW55vb9cJ8j2tn-FIN2ejSutcz8OIGImT2fY-ifLI8VvhzES1Xn4gKrU4wq3RMWspdJO8EtNu0)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
if (Paired?) then (no)
  stop
else (yes)
endif
:Send UNLOCK MSG;
:Receive NONCE MSG;
:Compute AES-CMAC(nonce);
:Send RESPONSE MSG;
if (Rec'd ACK_SUCCESS?) then (yes)
  :Send START MSG;
else (no)
endif
stop
@enduml
```
</details>

### Car

#### Main flowchart

![](https://img.plantuml.biz/plantuml/png/ROv12i8m50NtESNRcLn15xRMHNU5M0yGabyQR9EI_23Utc0t2kuUp6EO9hD9NDP5V8P8j95X0VW9KfCzEFJ3ROIDwsg2EolmJ07oHLdL5t3SKhIKSnypT_j9gbD559oVVaJEi44Ck0ojlkBUwl6FheGbsaTdqhTbhy9pzWj1SYgaQc_SH5DvZNy3)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
repeat
  if (Rec'd HOST command?) then (yes)
    :processHostCommand();
  endif
  if (Rec'd data on BOARD UART?) then (yes)
    :unlockCar();
  endif
repeat while (true)
stop
@enduml
```
</details>

#### Flowchart for unlockCar()

![](https://img.plantuml.biz/plantuml/png/PP51Ri8m44Ntd69sJHPSe0Y1Qqo4WAIoatLbXKc9cjWeTf1w-quSJALsDPxl_-UDR82jythmOzyj0CAHwgl46jixGfMV2dw4iyfMavoXmK5x16DDZP3mKYvtyYrBmwr2Su6yoBbu1hZjRoFvcL1BVcOy2S7P7XbIgFSYLyzGsz3WENS1oi1w3UHz2Sqc1Nz50yatkfJCD4VqhOVHTBR-WgRJdwjP3jimVlnG5UT2gOSSgQfaiep81rGFSDWvwBMlh_z14TMWzkE0WUNcD7QENiFOsKZWjbdyLNyNshF3gP9YYaQhy_P6PKlzz1C_)

<details><summary>PlantUML code</summary>

```plantuml
@startuml
start
:Receive UNLOCK MSG;
:Generate nonce (CTR-DRBG);
:Send NONCE MSG;
:Compute AES-CMAC(nonce);
:Receive RESPONSE MSG;
if (Computed MAC == Rec'd MAC?) then (yes)
  :Emit unlock flag;
  :Send ACK_SUCCESS;
  :Receive START MSG;
  if (Car IDs match?) then (yes)
    :Emit feature flags;
  else (no)
  endif
else (no)
  :Send ACK_FAILURE;
endif
stop
@enduml
```
</details>

### Unlock sequence diagram

```mermaid
sequenceDiagram
    Paired fob->>Car: UNLOCK MSG
    Car->>Paired fob: NONCE MSG
    Paired fob->>Car: RESPONSE MSG
    alt MAC matches
        Car->>Host: Unlock flag
        Car->>Paired fob: ACK SUCCESS
        Paired fob->>Car: START MSG
        Car->>Host: Feature flags
    else MAC does not match
        Car->>Paired fob: ACK FAILURE
    end
```

```
                 Tag Len
      (UNLOCK_MAGIC)  │
                  │   │
                  ▼   ▼
               ┌────┬────┐
UNLOCK MSG:    │0x56│0x00│
               └────┴────┘

                 Tag Len
       (NONCE_MAGIC)  │
                  │   │
                  ▼   ▼
               ┌────┬────┬──────────────────────┐
NONCE MSG:     │0x58│0x04│    Nonce (4 bytes)   │
               └────┴────┴──────────────────────┘

                 Tag Len
    (RESPONSE_MAGIC)  │
                  │   │
                  ▼   ▼
               ┌────┬────┬──────────────────────────────────────┐
RESPONSE MSG:  │0x59│0x08│      Truncated CMAC (8 bytes)        │
               └────┴────┴──────────────────────────────────────┘

                 Tag Len
       (START_MAGIC)  │
                  │   │
                  ▼   ▼
               ┌────┬────┬────────────────────────────┐
START MSG:     │0x57│0x0F│  Feature info (15 bytes)   │
               └────┴────┴─────────────┬──────────────┘
                                       │
                                       ▼
     ┌───────────────────┬───────────────────────────┬───────────────────────────┐
     │ Car ID (11 bytes) │# active features (1 byte) │List of features (3 bytes) │
     └───────────────────┴───────────────────────────┴───────────────────────────┘

                 Tag Len
         (ACK_MAGIC)  │
                  │   │
                  ▼   ▼
               ┌────┬────┬────┐
ACK MSG:       │0x54│0x01│0x01│ ◀──── ACK_SUCCESS
               └────┴────┴────┘

               ┌────┬────┬────┐
               │0x54│0x01│0x00│ ◀──── ACK_FAILURE
               └────┴────┴────┘
```

### Pairing sequence diagram

```mermaid
sequenceDiagram
    Host->>Paired fob: "pair <pin>"
    alt Valid pair command
        Paired fob->>Unpaired fob: PAIR MSG
        Paired fob->>Host: "OK"
    else Invalid pair command
        Paired fob->>Host: "ERROR: <msg>"
    end
```

```
                  Tag Len
         (PAIR_MAGIC)  │
                   │   │
                   ▼   ▼
                ┌────┬────┬──────────────────┬───────────────────┬──────────────┐
 PAIR MSG:      │0x55│0x1E│Car ID (11 bytes) │ Key (16 bytes)    │Pin (3 bytes) │
                └────┴────┴──────────────────┴───────────────────┴──────────────┘
```

### Enabling sequence diagram

```mermaid
sequenceDiagram
    Host->>Paired fob: "enable <feature packet>"
    alt Valid enable command
        Paired fob->>Host: "OK"
    else Invalid enable command
        Paired fob->>Host: "ERROR: <msg>"
    end
```

```
                ┌──────────────────┬───────────────────┬────────────────────┐
 FEATURE PKT:   │Car ID (11 bytes) │Feature # (1 byte) │MAC value (8 bytes) │
                └──────────────────┴───────────────────┴────────────────────┘
```
