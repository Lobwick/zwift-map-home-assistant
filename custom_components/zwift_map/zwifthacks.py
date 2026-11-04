"""Zwift-style route maps from ZwiftHacks, cached in ``/config`` for personal use.

ZwiftHacks (https://zwifthacks.com) publishes, for every Zwift route, an SVG
with the world's illustrated map, the route and its lead-in in game
coordinates, the timed segments and the elevation profile. Its route list
links each of its routes to Zwift's own route id (``data-signature``).

This module downloads a route's SVG the first time it is needed, keeps only
what the card draws (as JSON), downloads the world's background picture once,
and serves everything from the local cache afterwards. Nothing from ZwiftHacks
is bundled with the integration.

The parsing functions are pure Python so they can be unit tested.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

BASE_URL = "https://zwifthacks.com"
INDEX_URL = f"{BASE_URL}/app/routes/"
ROUTE_SVG_URL = (
    f"{BASE_URL}/app/routes/svg/route/"
    "?world={world}&route={route}&showprofile=1&showlegend=1&encodeminimap=0"
)
BACKGROUND_HOSTS = ("https://cdn.zwifthacks.com/maps/background/",)
USER_AGENT = "HomeAssistant-ZwiftMap (+https://github.com/Lobwick/zwift-map-home-assistant)"
INDEX_MAX_AGE_S = 7 * 24 * 3600
FORMAT_VERSION = 1

_SVG = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_ITEM_TAG = re.compile(r"<div\b[^>]*\bdata-signature=\"\d+\"[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"\bdata-(type|map|route|signature)=\"([^\"]*)\"")
_COLOR = re.compile(r"stroke:\s*(#[0-9a-fA-F]{3,8})")
_FILL = re.compile(r"fill:\s*(#[0-9a-fA-F]{3,8})")
_BACKGROUND_NAME = re.compile(r"^[a-z0-9_\-]+\.(png|jpg|jpeg|webp)$")

_LOGGER = logging.getLogger(__name__)


class ZwiftHacksFormatError(ValueError):
    """The downloaded page does not look like what this parser expects."""


# --------------------------------------------------------------------- parsing


def parse_index(html: str) -> dict[int, dict[str, int]]:
    """Map Zwift route ids to ZwiftHacks ``{"world": .., "route": ..}``."""
    index: dict[int, dict[str, int]] = {}
    for tag in _ITEM_TAG.findall(html):
        attrs = dict(_ATTR.findall(tag))
        if attrs.get("type", "routes") != "routes":
            continue
        try:
            signature = int(attrs["signature"])
            index[signature] = {"world": int(attrs["map"]), "route": int(attrs["route"])}
        except (KeyError, ValueError):
            continue
    return index


def _numbers(d: str) -> list[float]:
    return [float(n) for n in _NUMBER.findall(d)]


def _pairs(d: str) -> list[tuple[float, float]]:
    nums = _numbers(d)
    return list(zip(nums[0::2], nums[1::2], strict=False))


def _classes(el: ET.Element) -> set[str]:
    return set((el.get("class") or "").split())


def parse_route_svg(svg: str) -> dict[str, Any]:
    """Keep what the card needs from a ZwiftHacks route SVG.

    Map paths stay in ZwiftHacks' world coordinates (centimetres); the card
    places the rider by distance along them. Profile points become
    ``[distance_m, altitude_m]`` with 0 at the route's start line (lead-in
    negative).
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as err:
        raise ZwiftHacksFormatError(f"not an SVG: {err}") from err

    profiles = None
    for g in root.iter(f"{_SVG}g"):
        if "profiles" in _classes(g):
            profiles = g
            break
    profile_ids = {id(el) for el in profiles.iter()} if profiles is not None else set()

    route_d = leadin_d = None
    segments: dict[str, dict[str, str]] = {}
    for path in root.iter(f"{_SVG}path"):
        if id(path) in profile_ids:
            continue
        pid, cls = path.get("id") or "", _classes(path)
        if "route" in cls and pid.startswith("route_") and route_d is None:
            route_d = path.get("d")
        elif "leadin" in cls and pid.startswith("leadin_") and leadin_d is None:
            leadin_d = path.get("d")
        elif "ts" in cls and pid and pid not in segments:
            color = _COLOR.search(path.get("style") or "")
            segments[pid] = {"d": path.get("d") or "", "color": color.group(1) if color else "#ff0000"}
    if not route_d:
        raise ZwiftHacksFormatError("no route path")

    background = None
    for img in root.iter(f"{_SVG}image"):
        if "minimap" in _classes(img) or "background" in _classes(img):
            href = img.get("href") or img.get(_XLINK_HREF)
            try:
                background = {
                    "href": href,
                    "x": float(img.get("x", 0)),
                    "y": float(img.get("y", 0)),
                    "width": float(img.get("width", 0)),
                    "height": float(img.get("height", 0)),
                    "opacity": float(img.get("opacity", 1)),
                }
            except ValueError:
                background = None
            break

    view = None
    for v in root.iter(f"{_SVG}view"):
        if v.get("id") == "tightView":
            nums = _numbers(v.get("viewBox") or "")
            if len(nums) == 4:
                view = nums
    if view is None:
        xs = [p[0] for p in _pairs(route_d)]
        ys = [p[1] for p in _pairs(route_d)]
        view = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]

    profile = {"route": [], "leadin": [], "segments": []}
    if profiles is not None:
        route_pts: list[tuple[float, float]] = []
        leadin_pts: list[tuple[float, float]] = []
        outlines: list[tuple[list[tuple[float, float]], str]] = []
        for path in profiles.iter(f"{_SVG}path"):
            cls, pid = _classes(path), path.get("id") or ""
            if "route" in cls and pid.startswith("profile_"):
                route_pts = _pairs(path.get("d") or "")
            elif "leadin" in cls and pid.startswith("profile_"):
                leadin_pts = _pairs(path.get("d") or "")
            elif "outline" in cls and pid.startswith("ts_outline"):
                fill = _FILL.search(path.get("style") or "")
                outlines.append((_pairs(path.get("d") or ""), fill.group(1) if fill else "#ff0000"))
        if route_pts:
            start = route_pts[0][0]

            def conv(pts: list[tuple[float, float]]) -> list[list[float]]:
                return [[round((x - start) / 100, 1), round(-y / 100, 1)] for x, y in pts]

            profile["route"] = conv(route_pts)
            profile["leadin"] = conv(leadin_pts)
            for pts, color in outlines:
                xs = [x for x, _ in pts]
                if xs:
                    profile["segments"].append(
                        {
                            "from_m": round((min(xs) - start) / 100, 1),
                            "to_m": round((max(xs) - start) / 100, 1),
                            "color": color,
                        }
                    )

    return {
        "format": FORMAT_VERSION,
        "source": "zwifthacks",
        "view": [round(v, 1) for v in view],
        "background": background,
        "route": route_d,
        "leadin": leadin_d,
        "segments": list(segments.values()),
        "profile": profile,
    }


