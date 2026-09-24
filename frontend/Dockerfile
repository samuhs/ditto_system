FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# Trust the host's CAs (see backend/Dockerfile) so npm works behind VPNs/proxies.
COPY --from=certs . /tmp/host-certs/
RUN if [ -s /tmp/host-certs/host-ca.pem ]; then \
      export NODE_EXTRA_CA_CERTS=/tmp/host-certs/host-ca.pem; \
    fi; npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
