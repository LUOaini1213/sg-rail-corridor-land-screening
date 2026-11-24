"""Stylised alignment geometry in SVY21 (metres): tangents joined by circular arcs, station boxes,
twin bored-tunnel footprint and worksites.

Bearings are measured clockwise from grid north, in radians; x = easting, y = northing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring


def bearing(p: tuple[float, float], q: tuple[float, float]) -> float:
    return math.atan2(q[0] - p[0], q[1] - p[1])


def unit(b: float) -> np.ndarray:
    return np.array([math.sin(b), math.cos(b)])


def wrap(a: float) -> float:
    """Angle wrapped to (-pi, pi]."""
    return math.atan2(math.sin(a), math.cos(a))


@dataclass
class Arc:
    pi_index: int
    radius: float
    deflection: float          # signed: + = turn to the right (clockwise), - = left
    tangent_length: float      # R tan(|delta|/2)
    tc: np.ndarray             # tangent-to-curve point
    ct: np.ndarray             # curve-to-tangent point
    centre: np.ndarray

    @property
    def length(self) -> float:
        return self.radius * abs(self.deflection)


@dataclass
class Alignment:
    pis: np.ndarray
    radius: float
    arcs: list[Arc]
    line: LineString

    @property
    def length(self) -> float:
        """Exact length: straight parts plus R * |delta| for each arc."""
        straight = 0.0
        pts = [self.pis[0]]
        for a in self.arcs:
            pts += [a.tc, a.ct]
        pts.append(self.pis[-1])
        for k in range(0, len(pts), 2):
            straight += float(np.linalg.norm(pts[k + 1] - pts[k]))
        return straight + sum(a.length for a in self.arcs)

    def straight_at_ends(self) -> tuple[float, float]:
        """Length of the straight before the first arc and after the last arc."""
        if not self.arcs:
            return self.length, self.length
        first = float(np.linalg.norm(self.arcs[0].tc - self.pis[0]))
        last = float(np.linalg.norm(self.pis[-1] - self.arcs[-1].ct))
        return first, last


def fillet(pis: list[tuple[float, float]], radius: float, max_chord_m: float = 1.0) -> Alignment:
    """Alignment through the PIs with a circular arc of the given radius at every interior PI.

    Raises ValueError when two arcs would overlap on a tangent (the PIs are too close for the radius).
    """
    p = np.asarray(pis, dtype=float)
    if len(p) < 2:
        raise ValueError("need at least two PIs")
    arcs: list[Arc] = []
    for i in range(1, len(p) - 1):
        b_in, b_out = bearing(p[i - 1], p[i]), bearing(p[i], p[i + 1])
        delta = wrap(b_out - b_in)
        if abs(delta) < 1e-12:
            continue
        if abs(abs(delta) - math.pi) < 1e-9:
            raise ValueError(f"PI {i}: the alignment doubles back")
        t = radius * math.tan(abs(delta) / 2.0)
        u_in, u_out = unit(b_in), unit(b_out)
        tc, ct = p[i] - t * u_in, p[i] + t * u_out
        # right turn (delta > 0, clockwise): centre lies to the right of the incoming direction
        normal = np.array([u_in[1], -u_in[0]]) if delta > 0 else np.array([-u_in[1], u_in[0]])
        arcs.append(Arc(i, radius, delta, t, tc, ct, tc + radius * normal))
    # tangents must not be over-used
    for k in range(len(p) - 1):
        used = sum(a.tangent_length for a in arcs if a.pi_index in (k, k + 1))
        seg = float(np.linalg.norm(p[k + 1] - p[k]))
        if used > seg + 1e-9:
            raise ValueError(f"tangent {k}-{k + 1} is {seg:.1f} m but the arcs need {used:.1f} m")
    coords: list[np.ndarray] = [p[0]]
    for a in arcs:
        coords.append(a.tc)
        n = max(2, int(math.ceil(a.length / max_chord_m)) + 1)
        phi0 = math.atan2(a.tc[1] - a.centre[1], a.tc[0] - a.centre[0])
        sweep = -abs(a.deflection) if a.deflection > 0 else abs(a.deflection)   # clockwise = negative maths angle
        for s in np.linspace(0.0, 1.0, n)[1:-1]:
            phi = phi0 + sweep * s
            coords.append(a.centre + a.radius * np.array([math.cos(phi), math.sin(phi)]))
        coords.append(a.ct)
    coords.append(p[-1])
    clean = [coords[0]]
    for c in coords[1:]:
        if np.linalg.norm(c - clean[-1]) > 1e-9:
            clean.append(c)
    return Alignment(p, radius, arcs, LineString(clean))


def rectangle(centre: tuple[float, float], axis_bearing: float, length: float, width: float) -> Polygon:
    """Rectangle centred on a point, long side along the bearing."""
    c = np.asarray(centre, dtype=float)
    u = unit(axis_bearing)
    n = np.array([u[1], -u[0]])   # to the right
    hl, hw = length / 2.0, width / 2.0
    pts = [c - hl * u - hw * n, c + hl * u - hw * n, c + hl * u + hw * n, c - hl * u + hw * n]
    return Polygon(pts)


def station_boxes(al: Alignment, length: float, width: float) -> dict[str, Polygon]:
    """Boxes over the first and the last `length` metres of the alignment, which must be straight there."""
    first, last = al.straight_at_ends()
    if first < length - 1e-9 or last < length - 1e-9:
        raise ValueError(f"the end straights ({first:.1f} m, {last:.1f} m) are shorter than the box ({length} m)")
    p0, p1 = al.pis[0], al.pis[1]
    b0 = bearing(p0, p1)
    pn1, pn = al.pis[-2], al.pis[-1]
    bn = bearing(pn1, pn)
    s_centre = p0 + (length / 2.0) * unit(b0)
    n_centre = pn - (length / 2.0) * unit(bn)
    return {"south": rectangle(tuple(s_centre), b0, length, width), "north": rectangle(tuple(n_centre), bn, length, width)}


def tunnel_footprint(al: Alignment, start_ch: float, end_ch: float, outer_width: float) -> Polygon:
    """Plan footprint of twin bored tunnels between two chainages: the centre line buffered by half the
    outer-to-outer width, with flat ends."""
    part = substring(al.line, start_ch, end_ch)
    return part.buffer(outer_width / 2.0, cap_style="flat", join_style="round", quad_segs=32)


def twin_tube_outer_width(tube_outer_diameter: float, centre_spacing: float) -> float:
    return centre_spacing + tube_outer_diameter


def worksite(box: Polygon, axis_bearing: float, side: str, width: float, extra_length: float, box_length: float,
             box_width: float) -> Polygon:
    """Rectangle along one long side of a box ('east'/'west' resolved against the box axis)."""
    u = unit(axis_bearing)
    right = np.array([u[1], -u[0]])
    # 'east' means the side whose normal points to positive x
    sign = 1.0 if (side == "east") == (right[0] >= 0) else -1.0
    c = np.array(box.centroid.coords[0]) + sign * right * (box_width / 2.0 + width / 2.0)
    return rectangle(tuple(c), axis_bearing, box_length + 2 * extra_length, width)


def distance_to(geom, xy: tuple[float, float]) -> float:
    return float(geom.distance(Point(xy)))
