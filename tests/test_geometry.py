"""Geometry checked against shapes worked out by hand."""
import math

import numpy as np
import pytest
from shapely.geometry import Point

from corridor import components, config, geometry, quality


def test_bearing_is_clockwise_from_north_and_wrap_is_signed():
    assert geometry.bearing((0, 0), (0, 10)) == pytest.approx(0.0)
    assert geometry.bearing((0, 0), (10, 0)) == pytest.approx(math.pi / 2)
    assert geometry.bearing((0, 0), (-10, 0)) == pytest.approx(-math.pi / 2)
    assert geometry.wrap(3 * math.pi / 2) == pytest.approx(-math.pi / 2)
    assert geometry.wrap(-3 * math.pi / 2) == pytest.approx(math.pi / 2)


def test_right_angle_right_turn_hand_values():
    # north 100 m, then east: R = 100, T = R tan(45 deg) = 100, so the arc runs from (0,0) to (100,100)
    al = geometry.fillet([(0, 0), (0, 100), (100, 100)], 100.0)
    a = al.arcs[0]
    assert a.deflection == pytest.approx(math.pi / 2)            # right turn is positive
    assert a.tangent_length == pytest.approx(100.0)
    assert np.allclose(a.tc, [0, 0]) and np.allclose(a.ct, [100, 100])
    assert np.allclose(a.centre, [100, 0])
    assert al.length == pytest.approx(50 * math.pi)                # quarter circle, nothing straight
    assert al.line.length == pytest.approx(50 * math.pi, abs=1e-3)  # chords of at most 1 m
    for x, y in al.line.coords:
        assert math.hypot(x - 100, y - 0) == pytest.approx(100.0, abs=1e-9)
    mid = al.line.interpolate(0.5, normalized=True)                # bulges towards the PI
    assert mid.distance(Point(0, 100)) < Point(50, 50).distance(Point(0, 100))


def test_left_turn_is_the_mirror_image():
    al = geometry.fillet([(0, 0), (0, 100), (-100, 100)], 100.0)
    a = al.arcs[0]
    assert a.deflection == pytest.approx(-math.pi / 2)
    assert np.allclose(a.centre, [-100, 0])
    for x, y in al.line.coords:
        assert math.hypot(x + 100, y) == pytest.approx(100.0, abs=1e-9)


def test_general_deflection_length_formula():
    # 60 degree right turn, R = 300: T = 300 tan(30 deg); length = (500 - T) + R*pi/3 + (400 - T)
    p1 = (0.0, 500.0)
    p2 = (p1[0] + 400 * math.sin(math.radians(60)), p1[1] + 400 * math.cos(math.radians(60)))
    al = geometry.fillet([(0, 0), p1, p2], 300.0)
    t = 300 * math.tan(math.radians(30))
    assert al.arcs[0].tangent_length == pytest.approx(t)
    assert al.length == pytest.approx((500 - t) + 300 * math.pi / 3 + (400 - t))
    assert al.line.length == pytest.approx(al.length, abs=2e-3)
    assert al.straight_at_ends() == pytest.approx((500 - t, 400 - t))


def test_collinear_pis_give_no_arc():
    al = geometry.fillet([(0, 0), (0, 50), (0, 120)], 300.0)
    assert al.arcs == [] and al.length == pytest.approx(120.0)


def test_pis_too_close_for_the_radius_are_rejected():
    with pytest.raises(ValueError):
        geometry.fillet([(0, 0), (0, 100), (100, 100)], 150.0)   # needs T = 150 m on a 100 m tangent
    with pytest.raises(ValueError):
        geometry.fillet([(0, 0), (0, 100), (0, 0)], 50.0)        # doubles back


def test_rectangle_dimensions_and_orientation():
    r = geometry.rectangle((10.0, 20.0), math.radians(30), 150.0, 24.0)
    assert r.area == pytest.approx(3600.0)
    assert r.centroid.x == pytest.approx(10.0) and r.centroid.y == pytest.approx(20.0)
    # the long side runs along a 30 degree bearing
    xs, ys = zip(*list(r.exterior.coords)[:2])
    assert math.atan2(xs[1] - xs[0], ys[1] - ys[0]) == pytest.approx(math.radians(30))
    assert math.hypot(xs[1] - xs[0], ys[1] - ys[0]) == pytest.approx(150.0)


