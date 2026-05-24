```
@startuml
skinparam rectangle<<OUT OF SCOPE>> {
    BorderStyle dashed
    BackgroundColor #F5F5F5
    FontColor gray
    BorderColor gray
}
rectangle " " <<Out of Scope>> as OOS1

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
note right of DBG : Pitfalls\n• Distributing plaintext binary files\n• Changing debug pins to GPIO\nAlternatives\n• RDP level 2\n• PCROP/FMPRE\n• MPU\n• Different MCU
DBG --> REPLAY : <:crossed_swords:> Create unlock message\n (replay attack)\nFlags captured: Cars #1-4
DBG --> OOS1 : <:crossed_swords:> Decap MCU and read memory values using SEM\nFlags captured: all
note right of [REPLAY] : Pitfalls\n• “Home grown”, i.e. unverified, cryptographically secure function\n• Car key gets leaked into the source code\n• Counter WINDOW too small or too large\nAlternatives\n• Counter rollover\n• Deactivating fobs\n• Pairing more fobs than a car has allocated memory for\n• Flash wear leveling
@enduml
```

[![](https://img.plantuml.biz/plantuml/svg/ZLHHJjj04FttAKRb1oIWWj9MZL14S1AAr3HMKeGgWgg9FRPNMUzQk-k4gAh43Ng1zgUdw7cuGA_GMTlG8FYezylZsVTctflnYNLeN5N8m2w4Aj5W0OPYXogJT7myllW4uo5Cmt4qw7RXQm3yd6gJa9cwjIH8qEQKD66C5vdHbKf2BRM1hU5hV-flGwrS4yqChZTGDeBVWWTYUC67sIi7EeLfh4jYThGm7ayFWesyqzvq05Srtd77ve9aqkd--VsTYx44sq9PYYj3Eq0tM9IIwinG5uLm7Q0qVNiK9y7r9cB_zAm5P9X_cD0N5kU-OPfN6PJQk4TOoQjtHsyEyJ7MP11zw7r-5gvNkPoK4p4wWfLmEHWjfL0Pn3eX2wWI6FN2HnnRpUCvwhxtzhfrkHtkFJRQMag-s1NBQfbWGfY0PW5JYPc5rEW22YgqMS-KNfA1IaaTBoZPw6YcXdLoZALZrP8Ee9I1qboY4LbUcz4GHiAb_CtErDtjBw-DCs9UELz_AL4eHpSEvaAXMKCg9BM9OSx2-AIMa_q1f-4iEX_FL4ywCWgTMDwdJ_eHI5gIXCCc48MJSVHoE8ecWoOmYYxkIqXJCgmeZCABm1VfrMaDU5QWq93Nlf61fR4MCvefs3R4BQm1dUE1tdcgIOZ6mjR1tj43ZP_AvqdwnFTyIRMXndlIc01Bb1NxN5alntGm-X_jhvf-hfyOS7VxuxqkYFT8hpZmSnV4FkrpRsoqI0Kbkn2RTUaqBrgPyz19kOPcDI2jLEo4Lgr3Q611QyZ8MTOU_O2mdHfuNC7goiHKJsYRpTlEfi7b-SV--9Ajr60B1WVUQVyYqNXDdpfxVz4FlP_6raH2BcM9zHobUjucHoYCZx1kL8Uv65I0h9M1dFyApAZz8Zs8c-eMaJMrEQo84-j1OfZWX5J2Fxo_)](https://editor.plantuml.com/uml/ZLHHJjj04FttAKRb1oIWWj9MZL14S1AAr3HMKeGgWgg9FRPNMUzQk-k4gAh43Ng1zgUdw7cuGA_GMTlG8FYezylZsVTctflnYNLeN5N8m2w4Aj5W0OPYXogJT7myllW4uo5Cmt4qw7RXQm3yd6gJa9cwjIH8qEQKD66C5vdHbKf2BRM1hU5hV-flGwrS4yqChZTGDeBVWWTYUC67sIi7EeLfh4jYThGm7ayFWesyqzvq05Srtd77ve9aqkd--VsTYx44sq9PYYj3Eq0tM9IIwinG5uLm7Q0qVNiK9y7r9cB_zAm5P9X_cD0N5kU-OPfN6PJQk4TOoQjtHsyEyJ7MP11zw7r-5gvNkPoK4p4wWfLmEHWjfL0Pn3eX2wWI6FN2HnnRpUCvwhxtzhfrkHtkFJRQMag-s1NBQfbWGfY0PW5JYPc5rEW22YgqMS-KNfA1IaaTBoZPw6YcXdLoZALZrP8Ee9I1qboY4LbUcz4GHiAb_CtErDtjBw-DCs9UELz_AL4eHpSEvaAXMKCg9BM9OSx2-AIMa_q1f-4iEX_FL4ywCWgTMDwdJ_eHI5gIXCCc48MJSVHoE8ecWoOmYYxkIqXJCgmeZCABm1VfrMaDU5QWq93Nlf61fR4MCvefs3R4BQm1dUE1tdcgIOZ6mjR1tj43ZP_AvqdwnFTyIRMXndlIc01Bb1NxN5alntGm-X_jhvf-hfyOS7VxuxqkYFT8hpZmSnV4FkrpRsoqI0Kbkn2RTUaqBrgPyz19kOPcDI2jLEo4Lgr3Q611QyZ8MTOU_O2mdHfuNC7goiHKJsYRpTlEfi7b-SV--9Ajr60B1WVUQVyYqNXDdpfxVz4FlP_6raH2BcM9zHobUjucHoYCZx1kL8Uv65I0h9M1dFyApAZz8Zs8c-eMaJMrEQo84-j1OfZWX5J2Fxo_)