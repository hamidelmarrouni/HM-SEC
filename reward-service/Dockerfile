FROM node:22-bookworm-slim

WORKDIR /app

# Keep the first Docker baseline behavior-equivalent to the current EC2 runtime.
# The services execute TypeScript through the existing tsx start:hmsec script.
ENV NODE_ENV=development

# Prisma on Debian/OpenSSL 3 needs the system OpenSSL runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --maxsockets=5 --fetch-retries=5

COPY tsconfig.json ./
COPY prisma ./prisma
COPY scripts ./scripts
COPY src ./src

RUN POSTGRES_URI='postgresql://hmsec:hmsec@localhost:5432/hm_sec?schema=reward_service' \
    npx prisma generate --schema prisma/schema.prisma

EXPOSE 3008

HEALTHCHECK --interval=10s --timeout=3s --start-period=25s --retries=6 \
  CMD node -e "fetch('http://127.0.0.1:3008/api/v1/reward/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["npm", "run", "start:hmsec"]
