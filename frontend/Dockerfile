# p15-frontend: the React build served by nginx, which is also the API gateway
# (gateway/nginx.conf routes each API path to its p15 service). One origin for
# the app and the API: no CORS, and one LoadBalancer on EKS.
#   docker build -f frontend/Dockerfile -t p15-frontend:latest .
FROM node:20-alpine AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty = relative URLs: the browser calls the same host that served the page.
ENV VITE_API_URL=""
RUN npm run build

FROM nginx:1.27-alpine
COPY gateway/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 9150
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:9150/health >/dev/null || exit 1
