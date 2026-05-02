# OpenTofu never reads SOPS

A wrapper script (`tofu-wrap.sh`) decrypts PVE API tokens from each Host's sibling SOPS file into `TF_VAR_pve_token_<host>` env vars and invokes tofu; variables are marked `sensitive = true`. The obvious alternative — the `sops_file` provider in HCL — is rejected. Keeping secrets out of HCL eliminates an entire class of leaks (state files, plan output, debug logs) and keeps the secrets pipeline in one place (the wrapper) instead of two. Tofu cannot be invoked directly: the wrapper is the only entry point.