def test_station_boxes_on_a_straight_alignment():
    al = geometry.fillet([(0, 0), (0, 1000)], 300.0)
    boxes = geometry.station_boxes(al, 150.0, 24.0)
    assert boxes["south"].bounds == pytest.approx((-12.0, 0.0, 12.0, 150.0))
    assert boxes["north"].bounds == pytest.approx((-12.0, 850.0, 12.0, 1000.0))


def test_station_box_needs_a_long_enough_end_straight():
    al = geometry.fillet([(0, 0), (0, 200), (200, 400)], 300.0)   # T = 124 m leaves 76 m straight
    with pytest.raises(ValueError):
        geometry.station_boxes(al, 150.0, 24.0)


def test_tunnel_footprint_area_is_width_times_centre_line_length():
    al = geometry.fillet([(0, 0), (0, 1000)], 300.0)
    straight = geometry.tunnel_footprint(al, 150.0, 850.0, 21.6)
    assert straight.area == pytest.approx(700.0 * 21.6, rel=1e-9)
    # on a curve the band area still equals width x centre-line length (theorem of Pappus)
    al2 = geometry.fillet([(0, 0), (0, 600), (500, 900)], 300.0)
    curved = geometry.tunnel_footprint(al2, 150.0, al2.line.length - 150.0, 21.6)
    assert curved.area == pytest.approx((al2.line.length - 300.0) * 21.6, rel=2e-3)


def test_twin_tube_outer_width():
    assert geometry.twin_tube_outer_width(6.6, 15.0) == pytest.approx(21.6)


def test_worksite_sits_beside_the_box_on_the_requested_side():
    box = geometry.rectangle((0.0, 75.0), 0.0, 150.0, 24.0)
    east = geometry.worksite(box, 0.0, "east", 40.0, 10.0, 150.0, 24.0)
    west = geometry.worksite(box, 0.0, "west", 40.0, 10.0, 150.0, 24.0)
    assert east.area == pytest.approx(170.0 * 40.0)
    assert east.centroid.x == pytest.approx(12.0 + 20.0) and west.centroid.x == pytest.approx(-32.0)
    assert east.intersection(box).area == pytest.approx(0.0, abs=1e-9) and east.touches(box)
    # a box running south-west to north-east: 'east' still means the side towards larger eastings
    b2 = geometry.rectangle((0.0, 0.0), math.radians(45), 150.0, 24.0)
    e2 = geometry.worksite(b2, math.radians(45), "east", 40.0, 10.0, 150.0, 24.0)
    assert e2.centroid.x > 0 and e2.centroid.y < 0


def test_crs_round_trip_is_sub_millimetre():
    pts = np.array([[38300.0, 33700.0], [39700.0, 35800.0], [20000.0, 30000.0]])
    assert quality.crs_round_trip_error_m(pts) < 1e-3


def test_variants_in_the_inputs_build_with_the_stated_sizes():
    geo = config.corridor()["geometry"]
    for key, (al, comps) in components.all_variants().items():
        boxes = comps[comps["component_type"] == "station_box"]
        assert len(boxes) == 2
        assert boxes.area.tolist() == pytest.approx([geo["station_box"]["length_m"] * geo["station_box"]["width_m"]] * 2)
        tun = comps[comps["component_type"] == "bored_tunnel"].geometry.iloc[0]
        width = geo["bored_tunnel"]["tube_centre_spacing_m"] + geo["bored_tunnel"]["tube_outer_diameter_m"]
        expect = (al.line.length - 2 * geo["station_box"]["length_m"]) * width
        assert tun.area == pytest.approx(expect, rel=2e-3), key
        # first and last PI are the ends of the alignment
        assert al.line.coords[0] == pytest.approx(tuple(al.pis[0]))
        assert al.line.coords[-1] == pytest.approx(tuple(al.pis[-1]))
        # boxes do not overlap the tunnel footprint
        assert tun.intersection(boxes.geometry.union_all()).area < 1e-6
