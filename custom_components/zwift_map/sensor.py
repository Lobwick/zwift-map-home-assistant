"""Sensors: route, world, progress, remaining distance, gradient and live state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import MATCH_ALL, PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ZwiftMapConfigEntry
from .coordinator import ZwiftMapData
from .entity import ZwiftMapEntity
from .tracker import (
    PHASE_FINISHED,
    PHASE_FREE_RIDE,
    PHASE_LEAD_IN,
    PHASE_ON_ROUTE,
    PHASE_UNKNOWN_ROUTE,
)

PHASES = [PHASE_FREE_RIDE, PHASE_LEAD_IN, PHASE_ON_ROUTE, PHASE_FINISHED, PHASE_UNKNOWN_ROUTE]


def _route_name(d: ZwiftMapData) -> str | None:
    if not d.progress or not d.progress.route_id:
        return None
    if d.progress.route:
        return d.progress.route.name
    return f"Route {d.progress.route_id}"


def _km(value: float | None) -> float | None:
    return None if value is None else round(value / 1000, 2)


def _progress(d: ZwiftMapData) -> float | None:
    if d.progress and d.progress.progress_pct is not None:
        return round(d.progress.progress_pct, 1)
    return None


def _route_attrs(d: ZwiftMapData) -> dict[str, Any]:
    if not d.progress or not d.progress.route:
        return {"route_id": d.progress.route_id if d.progress else None}
    return {**d.progress.route.as_dict(), "track_coverage": round(d.track_coverage, 3)}


@dataclass(frozen=True, kw_only=True)
class ZwiftMapSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ZwiftMapData], Any]
    attrs_fn: Callable[[ZwiftMapData], dict[str, Any]] | None = None


SENSORS: tuple[ZwiftMapSensorDescription, ...] = (
    ZwiftMapSensorDescription(
        key="route",
        icon="mdi:map-marker-path",
        value_fn=_route_name,
        attrs_fn=_route_attrs,
    ),
    ZwiftMapSensorDescription(
        key="world",
        icon="mdi:earth",
        value_fn=lambda d: d.world,
    ),
    ZwiftMapSensorDescription(
        key="route_progress",
        icon="mdi:progress-check",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=_progress,
    ),
    ZwiftMapSensorDescription(
        key="route_distance",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        value_fn=lambda d: _km(d.progress.lap_distance_m) if d.progress else None,
    ),
    ZwiftMapSensorDescription(
        key="remaining_distance",
        icon="mdi:flag-checkered",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        value_fn=lambda d: _km(d.progress.remaining_m) if d.progress else None,
    ),
    ZwiftMapSensorDescription(
        key="lap",
        icon="mdi:repeat",
        value_fn=lambda d: d.progress.lap if d.progress else None,
    ),
    ZwiftMapSensorDescription(
        key="next_segment",
        icon="mdi:flag-variant",
        value_fn=lambda d: d.segment.segment.name if d.riding and d.segment else None,
        attrs_fn=lambda d: d.segment.as_dict() if d.riding and d.segment else {},
    ),
    ZwiftMapSensorDescription(
        key="gradient",
        icon="mdi:slope-uphill",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.gradient_pct if d.riding else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZwiftMapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [ZwiftMapSensor(coordinator, desc) for desc in SENSORS]
    entities.append(ZwiftMapLiveSensor(coordinator))
    async_add_entities(entities)


class ZwiftMapSensor(ZwiftMapEntity, SensorEntity):
    entity_description: ZwiftMapSensorDescription

    def __init__(self, coordinator, description: ZwiftMapSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class ZwiftMapLiveSensor(ZwiftMapEntity, SensorEntity):
    """Everything the card needs, refreshed every poll.

    The attributes change every 2 s while riding, so they are kept out of the
    recorder.
    """

    _attr_icon = "mdi:bike-fast"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["offline", *PHASES]
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "live")

    @property
    def native_value(self) -> str:
        d = self.coordinator.data
        if not d.riding or not d.progress:
            return "offline"
        return d.progress.phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        attrs: dict[str, Any] = {
            "track_version": d.track_version,
            "track_coverage": round(d.track_coverage, 3),
        }
        if not d.riding or not d.state or not d.progress:
            return attrs
        s, p = d.state, d.progress
        route = p.route
        attrs.update(
            {
                "route_id": p.route_id or None,
                "route_name": _route_name(d),
                "world": d.world,
                "route_length_m": route.distance_m if route else None,
                "route_elevation_m": route.elevation_m if route else None,
                "lead_in_m": p.lead_in_m,
                "route_distance_m": None if p.route_distance_m is None else round(p.route_distance_m, 1),
                "lap_distance_m": None if p.lap_distance_m is None else round(p.lap_distance_m, 1),
                "lap": p.lap,
                "lap_route": route.lap if route else None,
                "progress_pct": _progress(d),
                "remaining_m": None if p.remaining_m is None else round(p.remaining_m),
                "gradient_pct": d.gradient_pct,
                "x": round(s.x_m, 2),
                "z": round(s.z_m, 2),
                "altitude_m": round(s.altitude_m, 1),
                "distance_m": s.distance_m,
                "power_w": s.power_w,
                "cadence_rpm": s.cadence_rpm,
                "heart_rate": s.heart_rate,
                "speed_kmh": round(s.speed_kmh, 1),
                "climbing_m": s.climbing_m,
                "time_s": s.time_s,
                "in_event": s.in_event,
                "road_id": s.road_id,
                "is_forward": s.is_forward,
                "segments": [seg.as_list() for seg in route.segments] if route else [],
                "segment": d.segment.as_dict() if d.segment else None,
            }
        )
        return attrs
