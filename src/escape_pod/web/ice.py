# Owner: Teammate 1 (Game, scenes, widgets)
"""STUN/TURN servers for the WebRTC video (served at /api/ice).

STUN alone connects most home networks. Phone data, campus and venue Wi-Fi often
need TURN: a relay that forwards the (still encrypted) video when the two browsers
cannot reach each other directly. We use Metered's Open Relay free tier:

    etc/.env (or the host's environment):
        METERED_APP=<your app name>        # the part before .metered.live
        METERED_API_KEY=<your API key>

The server fetches the TURN logins and caches them, so the API key never reaches a
browser. Without an API key, a fixed login works too (TURN_USERNAME, TURN_CREDENTIAL,
optional TURN_URLS; see _static_turn). With neither, or if Metered fails, it falls
back to config.ICE_SERVERS (STUN only).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.parse
import urllib.request

from escape_pod import config

log = logging.getLogger("escape_pod.ice")
CACHE_S = 600
_cache: tuple[float, list[dict]] | None = None


def _fetch_metered(app: str, key: str) -> list[dict]:
    url = (f"https://{urllib.parse.quote(app)}.metered.live/api/v1/turn/credentials"
           f"?apiKey={urllib.parse.quote(key)}")
    with urllib.request.urlopen(url, timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    servers = [s for s in data if isinstance(s, dict) and s.get("urls")] if isinstance(data, list) else []
    if not servers:
        raise ValueError("Metered returned no ICE servers")
    return servers


def _static_turn() -> list[dict]:
    """A fixed TURN login from the env (TURN_USERNAME / TURN_CREDENTIAL), or [].

    Unlike the API-key path, this login does reach the browser: a browser cannot use
    TURN without it. Anyone who opens the game could copy it and spend the relay quota.
    Fine for a hackathon; switch to METERED_API_KEY for short-lived logins.
    """
    user = os.environ.get(config.TURN_USERNAME_ENV, "").strip()
    cred = os.environ.get(config.TURN_CREDENTIAL_ENV, "").strip()
    if not (user and cred):
        return []
    raw = os.environ.get(config.TURN_URLS_ENV, "").strip()
    urls = [u.strip() for u in raw.split(",") if u.strip()] if raw else config.METERED_TURN_URLS
    return [{"urls": urls, "username": user, "credential": cred}]


async def ice_servers() -> list[dict]:
    global _cache
    app = os.environ.get(config.METERED_APP_ENV, "").strip()
    key = os.environ.get(config.METERED_API_KEY_ENV, "").strip()
    if not (app and key):
        return config.ICE_SERVERS + _static_turn()
    if _cache and time.monotonic() - _cache[0] < CACHE_S:
        return _cache[1]
    try:
        # urllib blocks, so run it in a thread: the event loop must never block (spec rule 6).
        servers = await asyncio.to_thread(_fetch_metered, app, key)
    except Exception as e:  # network down, bad key: video still works where STUN is enough
        log.warning("TURN credentials from Metered failed (%s); using STUN only", e)
        return _cache[1] if _cache else config.ICE_SERVERS + _static_turn()
    _cache = (time.monotonic(), servers)
    return servers
