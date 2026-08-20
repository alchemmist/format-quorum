# Getting started

## Run locally

The whole stack runs in one container. Node and the formatter toolchains do not
need to be installed on the host.

```bash
docker compose up --build
```

Podman is supported too:

```bash
podman compose up --build
```

Open `http://localhost:3000`. After rebuilding with Podman, recreate the
container so the new image is served:

```bash
podman compose up -d --build --force-recreate
```

## Development

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

cd ../app
npm install
npm run dev
```

`npm run dev` starts Vite at `http://localhost:5173` and the FastAPI backend on
port `3001`. Vite proxies `/api` and the raw formatter config routes to the
backend.

Run the backend test suite from the repository root:

```bash
make test
```

## Stack

| Component | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Editor | CodeMirror 6 via `@uiw/react-codemirror` |
| UI | Gravity UI |
| Backend | Python, FastAPI, uvicorn |
| C++ | clang-format |
| Python | Ruff and Black |
| Web formats | Prettier |
| Rust | rustfmt |
| Shell | shfmt |
| TOML | Taplo |
| Java | google-java-format |
