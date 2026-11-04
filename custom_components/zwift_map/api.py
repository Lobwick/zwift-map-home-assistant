"""Small async client for the (unofficial) Zwift API."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from .protobuf import PlayerState, parse_player_state

TOKEN_URL = "https://secure.zwift.com/auth/realms/zwift/tokens/access/codes"
CLIENT_ID = "Zwift_Mobile_Link"
API_BASE = "https://us-or-rly101.zwift.com"
USER_AGENT = "Zwift/115 CFNetwork/758.0.2 Darwin/15.0.0"
# The relay serves every course under world 1.
RELAY_WORLD = 1
TIMEOUT = aiohttp.ClientTimeout(total=15)


class ZwiftError(Exception):
    """Base error."""


class ZwiftAuthError(ZwiftError):
    """Credentials were rejected."""


class ZwiftRateLimited(ZwiftError):
    """Zwift answered 429 Too Many Requests."""


class ZwiftNotRiding(ZwiftError):
    """The relay has no live state for the player."""


class ZwiftClient:
    """Handles tokens and the few endpoints this integration needs."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._access_expiry = 0.0
        self._refresh_token: str | None = None
        self._refresh_expiry = 0.0
        self._lock = asyncio.Lock()

    async def _fetch_token(self) -> None:
        now = time.time()
        if self._refresh_token and now < self._refresh_expiry:
            data = {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
        else:
            data = {
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            }
        data["client_id"] = CLIENT_ID
        async with self._session.post(TOKEN_URL, data=data, timeout=TIMEOUT) as resp:
            if resp.status in (400, 401, 403):
                if data["grant_type"] == "refresh_token":
                    # Refresh token rejected: retry once with the password.
                    self._refresh_token = None
                    await self._fetch_token()
                    return
                raise ZwiftAuthError("Zwift rejected the credentials")
            if resp.status == 429:
                raise ZwiftRateLimited("token endpoint throttled")
            if resp.status >= 400:
                raise ZwiftError(f"token endpoint returned {resp.status}")
            payload = await resp.json(content_type=None)
        if "access_token" not in payload:
            raise ZwiftAuthError("no access token in Zwift response")
        self._access_token = payload["access_token"]
        self._access_expiry = now + float(payload.get("expires_in", 300)) - 30
        self._refresh_token = payload.get("refresh_token")
        self._refresh_expiry = now + float(payload.get("refresh_expires_in", 0)) - 30

    async def _token(self) -> str:
        async with self._lock:
            if not self._access_token or time.time() >= self._access_expiry:
                await self._fetch_token()
            assert self._access_token
            return self._access_token

    async def _get(self, path: str, accept: str) -> aiohttp.ClientResponse:
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {await self._token()}",
            "User-Agent": USER_AGENT,
        }
        resp = await self._session.get(API_BASE + path, headers=headers, timeout=TIMEOUT)
        if resp.status == 401:
            resp.release()
            self._access_token = None
            raise ZwiftAuthError("access token rejected")
        if resp.status == 429:
            resp.release()
            raise ZwiftRateLimited(path)
        return resp

    async def async_get_profile(self, player: str | int = "me") -> dict[str, Any]:
        """Return a player profile (``me`` by default)."""
        resp = await self._get(f"/api/profiles/{player}", "application/json")
        async with resp:
            if resp.status >= 400:
                raise ZwiftError(f"profile request returned {resp.status}")
            return await resp.json(content_type=None)

    async def async_get_player_state(self, player_id: int) -> PlayerState:
        """Return the live relay state of a player who is riding."""
        resp = await self._get(
            f"/relay/worlds/{RELAY_WORLD}/players/{player_id}",
            "application/x-protobuf-lite",
        )
        async with resp:
            if resp.status in (204, 404):
                raise ZwiftNotRiding(str(player_id))
            if resp.status >= 400:
                raise ZwiftError(f"relay request returned {resp.status}")
            body = await resp.read()
        if not body:
            raise ZwiftNotRiding(str(player_id))
        state = parse_player_state(body)
        if not state.is_active:
            raise ZwiftNotRiding(str(player_id))
        return state
