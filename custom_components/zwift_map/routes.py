"""Zwift route catalogue (bundled from zwift-data, MIT)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CATALOGUE_PATH = Path(__file__).parent / "data" / "routes.json"


SEGMENT_TYPES = ("sprint", "climb", "segment")

# Zwift course ids, as sent live by the relay (field 35 / field 19), are not
# the world ids of the route catalogue: Watopia is course 6 but world 1.
COURSE_NAMES = {
    2: "Richmond",
    6: "Watopia",
    7: "London",
    8: "New York",
    9: "Innsbruck",
    10: "Bologna",
    11: "Yorkshire",
    12: "Crit City",
    13: "Makuri Islands",
    14: "France",
    15: "Paris",
    16: "Gravel Mountain",
    17: "Scotland",
}


def _metres(route: dict, key: str) -> int | None:
    value = route.get(key)
    return None if value is None else int(round(float(value)))


# World names as Zwift's game_info spells them.
MAP_NAMES = {
    "WATOPIA": "Watopia",
    "RICHMOND": "Richmond",
    "LONDON": "London",
    "NEWYORK": "New York",
    "INNSBRUCK": "Innsbruck",
    "BOLOGNATT": "Bologna",
    "YORKSHIRE": "Yorkshire",
    "CRITCITY": "Crit City",
    "MAKURIISLANDS": "Makuri Islands",
    "FRANCE": "France",
    "PARIS": "Paris",
    "GRAVEL MOUNTAIN": "Gravel Mountain",
    "SCOTLAND": "Scotland",
}


def course_name(course: int | None) -> str | None:
    """World name for a live course id."""
    if not course:
        return None
    return COURSE_NAMES.get(course, f"Course {course}")


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

    def add(self, route: RouteInfo) -> None:
        """Add a route the bundled catalogue does not know."""
        self._routes.setdefault(route.id, route)

    def merge_game_info(self, data: dict) -> int:
        """Add the routes of Zwift's ``game_info`` missing from the catalogue.

        Bundled routes keep their data (they carry segment positions); new
        routes get Zwift's own name, length and lead-ins. Returns the number of
        routes added.
        """
        added = 0
        for world in data.get("maps", []):
            world_name = MAP_NAMES.get(world.get("name", ""), str(world.get("name", "")).title())
            for r in world.get("routes", []):
                try:
                    rid = int(r["id"]) & 0xFFFFFFFF
                    distance = int(round(float(r["distanceInMeters"])))
                except (KeyError, TypeError, ValueError):
                    continue
                if rid in self._routes or distance <= 0:
                    continue
                self._routes[rid] = RouteInfo(
                    id=rid,
                    name=str(r.get("name") or f"Route {rid}"),
                    world=world_name,
                    world_id=None,
                    distance_m=distance,
                    elevation_m=_metres(r, "ascentInMeters"),
                    lead_in_m=_metres(r, "leadinDistanceInMeters") or 0,
                    lead_in_free_ride_m=_metres(r, "freeRideLeadinDistanceInMeters"),
                    lap=bool(r.get("supportedLaps", True)),
                    event_only=bool(r.get("publicEventsOnly", False)),
                )
                added += 1
        return added

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
