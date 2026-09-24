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
# torch: prefer the wheel `make up` fetched on the host (backend/wheels/, see
# scripts/prepare-artifacts.sh) for networks where the container cannot reach
# download.pytorch.org; otherwise download the CPU build here. The CPU index
# avoids the default Linux wheel's ~4 GB of CUDA libraries (no GPU in Docker).
# The "local" extra makes the sentence-transformers embedders (e5, paraphrase)
# work in-container, not only the Gemini provider.
COPY wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --upgrade pip \
 && wheel="$(ls /tmp/wheels/torch-*"$(uname -m)".whl 2>/dev/null | head -1)" \
 && if [ -n "$wheel" ]; then \
      echo "instalando torch do host: $wheel" && pip install --no-cache-dir "$wheel"; \
    else \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu; \
    fi \
 && pip install --no-cache-dir ".[local]" \
 && rm -rf /tmp/wheels

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
