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

# install clang-format 22 and ruff
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg ca-certificates python3 python3-pip && \
    curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key | gpg --dearmor -o /usr/share/keyrings/llvm.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/llvm.gpg] https://apt.llvm.org/bookworm/ llvm-toolchain-bookworm-22 main" \
        > /etc/apt/sources.list.d/llvm.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends clang-format-22 && \
    ln -s /usr/bin/clang-format-22 /usr/local/bin/clang-format && \
    pip install --no-cache-dir --break-system-packages ruff && \
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
