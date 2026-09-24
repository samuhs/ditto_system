# certs/

`make build`/`make up` fill `host-ca.pem` with the certificate authorities this
machine already trusts (see `scripts/host-certs.sh`). The Docker builds add it
to the containers' trust store, so builds work behind corporate VPNs/proxies
that inspect HTTPS. The `.pem` is machine-specific and not committed.
