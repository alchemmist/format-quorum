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
  - **Run all** with a summary (passed / failed / muted), per-case panes showing
    *Before / Desired / Actual* with the diff, and an add-test form.
  - Tests are plain JSON under `backend/tests/` and are version-controlled, so a
    test added in the UI lands in the repo.

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

- `clang-format` — C++ style (YT/Yandex conventions)
- `ruff.toml` — Python style (line length 88, single quotes)

They're served at `/clang-format` and `/ruff.toml` (the **Config** link), so the
UI always shows the config formatting actually uses.

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/format` | format `{code, language, clangVersion?}` |
| GET/POST | `/api/clang-versions` | list / install a clang-format version |
| DELETE | `/api/clang-versions/{v}` | remove an installed version |
| GET/POST/PUT/DELETE | `/api/tests` … | manage tests |
| POST | `/api/tests/run` | run the suite |

---

## License

[MIT](LICENSE)
