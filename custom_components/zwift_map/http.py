"""HTTP endpoints: recorded route tracks and the Lovelace card script."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from aiohttp import web
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, DOMAIN, STATIC_URL, VERSION

FRONTEND_DIR = Path(__file__).parent / "frontend"
_REGISTERED = f"{DOMAIN}_http_registered"


class ZwiftMapTrackView(HomeAssistantView):
    """``GET /api/zwift_map/track/<route_id>``: recorded geometry of a route."""

    url = "/api/zwift_map/track/{route_id}"
    name = "api:zwift_map:track"
    requires_auth = True

    async def get(self, request: web.Request, route_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            rid = int(route_id)
        except ValueError:
            return self.json_message("invalid route id", HTTPStatus.BAD_REQUEST)
        for coordinator in hass.data.get(DOMAIN, {}).values():
            track = await coordinator.async_get_track(rid)
            if track:
                return self.json(track)
        return self.json({"route_id": rid, "points": []}, HTTPStatus.NOT_FOUND)


async def async_register_http(hass: HomeAssistant) -> None:
    """Register the view and the card once, whatever the number of entries."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    hass.http.register_view(ZwiftMapTrackView())
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILENAME}?v={VERSION}")
