FROM python:3.11-slim

WORKDIR /app

# Trust the CAs the host trusts (certs/host-ca.pem, filled by scripts/host-certs.sh),
# so pip and runtime downloads work behind VPNs/proxies that inspect HTTPS.
# An empty or missing file leaves the default CAs untouched.
COPY --from=certs . /tmp/host-certs/
RUN if [ -s /tmp/host-certs/host-ca.pem ]; then \
      cp /tmp/host-certs/host-ca.pem /usr/local/share/ca-certificates/host-ca.crt \
      && update-ca-certificates >/dev/null; \
    fi; rm -rf /tmp/host-certs
# pip, requests, httpx and huggingface all read the system bundle through these.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

COPY pyproject.toml ./
# Install with the "local" extra so the sentence-transformers embedders
# (e5, paraphrase) work in-container, not only the Gemini provider.
# torch comes from the CPU-only index first: the default Linux wheel bundles
# ~4 GB of CUDA libraries that are useless under Docker Desktop (no GPU).
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir ".[local]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
