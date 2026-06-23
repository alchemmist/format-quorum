"""Corporate-account authentication (Yandex internal).

In production the app is meant to run behind WebAuth / an Awacs L7 balancer that
validates the corporate session (Blackbox/OAuth) and injects the authenticated
login as a trusted header. The app simply reads that header.

For local development there is no proxy, so we fall back to a configurable
DEV_USER, keeping `docker compose up` usable as-is.

Env:
  AUTH_MODE         "dev" (default) | "webauth"
  AUTH_LOGIN_HEADER trusted header with the login (default "X-Webauth-Login")
  DEV_USER          login used in dev mode (default "dev")
"""

from __future__ import annotations

import os

from fastapi import Request

AUTH_MODE = os.environ.get("AUTH_MODE", "dev")
AUTH_LOGIN_HEADER = os.environ.get("AUTH_LOGIN_HEADER", "X-Webauth-Login")
DEV_USER = os.environ.get("DEV_USER", "dev")


def get_current_login(request: Request) -> str | None:
    """Authenticated corporate login, or None if not authenticated.

    Trusts the proxy-injected header; in dev mode falls back to DEV_USER so the
    app works without the proxy.
    """
    login = request.headers.get(AUTH_LOGIN_HEADER)
    if login:
        return login.strip().lower() or None
    if AUTH_MODE == "dev":
        return DEV_USER
    return None
