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
rectangle " " <<Out of Scope>> as OOS3

rectangle BASE [
    <:shield:>️ Base (insecure) example
    Commit: eff74cd
]

rectangle DBG [
    ️<:shield:> Disable debug port
    Commit: d39462a
]

rectangle REPLAY [
    ️<:shield:> Authenticate with rolling codes and MAC
    Commit: a969509
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
DBG --> REPLAY : <:crossed_swords:> Create unlock message\n (replay attack)\nFlags captured: Cars #1-4
DBG --> OOS1 : <:crossed_swords:> Decap MCU and read memory values using SEM\nFlags captured: all
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
REPLAY --> OOS2 : <:crossed_swords:> Brute forcing the car key\nFlags captured: Cars #1-4 
REPLAY --> OOS3 : <:crossed_swords:> Reversing key generation using exact order\nand three known consecutive keys\nFlags captured: Cars #1-4
note "Navigate to the commit in question by appending the\
\ncommit number to the URL www.github.com/nathan\
\ncharlesjones/howHardwareGetsHacked/tree/<6-digit\
\ncommit #>, i.e. www.github.com/nathancharlesjones\
\n/howHardwareGetsHacked/tree/d39462a" as N1
@enduml
```

[![](https://img.plantuml.biz/plantuml/svg/ZLNBRjj65DthAoxaJOpMLls82nk645aFswXb4MA4e8Y2OaHUabCFPvYPeHIr291LjWMoJZVzYdoFVw2_q3j3IfPRrR2uql3CVPnpxkKhOvcsPIuQvexBWccMWyR8CfaAF3yVJLx3Q01XTnJqsstulG7qkr0wHXtQfK28cSamhevPT9TgLSguguJIi3DuwHx_Rg2ahKvJpPORKJOEFpRMYQ593sKlBQW4maWLIDcPWT4eF7WUxF1viAF61kwY4_RXhQ_k_Cna74Lyrlxxsn_Kca5umQN1gDIu2_Y1vOL0Z-ogFEVs3319VZoEuiQxpOYzYyiw88LvY0azRjZCqOUpCeL2QVieLdnqUdnoo1x76lU3cyxFMyDrIfkXj3nY5c71RGPQ2S5b2f6AqG2JCGmxtKSvsEd9wSiVJbqEt_VUNjkNUqQzHrePW_4lPa4Y6KemHXQ38W8JmL83YLOvv9WhlPnADKSDfHGgkiDuewEf77Xmn0fBhCMKKeY6L5IYvcdcnQWI1jmczCvC6rDv_-alnuxLV5PQrq4X69SMFrYOSSdq4X8kS0tjPaIEWzLvIIEm2Yw3wv63J6L7MDIIMJv_k3Jk1I1mZW8ELqT1TpmAMeDXCEwlZeR1vA6W945D3CEmEscueXrRjI1R2UjgT5fKj11Lnh0Kfn9UQAI6bi2ifN7P_Iz7NQODx1pi7Q_JECzlJz93kkTAyW9hfr4b2ioPA4dtqZXgmlxmELgyhVfvjqMG-qzVhrIEDATgGGT_GgINXLKqjaMsN4l1DDpX4bAqXkXbpWsad0Bo9XXLwWYz7LVuQr8r9UiugpeFhSv3DdTLIrmGl2IGhjg1LeibzA_L0eCoTXZdnjMrPlFDzMrlzARP1CD_moVKtnWD-0vG-cQu8d5-GhnHxtTNo8cdBwA-hdkFpvZqjBjHSo_SNDr__W9NJCSBfX4w_H0ArBp8K3En2Gdz2l54KMR1vci-WgNDg8XcaxQC9WwfaLp59QsPscYr6Gwtc-52bwHcedJa2dISHvKWJtWC_XNwwF-cd-JnVLVwIchA4rRvYxPXH0vowtmgdHDjff5Qb6GMOjblJQU0kssUShptO_EMz4_TyDJMYVp28Yl1U_AqppkZ0IgAsWI4SHJMC5dcCt9CVNSole75Oh6Vab3bR9ymBN83xGn_8sEQLiclIg9fPMgnKk-IoBzYRfkrB3NIEZ_PYpb5sCYoq_uU-3xkRm--6TXTUYfulUgRxdjqUz1uHKsvh_4_)](https://editor.plantuml.com/uml/ZLNBRjj65DthAoxaJOpMLls82nk645aFswXb4MA4e8Y2OaHUabCFPvYPeHIr291LjWMoJZVzYdoFVw2_q3j3IfPRrR2uql3CVPnpxkKhOvcsPIuQvexBWccMWyR8CfaAF3yVJLx3Q01XTnJqsstulG7qkr0wHXtQfK28cSamhevPT9TgLSguguJIi3DuwHx_Rg2ahKvJpPORKJOEFpRMYQ593sKlBQW4maWLIDcPWT4eF7WUxF1viAF61kwY4_RXhQ_k_Cna74Lyrlxxsn_Kca5umQN1gDIu2_Y1vOL0Z-ogFEVs3319VZoEuiQxpOYzYyiw88LvY0azRjZCqOUpCeL2QVieLdnqUdnoo1x76lU3cyxFMyDrIfkXj3nY5c71RGPQ2S5b2f6AqG2JCGmxtKSvsEd9wSiVJbqEt_VUNjkNUqQzHrePW_4lPa4Y6KemHXQ38W8JmL83YLOvv9WhlPnADKSDfHGgkiDuewEf77Xmn0fBhCMKKeY6L5IYvcdcnQWI1jmczCvC6rDv_-alnuxLV5PQrq4X69SMFrYOSSdq4X8kS0tjPaIEWzLvIIEm2Yw3wv63J6L7MDIIMJv_k3Jk1I1mZW8ELqT1TpmAMeDXCEwlZeR1vA6W945D3CEmEscueXrRjI1R2UjgT5fKj11Lnh0Kfn9UQAI6bi2ifN7P_Iz7NQODx1pi7Q_JECzlJz93kkTAyW9hfr4b2ioPA4dtqZXgmlxmELgyhVfvjqMG-qzVhrIEDATgGGT_GgINXLKqjaMsN4l1DDpX4bAqXkXbpWsad0Bo9XXLwWYz7LVuQr8r9UiugpeFhSv3DdTLIrmGl2IGhjg1LeibzA_L0eCoTXZdnjMrPlFDzMrlzARP1CD_moVKtnWD-0vG-cQu8d5-GhnHxtTNo8cdBwA-hdkFpvZqjBjHSo_SNDr__W9NJCSBfX4w_H0ArBp8K3En2Gdz2l54KMR1vci-WgNDg8XcaxQC9WwfaLp59QsPscYr6Gwtc-52bwHcedJa2dISHvKWJtWC_XNwwF-cd-JnVLVwIchA4rRvYxPXH0vowtmgdHDjff5Qb6GMOjblJQU0kssUShptO_EMz4_TyDJMYVp28Yl1U_AqppkZ0IgAsWI4SHJMC5dcCt9CVNSole75Oh6Vab3bR9ymBN83xGn_8sEQLiclIg9fPMgnKk-IoBzYRfkrB3NIEZ_PYpb5sCYoq_uU-3xkRm--6TXTUYfulUgRxdjqUz1uHKsvh_4_)