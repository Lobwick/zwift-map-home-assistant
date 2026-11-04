"""Polling coordinator: live Zwift state, route progress and track recording."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ZwiftAuthError, ZwiftClient, ZwiftError, ZwiftNotRiding, ZwiftRateLimited
from .const import (
    CONF_PLAYER_ID,
    DOMAIN,
    GAME_INFO_FILE,
    GAME_INFO_MAX_AGE_S,
    OFFLINE_INTERVAL,
    ONLINE_INTERVAL,
    RATE_LIMIT_DECAY_S,
    RATE_LIMIT_MAX_S,
    RATE_LIMIT_STEP_S,
    STALE_STATE_AFTER,
    STORAGE_VERSION,
    TRACK_SAVE_INTERVAL,
    TRACKS_DIR,
)
from .protobuf import PlayerState
from .routes import RouteCatalogue, RouteInfo, course_name
from .tracker import (
    PHASE_LEAD_IN,
    PHASE_ON_ROUTE,
    GradientEstimator,
    Progress,
    ProgressTracker,
    RouteTrack,
    SegmentStatus,
    segment_status,
)
from .zwifthacks import route_info_from_map

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ZwiftMapData:
    """Snapshot handed to the entities."""

    riding: bool = False
    state: PlayerState | None = None
    progress: Progress | None = None
    world: str | None = None
    gradient_pct: float | None = None
    track_version: int = 0
    track_coverage: float = 0.0
    segment: SegmentStatus | None = None


class ZwiftMapCoordinator(DataUpdateCoordinator[ZwiftMapData]):
    """Polls Zwift every 2 s while riding, every 30 s otherwise."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ZwiftClient,
        catalogue: RouteCatalogue,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=OFFLINE_INTERVAL,
        )
        self.client = client
        self.catalogue = catalogue
        self.player_id: int = entry.data[CONF_PLAYER_ID]
        self.tracks_dir = Path(hass.config.path(TRACKS_DIR))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._progress = ProgressTracker()
        self._gradient = GradientEstimator()
        self._track: RouteTrack | None = None
        self._track_saved_at = dt_util.utcnow()
        self._track_version = 0
        self._rate_penalty_s = 0.0
        self._fallback_tried: set[int] = set()
        self._last_world_time = 0
        self._world_time_changed_at = dt_util.utcnow()
        self.data = ZwiftMapData()

    # ----------------------------------------------------------- lifecycle

    async def async_load(self) -> None:
        """Restore the in-progress route after a Home Assistant restart."""
        stored = await self._store.async_load() or {}
        self._progress.restore(stored.get("progress"))
        await self._async_load_game_info()

    async def _async_load_game_info(self) -> None:
        """Merge Zwift's own route list (cached a day) into the catalogue.

        The bundled catalogue misses routes added after it was built; Zwift's
        game_info has them all. Best effort: failures only cost those names.
        """
        path = Path(self.hass.config.path(GAME_INFO_FILE))
        cached = await self.hass.async_add_executor_job(self._read_json, path)
        data = cached.get("data") if isinstance(cached, dict) else None
        fresh = isinstance(cached, dict) and time.time() - cached.get("fetched_at", 0) < GAME_INFO_MAX_AGE_S
        if not fresh:
            try:
                data = await self.client.async_get_game_info()
                payload = {"fetched_at": time.time(), "data": data}
                await self.hass.async_add_executor_job(self._write_json, path, payload)
            except Exception as err:  # network, auth, format: keep the cached copy
                _LOGGER.warning("Could not fetch Zwift's route list (game_info): %s", err)
        if isinstance(data, dict):
            added = self.catalogue.merge_game_info(data)
            _LOGGER.debug("game_info added %s routes to the catalogue", added)

    def _read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)

    async def _async_route_from_zwifthacks(self, route_id: int, world: str | None) -> None:
        """Last resort for a route nobody else knows: its ZwiftHacks map."""
        cache = self.hass.data.get(f"{DOMAIN}_zwifthacks")
        if cache is None:
            return
        data = await cache.async_get_map(route_id)
        info = route_info_from_map(route_id, data) if data else None
        if not info or self.catalogue.get(route_id):
            return
        self.catalogue.add(
            RouteInfo(
                id=route_id,
                name=f"Route {route_id}",
                world=world or "",
                world_id=None,
                distance_m=info["distance_m"],
                elevation_m=info["elevation_m"],
                lead_in_m=info["lead_in_m"],
                lead_in_free_ride_m=None,
                lap=info["lap"],
                event_only=False,
            )
        )

    async def async_shutdown(self) -> None:
        await self._async_save_track(force=True)
        await self._store.async_save(self._stored())
        await super().async_shutdown()

    def _stored(self) -> dict[str, Any]:
        return {"progress": self._progress.as_dict()}

    # ------------------------------------------------------------- polling

    async def _async_update_data(self) -> ZwiftMapData:
        try:
            if not self.data.riding:
                profile = await self.client.async_get_profile()
                if not profile.get("riding"):
                    return ZwiftMapData(
                        track_version=self._track_version,
                        track_coverage=self.data.track_coverage,
                    )
            state = await self.client.async_get_player_state(self.player_id)
        except ZwiftNotRiding:
            return await self._went_offline()
        except ZwiftRateLimited as err:
            self._rate_penalty_s = min(self._rate_penalty_s + RATE_LIMIT_STEP_S, RATE_LIMIT_MAX_S)
            self._set_interval(online=self.data.riding)
            _LOGGER.warning(
                "Zwift throttled the request (429); polling every %.1f s for now",
                self.update_interval.total_seconds() if self.update_interval else 0,
            )
            raise UpdateFailed(f"rate limited: {err}") from err
        except ZwiftAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (ZwiftError, TimeoutError, OSError) as err:
            raise UpdateFailed(str(err)) from err

        now = dt_util.utcnow()
        if state.world_time_ms != self._last_world_time:
            self._last_world_time = state.world_time_ms
            self._world_time_changed_at = now
        elif now - self._world_time_changed_at > STALE_STATE_AFTER:
            return await self._went_offline()

        self._rate_penalty_s = max(self._rate_penalty_s - RATE_LIMIT_DECAY_S, 0.0)
        self._set_interval(online=True)
        return await self._process(state)

    def _set_interval(self, online: bool) -> None:
        base = ONLINE_INTERVAL if online else OFFLINE_INTERVAL
        self.update_interval = base + timedelta(seconds=self._rate_penalty_s if online else 0)

    async def _went_offline(self) -> ZwiftMapData:
        self._set_interval(online=False)
        await self._async_save_track(force=True)
        self._gradient.reset()
        return ZwiftMapData(
            track_version=self._track_version,
            track_coverage=self.data.track_coverage,
        )

    async def _process(self, state: PlayerState) -> ZwiftMapData:
        route = self.catalogue.get(state.route_id)
        if route is None and state.route_id and state.route_id not in self._fallback_tried:
            self._fallback_tried.add(state.route_id)
            self.hass.async_create_task(
                self._async_route_from_zwifthacks(state.route_id, course_name(state.course_id))
            )
        previous_route_id = self._progress.route_id
        progress = self._progress.update(
            state.route_id, state.distance_m, route, in_event=state.in_event
        )
        if progress.route_id != previous_route_id:
            await self._async_switch_track(route)
            self._gradient.reset()
        self._store.async_delay_save(self._stored, 15)

        gradient = self._gradient.update(state.distance_m, state.altitude_m)
        self._record(progress, state)
        await self._async_save_track()

        world = course_name(state.course_id) or (route.world if route else None)
        return ZwiftMapData(
            riding=True,
            state=state,
            progress=progress,
            world=world,
            gradient_pct=gradient,
            segment=segment_status(progress),
            track_version=self._track_version,
            track_coverage=self._track.coverage() if self._track else 0.0,
        )

    # -------------------------------------------------------------- tracks

    def track_path(self, route_id: int) -> Path:
        return self.tracks_dir / f"{route_id}.json"

    def _record(self, progress: Progress, state: PlayerState) -> None:
        if self._track is None or progress.route_distance_m is None:
            return
        if progress.phase == PHASE_LEAD_IN:
            distance = progress.route_distance_m
        elif progress.phase == PHASE_ON_ROUTE and progress.lap_distance_m is not None:
            distance = progress.lap_distance_m
        else:
            return
        self._track.add(distance, state.x_m, state.z_m, state.altitude_m)

    async def _async_switch_track(self, route: RouteInfo | None) -> None:
        await self._async_save_track(force=True)
        self._track = None
        if route is None:
            return
        data = await self.hass.async_add_executor_job(self._read_track, route.id)
        if data:
            try:
                self._track = RouteTrack.from_json(data)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring unreadable track file for route %s", route.id)
        if self._track is None:
            self._track = RouteTrack(
                route_id=route.id,
                length_m=route.distance_m,
                lead_in_m=max(route.lead_in_m, route.lead_in_free_ride_m or 0),
            )

    async def _async_save_track(self, force: bool = False) -> None:
        track = self._track
        if track is None or not track.dirty:
            return
        now = dt_util.utcnow()
        if not force and now - self._track_saved_at < TRACK_SAVE_INTERVAL:
            return
        payload = track.to_json()
        await self.hass.async_add_executor_job(self._write_track, track.route_id, payload)
        track.dirty = False
        self._track_saved_at = now
        self._track_version += 1

    def _read_track(self, route_id: int) -> dict[str, Any] | None:
        path = self.track_path(route_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_track(self, route_id: int, payload: dict[str, Any]) -> None:
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        path = self.track_path(route_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)

    async def async_get_track(self, route_id: int) -> dict[str, Any] | None:
        """Track for the card: the live, still-growing one if it is current."""
        if self._track is not None and self._track.route_id == route_id:
            return self._track.to_json()
        return await self.hass.async_add_executor_job(self._read_track, route_id)
