# format-quorum

A minimal code formatting playground. Paste code, hit **Format**, see exactly what the formatter changed.

Supports **C++** via `clang-format` and **Python** via `ruff format`, each with an opinionated house style. Changed lines are highlighted in the output — toggle the diff on or off from the header.

---

## Running locally

**Requirements:** Node.js 18+, `clang-format` and `ruff` installed (expected at `/opt/homebrew/bin/`).

```bash
cd app
npm install
npm run dev
```

Opens at `http://localhost:5173`. The formatting API runs on port `3001`.

---

## Stack

| | |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Editor | CodeMirror 6 via `@uiw/react-codemirror` |
| UI | Gravity UI |
| Backend | Express 5, Node.js |
| C++ formatter | `clang-format` |
| Python formatter | `ruff format` |

---

## Configuration

Formatter configs live at the repo root:

- `.clang-format` — C++ style (YT/Yandex conventions)
- `ruff.toml` — Python style (line length 88, double quotes)

---

## License

[MIT](LICENSE)
