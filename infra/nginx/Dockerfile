# Configuration only. The dev stack stops here and proxies the site to Vite.
FROM nginxinc/nginx-unprivileged:1.30.6-alpine AS nginx-base

COPY default.conf proxy_headers.inc media_proxy.inc /etc/nginx/conf.d/

# `frontend` is a named build context, from compose.yaml.
FROM node:22.22.1-alpine AS spa

WORKDIR /app
COPY --from=frontend package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY --from=frontend index.html vite.config.ts tsconfig.json ./
COPY --from=frontend src ./src
COPY --from=frontend public ./public
RUN npm run build

FROM nginx-base

COPY spa-prod/location.inc /etc/nginx/spa/location.inc
COPY --from=spa /app/dist/ /usr/share/nginx/html/
