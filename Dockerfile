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

# clang-format (base/default version) and ruff are installed via pip; the
# clang-format wheel ships a bundled binary at /usr/local/bin/clang-format.
# 18.1.8 is the version the codebase was formatted with (LOGS-4271).
RUN pip install --no-cache-dir clang-format==18.1.8

WORKDIR /app

# Python backend deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# backend source + formatter configs
COPY backend/ .

# built frontend
COPY --from=builder /build/dist ./frontend

ENV FRONTEND_DIST=/app/frontend \
    PORT=3000

EXPOSE 3000

# shell form so ${PORT} is expanded at runtime
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
