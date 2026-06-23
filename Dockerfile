# ── Stage 1: build frontend ──────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

# install JS dependencies
COPY app/package.json app/package-lock.json* ./
RUN npm ci

# copy source and config files needed for the build
COPY app/ .

RUN npm run build
# result: /build/dist/


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS runtime

# install clang-format 22 and ruff via pip (apt.llvm.org has no clang-format-22 package).
# The clang-format wheel ships a bundled binary at /usr/local/bin/clang-format.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates python3 python3-pip && \
    pip install --no-cache-dir --break-system-packages clang-format==22.1.5 ruff && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install only production JS deps
COPY app/package.json app/package-lock.json* ./
RUN npm ci --omit=dev

# server source
COPY app/server.js .

# built frontend
COPY --from=builder /build/dist ./dist


EXPOSE 3000

CMD ["node", "server.js"]
