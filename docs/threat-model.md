```
@startuml
skinparam rectangle<<OUT OF SCOPE>> {
    BorderStyle dashed
    BackgroundColor #F5F5F5
    FontColor gray
    BorderColor gray
}
rectangle " " <<Out of Scope>> as OOS1
rectangle " " <<Out of Scope>> as OOS2

skinparam rectangle<<Not pursued>> {
    BorderStyle dashed
    BackgroundColor #F5F5F5
    FontColor gray
    BorderColor gray
}
rectangle " " <<Not pursued>> as NP1

rectangle BASE [
    <:shield:>️ Base (insecure) example
    Commit: eff74cd
]

rectangle DBG [
    ️<:shield:> Disable debug port
    Commit: d39462a
]

rectangle REPLAY [
    ️<:shield:> Authenticate with rolling codes and MAC;
    Per-car unlock keys generated randomly at build-time
    Commit: a969509
]

rectangle CR [
    ️<:shield:> Challenge-response with nonce
    Commit: 8c758ac
]

rectangle DELAY [
    ️<:shield:> Add a 1 sec delay to pairing
    Commit: c6cbcae
]

rectangle CT_PAIR [
    ️<:shield:> Perform memcmp in constant-time
    Commit: c6cbcae
]

rectangle MAC_FEAT [
    ️<:shield:> Authenticate feature file with MAC
    Commit: edbd8ae
]

rectangle CT_FEATURE [
    ️<:shield:> Perform memcmp in constant-time
    Commit: 6d3b3b0
]

rectangle MAC_ST [
    ️<:shield:> Authenticate start message with MAC
    Commit: 7df9584
]

rectangle NONCE [
    ️<:shield:> Widen nonces to 128-bits
    Commit: bd38ea6
]

rectangle LENGTH [
    ️<:shield:> Add length checks to all array writes
    Commit: xxxxxxx
]

note "Navigate to the commit in question by appending the\
\ncommit number to the URL www.github.com/nathan\
\ncharlesjones/howHardwareGetsHacked/tree/<6-digit\
\ncommit #>, i.e. www.github.com/nathancharlesjones\
\n/howHardwareGetsHacked/tree/d39462a" as N1

BASE --> DBG : <:crossed_swords:> Read out flags from memory\nover unlocked debug port\nFlags captured: all
note left of DBG : Pitfalls\
\n• Distributing plaintext binary files\
\n• Changing debug pins to GPIO\
\n\nAdd-ons\
\n• RDP level 2\
\n• PCROP/FMPRE\
\n• MPU\
\n• Different MCU

DBG -up-> OOS1 : <:crossed_swords:> Decap MCU and read memory values using SEM\nFlags captured: all
DBG --> REPLAY : <:crossed_swords:> Capture and replay an unlock message\nFlags captured: Cars #1-4
DBG --> REPLAY : <:crossed_swords:> Create an unlock message\nFlags captured: Cars #1-4
DBG --> REPLAY : <:crossed_swords:> Unlock Car #N with Fob #0\nFlags captured: Cars #1-4
note right of [REPLAY] : Pitfalls\
\n• “Home grown” cryptography\
\n• Car key gets leaked into the source code\
\n• Integer rollover\
\n• Saving new counter value //after// sending flag\
\n• ""WINDOW"" size\
\n\nAlternatives\
\n• Rolling code + encryption (KeeLoq)\
\n\nAdd-ons\
\n• Using car ID\
\n• Using an MCU with\
\n    → Hardware AES peripheral\
\n    → Secure key enclave\
\n• Python ""secrets"" module

REPLAY -left-> OOS2 : <:crossed_swords:> Brute forcing the car key\nFlags captured: Cars #1-4 
REPLAY -left-> OOS2 : <:crossed_swords:> Reversing key generation using exact order\nand three known consecutive keys\nFlags captured: Cars #1-4
REPLAY --> CR : <:crossed_swords:> RollJam\nFlags captured: Cars #2,3
REPLAY --> CR : <:crossed_swords:> Forced rollback\nFlags captured: Cars #2,3
REPLAY --> CR : <:crossed_swords:> Forced rollover\nFlags captured: Cars #2,3
note right of [CR] : Pitfalls\
\n• Not enough bits in nonce values\
\n• Not using proper PRNG algorithm\
\n• Not seeding the PRNG, or not it seeding properly\
\n• Not enough bits in seed value\
\n• Reusing keys for multiple different purposes\
\n\nAlternatives\
\n• TOTP\
\n\nAdd-ons\
\n• Rate-limit unlock attempts\
\n• Log/lockout/erase after repeated unlock attempts\
\n• Use better hardware\
\n    → HSM with anti-rollback counter\
\n    → MCU with TRNG

DBG --> DELAY : <:crossed_swords:> Brute force attack on pairing pin\nFlags captured: Cars #2,5
note right of [DELAY] : Pitfalls\
\n• Storing attempt counter in RAM/flash\
\n• Delaying only after pin is checked\
\n\nAlternatives\
\n• Make it harder (e.g. fingerprint)\
\n• Make pin longer\
\n\nAdd-ons\
\n• Log/lockout/erase after repeated pairing attempts

DELAY --> CT_PAIR : <:crossed_swords:> Timing attack on pairing pin comparison\nFlags captured: Cars #2,5
note right of [CT_PAIR] : Pitfalls\
\n• Using a random delay\
\n• Encrypting pairing info\
\n• Compiler optimizations\
\n\nAlternatives\
\n• Library memcmp_ct (e.g. from wolfSSL)\
\n• Compare MACs, not pin values

DBG -right-> MAC_FEAT : <:crossed_swords:> Forge a feature file\nFlags captured: Car #5
note right of [MAC_FEAT] : Pitfalls\
\n• Using hash instead of MAC\
\n\nAlternatives\
\n• Encrypt feature files\
\n\nAdd-ons\
\n• Python ""secrets"" module\
\n• Remove explicit error messages\
\n• Per-device feature keys\
\n• Digital signatures

MAC_FEAT --> CT_FEATURE : <:crossed_swords:> Timing attack on feature MAC comparison\nFlags capture: Car #5
note right of [CT_FEATURE] : Pitfalls\
\n• Compiler optimizations\
\n\nAdd-ons\
\n• Delay for each enable attempt

CT_FEATURE --> MAC_ST : <:crossed_swords:> Forge a start message\nFlags captured: Car #5
note right of [MAC_ST] : Pitfalls\
\n• Using hash instead of MAC\
\n\nAlternatives\
\n• Encrypt start messages\
\n\nAdd-ons\
\n• Python ""secrets"" module\
\n• Per-device start msg keys\
\n• Digital signatures

CR --> NONCE : <:crossed_swords:> "Birthday problem" attack\nFlags captured: Car #2
note right of [NONCE] : Pitfalls\
\n• Adding a rolling code+MAC to the unlock message\
\n• Tracking a "seen nonce" history\
\n• Assuming a CSPRNG doesn't repeat values\
\n\nAlternatives\
\n• Make it harder (e.g. fingerprint, passive keyless entry)\
\n• Using a non-repeating PRNG algorithm +\
\nHSM with anti-rollback counter\
\n\nAdd-ons\
\n• Add a 1 sec delay to unlocking\
\n• Add a MAC to the nonce message\
\n• Log/lockout/erase after rapid unlock requests\
\nor repeated failed unlock attempts

DBG --> LENGTH : <:crossed_swords:> Buffer overflow attack\nFlags captured: all
note right of [LENGTH] : Pitfalls\
\n• Checking length parameter only AFTER copying all the data\
\n• Add stack guards (wouldn't prevent overflow into\
\n  computed_mac, but *would* help prevent overflow of LR)\
\n• Add a checksum to each message\
\n\nAlternatives\
\n• Store expected length of each message\
\n• Make each receive buffer 255 bytes\
\n• Redesign the protocol around fixed-sized messages only\
\n\nAdd-ons\
\n• Reject malformed messages, don't just truncate them\
\n• Add static analysis to the project to catch\
\n  future problems like unbounded writes\
\n• To prevent/mitigate overflow of LR:\
\n    → Add stack guards\
\n    → Make RAM non-executable\
\n• Log when messages are truncated, or when receiving an\
\n  unexpected message type.

LENGTH --> NP1 : <:crossed_swords:> Fuzzing board messages\nFlags captured: Unknown
@enduml
```
