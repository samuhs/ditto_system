FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# Trust the host's CAs (see backend/Dockerfile) so npm works behind VPNs/proxies.
# npm gets an explicit bundle (image roots + host CAs), fewer parallel sockets
# and patient retries: VPNs tend to stall or reset bursts of TLS connections,
# which npm reports only as "Exit handler never called". On failure the real
# cause from npm's debug log is printed.
COPY --from=certs . /tmp/host-certs/
RUN cat /etc/ssl/certs/ca-certificates.crt /tmp/host-certs/host-ca.pem > /tmp/ca-bundle.pem 2>/dev/null; \
    npm_config_cafile=/tmp/ca-bundle.pem \
    npm ci --no-audit --no-fund --maxsockets=4 \
      --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 \
      --fetch-timeout=600000 \
    || { echo "---- npm debug log (tail) ----"; tail -n 60 /root/.npm/_logs/*-debug-0.log; exit 1; }
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
