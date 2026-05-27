```
@startuml
skinpar@startuml
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
    Commit: #######
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
@enduml
```

[![](https://img.plantuml.biz/plantuml/svg/ZLLVR-D447_FfnYbBrUXAhgsW8Ygwb8dkQku42kcEg7B2MtjiRtgUjVChfCp2EcUU4NY6Lxu57oUVW6-0hFh94qXLBMVCfwTcT-VsRooJf1hAjMpTrBNWaG5XAaJkb1uSJ6_-HRcKqYYUJovl8IVUi3FbQ4CAN6jGiY4BJ7hmYAzAyWqEekCCWH7qy_z6xvDZNPTj23HxbNP2_xSspM6Fh_SlN5WSaXIKoDt5nRcy-Jbyz9EdvTsrjlBkneb4tWVfhiOsbAYoeQNV__rAqEp22-ajfWsXCU07qLLAmoPaQagwOQ0UVxbUPhrFknN75-ztXJaCWyrOIojkFNquMrJG6t8FQgLdNrr_iMfU5nhCOdVZhuxM6xKk1Arawbm26lfIY2ZbDG5f2P32q9dC1j5ZteSTO_l4N2Vd5o6SOUCFILZBMRVspMBPBd10aK6XWdCbIWiv6GggB0or2wrMI51evL9xp3RGxJKqv2SYjenQzaGX58zRNX4aaKPnEWQnjBb_CqkUqjz_-bFpuuZUTiuZw1MGcg77ntSIYseXLmgtAL69PFZqpPzMIDm1bx7rtEVijGZvP2qS7BrS6WnZa7X2XMSRaDnj9Z7W-aiNaoseLbyyp1GdYCnmp2BRdf-QC_MHf23X4M4NekE5gRAMb7WKiCBGWRKWd2Er-Nulnn5WYmSlJmvtxNndZ_SP8nypeyK12QlKISAh8HgMFV6UcgIoUmvMhply7mu8CZzfz_Vc0fvJysQ0tz0Ictj3AzjNROxAGJ17RPGeBDCh_1kOEKCi3V1cePI37RSvb-pgWLRnrlLUsWRJyJAJwrnpUaD9r471mO3aVElmG0iwipdU3TkZ_Nxxww_6S_VzVjWvO_uXFfxgm6V0Ue0HXeMvsl4j-Q7ustcJQ0lPLpNuySneGFjVjNy1xzNzx_y1cy4PMj12AD90ZMIh4iaeVPJad251AAuinAh7HznwqeUej_dMuQOGmPIcQpXQsPZj8qPJW-RuOeQLZCtbFe1FUTf9yWJ7eD_bJxxl-rdUGBkJb_De09XdR_uDapPGVuwNshlH5SICaJDPc6Mmwtf5V2dxLEEVyMoyb_HFm00)](https://editor.plantuml.com/uml/ZLLVR-D447_FfnYbBrUXAhgsW8Ygwb8dkQku42kcEg7B2MtjiRtgUjVChfCp2EcUU4NY6Lxu57oUVW6-0hFh94qXLBMVCfwTcT-VsRooJf1hAjMpTrBNWaG5XAaJkb1uSJ6_-HRcKqYYUJovl8IVUi3FbQ4CAN6jGiY4BJ7hmYAzAyWqEekCCWH7qy_z6xvDZNPTj23HxbNP2_xSspM6Fh_SlN5WSaXIKoDt5nRcy-Jbyz9EdvTsrjlBkneb4tWVfhiOsbAYoeQNV__rAqEp22-ajfWsXCU07qLLAmoPaQagwOQ0UVxbUPhrFknN75-ztXJaCWyrOIojkFNquMrJG6t8FQgLdNrr_iMfU5nhCOdVZhuxM6xKk1Arawbm26lfIY2ZbDG5f2P32q9dC1j5ZteSTO_l4N2Vd5o6SOUCFILZBMRVspMBPBd10aK6XWdCbIWiv6GggB0or2wrMI51evL9xp3RGxJKqv2SYjenQzaGX58zRNX4aaKPnEWQnjBb_CqkUqjz_-bFpuuZUTiuZw1MGcg77ntSIYseXLmgtAL69PFZqpPzMIDm1bx7rtEVijGZvP2qS7BrS6WnZa7X2XMSRaDnj9Z7W-aiNaoseLbyyp1GdYCnmp2BRdf-QC_MHf23X4M4NekE5gRAMb7WKiCBGWRKWd2Er-Nulnn5WYmSlJmvtxNndZ_SP8nypeyK12QlKISAh8HgMFV6UcgIoUmvMhply7mu8CZzfz_Vc0fvJysQ0tz0Ictj3AzjNROxAGJ17RPGeBDCh_1kOEKCi3V1cePI37RSvb-pgWLRnrlLUsWRJyJAJwrnpUaD9r471mO3aVElmG0iwipdU3TkZ_Nxxww_6S_VzVjWvO_uXFfxgm6V0Ue0HXeMvsl4j-Q7ustcJQ0lPLpNuySneGFjVjNy1xzNzx_y1cy4PMj12AD90ZMIh4iaeVPJad251AAuinAh7HznwqeUej_dMuQOGmPIcQpXQsPZj8qPJW-RuOeQLZCtbFe1FUTf9yWJ7eD_bJxxl-rdUGBkJb_De09XdR_uDapPGVuwNshlH5SICaJDPc6Mmwtf5V2dxLEEVyMoyb_HFm00)