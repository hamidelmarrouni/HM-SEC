#!/usr/bin/env bash
# Helpers for INSTALL.sh. All assets retain HTTPS and checksum verification.
download(){
  curl --fail --location --retry 2 --retry-delay 2 --connect-timeout 15 \
    --max-time 300 --proto '=https' --tlsv1.2 "$1" -o "$2"
}
install_kubectl(){
  local origin base download_dir="${tmp:?Installer temporary directory is missing}"
  for origin in https://dl.k8s.io https://cdn.dl.k8s.io; do
    base="$origin/release/$HMSEC_KUBECTL_VERSION/bin/linux/$ARCH"
    say "Downloading kubectl from $origin"
    if download "$base/kubectl" "$download_dir/kubectl" && download "$base/kubectl.sha256" "$download_dir/kubectl.sha256"; then
      if python3 "$BUNDLE/lib/checksum.py" --raw "$download_dir/kubectl" "$download_dir/kubectl.sha256"; then
        install -m 755 "$download_dir/kubectl" "$BUNDLE/bin/kubectl"
        install -m 644 "$download_dir/kubectl.sha256" "$BUNDLE/bin/kubectl.sha256"
        return 0
      fi
    fi
    say "kubectl download/verification failed at $origin; trying the next official endpoint."
    rm -f "$download_dir/kubectl" "$download_dir/kubectl.sha256"
  done
  die 'Cannot download verified kubectl from either official endpoint. Check DNS/internet access, then rerun INSTALL.sh. Do not run UP.sh until installation succeeds.'
}
