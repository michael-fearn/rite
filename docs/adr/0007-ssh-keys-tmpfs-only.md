# SSH private keys decrypted to RAM-backed tmpfs only

At the start of every operator command that runs ansible, the needed SSH private keys are decrypted into `/dev/shm/fortress2/<entity>.key` (a RAM-backed tmpfs) and trap-cleaned on exit. Persistent disk never sees decrypted private keys, even briefly. The pattern is uniform across every ansible-invoking command, and aborted runs still trap-clean. The cost is one wrapper layer around every command; the benefit is that a stolen disk yields no usable SSH material.
