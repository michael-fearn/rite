#!/usr/bin/env bash
# Installs the fortress toolchain on Debian 13 (Trixie).
#
# Single source of truth for environment provisioning. The devcontainer
# Dockerfile runs this verbatim; future CI runners should run the same script
# against a Debian 13 base image so the two environments cannot drift.
#
# Idempotent. Must run as root (use sudo on a CI runner).
#
# Pinned versions can be overridden via env vars — see the block below.

set -euo pipefail

OPENTOFU_VERSION="${OPENTOFU_VERSION:-1.11.6}"
JUST_VERSION="${JUST_VERSION:-1.50.0}"
# sops isn't packaged in Debian 13; pulled from upstream .deb releases.
SOPS_VERSION="${SOPS_VERSION:-3.12.2}"
TRUENAS_API_CLIENT_TAG="${TRUENAS_API_CLIENT_TAG:-TS-25.10.3}"
FORTRESS_PYTHON_VENV="${FORTRESS_PYTHON_VENV:-/opt/fortress-python}"

# Empty = let pipx pull the latest from PyPI. Pin in CI when reproducibility
# matters more than freshness.
ANSIBLE_VERSION="${ANSIBLE_VERSION:-}"
ANSIBLE_LINT_VERSION="${ANSIBLE_LINT_VERSION:-}"
PRE_COMMIT_VERSION="${PRE_COMMIT_VERSION:-}"
CHECK_JSONSCHEMA_VERSION="${CHECK_JSONSCHEMA_VERSION:-}"
YQ_VERSION="${YQ_VERSION:-}"

export DEBIAN_FRONTEND=noninteractive
# pipx writes shims to PIPX_BIN_DIR; /usr/local/bin is on PATH for all users.
export PIPX_HOME="${PIPX_HOME:-/opt/pipx}"
export PIPX_BIN_DIR="${PIPX_BIN_DIR:-/usr/local/bin}"
export PIPX_MAN_DIR="${PIPX_MAN_DIR:-/usr/local/share/man}"

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "install-toolchain.sh must run as root" >&2
    exit 1
  fi
}

assert_debian_13() {
  if [[ ! -r /etc/os-release ]]; then
    echo "cannot read /etc/os-release; refusing to run on unknown OS" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "13" ]]; then
    echo "expected Debian 13 (got ID=${ID:-?} VERSION_ID=${VERSION_ID:-?})" >&2
    exit 1
  fi
}

apt_install() {
  apt-get install -y --no-install-recommends "$@"
}

install_apt_packages() {
  apt-get update
  apt_install \
    age \
    bash-completion \
    bind9-dnsutils \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    less \
    locales \
    nano \
    openssh-client \
    pipx \
    python3 \
    python3-pip \
    python3-venv \
    direnv \
    sudo \
    tini \
    unzip
}

configure_locale() {
  sed -i 's/^# *\(en_US.UTF-8 UTF-8\)$/\1/' /etc/locale.gen
  locale-gen en_US.UTF-8
  update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
}

dpkg_arch() { dpkg --print-architecture; }

just_release_arch() {
  case "$(dpkg_arch)" in
    amd64) echo x86_64-unknown-linux-musl ;;
    arm64) echo aarch64-unknown-linux-musl ;;
    *) echo "unsupported arch for just: $(dpkg_arch)" >&2; exit 1 ;;
  esac
}

install_opentofu() {
  if command -v tofu >/dev/null 2>&1 \
     && tofu version 2>/dev/null | head -n1 | grep -qF "v${OPENTOFU_VERSION}"; then
    echo "opentofu ${OPENTOFU_VERSION} already installed"
    return
  fi
  local arch tmp url
  arch="$(dpkg_arch)"
  tmp="$(mktemp -d)"
  # Expand $tmp at trap-set time (double quotes) so the RETURN trap doesn't
  # try to re-read $tmp from outer scopes after this function returns.
  trap "rm -rf '$tmp'" RETURN
  url="https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_${arch}.deb"
  echo "fetching opentofu ${OPENTOFU_VERSION} (${arch})"
  curl -fsSL -o "$tmp/tofu.deb" "$url"
  apt-get install -y "$tmp/tofu.deb"
}

