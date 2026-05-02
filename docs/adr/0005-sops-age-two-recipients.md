# SOPS+age, two recipients (operator workstation + offline backup)

Secrets are encrypted with SOPS using age, with exactly two recipients: the operator's workstation key and an offline backup key on physical media in a separate location. No CI runner key today. Two recipients is the minimum that survives "I dropped my laptop in a lake" without spreading blast radius further than necessary. Adding CI later is a deliberate `sops updatekeys` ceremony with the new recipient added; loss of both recipients is loss of all encrypted material, by design.
