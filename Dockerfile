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


# ── Stage 2: Python runtime ──────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# clang-format (base/default version) is installed via pip; the wheel ships a
# bundled binary at /usr/local/bin/clang-format. 18.1.8 is the version the
# codebase was formatted with (LOGS-4271). The Python formatters (ruff, black)
# come from requirements.txt below.
RUN pip install --no-cache-dir clang-format==18.1.8

# ── classic-language formatter toolchains (issue #2) ──────────────────────────
# gofmt (Go), rustfmt (Rust), prettier (Node), shfmt, taplo, google-java-format.
ARG GO_VERSION=1.23.4
ARG SHFMT_VERSION=3.13.1
ARG GJF_VERSION=1.25.2
ARG NODE_MAJOR=22

# Go (for gofmt), shfmt static binary, JRE + google-java-format jar + wrapper
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl ca-certificates default-jre-headless; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) goa=amd64; sha=amd64 ;; \
        arm64) goa=arm64; sha=arm64 ;; \
        *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${goa}.tar.gz" | tar -C /usr/local -xz; \
    curl -fsSL -o /usr/local/bin/shfmt \
        "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_linux_${sha}"; \
    chmod +x /usr/local/bin/shfmt; \
    curl -fsSL -o /usr/local/lib/google-java-format.jar \
        "https://github.com/google/google-java-format/releases/download/v${GJF_VERSION}/google-java-format-${GJF_VERSION}-all-deps.jar"; \
    printf '#!/bin/sh\nexec java -jar /usr/local/lib/google-java-format.jar "$@"\n' \
        > /usr/local/bin/google-java-format; \
    chmod +x /usr/local/bin/google-java-format; \
    rm -rf /var/lib/apt/lists/*

# Node + prettier + taplo (the TOML formatter ships as an npm cli)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    npm install -g prettier@3 @taplo/cli@0.7; \
    rm -rf /var/lib/apt/lists/* /root/.npm

# rustfmt via rustup (minimal toolchain + the rustfmt component)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
        sh -s -- -y --profile minimal --default-toolchain stable --component rustfmt; \
    rm -rf /var/lib/apt/lists/*

# binary locations the backend resolves (overridable, like CLANG_FORMAT_BIN)
ENV PATH="/usr/local/go/bin:/root/.cargo/bin:${PATH}" \
    GOFMT_BIN=/usr/local/go/bin/gofmt \
    RUSTFMT_BIN=/root/.cargo/bin/rustfmt \
    PRETTIER_BIN=prettier \
    SHFMT_BIN=/usr/local/bin/shfmt \
    TAPLO_BIN=taplo \
    GJF_BIN=/usr/local/bin/google-java-format

# fail the build early if any toolchain didn't land
RUN set -eux; \
    test -x "$GOFMT_BIN"; \
    rustfmt --version; \
    prettier --version; \
    shfmt --version; \
    taplo --version; \
    google-java-format --version

WORKDIR /app

# Python backend deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# backend source + formatter configs
COPY backend/ .

# baseline tests baked into the image as a read-only seed; the entrypoint copies
# them into the (named-volume) tests dir only when that volume is still empty.
COPY backend/tests /app/tests-seed

# built frontend
COPY --from=builder /build/dist ./frontend

RUN chmod +x /app/entrypoint.sh

ENV FRONTEND_DIST=/app/frontend \
    PORT=3000

EXPOSE 3000

# entrypoint seeds the tests volume if empty, then execs uvicorn
CMD ["/app/entrypoint.sh"]
