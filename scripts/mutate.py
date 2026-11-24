"""Plant hand-written bugs one at a time and check that the test suite notices each one.

Usage: python scripts/mutate.py --record first|final|ci [--require-all] [--only ID ...]

Each mutant replaces one exact snippet of source (it must occur exactly once). The unmutated suite must pass
first. Tests marked `golden` (committed results and documents against a fresh run) are left out, so a kill
has to come from a behavioural test with hand-worked expectations. Every file is restored after its mutant
(and again on exit, from a backup). Results go to results/mutation.json under the given key; mutants judged
equivalent (no input can tell them apart) are listed in EQUIVALENT with the reason.
"""
from __future__ import annotations

import argparse
import atexit
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "mutation.json"
BACKUP = ROOT / ".mutation_backup"
PYTEST = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-m", "not golden"]
GEO, COMP, SCR = "corridor/geometry.py", "corridor/components.py", "corridor/screening.py"
OPT, DB, DOCS = "corridor/options.py", "corridor/landdb.py", "corridor/docs.py"
XLS, DXF = "corridor/outputs/schedule_xlsx.py", "corridor/outputs/dxf_export.py"

# (id, file, original, mutant, what the bug is)
MUTANTS = [
    # geometry
    ("G01", GEO, "return math.atan2(q[0] - p[0], q[1] - p[1])", "return math.atan2(q[1] - p[1], q[0] - p[0])", "bearing measured from east, anticlockwise"),
    ("G02", GEO, "t = radius * math.tan(abs(delta) / 2.0)", "t = radius * math.tan(abs(delta))", "tangent length uses the full deflection"),
    ("G03", GEO, "normal = np.array([u_in[1], -u_in[0]]) if delta > 0 else", "normal = np.array([u_in[1], -u_in[0]]) if delta < 0 else", "arc centre on the wrong side"),
    ("G04", GEO, "return self.radius * abs(self.deflection)", "return self.radius * abs(self.deflection) / 2", "arc length halved"),
    ("G05", GEO, "sweep = -abs(a.deflection) if a.deflection > 0 else abs(a.deflection)", "sweep = abs(a.deflection) if a.deflection > 0 else -abs(a.deflection)", "arc swept the wrong way"),
    ("G06", GEO, "if used > seg + 1e-9:", "if used > 2 * seg + 1e-9:", "overlapping arcs accepted"),
    ("G07", GEO, "n = np.array([u[1], -u[0]])   # to the right", "n = np.array([u[0], -u[1]])   # to the right", "rectangle built with a wrong normal"),
    ("G08", GEO, "n_centre = pn - (length / 2.0) * unit(bn)", "n_centre = pn + (length / 2.0) * unit(bn)", "north box placed beyond the end of the alignment"),
    ("G09", GEO, 'cap_style="flat"', 'cap_style="round"', "tunnel footprint with round ends overlapping the boxes"),
    ("G10", GEO, "(box_width / 2.0 + width / 2.0)", "(box_width / 2.0 + width)", "worksite set off from the box"),
    ("G11", GEO, 'sign = 1.0 if (side == "east") == (right[0] >= 0) else -1.0', 'sign = 1.0 if (side == "east") != (right[0] >= 0) else -1.0', "worksite on the opposite side"),
    ("G12", GEO, "return centre_spacing + tube_outer_diameter", "return centre_spacing + 2 * tube_outer_diameter", "twin-tube width double-counts a diameter"),
    ("G13", GEO, "return math.atan2(math.sin(a), math.cos(a))", "return a", "deflection angle not wrapped"),
    ("G14", GEO, "last = float(np.linalg.norm(self.pis[-1] - self.arcs[-1].ct))", "last = float(np.linalg.norm(self.pis[-1] - self.arcs[-1].tc))", "end straight measured from the wrong arc end"),
    # components
    ("C01", COMP, "tunnel = geometry.tunnel_footprint(al, L, al.line.length - L, tw)", "tunnel = geometry.tunnel_footprint(al, 0.0, al.line.length, tw)", "tunnel footprint runs under the boxes"),
    ("C02", COMP, 'return crown, crown - float(geo["bored_tunnel"]["tube_outer_diameter_m"])', 'return crown, crown + float(geo["bored_tunnel"]["tube_outer_diameter_m"])', "stratum bottom above its top"),
    ("C03", COMP, 'perm = components[components["take"].isin(["permanent_surface", "permanent_subterranean"])]', "perm = components", "worksites counted as railway structure"),
    # protection distances
    ("Z01", SCR, 'return {"first_reserve": float(config.fact_value("F15")), "protection_zone": float(config.fact_value("F13")),', 'return {"first_reserve": float(config.fact_value("F15")), "protection_zone": float(config.fact_value("F14")),', "protection zone read from the safety-zone fact"),
    ("Z02", SCR, '"protection_zone": b2.difference(b1),', '"protection_zone": b2.difference(structure),', "protection ring overlaps the first reserve"),
    ("Z03", SCR, 'return {"first_reserve": b1.difference(structure),', 'return {"first_reserve": b1,', "first reserve includes the structure itself"),
    ("Z04", SCR, 'if d <= distances["first_reserve"]:', 'if d <= distances["protection_zone"]:', "interfaces within 40 m reported as first reserve"),
    ("Z05", SCR, 'return float(config.fact_value("F21"))', 'return -float(config.fact_value("F21"))', "default ownership depth sign flipped"),
    ("Z06", SCR, "if crown_level > default_level:", "if crown_level < default_level:", "stratum rule inverted"),
    ("Z07", SCR, 'if take == "temporary_surface":\n        if state_land:', 'if take == "temporary_surface":\n        if not state_land:', "TOL and s.42 swapped"),
    # area accounting
    ("A01", SCR, "MIN_PIECE_M2 = 1.0", "MIN_PIECE_M2 = 0.0", "slivers counted as land take"),
    ("A02", SCR, '"residual_m2": a - (counted + sliver + gap)', '"residual_m2": a - (counted + gap)', "slivers left out of the accounting"),
    ("A03", SCR, "sliver = float(mine[mine < MIN_PIECE_M2].sum())", "sliver = 0.0", "sliver area not summed"),
    ("A04", SCR, 'out["state_land_indicated"] = out["state_land_share"] >= STATE_LAND_SHARE', 'out["state_land_indicated"] = out["state_land_share"] >= 0.0', "every lot shown as State land"),
    ("A05", SCR, 'lu = lu.sort_values(["LOT_KEY", "a", "LU_DESC"], ascending=[True, False, True])', 'lu = lu.sort_values(["LOT_KEY", "a", "LU_DESC"], ascending=[True, True, True])', "dominant zone is the smallest share"),
    ("A06", SCR, "if a >= MIN_BUILDING_M2:", "if a > 0:", "buildings touching by a sliver counted"),
    ("A07", SCR, 'df["in_scope"] = (df[[f"{t}_m2" for t in TAKES]].sum(axis=1) > 0)', 'df["in_scope"] = (df[[f"{t}_m2" for t in TAKES]].sum(axis=1) >= 0)', "lots only near the works counted as in scope"),
    ("A08", SCR, 'gap = c.geometry.difference(lot_union).area', 'gap = 0.0', "area outside the lots ignored"),
    # added after the first run, with the code it tests (buildings counted per lot)
    ("A09", SCR, "ids.setdefault(r.LOT_KEY, set()).update(found)", "ids[r.LOT_KEY] = found", "buildings of earlier pieces in a lot forgotten"),
    ("A10", SCR, "return {k: len(v) for k, v in ids.items()}", "return {k: len(v) + 1 for k, v in ids.items()}", "one building too many per lot"),
    # scoring
    ("S01", OPT, "out = (worst - raw) / span.replace(0, np.nan)", "out = (raw - best) / span.replace(0, np.nan)", "score direction reversed"),
    ("S02", OPT, "return out.fillna(1.0)", "return out.fillna(0.0)", "ties score zero"),
    ("S03", OPT, "return scores @ (w / w.sum())", "return scores @ w", "weights not renormalised"),
    ("S04", OPT, "key=lambda v: (-round(float(total[v]), 12), v)", "key=lambda v: (round(float(total[v]), 12), v)", "ranking from worst"),
    ("S05", OPT, "out.loc[raw[c] <= best[c] * (1.0 + tol) + 1e-12, c] = best[c]", "out.loc[raw[c] <= best[c] * (1.0 - tol) + 1e-12, c] = best[c]", "tie tolerance below the best"),
    ("S06", OPT, "w[j] = w[j] * f", "w[j] = f", "one-at-a-time sets the weight instead of scaling it"),
    ("S07", OPT, "w[j] = 0.0", "w[j] = 1.0", "leave-one-out keeps the criterion"),
    ("S08", OPT, "first[rank(weighted(scores, w))[0]] += 1", "first[rank(weighted(scores, w))[-1]] += 1", "random weights count the last place"),
    # database update and rules
    ("D01", DB, "out_keys, in_keys = sorted(set(ko) - set(kn)), sorted(set(kn) - set(ko))", "out_keys, in_keys = sorted(set(kn) - set(ko)), sorted(set(ko) - set(kn))", "in and out of scope swapped"),
    ("D02", DB, 'self.interests.loc[idx, ["status", "updated"]] = ["withdrawn", AS_OF]', 'self.interests.loc[idx, ["status", "updated"]] = ["proposed", AS_OF]', "interests out of scope not withdrawn"),
    ("D03", DB, 'if s.status == "done":\n                    review.append(s.step_id)', 'if s.status == "in_progress":\n                    review.append(s.step_id)', "completed steps not flagged for review"),
    ("D04", DB, "if abs(a.area_m2 - b.area_m2) > area_tol_m2 or a.instrument_code != b.instrument_code:", "if abs(a.area_m2 - b.area_m2) > area_tol_m2:", "change of instrument not reported"),
    ("D05", DB, 'if s.status in ("done", "in_progress") and a.instrument_code == b.instrument_code:', "if False:", "progress not carried over"),
    ("D06", DB, 'limit = max_years if r.instrument_code == "TEMP-OCC" else 10.0', "limit = 10.0", "s.42 limit not applied"),
    ("D07", DB, 'if r.instrument_code == "TOL" and not state.get(r.lot_key, False):', 'if r.instrument_code == "TOL" and state.get(r.lot_key, False):', "TOL tenure rule inverted"),
    ("D08", DB, "if s.mandatory and s.status == \"done\" and seen_open:", "if s.mandatory and s.status == \"done\" and not seen_open:", "step order rule inverted"),
    ("D09", DB, "if abs(s - r.area_m2) > 0.01:", "if abs(s - r.area_m2) > 1000:", "interest and pieces may disagree"),
    ("D10", DB, '"agency": inst.agency, "area_m2": float(g["area_m2"].sum()),', '"agency": inst.agency, "area_m2": float(g["area_m2"].max()),', "interest area is its largest piece"),
    ("D11", DB, 'if g["area_m2"].sum() > parea.get(lot, float("inf")) + 0.01:', 'if g["area_m2"].max() > parea.get(lot, float("inf")) + 0.01:', "surface take per lot not summed"),
    # outputs and documents
    ("O01", XLS, 'c = ws.cell(row=tot, column=j, value=f"=SUM({L}{first}:{L}{last})")', 'c = ws.cell(row=tot, column=j, value=f"=SUM({L}{first}:{L}{last - 1})")', "workbook total misses the last row"),
    ("O02", DXF, 'msp.add_lwpolyline(list(zip(xs, ys)), dxfattribs={"layer": layer_name(k, "ALIGNMENT")})', 'msp.add_lwpolyline(list(zip(ys, xs)), dxfattribs={"layer": layer_name(k, "ALIGNMENT")})', "DXF alignment written northing, easting"),
    ("R01", DOCS, 'return re.findall(r"[^\\s|]*\\d[^\\s|]*", t)', "return []", "typed-number check disabled"),
    ("R02", DOCS, 'return f"{100 * float(value):.0f}%"', 'return f"{float(value):.0f}%"', "percentages not multiplied by 100"),
]

