#!/bin/sh
# Container entrypoint.
#
# Tests live in a named volume (TESTS_DIR) so that edits made through the UI on
# a running deployment survive `docker compose up --build` / `git reset --hard`.
# The git repo only provides the *initial* baseline: if the volume is empty
# (fresh server), we seed it once from the image-baked snapshot at /app/tests-seed.
# A non-empty volume is left untouched — prod edits are the source of truth.
set -e

TESTS_DIR="${TESTS_DIR:-/app/tests}"
SEED_DIR="/app/tests-seed"

mkdir -p "$TESTS_DIR/cpp" "$TESTS_DIR/python"

if [ -z "$(find "$TESTS_DIR" -name '*.json' -print -quit 2>/dev/null)" ]; then
    if [ -d "$SEED_DIR" ]; then
        echo "[entrypoint] tests volume is empty — seeding baseline from image snapshot"
        cp -a "$SEED_DIR/." "$TESTS_DIR/" 2>/dev/null || true
    else
        echo "[entrypoint] tests volume is empty and no baked seed found — starting empty"
    fi
else
    echo "[entrypoint] tests volume already populated — keeping existing tests"
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-3000}"
