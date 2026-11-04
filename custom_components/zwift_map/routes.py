"""Zwift route catalogue (bundled from zwift-data, MIT)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CATALOGUE_PATH = Path(__file__).parent / "data" / "routes.json"


SEGMENT_TYPES = ("sprint", "climb", "segment")


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """A timed segment (sprint, climb/KOM, other) as it appears on a route."""

    slug: str
    name: str
    type: str
    from_m: int  # from the route's start line
    to_m: int
    avg_grade: float | None = None

    @property
    def length_m(self) -> int:
        return self.to_m - self.from_m

    def as_list(self) -> list:
        """Compact form for the card: [from_m, to_m, type, name]."""
        return [self.from_m, self.to_m, self.type, self.name]


@dataclass(frozen=True, slots=True)
class RouteInfo:
    """Static description of a Zwift route."""

    id: int
    name: str
    world: str
    world_id: int | None
    distance_m: int
    elevation_m: int | None
    lead_in_m: int
    lead_in_free_ride_m: int | None
    lap: bool
    event_only: bool
    segments: tuple[RouteSegment, ...] = ()

    def lead_in_for(self, in_event: bool) -> int:
        """Lead-in length: events and free rides start from different pens."""
        if not in_event and self.lead_in_free_ride_m is not None:
            return self.lead_in_free_ride_m
        return self.lead_in_m

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "world": self.world,
            "world_id": self.world_id,
            "distance_m": self.distance_m,
            "elevation_m": self.elevation_m,
            "lead_in_m": self.lead_in_m,
            "lead_in_free_ride_m": self.lead_in_free_ride_m,
            "lap": self.lap,
            "event_only": self.event_only,
            "segments": [s.as_list() for s in self.segments],
        }


class RouteCatalogue:
    """Lookup of routes by Zwift route id and of world names by world id."""

    def __init__(self, data: dict) -> None:
        self.source: str = data.get("source", "")
        self._worlds = {int(k): v for k, v in data.get("worlds", {}).items()}
        seg_info: dict = data.get("segments", {})
        self._routes: dict[int, RouteInfo] = {}
        for r in data.get("routes", []):
            if not r.get("distance_m"):
                continue
            segments = []
            for slug, start, end in r.get("segments", []):
                info = seg_info.get(slug, {})
                if start is None or end is None or end <= start:
                    continue
                kind = info.get("type") if info.get("type") in SEGMENT_TYPES else "segment"
                segments.append(
                    RouteSegment(
                        slug=slug,
                        name=info.get("name", slug),
                        type=kind,
                        from_m=int(start),
                        to_m=int(end),
                        avg_grade=info.get("avg_grade"),
                    )
                )
            segments.sort(key=lambda seg: seg.from_m)
            self._routes[int(r["id"])] = RouteInfo(
                id=int(r["id"]),
                name=r["name"],
                world=r.get("world") or "",
                world_id=r.get("world_id"),
                distance_m=int(r["distance_m"]),
                elevation_m=r.get("elevation_m"),
                lead_in_m=int(r.get("lead_in_m") or 0),
                lead_in_free_ride_m=r.get("lead_in_free_ride_m"),
                lap=bool(r.get("lap")),
                event_only=bool(r.get("event_only")),
                segments=tuple(segments),
            )

    @classmethod
    def load(cls, path: Path = CATALOGUE_PATH) -> RouteCatalogue:
        """Read the catalogue file (blocking: call from an executor)."""
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def __len__(self) -> int:
        return len(self._routes)

    def get(self, route_id: int | None) -> RouteInfo | None:
        if not route_id:
            return None
        return self._routes.get(route_id)

    def world_name(self, world_id: int | None) -> str | None:
        if not world_id:
            return None
        return self._worlds.get(world_id, f"World {world_id}")
