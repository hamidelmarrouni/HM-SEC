#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
# shellcheck source=lib/install_tools.sh
source "$BUNDLE/lib/install_tools.sh"
lock
[[ "$(uname -s)" == Linux ]] || die 'This bundle requires Linux.'
[[ -f /etc/os-release ]] || die 'Cannot identify this distribution.'
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-} ${ID_LIKE:-}" == *debian* || "${ID:-}" == ubuntu || "${ID:-}" == kali ]] || die 'Use Kali, Debian or Ubuntu.'
if ((EUID == 0)); then ADMIN=(); else require sudo; ADMIN=(sudo); fi
say 'Installing prerequisites and reusing an existing Docker Engine.'
missing_packages=()
for package in ca-certificates curl python3 python3-yaml jq util-linux unzip; do
  if [[ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$package" 2>/dev/null || true)" != 'ii ' ]]; then
    missing_packages+=("$package")
  fi
done
if ((${#missing_packages[@]})); then
  "${ADMIN[@]}" apt-get update
  "${ADMIN[@]}" apt-get install -y "${missing_packages[@]}"
else
  say 'Prerequisites are already installed; skipping the package refresh.'
fi
pin_client
if ! command -v docker >/dev/null; then
  "${ADMIN[@]}" apt-get update
  "${ADMIN[@]}" apt-get install -y docker.io
  "${ADMIN[@]}" systemctl enable --now docker
fi
docker info >/dev/null 2>&1 || die 'Docker is not accessible. Start Docker or run these scripts with sudo consistently.'
mkdir -p "$BUNDLE/bin"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
case "$(uname -m)" in
  x86_64) ARCH=amd64; COMPOSE_ARCH=x86_64 ;;
  aarch64|arm64) ARCH=arm64; COMPOSE_ARCH=aarch64 ;;
  *) die 'Supported architectures: x86_64 and arm64.' ;;
esac
asset(){
  local base="$1" name="$2" dest="$3"
  download "$base/$name" "$tmp/$name"
  download "$base/checksums.txt" "$tmp/checksums.txt"
  python3 "$BUNDLE/lib/checksum.py" "$tmp/$name" "$tmp/checksums.txt"
  install -m 755 "$tmp/$name" "$dest"
}
if [[ -x "$BUNDLE/bin/k3d" && "$("$BUNDLE/bin/k3d" version 2>/dev/null | sed -n '1p')" == "k3d version $HMSEC_K3D_VERSION" ]]; then
  say 'Reusing the installed pinned k3d binary.'
else
  asset "https://github.com/k3d-io/k3d/releases/download/$HMSEC_K3D_VERSION" "k3d-linux-$ARCH" "$BUNDLE/bin/k3d"
fi
if [[ -x "$BUNDLE/bin/kubectl" && -f "$BUNDLE/bin/kubectl.sha256" ]] \
  && python3 "$BUNDLE/lib/checksum.py" --raw "$BUNDLE/bin/kubectl" "$BUNDLE/bin/kubectl.sha256" \
  && [[ "$("$BUNDLE/bin/kubectl" version --client -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])')" == "$HMSEC_KUBECTL_VERSION" ]]; then
  say 'Reusing the installed verified kubectl binary.'
else
  install_kubectl
fi
# Standalone Compose is needed only when the existing Docker lacks its plugin.
if ! docker compose version >/dev/null 2>&1; then
  asset "https://github.com/docker/compose/releases/download/$HMSEC_COMPOSE_VERSION" "docker-compose-linux-$COMPOSE_ARCH" "$BUNDLE/bin/docker-compose"
fi
"$BUNDLE/bin/k3d" version
"$BUNDLE/bin/kubectl" version --client
say 'Installation complete. Next: ./UP.sh (or ./SETUP.sh for a cluster only).'
