# format-quorum

A code-formatting playground and a test bench for a shared formatter config.
Paste code, hit **Format**, and see exactly what the formatter changed — changed
lines are highlighted. Then capture the cases you care about as **tests** and
watch, IDE-style, what the current config gets right and what it doesn't.

![](demo.png)

Supports **C++** via `clang-format` and **Python** via `ruff format`, each with
an opinionated house style.

---

## Running locally (one command)

The whole stack runs from a single container — no Node or clang-format needed on
the host:

```bash
docker compose up --build        # or: podman compose up --build
```

Then open `http://localhost:3000`.

> On a host without Docker you can use Podman: `podman compose up --build`.
> After a rebuild, recreate the container so the new image is served:
> `podman compose up -d --build --force-recreate`.

---

## Features

- **Playground** — format C++/Python and see a line-level diff of the changes.
- **clang-format versions** — pick the version to format with, or **Try add** an
  arbitrary `X.Y.Z`. The backend installs it (`pip install clang-format==X.Y.Z`)
  into an isolated venv; if there's no wheel for that version/platform it tells
  you. Installed versions persist across restarts.
- **Tests** — BEFORE → AFTER cases run against the current config:
  - green = pass, red = fail, **yellow = muted** (a conscious compromise / one to
    revisit later);
  - **Run all** with a summary (passed / failed / muted), or run a single case
    with its ▶ button; per-case panes show *Before / Desired / Actual* with the
    diff, plus an add-test form.
- **Edit the config in the browser** — the **Config** drawer edits
  `clang-format` / `ruff.toml` live. **Check impact** runs the whole suite
  against the edited config and the live one and reports what flips:
  `+N fixed · −N broken · N muted would pass`, so you see a change's blast radius
  before committing to it.
- **Drafts & Publish** — config and test edits first land in a **local draft**
  (browser `localStorage`), not on the shared server. A header bar shows the
  unsaved count with **Publish** (push the draft to the server) and **Discard**.
  This keeps concurrent users from clobbering each other on a shared instance —
  the server is the source of truth, everyone else stages locally until they
  publish.

A baseline suite seeded from ticket **LOGS-5799** and the config-review PR ships
in `backend/tests/`.

---

## Development

```bash
cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cd ../app && npm install && npm run dev
```

`npm run dev` runs Vite (`http://localhost:5173`) and the FastAPI backend
(`uvicorn`, port `3001`) together; Vite proxies `/api`, `/clang-format` and
`/ruff.toml` to the backend.

---

## Stack

| | |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Editor | CodeMirror 6 via `@uiw/react-codemirror` |
| UI | Gravity UI |
| Backend | Python, FastAPI, uvicorn |
| C++ formatter | `clang-format` (pip, multi-version) |
| Python formatter | `ruff format` |

---

## Configuration

Formatter configs are the single source of truth in `backend/configs/`:

- `clang-format` — C++ style (anonymised house conventions)
- `ruff.toml` — Python style (line length 88, single quotes)

They're served at `/clang-format` and `/ruff.toml` (and via `GET /api/config/{lang}`),
so the UI always shows the config formatting actually uses. The **Config** drawer
edits them through `PUT /api/config/{lang}`.

### Persistence on a deployed instance

`docker-compose.prod.yml` separates the two:

- **Configs** stay git-backed — the repo is the canonical team config, bind-mounted
  from `./backend/configs`, so a deploy resets them to what's committed.
- **Tests** live in a named volume (`tests_data`), so edits made in the UI survive
  deploys. A fresh volume is seeded once from the image-baked snapshot
  (`backend/tests/` → `/app/tests-seed`) by `entrypoint.sh`.

Locally, tests are just JSON under `backend/tests/` and version-controlled, so the
baseline suite lives in the repo.

---

## API

The API is open (no auth) so it can be driven by scripts/agents. Every
format/run call also accepts an ad-hoc `config` string to format against a
candidate config **without** overwriting the stored one (used by the tuning
bench and the impact preview).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/format` | format `{code, language, clang_version?, config?}` |
| GET/POST | `/api/clang-versions` | list / install a clang-format version |
| DELETE | `/api/clang-versions/{v}` | remove an installed version |
| GET/POST/PUT/DELETE | `/api/tests` … | manage tests |
| POST | `/api/tests/run` | run the suite (`{clang_version?, config?}`) |
| POST | `/api/tests/{id}/run` | run a single test |
| GET/PUT | `/api/config/{lang}` | get / update a formatter config (`cpp` \| `python`) |
| GET | `/clang-format`, `/ruff.toml` | raw config files |

---

## Skills

`.claude/skills/` ships two agent skills that drive this instance over the API:

- **`format-quorum-api`** — manage tests and configs over HTTP (list / add /
  update / delete / run, get / put config).
- **`clang-format-tuning`** — a disciplined loop for solving a formatting
  problem: pin one clang-format version, pull the version-matched docs, sweep
  option combinations against a target test, and report the fix only if the
  target actually passes (with any regressions it causes). Its `cfprobe.py`
  works entirely through the `config`-override API.

---

## License

[MIT](LICENSE)
