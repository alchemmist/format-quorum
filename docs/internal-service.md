# Running format-quorum as an internal Yandex service

The app already runs as a single container. To make it a proper internal
service with corporate-account auth (e.g. for future format voting), the plan
below is grounded in the internal docs (Blackbox / TVM / Y.Deploy).

## Authentication (chosen: WebAuth / proxy header)

Run the app behind **WebAuth / an Awacs L7 balancer** that validates the
corporate session (Blackbox/OAuth) and injects the authenticated login as a
trusted header. The backend just reads it — see `backend/auth.py`.

- `AUTH_MODE=webauth` in production; the login is read from `AUTH_LOGIN_HEADER`
  (default `X-Webauth-Login`).
- `AUTH_MODE=dev` locally (default) returns `DEV_USER` so `docker compose up`
  keeps working without a proxy.
- `GET /api/me` → `{ login, authenticated, mode }`.

Alternative (more code, fewer infra deps): the app validates the `Session_id`
cookie itself via Blackbox `sessionid`, which needs a **TVM** service ticket
(register a TVM app in ABC → secret in Vault → tvmtool sidecar) and the
`allow_method__sessionid` grant. Not used for now.

## Hosting

- Build the image (existing `Dockerfile`) and push to `registry.yandex.net`.
- Deploy on **Y.Deploy** (deploy.yandex-team.ru): a project + stage + deploy
  unit running the container.
- Front it with an **Awacs L7 balancer** + a `*.yandex-team.ru` domain, with
  WebAuth enabled so every request is authenticated.

## Voting (future)

- Identity comes from auth (the login).
- Permission to vote / administer → an **IDM** role tree (skill: `stefania-idm`),
  checked at runtime (Tirole).
- Store votes keyed by login (same git-backed JSON approach as tests, or a DB).

## One-time infra checklist (needs a human via internal portals)

- [ ] ABC service for the app (owns TVM apps, Deploy, balancer)
- [ ] Y.Deploy project/stage + Docker registry access
- [ ] Awacs L7 balancer + `*.yandex-team.ru` domain + WebAuth
- [ ] (Alt B only) TVM app + Vault secret + Blackbox `allow_method__sessionid`
- [ ] IDM role tree for voting/admin (when the voting feature lands)
