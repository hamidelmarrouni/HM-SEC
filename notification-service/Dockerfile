FROM node:22-bookworm-slim

WORKDIR /app

# Keep the first Docker baseline behavior-equivalent to the current EC2 runtime.
# The services execute TypeScript through the existing tsx start:hmsec script.
ENV NODE_ENV=development

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --maxsockets=5 --fetch-retries=5

COPY tsconfig.json ./
COPY src ./src

EXPOSE 3005

HEALTHCHECK --interval=10s --timeout=3s --start-period=25s --retries=6 \
  CMD node -e "fetch('http://127.0.0.1:3005/api/v1/notification/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["npm", "run", "start:hmsec"]
