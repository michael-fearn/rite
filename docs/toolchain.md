# Toolchain

How a fortress2 working environment is provisioned, and why it's structured this way.

---

## 1. Goal

One script — [`scripts/setup/install-toolchain.sh`](../scripts/setup/install-toolchain.sh) — is the single source of truth for "what does a fortress2 environment contain." Every consumer (devcontainer image, future CI runner, a fresh Debian 13 workstation) runs the same script against the same Debian 13 base, so the three environments cannot drift.

The Dockerfile holds nothing platform-shared. If a tool is needed to work on the repo, it goes in the script.

---

## 2. Flow

```
                    scripts/setup/install-toolchain.sh
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
       devcontainer         CI runner            local Debian 13
       (Dockerfile)         (Debian 13 VM)       workstation
              │                   │                   │
              ▼                   ▼                   ▼
        operator dev        automated checks      operator dev
                            (lint, validate,      (alternative to
                             tofu plan, ...)       devcontainer)
```

**Devcontainer** ([`.devcontainer/Dockerfile`](../.devcontainer/Dockerfile)): `FROM debian:13`, copies the script in, runs it as root, then creates a `vscode` user (UID 1000, `/bin/bash` login shell, passwordless sudo). [`.devcontainer/devcontainer.json`](../.devcontainer/devcontainer.json) wires VS Code's terminal to bash with login profile.

**CI runner** (future): `sudo bash scripts/setup/install-toolchain.sh` on a Debian 13 base. No CI yet — see architecture.md §1.

**Local workstation**: same script, same command. Useful when the operator wants to run `just`, `tofu`, or `ansible` without spinning up the container.

---

## 3. What's installed and why

| Tool | Source | Why this source |
|---|---|---|
| `bash`, `git`, `curl`, `gnupg`, `openssh-client`, `sudo`, `jq`, `unzip`, `less`, `tini`, `bash-completion`, `ca-certificates` | apt | Stable, in Debian main, no version sensitivity. |
| `python3` (3.13), `python3-pip`, `python3-venv`, `pipx` | apt | Debian 13 ships Python 3.13 in main; pipx is the install vector for Python tooling. |
| `age` (1.2.1) | apt | In Debian 13 main. Close enough to upstream for our use; SOPS only needs the binary. |
| `sops` (3.12.2) | upstream `.deb` from `getsops/sops` GitHub release | Not packaged in Debian 13. Pinned. |
| `tofu` (1.11.6) | upstream `.deb` from `opentofu/opentofu` GitHub release | Not in Debian repos. Pinned. |
| `just` (1.50.0) | upstream tarball from `casey/just` GitHub release | Not in Debian repos. Pinned. |
| `ansible-core`, `ansible-lint`, `pre-commit`, `check-jsonschema`, `yq` | pipx | Need newer than apt; pipx with `PIPX_HOME=/opt/pipx` and `PIPX_BIN_DIR=/usr/local/bin` makes shims available system-wide. `passlib` is injected into the `ansible-core` venv for the `password_hash` filter. |

**apt-vs-upstream rule**: if a tool ships in Debian 13 main and we don't care about being on the bleeding edge, use apt. Otherwise use the upstream release artifact (`.deb` if available, tarball otherwise) and pin the version.

**pipx-vs-pip rule**: never `pip install` system-wide on Debian 13 — it errors on PEP 668 anyway. pipx isolates each tool in its own venv and exposes the binaries via shims; we redirect the shim dir to `/usr/local/bin` so non-`vscode` users (root, future CI users) get them too.

---

## 4. Version pinning

Pinned versions live at the top of [`scripts/setup/install-toolchain.sh`](../scripts/setup/install-toolchain.sh) as env-var-overridable defaults:

```
OPENTOFU_VERSION="${OPENTOFU_VERSION:-1.11.6}"
JUST_VERSION="${JUST_VERSION:-1.50.0}"
SOPS_VERSION="${SOPS_VERSION:-3.12.2}"
```

**Pinned**: tofu, just, sops. These are downloaded directly from GitHub and we want builds to be reproducible.

**Unpinned (latest from PyPI)**: `ansible-core`, `ansible-lint`, `pre-commit`, `check-jsonschema`, `yq`. Each has an `_VERSION` env var — set it in CI when reproducibility matters more than freshness.

**Bumping**: edit the default in the script, rebuild the devcontainer (`Dev Containers: Rebuild Container`), and verify with `tofu version` / `just --version` / etc. The script's idempotent re-run will skip already-installed binaries when the version matches and replace them when it doesn't.

---

## 5. Adding a tool

1. If apt: add to the list in `install_apt_packages()`.
2. If a Go/Rust binary distributed via GitHub releases: copy the `install_just` or `install_sops` pattern — pin the version at the top, fetch into a `mktemp` dir, install to `/usr/local/bin` (or apt-install the `.deb`), check version before redownloading for idempotency.
3. If a Python tool: add a `pipx_install <pkg>` line in `install_python_tools()` and an optional `${PKG}_VERSION` env var at the top.

Don't add it to the Dockerfile. The Dockerfile is intentionally thin.

---

## 6. Known limitations

- **Network egress required at provision time.** The script fetches from `deb.debian.org`, `github.com` (releases), and `pypi.org`. A CI runner or workstation with no egress to those hosts will fail. If we ever need fully offline builds, mirror the `.deb` / tarball assets to internal object storage and parameterize the URLs at the top of the script.
- **Architecture coverage.** Tested on `amd64` only; the `dpkg_arch` / `just_release_arch` mapping handles `arm64` symbolically but the build hasn't been validated on it.
- **Debian-13-only.** The script asserts `ID=debian VERSION_ID=13` and refuses to run otherwise. Bumping to Debian 14 will need a deliberate review of upstream package availability (especially whether `sops` lands in main).