install_sops() {
  if command -v sops >/dev/null 2>&1 \
     && sops --version 2>/dev/null | head -n1 | grep -qF "${SOPS_VERSION}"; then
    echo "sops ${SOPS_VERSION} already installed"
    return
  fi
  local arch tmp url
  arch="$(dpkg_arch)"
  tmp="$(mktemp -d)"
  # Expand $tmp at trap-set time (double quotes) so the RETURN trap doesn't
  # try to re-read $tmp from outer scopes after this function returns.
  trap "rm -rf '$tmp'" RETURN
  url="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops_${SOPS_VERSION}_${arch}.deb"
  echo "fetching sops ${SOPS_VERSION} (${arch})"
  curl -fsSL -o "$tmp/sops.deb" "$url"
  apt-get install -y "$tmp/sops.deb"
}

install_just() {
  if command -v just >/dev/null 2>&1 \
     && [[ "$(just --version 2>/dev/null)" == "just ${JUST_VERSION}" ]]; then
    echo "just ${JUST_VERSION} already installed"
    return
  fi
  local arch tmp url
  arch="$(just_release_arch)"
  tmp="$(mktemp -d)"
  # Expand $tmp at trap-set time (double quotes) so the RETURN trap doesn't
  # try to re-read $tmp from outer scopes after this function returns.
  trap "rm -rf '$tmp'" RETURN
  url="https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-${arch}.tar.gz"
  echo "fetching just ${JUST_VERSION} (${arch})"
  curl -fsSL -o "$tmp/just.tar.gz" "$url"
  tar -xzf "$tmp/just.tar.gz" -C "$tmp" just
  install -m 0755 "$tmp/just" /usr/local/bin/just
}

pipx_install() {
  local pkg="$1" version="${2:-}"
  local spec="$pkg"
  [[ -n "$version" ]] && spec="${pkg}==${version}"
  # --force makes the install idempotent across re-runs / version bumps.
  pipx install --force "$spec"
}

install_python_tools() {
  pipx_install ansible-core "$ANSIBLE_VERSION"
  # passlib is needed by ansible's password_hash filter; inject into the same
  # venv so it's importable from ansible modules.
  pipx inject --force ansible-core passlib
  pipx_install ansible-lint "$ANSIBLE_LINT_VERSION"
  pipx_install pre-commit "$PRE_COMMIT_VERSION"
  pipx_install check-jsonschema "$CHECK_JSONSCHEMA_VERSION"
  pipx_install yq "$YQ_VERSION"
}

install_fortress_python_runtime() {
  python3 -m venv "$FORTRESS_PYTHON_VENV"
  "$FORTRESS_PYTHON_VENV/bin/python3" -m pip install --upgrade pip
  "$FORTRESS_PYTHON_VENV/bin/python3" -m pip install --force-reinstall \
    "git+https://github.com/truenas/api_client.git@${TRUENAS_API_CLIENT_TAG}"
}

cleanup_apt() {
  apt-get clean
  rm -rf /var/lib/apt/lists/*
}

main() {
  require_root
  assert_debian_13
  install_apt_packages
  configure_locale
  install_opentofu
  install_sops
  install_just
  install_python_tools
  install_fortress_python_runtime
  cleanup_apt
  echo
  echo "fortress toolchain installed."
  echo "  tofu          $(tofu version | head -n1)"
  echo "  just          $(just --version)"
  echo "  ansible       $(ansible --version | head -n1)"
  echo "  ansible-lint  $(ansible-lint --version | head -n1)"
  echo "  pre-commit    $(pre-commit --version)"
  echo "  sops          $(sops --version | head -n1)"
  echo "  age           $(age --version)"
  echo "  python        $(python3 --version)"
  echo "  fortress py   $("$FORTRESS_PYTHON_VENV/bin/python3" --version)"
  echo "  TrueNAS API   ${TRUENAS_API_CLIENT_TAG}"
}

main "$@"
