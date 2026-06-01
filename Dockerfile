# ── Stage 1: build frontend ──────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

# install JS dependencies
COPY app/package.json app/package-lock.json* ./
RUN npm ci

# copy source and config files needed for the build
COPY app/ .
COPY .clang-format ../
COPY ruff.toml      ../

RUN npm run build
# result: /build/dist/


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime

# install formatters
RUN apk add --no-cache clang-extra-tools python3 py3-pip && \
    pip install --no-cache-dir --break-system-packages ruff

WORKDIR /app

# install only production JS deps
COPY app/package.json app/package-lock.json* ./
RUN npm ci --omit=dev

# server source
COPY app/server.js .

# built frontend
COPY --from=builder /build/dist ./dist

# formatter configs (server.js references them relative to itself)
COPY .clang-format ./
COPY ruff.toml     ./

EXPOSE 3000

CMD ["node", "server.js"]
