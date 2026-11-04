import json
from pathlib import Path

import pytest
from zwift_map_pure.zwifthacks import (
    ZwiftHacksCache,
    ZwiftHacksFormatError,
    background_name,
    parse_index,
    parse_route_svg,
)

FIXTURES = Path(__file__).parent / "fixtures"
BIG_LOOP = 2947111049

INDEX_HTML = """
<div class="item row py-3 my-1 px-1" data-type="routes" data-map="1" data-route="11" data-signature="2947111049">
  <a name="1-11"></a><a name="big+loop"></a>
</div>
<div class="item row py-3 my-1 px-1" data-map="1" data-route="5" data-signature="2494975884" data-type="routes"></div>
<div class="item row" data-type="events" data-map="1" data-route="99" data-signature="123"></div>
<div class="item row" data-type="routes" data-signature="456"></div>
"""


def test_parse_index_maps_zwift_ids_to_zwifthacks_routes():
    index = parse_index(INDEX_HTML)
    assert index == {
        BIG_LOOP: {"world": 1, "route": 11},
        2494975884: {"world": 1, "route": 5},
    }


def test_parse_route_svg_real_structure():
    data = parse_route_svg((FIXTURES / "zwifthacks_big_loop.svg").read_text())
    assert data["route"].startswith("M 20593.076,-89324.141")
    assert data["leadin"].startswith("M 6568.7285,-101437.23")
    assert data["view"] == [-331671, -136098, 593639, 700172]
    assert data["background"]["href"].endswith("/watopia_50pct.png")
    assert data["background"]["x"] == -824000
    assert data["background"]["width"] == 1694000
    # Two strokes per segment in the source: kept once, with its colour.
    assert data["segments"] == [
        {"d": data["segments"][0]["d"], "color": "#1192cc"},
    ]
    prof = data["profile"]
    # Distances in metres from the start line, altitude in metres.
    assert prof["route"][0] == [0.0, 18.2]
    assert prof["route"][1] == [10.1, 18.5]
    assert prof["leadin"][0] == [-525.4, 22.8]
    assert prof["segments"] == [{"from_m": 3979.7, "to_m": 4009.1, "color": "#1192cc"}]


def test_parse_route_svg_rejects_other_content():
    with pytest.raises(ZwiftHacksFormatError):
        parse_route_svg("<html><body>Not found</body></html>")
    with pytest.raises(ZwiftHacksFormatError):
        parse_route_svg('<svg xmlns="http://www.w3.org/2000/svg"></svg>')


def test_background_name_only_accepts_known_host_and_safe_names():
    assert background_name("https://cdn.zwifthacks.com/maps/background/watopia_50pct.png") == "watopia_50pct.png"
    assert background_name("https://evil.example/watopia.png") is None
    assert background_name("https://cdn.zwifthacks.com/maps/background/../../x.png") is None
    assert background_name("data:image/png;base64,AAAA") is None


async def test_cache_downloads_once_then_serves_locally(tmp_path):
    svg = (FIXTURES / "zwifthacks_big_loop.svg").read_text()
    calls: list[str] = []

    async def fetch_text(url):
        calls.append(url)
        return INDEX_HTML if url.endswith("/app/routes/") else svg

    async def fetch_bytes(url):
        calls.append(url)
        return b"\x89PNG fake"

    async def run(func, *args):
        return func(*args)

    cache = ZwiftHacksCache(tmp_path, fetch_text, fetch_bytes, run, "/zwift_map_maps/")
    first = await cache.async_get_map(BIG_LOOP)
    second = await cache.async_get_map(BIG_LOOP)
    unknown = await cache.async_get_map(42)
    assert first == second
    assert first["world"] == 1 and first["zwifthacks_route"] == 11
    assert first["background"]["url"] == "/zwift_map_maps/watopia_50pct.png"
    assert "href" not in first["background"]
    assert (tmp_path / "maps" / "watopia_50pct.png").read_bytes() == b"\x89PNG fake"
    assert json.loads((tmp_path / "routes" / f"{BIG_LOOP}.json").read_text())["route_id"] == BIG_LOOP
    # index + svg + background, once; the unknown route re-reads the index once.
    assert sum("svg/route" in c for c in calls) == 1
    assert sum(c.endswith(".png") for c in calls) == 1
    assert unknown is None


async def test_cache_survives_network_failure(tmp_path):
    async def fail(url):
        raise OSError("offline")

    async def run(func, *args):
        return func(*args)

    cache = ZwiftHacksCache(tmp_path, fail, fail, run, "/m")
    assert await cache.async_get_map(BIG_LOOP) is None
