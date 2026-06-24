# Deploying format-quorum

The app is served behind **Caddy** (automatic HTTPS via Let's Encrypt) at
**https://fq.alchemmist.xyz**, and redeployed automatically on every push to
`main` via GitHub Actions.

## 1. DNS (one-time)

Create an `A` record:

```
fq.alchemmist.xyz  ->  185.221.153.135
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
git clone https://github.com/alchemmist/format-quorum.git /opt/format-quorum
cd /opt/format-quorum
docker compose -f docker-compose.prod.yml up -d --build
```

Open ports 80 and 443 in the firewall.

## 3. GitHub Actions secrets (one-time)

In the repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | `185.221.153.135` |
| `DEPLOY_USER` | the SSH user (e.g. `root`) |
| `DEPLOY_PASSWORD` | the SSH password |

> Prefer an SSH key over a password: add a deploy key and swap `password:` for
> `key:` in `.github/workflows/deploy.yml`. Rotate the password you shared.

## 4. Continuous deployment

After the bootstrap, every push to `main` runs `.github/workflows/deploy.yml`,
which SSHes in, `git reset --hard origin/main`, and
`docker compose -f docker-compose.prod.yml up -d --build`. Trigger manually from
the Actions tab via **Run workflow** (workflow_dispatch).

## Notes

- `clang-format` versions installed via the UI persist (named volume).
- Tests and configs are reset to `main` on each deploy — curate them via git;
  UI edits on prod are temporary. The repo is the source of truth.
