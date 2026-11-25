FROM node:22-bookworm-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --maxsockets=5 --fetch-retries=5

COPY . .

# Vite embeds VITE_* values at build time.  We deliberately compile stable
# placeholders, then the runtime entrypoint replaces them with deployment URLs.
ARG VITE_BACKEND_BASE_URL=__HMSEC_BACKEND_BASE_URL__
ARG VITE_FRONTEND_BASE_URL=__HMSEC_FRONTEND_BASE_URL__
ARG VITE_GOOGLE_CLIENT_ID=
ENV VITE_BACKEND_BASE_URL=${VITE_BACKEND_BASE_URL}
ENV VITE_FRONTEND_BASE_URL=${VITE_FRONTEND_BASE_URL}
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
RUN npm run build

FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /usr/local/bin/hmsec-frontend-entrypoint.sh
COPY --from=build /app/dist /opt/hmsec-dist-template
RUN chmod +x /usr/local/bin/hmsec-frontend-entrypoint.sh

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
  CMD wget -q -O - http://127.0.0.1:5173/hmsec-frontend-health >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/usr/local/bin/hmsec-frontend-entrypoint.sh"]
