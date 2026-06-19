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

#### Flowchart for enableFeature()

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

#### Flowchart for pairFob()

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

#### Flowchart for attemptUnlock()

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

### Car

#### Main flowchart

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

#### Flowchart for unlockCar()

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
NONCE MSG:     │0x58│0x04│    Nonce (4 bytes)    │
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
 PAIR MSG:      │0x55│0x22│Car ID (11 bytes) │ Key (16 bytes)    │Pin (7 bytes) │
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
                ┌──────────────────┬───────────────────┐
 FEATURE PKT:   │Car ID (11 bytes) │Feature # (1 byte) │
                └──────────────────┴───────────────────┘
```
