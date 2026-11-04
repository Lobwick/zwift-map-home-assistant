import pytest
from zwift_map_pure.routes import RouteCatalogue, RouteInfo
from zwift_map_pure.tracker import (
    PHASE_FINISHED,
    PHASE_FREE_RIDE,
    PHASE_LEAD_IN,
    PHASE_ON_ROUTE,
    PHASE_UNKNOWN_ROUTE,
    GradientEstimator,
    ProgressTracker,
    RouteTrack,
)


def route(distance_m=20_000, lead_in_m=0, lead_in_free_ride_m=None, lap=False, rid=42):
    return RouteInfo(
        id=rid,
        name="Test",
        world="Watopia",
        world_id=1,
        distance_m=distance_m,
        elevation_m=100,
        lead_in_m=lead_in_m,
        lead_in_free_ride_m=lead_in_free_ride_m,
        lap=lap,
        event_only=False,
    )


def test_progress_counts_from_route_start_not_activity_start():
    """10 km of free ride, then 1 km on a 20 km route = 5 %, not 55 %."""
    t = ProgressTracker()
    r = route()
    assert t.update(0, 10_000, None).phase == PHASE_FREE_RIDE
    t.update(42, 10_000, r)
    p = t.update(42, 11_000, r)
    assert p.phase == PHASE_ON_ROUTE
    assert p.progress_pct == pytest.approx(5.0)
    assert p.remaining_m == pytest.approx(19_000)


def test_lead_in_then_route():
    t = ProgressTracker()
    r = route(lead_in_m=500)
    t.update(42, 0, r)
    p = t.update(42, 300, r)
    assert p.phase == PHASE_LEAD_IN
    assert p.route_distance_m == pytest.approx(-200)
    assert p.progress_pct == 0
    p = t.update(42, 1_500, r)
    assert p.phase == PHASE_ON_ROUTE
    assert p.route_distance_m == pytest.approx(1_000)
    assert p.progress_pct == pytest.approx(5.0)


def test_free_ride_and_event_lead_ins_differ():
    r = route(lead_in_m=500, lead_in_free_ride_m=800)
    free, event = ProgressTracker(), ProgressTracker()
    free.update(42, 0, r, in_event=False)
    event.update(42, 0, r, in_event=True)
    assert free.update(42, 1_000, r, in_event=False).route_distance_m == pytest.approx(200)
    assert event.update(42, 1_000, r, in_event=True).route_distance_m == pytest.approx(500)


def test_lap_route_wraps_and_counts_laps():
    t = ProgressTracker()
    r = route(distance_m=10_000, lap=True)
    t.update(42, 0, r)
    p = t.update(42, 23_000, r)
    assert p.lap == 3
    assert p.lap_distance_m == pytest.approx(3_000)
    assert p.progress_pct == pytest.approx(30.0)
    assert p.remaining_m == pytest.approx(7_000)


def test_point_to_point_route_finishes():
    t = ProgressTracker()
    r = route(distance_m=10_000)
    t.update(42, 0, r)
    p = t.update(42, 10_400, r)
    assert p.phase == PHASE_FINISHED
    assert p.progress_pct == pytest.approx(100.0)
    assert p.remaining_m == 0


def test_route_change_restarts_counting():
    t = ProgressTracker()
    a, b = route(rid=1), route(rid=2)
    t.update(1, 0, a)
    t.update(1, 5_000, a)
    p = t.update(2, 5_000, b)
    assert p.route_distance_m == pytest.approx(0)
    assert t.update(2, 6_000, b).route_distance_m == pytest.approx(1_000)


def test_new_activity_resets():
    t = ProgressTracker()
    r = route()
    t.update(42, 0, r)
    t.update(42, 15_000, r)
    t.update(42, 100, r)  # distance dropped: new activity
    assert t.update(42, 1_100, r).route_distance_m == pytest.approx(1_000)


def test_restore_resumes_after_restart():
    t = ProgressTracker()
    r = route()
    t.update(0, 4_000, None)
    t.update(42, 4_000, r)
    t.update(42, 6_000, r)
    saved = t.as_dict()
    resumed = ProgressTracker()
    resumed.restore(saved)
    assert resumed.update(42, 7_000, r).route_distance_m == pytest.approx(3_000)


def test_unknown_route_id():
    t = ProgressTracker()
    t.update(999, 1_000, None)
    p = t.update(999, 1_500, None)
    assert p.phase == PHASE_UNKNOWN_ROUTE
    assert p.route_distance_m == pytest.approx(500)


def test_gradient():
    g = GradientEstimator(window_m=60)
    for d in range(0, 200, 10):
        value = g.update(d, d * 0.05)  # constant 5 %
    assert value == pytest.approx(5.0)
    for d in range(200, 400, 10):
        value = g.update(d, 10 - (d - 200) * 0.02)  # then -2 %
    assert value == pytest.approx(-2.0)


def test_track_records_one_point_per_step_and_keeps_existing():
    tr = RouteTrack(route_id=42, length_m=1_000, lead_in_m=100)
    assert tr.add(-50, 1, 1, 10)
    assert not tr.add(-52, 9, 9, 99)  # same 10 m bucket: kept as is
    for d in range(0, 1_001, 5):
        tr.add(d, d, 0, 10)
    assert tr.coverage() == pytest.approx(1.0)
    assert tr.points[0] == [-50, 1, 1, 10]
    assert not tr.add(5_000, 0, 0, 0)  # beyond the route


def test_track_coverage_ignores_gaps_and_round_trips():
    tr = RouteTrack(route_id=42, length_m=1_000)
    for d in list(range(0, 301, 10)) + list(range(700, 1_001, 10)):
        tr.add(d, 0, 0, 0)
    assert tr.coverage() == pytest.approx(0.6)
    again = RouteTrack.from_json(tr.to_json())
    assert again.points == tr.points
    assert again.coverage() == pytest.approx(0.6)


def test_bundled_catalogue_loads():
    cat = RouteCatalogue.load()
    assert len(cat) > 300
    big_loop = cat.get(2947111049)
    assert big_loop.name == "Big Loop"
    assert big_loop.world == "Watopia"
    assert cat.world_name(10) == "France"
    assert cat.get(0) is None
