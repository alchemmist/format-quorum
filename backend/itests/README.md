# Backend integration tests

End-to-end tests that drive the FastAPI app through HTTP (`TestClient`) and cover
every endpoint plus the store internals the HTTP layer can't reach cheaply.

## Running

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt   # pytest + httpx
.venv/bin/python -m pytest
```

The formatters must be runnable: `ruff` and `black` from the venv
(`backend/.venv/bin`), `clang-format` on `PATH`.

## How isolation works

Each test gets a **freshly imported app** rooted at its own temp directories
(`conftest.py`), so a run never touches the real `tests/` suite, the
`config_history` volume or the materialized config files, and tests can't leak
state into one another. The PyPI wheel probe is stubbed, so the suite is fully
offline and deterministic — no real version installs, no network.

## Layout

| File | Covers |
|------|--------|
| `test_format.py` | `POST /api/format` — formatters, aliases, ad-hoc config, errors |
| `test_registry_versions.py` | `/api/formatters`, version endpoints, clang aliases |
| `test_shadows.py` | shadow config create/delete |
| `test_suite_crud.py` | `/api/tests` CRUD |
| `test_run.py` | `/api/tests/run` and `/api/tests/{id}/run` |
| `test_whatif.py` | `/api/tests/whatif` config hypothesis |
| `test_matrix.py` | `/api/tests/matrix` tests × versions grid |
| `test_config.py` | config get/put/history/rollback + raw files |
| `test_spa.py` | the catch-all frontend route |
| `test_migration.py` | the legacy-key → formatter-key data migration |
| `test_stores_unit.py` | `ConfigStore` / `ShadowStore` / version internals |