def background_name(href: str | None) -> str | None:
    """File name of a ZwiftHacks background picture, if it is one we accept."""
    if not href:
        return None
    for host in BACKGROUND_HOSTS:
        if href.startswith(host):
            name = href[len(host) :]
            if _BACKGROUND_NAME.match(name):
                return name
    return None


# ----------------------------------------------------------------------- cache


class ZwiftHacksCache:
    """Downloads route maps on first use and serves them from ``/config``.

    ``fetch_text(url)`` and ``fetch_bytes(url)`` are injected (aiohttp in Home
    Assistant), as is ``run_blocking`` (``hass.async_add_executor_job``).
    """

    def __init__(self, root: Path, fetch_text, fetch_bytes, run_blocking, static_url: str) -> None:
        self.root = root
        self.routes_dir = root / "routes"
        self.maps_dir = root / "maps"
        self._fetch_text = fetch_text
        self._fetch_bytes = fetch_bytes
        self._run = run_blocking
        self._static_url = static_url.rstrip("/")
        self._index: dict[int, dict[str, int]] | None = None
        self._index_loaded_at = 0.0
        self._locks: dict[int, asyncio.Lock] = {}
        self._index_lock = asyncio.Lock()
        self._missing: dict[int, float] = {}

    # -- files (blocking)

    def _read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    # -- index

    async def _async_index(self, force: bool = False) -> dict[int, dict[str, int]]:
        async with self._index_lock:
            path = self.root / "index.json"
            if self._index is None:
                stored = await self._run(self._read_json, path)
                if isinstance(stored, dict) and "routes" in stored:
                    self._index = {int(k): v for k, v in stored["routes"].items()}
                    self._index_loaded_at = float(stored.get("fetched_at", 0))
            stale = time.time() - self._index_loaded_at > INDEX_MAX_AGE_S
            if self._index is None or stale or force:
                try:
                    html = await self._fetch_text(INDEX_URL)
                    index = parse_index(html)
                    if index:
                        self._index = index
                        self._index_loaded_at = time.time()
                        payload = {"fetched_at": self._index_loaded_at, "routes": index}
                        await self._run(self._write, path, json.dumps(payload).encode())
                except Exception as err:  # network or parse: keep the old index
                    _LOGGER.warning("Could not refresh the ZwiftHacks route list: %s", err)
            return self._index or {}

    # -- route maps

    def route_path(self, route_id: int) -> Path:
        return self.routes_dir / f"{route_id}.json"

    async def async_get_map(self, route_id: int) -> dict[str, Any] | None:
        """Route map for the card, downloading it on first use."""
        lock = self._locks.setdefault(route_id, asyncio.Lock())
        async with lock:
            cached = await self._run(self._read_json, self.route_path(route_id))
            if isinstance(cached, dict) and cached.get("format") == FORMAT_VERSION:
                return self._for_card(cached)
            # Do not hammer ZwiftHacks for routes it does not know.
            if time.time() - self._missing.get(route_id, 0) < 3600:
                return None
            index = await self._async_index()
            if route_id not in index:
                index = await self._async_index(force=True)
            ref = index.get(route_id)
            if ref is None:
                self._missing[route_id] = time.time()
                return None
            try:
                svg = await self._fetch_text(ROUTE_SVG_URL.format(**ref))
                data = await self._run(parse_route_svg, svg)
            except Exception as err:
                _LOGGER.warning("Could not get the ZwiftHacks map of route %s: %s", route_id, err)
                self._missing[route_id] = time.time()
                return None
            data.update(route_id=route_id, world=ref["world"], zwifthacks_route=ref["route"])
            await self._async_ensure_background(data)
            await self._run(self._write, self.route_path(route_id), json.dumps(data).encode())
            return self._for_card(data)

    async def _async_ensure_background(self, data: dict[str, Any]) -> None:
        bg = data.get("background")
        name = background_name(bg.get("href") if bg else None)
        if not bg or not name:
            data["background"] = None
            return
        bg["file"] = name
        target = self.maps_dir / name
        exists = await self._run(target.is_file)
        if not exists:
            try:
                content = await self._fetch_bytes(bg["href"])
                await self._run(self._write, target, content)
            except Exception as err:
                _LOGGER.warning("Could not download the map background %s: %s", name, err)
                bg["file"] = None

    def _for_card(self, data: dict[str, Any]) -> dict[str, Any]:
        out = dict(data)
        bg = data.get("background")
        if bg and bg.get("file"):
            out["background"] = {**bg, "url": f"{self._static_url}/{bg['file']}"}
            out["background"].pop("href", None)
        else:
            out["background"] = None
        return out
