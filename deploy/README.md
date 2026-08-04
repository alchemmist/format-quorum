# Deploying format-quorum

The app is served behind **Caddy** (automatic HTTPS via Let's Encrypt) at
**https://fq.alchemmist.xyz** on `laba`. The app listens on host port `30001`
and is redeployed automatically on every push to `main` via GitHub Actions.

## 1. DNS (one-time)

Create an `A` record:

```
fq.alchemmist.xyz  ->  178.208.79.42
```

Caddy can only obtain a TLS certificate once this resolves and ports 80/443 are
reachable.

## 2. Server bootstrap (one-time)

On the server (Ubuntu/Debian assumed):

```bash
# Docker + compose plugin + git
curl -fsSL https://get.docker.com | sh
apt-get install -y git
# get the code and start it
git clone https://github.com/alchemmist/format-quorum.git /home/www/format-quorum
cd /home/www/format-quorum
FORMAT_QUORUM_PORT=30001 docker compose up -d --build
```

Open ports 80 and 443 in the firewall.

## 3. GitHub Actions secrets (one-time)

In the repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | `178.208.79.42` (`laba`) |
| `DEPLOY_USER` | `www` |
| `DEPLOY_PASSWORD` | the SSH password for `www` |

> Prefer an SSH key over a password: add a deploy key and swap `password:` for
> `key:` in `.github/workflows/deploy.yml`. Rotate the password you shared.

## 4. Continuous deployment

After the bootstrap, every push to `main` runs `.github/workflows/deploy.yml`,
which SSHes into `laba`, fetches `origin/main`, and runs
`FORMAT_QUORUM_PORT=30001 docker compose up -d --build --force-recreate`.
Trigger manually from the Actions tab via **Run workflow** (`workflow_dispatch`).

## Tests persist across deploys (named volume)

Tests are stored in a **named docker volume** (`tests_data`), not in the repo
checkout, so test edits made through the UI on prod **survive every deploy** —
`git reset --hard` never touches the volume. The repo is only the *initial*
baseline: the image bakes a snapshot at `/app/tests-seed`, and the entrypoint
seeds the volume from it **only when the volume is empty** (a fresh server). A
non-empty volume is left alone — prod is the source of truth for tests.

### One-time migration (existing server with bind-mounted tests)

The old setup bind-mounted `./backend/tests`. To move to the volume **without
losing the tests currently live on the server**, run this once on the server
*before* pulling the new compose file (while the current tests are still in the
working tree):

```bash
cd /opt/format-quorum
# copy the tests live right now (incl. any UI edits) into the new named volume
docker volume create format-quorum_tests_data
docker run --rm \
  -v format-quorum_tests_data:/vol \
  -v "$PWD/backend/tests":/seed:ro \
  alpine sh -c 'cp -a /seed/. /vol/'
# now deploy as usual — the volume is non-empty, so it is kept as-is
git fetch --all && git reset --hard origin/main
docker compose -f docker-compose.prod.yml up -d --build
```

If instead you want prod to start from the **corrected baseline** in the repo,
skip the copy step: an empty volume auto-seeds from the image on first start.
To later reset prod tests to the repo baseline on purpose, empty the volume
(`docker compose down && docker volume rm format-quorum_tests_data`) and
redeploy, or re-run `scripts/seed_baseline_tests.py` against the prod API.

> The compose project name (volume prefix) defaults to the directory name —
> `/opt/format-quorum` → `format-quorum_tests_data`. Check with
> `docker volume ls` if your checkout dir differs.

## Notes

- `clang-format` versions installed via the UI persist (named volume).
- **Configs** (`.clang-format` / `ruff.toml`) stay git-backed and are reset to
  `main` on each deploy — curate them via git; the repo is the source of truth
  for the canonical team config.
