# ---- build the static site -------------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---- serve it with nginx (runs as a non-root user, listens on 8080) ---------------------------
FROM nginxinc/nginx-unprivileged:1.29-alpine

# Replaces the image's default site. Proxies /api to the "api" service.
COPY --chmod=644 nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html

EXPOSE 8080
