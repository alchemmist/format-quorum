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
# rustfmt (Rust), prettier (Node), shfmt, taplo, google-java-format.
ARG SHFMT_VERSION=3.13.1
ARG GJF_VERSION=1.25.2
ARG NODE_MAJOR=22
# exact formatter versions so the backend's reported defaults don't drift build-to-build
ARG PRETTIER_VERSION=3.4.2
ARG TAPLO_VERSION=0.7.0
ARG RUST_VERSION=1.83.0
# rustup fetches rustup-init and the toolchain from these. Override to a reachable
# mirror if static.rust-lang.org is blocked/throttled on the build network, e.g.
# --build-arg RUSTUP_UPDATE_ROOT=<mirror>/rustup --build-arg RUSTUP_DIST_SERVER=<mirror>
ARG RUSTUP_DIST_SERVER=https://static.rust-lang.org
ARG RUSTUP_UPDATE_ROOT=https://static.rust-lang.org/rustup

# shfmt static binary, JDK + google-java-format jar + wrapper.
# google-java-format reaches into the JDK compiler internals, so it needs a full
# JDK (not a JRE) plus --add-exports to open jdk.compiler on JDK 16+. JDK 21 is
# pinned: GJF 1.25.x targets the compiler API up to 21 and breaks on 22+.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl ca-certificates openjdk-21-jdk-headless; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) sha=amd64 ;; \
        arm64) sha=arm64 ;; \
        *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/shfmt \
        "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_linux_${sha}"; \
    chmod +x /usr/local/bin/shfmt; \
    curl -fsSL -o /usr/local/lib/google-java-format.jar \
        "https://github.com/google/google-java-format/releases/download/v${GJF_VERSION}/google-java-format-${GJF_VERSION}-all-deps.jar"; \
    printf '%s\n' \
        '#!/bin/sh' \
        'exec java \' \
        '  --add-exports jdk.compiler/com.sun.tools.javac.api=ALL-UNNAMED \' \
        '  --add-exports jdk.compiler/com.sun.tools.javac.file=ALL-UNNAMED \' \
        '  --add-exports jdk.compiler/com.sun.tools.javac.parser=ALL-UNNAMED \' \
        '  --add-exports jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED \' \
        '  --add-exports jdk.compiler/com.sun.tools.javac.util=ALL-UNNAMED \' \
        '  -jar /usr/local/lib/google-java-format.jar "$@"' \
        > /usr/local/bin/google-java-format; \
    chmod +x /usr/local/bin/google-java-format; \
    rm -rf /var/lib/apt/lists/*

# Node + prettier + taplo (the TOML formatter ships as an npm cli)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    npm install -g "prettier@${PRETTIER_VERSION}" "@taplo/cli@${TAPLO_VERSION}"; \
    rm -rf /var/lib/apt/lists/* /root/.npm

# rustfmt via rustup (minimal toolchain + the rustfmt component).
# Retried with a short connect timeout so a flaky/slow network fails fast and
# tries again instead of hanging ~75s per attempt; the mirror args above let a
# blocked static.rust-lang.org be swapped out entirely.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER}" RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT}"; \
    curl --proto '=https' --tlsv1.2 --connect-timeout 15 --retry 3 --retry-connrefused \
        -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh; \
    for attempt in 1 2 3 4 5; do \
        if sh /tmp/rustup-init.sh -y --profile minimal \
            --default-toolchain "${RUST_VERSION}" --component rustfmt; then break; fi; \
        echo "rustup install attempt ${attempt} failed; retrying" >&2; sleep 5; \
    done; \
    test -x /root/.cargo/bin/rustfmt; \
    rm -f /tmp/rustup-init.sh; \
    rm -rf /var/lib/apt/lists/*

# binary locations the backend resolves (overridable, like CLANG_FORMAT_BIN)
ENV PATH="/root/.cargo/bin:${PATH}" \
    RUSTFMT_BIN=/root/.cargo/bin/rustfmt \
    RUSTC_BIN=/root/.cargo/bin/rustc \
    RUSTUP_BIN=/root/.cargo/bin/rustup \
    PRETTIER_BIN=prettier \
    SHFMT_BIN=/usr/local/bin/shfmt \
    TAPLO_BIN=taplo \
    GJF_BIN=/usr/local/bin/google-java-format

# fail the build early if any toolchain didn't land. taplo and google-java-format
# are smoke-tested by actually formatting: their --version exit codes are
# unreliable (taplo --version exits 1), and a real run also proves the
# JDK/--add-exports wiring works.
RUN set -eux; \
    "$RUSTFMT_BIN" --version; \
    "$PRETTIER_BIN" --version; \
    "$SHFMT_BIN" --version; \
    printf 'a=1\n' | "$TAPLO_BIN" fmt - | grep -q 'a = 1'; \
    printf 'class A{int x=1;}\n' | "$GJF_BIN" - | grep -q 'class A'

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
