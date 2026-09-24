#!/usr/bin/env bash
# Export the certificate authorities this machine already trusts into
# certs/host-ca.pem, which the Docker builds add to their own trust store.
#
# Why: corporate VPNs and proxies often inspect HTTPS with their own root CA.
# The host trusts it (it was installed by IT), but a fresh container does not,
# so pip/npm/HuggingFace downloads inside Docker fail with
# "self-signed certificate in certificate chain". Reusing the host's trust
# keeps TLS verification on and needs no change on the machine.
#
# Always succeeds: with nothing to export it leaves an empty file, and the
# builds fall back to the image's default CAs.
set -u

cd "$(dirname "$0")/.."
out="certs/host-ca.pem"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

case "$(uname -s)" in
  Darwin)
    # System keychain holds MDM/IT-installed roots; login holds user-installed ones.
    for kc in /Library/Keychains/System.keychain "$HOME/Library/Keychains/login.keychain-db"; do
      [ -f "$kc" ] && security find-certificate -a -p "$kc" >>"$tmp" 2>/dev/null
    done
    ;;
  Linux)
    for bundle in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem; do
      if [ -f "$bundle" ]; then
        cat "$bundle" >>"$tmp"
        break
      fi
    done
    ;;
esac

# Extra CA files named explicitly (e.g. EXTRA_CA_CERTS=~/corp-root.pem make up).
if [ -n "${EXTRA_CA_CERTS:-}" ] && [ -f "$EXTRA_CA_CERTS" ]; then
  cat "$EXTRA_CA_CERTS" >>"$tmp"
fi

mkdir -p certs
# Only rewrite when the content changes, so Docker's layer cache stays valid.
if ! cmp -s "$tmp" "$out" 2>/dev/null; then
  cp "$tmp" "$out"
fi
chmod 644 "$out"

count="$(grep -c 'BEGIN CERTIFICATE' "$out" 2>/dev/null || true)"
echo "certificados do host exportados para o build: ${count:-0}"
