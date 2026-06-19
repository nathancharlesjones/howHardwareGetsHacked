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

BASE --> DBG : <:crossed_swords:> Read out flags from memory\nover unlocked debug port\nFlags captured: all
note right of DBG : Pitfalls\
\n• Distributing plaintext binary files\
\n• Changing debug pins to GPIO\
\n\nAlternatives\
\n• RDP level 2\
\n• PCROP/FMPRE\
\n• MPU\
\n• Different MCU
DBG --> REPLAY : <:crossed_swords:> Capture and replay an unlock message\nFlags captured: Cars #1-4
DBG --> REPLAY : <:crossed_swords:> Create an unlock message\nFlags captured: Cars #1-4
DBG --> REPLAY : <:crossed_swords:> Unlock Car #N with Fob #0\nFlags captured: Cars #1-4
DBG -left-> OOS1 : <:crossed_swords:> Decap MCU and read memory values using SEM\nFlags captured: all
note right of [REPLAY] : Pitfalls\
\n• “Home grown” cryptography\
\n• Car key gets leaked into the source code\
\n• Integer rollover\
\n• Saving new counter value //after// sending flag\
\n• ""WINDOW"" size\
\n\nAlternatives\
\n• Rolling code + encryption (KeeLoq)\
\n• Using car ID\
\n• Using an MCU with\
\n    → Hardware AES peripheral\
\n    → Secure key enclave\
\n• Python ""secrets"" module
REPLAY -left-> OOS2 : <:crossed_swords:> Brute forcing the car key\nFlags captured: Cars #1-4 
REPLAY -left-> OOS2 : <:crossed_swords:> Reversing key generation using exact order\nand three known consecutive keys\nFlags captured: Cars #1-4
note "Navigate to the commit in question by appending the\
\ncommit number to the URL www.github.com/nathan\
\ncharlesjones/howHardwareGetsHacked/tree/<6-digit\
\ncommit #>, i.e. www.github.com/nathancharlesjones\
\n/howHardwareGetsHacked/tree/d39462a" as N1
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
\n• Rate-limit unlock attempts\
\n• Use better hardware\
\n    → HSM with anti-rollback counter\
\n    → MCU with TRNG
@enduml
```
