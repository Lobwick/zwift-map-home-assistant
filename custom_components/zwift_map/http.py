"""HTTP endpoints: route maps, recorded tracks and the Lovelace card script."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import aiohttp
from aiohttp import web
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CARD_FILENAME,
    DOMAIN,
    MAPS_STATIC_URL,
    STATIC_URL,
    VERSION,
    ZWIFTHACKS_DIR,
)
from .zwifthacks import USER_AGENT, ZwiftHacksCache

FRONTEND_DIR = Path(__file__).parent / "frontend"
_REGISTERED = f"{DOMAIN}_http_registered"
ZWIFTHACKS_CACHE = f"{DOMAIN}_zwifthacks"
_TIMEOUT = aiohttp.ClientTimeout(total=60)


def _route_id(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


class ZwiftMapTrackView(HomeAssistantView):
    """``GET /api/zwift_map/track/<route_id>``: geometry recorded from your rides."""

    url = "/api/zwift_map/track/{route_id}"
    name = "api:zwift_map:track"
    requires_auth = True

    async def get(self, request: web.Request, route_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        rid = _route_id(route_id)
        if rid is None:
            return self.json_message("invalid route id", HTTPStatus.BAD_REQUEST)
        for coordinator in hass.data.get(DOMAIN, {}).values():
            track = await coordinator.async_get_track(rid)
            if track:
                return self.json(track)
        return self.json({"route_id": rid, "points": []}, HTTPStatus.NOT_FOUND)


class ZwiftMapRouteMapView(HomeAssistantView):
    """``GET /api/zwift_map/map/<route_id>``: Zwift-style map (ZwiftHacks, cached)."""

    url = "/api/zwift_map/map/{route_id}"
    name = "api:zwift_map:map"
    requires_auth = True

    async def get(self, request: web.Request, route_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        rid = _route_id(route_id)
        if rid is None:
            return self.json_message("invalid route id", HTTPStatus.BAD_REQUEST)
        cache: ZwiftHacksCache | None = hass.data.get(ZWIFTHACKS_CACHE)
        data = await cache.async_get_map(rid) if cache else None
        if data is None:
            return self.json_message("no map for this route", HTTPStatus.NOT_FOUND)
        return self.json(data)


def _make_cache(hass: HomeAssistant, root: Path) -> ZwiftHacksCache:
    session = async_get_clientsession(hass)
    headers = {"User-Agent": USER_AGENT}

    async def fetch_text(url: str) -> str:
        async with session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def fetch_bytes(url: str) -> bytes:
        async with session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.read()

    return ZwiftHacksCache(root, fetch_text, fetch_bytes, hass.async_add_executor_job, MAPS_STATIC_URL)


async def async_register_http(hass: HomeAssistant) -> None:
    """Register views, static files and the card once, whatever the number of entries."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True

    root = Path(hass.config.path(ZWIFTHACKS_DIR))
    maps_dir = root / "maps"
    await hass.async_add_executor_job(lambda: maps_dir.mkdir(parents=True, exist_ok=True))
    hass.data[ZWIFTHACKS_CACHE] = _make_cache(hass, root)

    hass.http.register_view(ZwiftMapTrackView())
    hass.http.register_view(ZwiftMapRouteMapView())
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False),
            # World backgrounds are public pictures; <image> tags cannot send a token.
            StaticPathConfig(MAPS_STATIC_URL, str(maps_dir), cache_headers=True),
        ]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILENAME}?v={VERSION}")
