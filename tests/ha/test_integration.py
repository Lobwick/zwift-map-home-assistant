"""End-to-end: config flow, polling, entities, track recording and the HTTP view."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zwift_map.api import ZwiftAuthError, ZwiftNotRiding
from custom_components.zwift_map.const import CONF_PLAYER_ID, DOMAIN
from custom_components.zwift_map.protobuf import PlayerState

PLAYER_ID = 1234567
BIG_LOOP = 2947111049  # 42.6 km lap route, 522 m lead-in (events)
PROFILE = {"id": PLAYER_ID, "firstName": "Félix", "lastName": "Moulin", "riding": True}


def state(distance: int, world_time: int, route_id: int = BIG_LOOP, power: int = 250) -> PlayerState:
    return PlayerState(
        player_id=PLAYER_ID,
        world_time_ms=world_time,
        distance_m=distance,
        road_time=0,
        laps=0,
        speed_kmh=30.0,
        cadence_rpm=90,
        heart_rate=140,
        power_w=power,
        climbing_m=0,
        time_s=0,
        f19=(6 << 16) | 4,
        aux3=0,
        calories=0,
        x_m=distance * 0.7,
        z_m=distance * 0.3,
        altitude_m=10 + distance * 0.02,
        group_id=0,
        sport=0,
        world_id=1,
        route_id=route_id,
    )


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with (
        patch(
            "custom_components.zwift_map.config_flow.ZwiftClient.async_get_profile",
            AsyncMock(return_value=PROFILE),
        ),
        patch("custom_components.zwift_map.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "me@example.com", CONF_PASSWORD: "secret"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zwift Map – Félix Moulin"
    assert result["data"][CONF_PLAYER_ID] == PLAYER_ID
    assert result["result"].unique_id == str(PLAYER_ID)


async def test_config_flow_bad_credentials(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.zwift_map.config_flow.ZwiftClient.async_get_profile",
        AsyncMock(side_effect=ZwiftAuthError("nope")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "me@example.com", CONF_PASSWORD: "bad"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(PLAYER_ID),
        data={CONF_USERNAME: "me@example.com", CONF_PASSWORD: "secret", CONF_PLAYER_ID: PLAYER_ID},
    )
    entry.add_to_hass(hass)
    return entry


async def test_ride_progress_track_and_view(
    hass: HomeAssistant, entry: MockConfigEntry, hass_client, tmp_path
) -> None:
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "http", {})

    # Free ride for 10 km, then Big Loop is selected and ridden.
    states = iter(
        [state(10_000, 1_000, route_id=0)]
        + [state(10_000 + i * 50, 2_000 + i * 1_000) for i in range(0, 120)]
    )
    current: dict[str, PlayerState] = {}

    async def next_state(_player_id):
        current["s"] = next(states)
        return current["s"]

    with (
        patch(
            "custom_components.zwift_map.api.ZwiftClient.async_get_profile",
            AsyncMock(return_value=PROFILE),
        ),
        patch(
            "custom_components.zwift_map.api.ZwiftClient.async_get_player_state",
            side_effect=next_state,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        live = hass.states.get("sensor.zwift_map_live")
        assert live.state == "free_ride"
        assert hass.states.get("binary_sensor.zwift_map_riding").state == "on"

        coordinator = entry.runtime_data
        assert coordinator.update_interval == timedelta(seconds=2)  # riding: fast polling
        for _ in range(1, 120):
            await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Route started at 10 000 m; 118 polls x 50 m later = 5 900 m ridden,
        # minus the 522 m lead-in = 5 378 m on Big Loop.
        live = hass.states.get("sensor.zwift_map_live")
        assert live.state == "on_route"
        assert live.attributes["route_name"] == "Big Loop"
        assert live.attributes["world"] == "Watopia"
        assert live.attributes["lap_distance_m"] == pytest.approx(5_378, abs=1)
        assert hass.states.get("sensor.zwift_map_route").state == "Big Loop"
        assert float(hass.states.get("sensor.zwift_map_route_progress").state) == pytest.approx(
            5_378 / 42_604 * 100, abs=0.1
        )
        assert float(hass.states.get("sensor.zwift_map_remaining_distance").state) == pytest.approx(
            (42_604 - 5_378) / 1000, abs=0.01
        )

        # The card's endpoint serves the live, still-growing track.
        client = await hass_client()
        resp = await client.get(f"/api/zwift_map/track/{BIG_LOOP}")
        assert resp.status == 200
        track = await resp.json()
        assert track["route_id"] == BIG_LOOP
        assert len(track["points"]) > 100
        assert track["points"][0][0] < 0  # lead-in recorded with negative distance

        resp = await client.get("/api/zwift_map/track/42")
        assert resp.status == 404

        # The card script is served by the integration.
        resp = await client.get("/zwift_map_static/zwift-map-card.js")
        assert resp.status == 200
        assert "zwift-map-card" in await resp.text()

    # Ride ends: the relay stops answering, the track is written to /config.
    with (
        patch(
            "custom_components.zwift_map.api.ZwiftClient.async_get_player_state",
            AsyncMock(side_effect=ZwiftNotRiding("x")),
        ),
        patch(
            "custom_components.zwift_map.api.ZwiftClient.async_get_profile",
            AsyncMock(return_value={**PROFILE, "riding": False}),
        ),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=30)  # back to slow polling
    assert hass.states.get("sensor.zwift_map_live").state == "offline"
    assert hass.states.get("binary_sensor.zwift_map_riding").state == "off"
    saved = tmp_path / "zwift_map" / "tracks" / f"{BIG_LOOP}.json"
    assert saved.is_file()
    assert json.loads(saved.read_text())["route_id"] == BIG_LOOP

    assert await hass.config_entries.async_unload(entry.entry_id)