# (mutant id, reason) for mutants no test can kill because they do not change behaviour
EQUIVALENT: list[tuple[str, str]] = []


def run_tests() -> tuple[bool, str]:
    p = subprocess.run(PYTEST, cwd=ROOT, capture_output=True, text=True)
    failed = re.findall(r"^FAILED (\S+)", p.stdout, flags=re.M)
    return p.returncode == 0, (failed[0] if failed else ("error" if p.returncode not in (0, 1) else ""))


def restore_all() -> None:
    if BACKUP.exists():
        for f in BACKUP.rglob("*.py"):
            target = ROOT / f.relative_to(BACKUP)
            shutil.copy2(f, target)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True, choices=["first", "final", "ci"])
    ap.add_argument("--require-all", action="store_true")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args(argv)
    ok, _ = run_tests()
    if not ok:
        print("the unmutated suite fails; fix it first")
        return 2
    if BACKUP.exists():
        shutil.rmtree(BACKUP)
    for f in sorted({m[1] for m in MUTANTS}):
        dst = BACKUP / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dst)
    atexit.register(restore_all)
    eq = dict(EQUIVALENT)
    rows = []
    t0 = time.time()
    for mid, f, orig, mut, what in MUTANTS:
        if args.only and mid not in args.only:
            continue
        path = ROOT / f
        src = (BACKUP / f).read_text(encoding="utf-8")
        if src.count(orig) != 1:
            raise SystemExit(f"{mid}: snippet found {src.count(orig)} times in {f}")
        path.write_text(src.replace(orig, mut), encoding="utf-8", newline="\n")
        try:
            passed, first = run_tests()
        finally:
            path.write_text(src, encoding="utf-8", newline="\n")
        status = "killed" if not passed else ("equivalent" if mid in eq else "survived")
        rows.append({"id": mid, "file": f, "bug": what, "status": status, "first_failing_test": first or None})
        print(f"{mid} {status:9s} {first or ''}", flush=True)
    restore_all()
    shutil.rmtree(BACKUP, ignore_errors=True)
    killed = sum(r["status"] == "killed" for r in rows)
    record = {"killed": killed, "total": len(rows), "equivalent": sum(r["status"] == "equivalent" for r in rows),
              "survived": [r["id"] for r in rows if r["status"] == "survived"], "mutants": rows,
              "seconds": round(time.time() - t0)}
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[args.record] = record
    data["equivalent_reasons"] = {k: v for k, v in EQUIVALENT}
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"{killed} of {len(rows)} killed")
    if args.require_all and killed + record["equivalent"] < len(rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
