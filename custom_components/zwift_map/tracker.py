"""Route progress, gradient and track recording.

Pure Python (no Home Assistant imports) so it can be unit tested.

Zwift's relay reports the *total* distance of the activity. The distance ridden
on the current route is therefore measured from the moment the route id
appears, minus the route's lead-in (the section before the official start
line). Lap routes wrap around and count laps.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .routes import RouteInfo

PHASE_FREE_RIDE = "free_ride"
PHASE_LEAD_IN = "lead_in"
PHASE_ON_ROUTE = "on_route"
PHASE_FINISHED = "finished"
PHASE_UNKNOWN_ROUTE = "unknown_route"

# A drop in total distance larger than this means a new activity started.
NEW_ACTIVITY_DROP_M = 50
# Distance between two recorded track points.
TRACK_STEP_M = 10
# A gap wider than this between recorded points counts as "not covered".
TRACK_GAP_M = 3 * TRACK_STEP_M


@dataclass(slots=True)
class Progress:
    """Where the rider is on the current route."""

    phase: str
    route_id: int
    route: RouteInfo | None
    lead_in_m: int = 0
    route_distance_m: float | None = None  # since the official start; < 0 in lead-in
    lap: int | None = None
    lap_distance_m: float | None = None  # 0..route length within the current lap
    progress_pct: float | None = None
    remaining_m: float | None = None


class ProgressTracker:
    """Turns the activity's total distance into a position on the route."""

    def __init__(self) -> None:
        self.route_id: int | None = None
        self.start_distance_m: float | None = None
        self.last_distance_m: float | None = None

    def reset(self) -> None:
        self.route_id = None
        self.start_distance_m = None
        self.last_distance_m = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "start_distance_m": self.start_distance_m,
            "last_distance_m": self.last_distance_m,
        }

    def restore(self, data: dict[str, Any] | None) -> None:
        """Resume after a Home Assistant restart in the middle of a ride."""
        if not data:
            return
        self.route_id = data.get("route_id")
        self.start_distance_m = data.get("start_distance_m")
        self.last_distance_m = data.get("last_distance_m")

    def update(
        self,
        route_id: int,
        distance_m: float,
        route: RouteInfo | None,
        in_event: bool = False,
    ) -> Progress:
        if (
            self.last_distance_m is not None
            and distance_m < self.last_distance_m - NEW_ACTIVITY_DROP_M
        ):
            self.reset()
        self.last_distance_m = distance_m

        if route_id != self.route_id or self.start_distance_m is None:
            self.route_id = route_id
            self.start_distance_m = distance_m

        if not route_id:
            return Progress(phase=PHASE_FREE_RIDE, route_id=0, route=None)

        ridden = distance_m - self.start_distance_m
        if route is None:
            return Progress(
                phase=PHASE_UNKNOWN_ROUTE,
                route_id=route_id,
                route=None,
                route_distance_m=ridden,
            )

        length = route.distance_m
        lead_in = route.lead_in_for(in_event)
        d = ridden - lead_in
        progress = Progress(
            phase=PHASE_ON_ROUTE,
            route_id=route_id,
            route=route,
            lead_in_m=lead_in,
            route_distance_m=d,
        )
        if d < 0:
            progress.phase = PHASE_LEAD_IN
            progress.lap = 0
            progress.lap_distance_m = d
            progress.progress_pct = 0.0
            progress.remaining_m = length - d
        elif route.lap:
            progress.lap = int(d // length) + 1
            progress.lap_distance_m = d % length
            progress.progress_pct = progress.lap_distance_m / length * 100
            progress.remaining_m = length - progress.lap_distance_m
        else:
            progress.lap = 1
            progress.lap_distance_m = min(d, length)
            progress.progress_pct = progress.lap_distance_m / length * 100
            progress.remaining_m = max(length - d, 0.0)
            if d >= length:
                progress.phase = PHASE_FINISHED
        return progress


class GradientEstimator:
    """Gradient (%) over the last stretch of road, from distance and altitude."""

    def __init__(self, window_m: float = 60) -> None:
        self._window = window_m
        self._samples: deque[tuple[float, float]] = deque()
        self.value: float = 0.0

    def reset(self) -> None:
        self._samples.clear()
        self.value = 0.0

    def update(self, distance_m: float, altitude_m: float) -> float:
        if self._samples and distance_m < self._samples[-1][0]:
            self._samples.clear()
        if not self._samples or distance_m > self._samples[-1][0]:
            self._samples.append((distance_m, altitude_m))
        while len(self._samples) > 2 and distance_m - self._samples[1][0] >= self._window:
            self._samples.popleft()
        first_d, first_alt = self._samples[0]
        run = distance_m - first_d
        if run >= self._window / 3:
            self.value = round((altitude_m - first_alt) / run * 100, 1)
        return self.value


@dataclass(slots=True)
class RouteTrack:
    """Geometry of a route recorded from the rider's own passes.

    Points are ``[distance_m, x_m, z_m, altitude_m]``, distance measured from
    the official start line (negative in the lead-in), one point per
    ``TRACK_STEP_M`` bucket. Existing points are kept, so the track only grows
    and stays stable between rides.
    """

    route_id: int
    length_m: int
    lead_in_m: int = 0
    buckets: dict[int, list[float]] = field(default_factory=dict)
    dirty: bool = False

    def add(self, distance_m: float, x_m: float, z_m: float, altitude_m: float) -> bool:
        if distance_m < -self.lead_in_m - TRACK_STEP_M or distance_m > self.length_m + TRACK_STEP_M:
            return False
        key = _bucket(distance_m)
        if key in self.buckets:
            return False
        self.buckets[key] = [round(distance_m, 1), round(x_m, 2), round(z_m, 2), round(altitude_m, 1)]
        self.dirty = True
        return True

    @property
    def points(self) -> list[list[float]]:
        return [self.buckets[k] for k in sorted(self.buckets)]

    def coverage(self) -> float:
        """Share of the route (0..1, lead-in excluded) covered without gaps."""
        dists = [p[0] for p in self.points if 0 <= p[0] <= self.length_m]
        if not dists or not self.length_m:
            return 0.0
        # Points sit anywhere inside their bucket: close the ends of the route.
        if dists[0] <= TRACK_GAP_M:
            dists.insert(0, 0.0)
        if self.length_m - dists[-1] <= TRACK_GAP_M:
            dists.append(float(self.length_m))
        covered = 0.0
        prev = dists[0]
        for d in dists[1:]:
            if d - prev <= TRACK_GAP_M:
                covered += d - prev
            prev = d
        return min(covered / self.length_m, 1.0)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": 1,
            "route_id": self.route_id,
            "length_m": self.length_m,
            "lead_in_m": self.lead_in_m,
            "step_m": TRACK_STEP_M,
            "coverage": round(self.coverage(), 3),
            "points": self.points,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RouteTrack:
        track = cls(
            route_id=int(data["route_id"]),
            length_m=int(data["length_m"]),
            lead_in_m=int(data.get("lead_in_m", 0)),
        )
        for p in data.get("points", []):
            track.buckets[_bucket(p[0])] = list(p)
        return track


def _bucket(distance_m: float) -> int:
    return math.floor(distance_m / TRACK_STEP_M + 0.5)
