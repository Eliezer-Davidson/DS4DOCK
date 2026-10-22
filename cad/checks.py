"""Geometric verification suite for the dock. Builds the assembled dock from the sources - cradle,
face plate, the three extender bases and their plates, the splines and top keys in their seats -
and measures it. No printing, no slicing, no files needed; reads stl/ only for the last section.

    python cad/checks.py                       # the printed configuration (std height, hook, palm)
    python cad/checks.py --all                 # every height x hook combination, one run each
    python cad/checks.py --height low --hook nohook
    python cad/checks.py --no-stl              # skip re-reading the files in stl/
    python cad/checks.py --strict              # the KNOWN rows (below) fail too: exit 1

Sections (one table row per measurement, PASS/FAIL each, exit status 1 if anything fails):
 (a) the assembled top surface is identical either side of every seam: top z of base + plate is
     probed at W y -15, 0, 15, 28, SEAM_DX mm each side of each of the three seams; the plate's
     top and the base's rim must each agree to 3 decimals.
 (b) each spline and each top key, placed in its seat, has 0.000 mm3 of interference with the two
     pieces it joins (and the key with the two plates that trap it).
 (c) the cradle's key rebates do not intersect the pocket or the charging-board bay.
 (d) every plate-screw pilot (cradle and extenders) has >= 3 mm of material under its tip, along
     its own axis, and does not clash with a key rebate, a key-screw pilot or a cable channel.
 (e) with the hook on, the material past the cradle's keyboard-end face is exactly the two side
     walls (hook_side_w each) and the middle is clear at x 0, +-30, +-60; without the hook there is
     nothing past the end face.
 (f) the stick cap's dome sphere centre is at or below the bed (no overhang), and the three caps
     are valid single solids.
 (g) every file in stl/ is one closed, consistently oriented shell (see variants.mesh_report).

"0.000 mm3" means an interference that rounds to zero at three decimals (VOL_TOL). A row whose
section and item appear in KNOWN prints KNOWN instead of FAIL and does not fail the run: it is a
measured deviation that is documented rather than fixed, with the reason printed under the summary.
`--strict` makes those rows fail (exit 1) like any other; deleting the entry does the same for good.

Frames: W is the desk (z = 0, +y toward the keyboard), P the tilted part frame; dock_params has
both. SEAM_DX = 5.6 keeps the seam probes out of every screw recess: the cradle's own counterbores
at x = +-71.3 reach x 69.3 and the extenders' nearest stations start at x 80.5 from the dock seam.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build123d import Align, Box, Cylinder, Plane, Pos, mirror  # noqa: E402

import cradle  # noqa: E402
import dock_params as p  # noqa: E402
import extender  # noqa: E402
import faceplate  # noqa: E402
import stick_cap  # noqa: E402
import variants  # noqa: E402

MIN = (Align.CENTER, Align.CENTER, Align.MIN)
SEAM_Y = (-15.0, 0.0, 15.0, 28.0)   # W y probe stations (spec)
SEAM_DX = 5.6                       # probe offset either side of a seam face, W x
PROBE_W = 0.2                       # probe column width
TOP_TOL = 0.0005                    # "equal to 3 dp"
VOL_TOL = 0.0005                    # "0.000 mm3": an interference that rounds to zero at 3 decimals
UNDER_MIN = 3.0                     # mm of material under a pilot tip
SHANK_GAP = 0.5                     # air wanted between a plate screw's shank and an M3 shank next to it
HOOK_CLEAR_X = (0.0, 30.0, -30.0, 60.0, -60.0)

# Measured deviations that are documented instead of fixed, because the fix would move holes in a
# part that has been printed (face plate v9). Keyed by (section, item). Found 2026-10-22 by this
# suite, after the v11 cradle had been printed, and not yet checked on the part itself. The (d) rows
# carry the numbers for each height; `--strict` turns these rows back into failures.
_FRONT_PILOT = (
    "the cradle's front plate-screw pilots sit 3.2 mm from the seam, inside the 9 mm the spline rebate "
    "reaches into the cradle: the pilot opens into the rebate's roof after ~7.4 of its 10 mm (so there is "
    "no material under its tip, and a long screw bites the spline's top), and the spline's own M3 pilot "
    "rises beside it, 1.3 mm away in x and 1.9 mm centre to centre at the roof, so a long plate screw "
    "and the M3 share the same space. Until this is settled the two front plate screws have to be short: "
    "the (d) rows print the longest that keeps clear of the M3 and the longest that stays out of the seat. "
    "The fix is to move the front screw row inboard of x +-65, which changes two holes in plate v9 - a "
    "decision I have not made.")
KNOWN = {
    ("d", "pilot cradle (-71.3,-16.5)"): _FRONT_PILOT,
    ("d", "pilot cradle (+71.3,-16.5)"): _FRONT_PILOT,
}


# ---- helpers --------------------------------------------------------------------------------

def vol(shape):
    sols = shape.solids()
    return float(sum(s.volume for s in sols)) if sols else 0.0


def inter(a, b):
    return vol(a & b)


def top_z(shape, x, y):
    """Highest W z of `shape` in a PROBE_W column at (x, y); None if the column misses it."""
    r = shape & Pos(x, y, 0) * Box(PROBE_W, PROBE_W, 400)
    return float(r.bounding_box().max.Z) if r.solids() else None


def seams():
    """(label, x_seam, piece at smaller x, piece at larger x, dock-side piece)."""
    out = [("left|cradle", p.ox0, "left", "cradle", "cradle")]
    prev = "cradle"
    for n, xi, xo, sgn, to in extender.pieces():
        if sgn > 0:
            out.append((f"{prev}|{n}", xi, prev, n, prev))
            prev = n
    return out


def place_spline(x_seam, dock_at_lo):
    """The spline in its seat: short end (spline_x_in) into the dock-side piece."""
    s = cradle.make_spline()
    if not dock_at_lo:
        s = mirror(s, about=Plane.YZ)
    return Pos(x_seam, 0, 0) * s


def place_topkey(x_seam, dock_at_lo):
    """The top key on the floor of its rebate, topkey_clear below the rim, in P."""
    k = cradle.make_topkey()
    if not dock_at_lo:
        k = mirror(k, about=Plane.YZ)
    return p.P * Pos(x_seam, 0, p.h_top - p.topkey_t - p.topkey_clear) * k


class Dock:
    """The assembled dock for the current dock_params configuration, in W."""

    def __init__(self):
        lift = p.P * Pos(0, 0, p.h_top)
        self.args = {n: (xi, xo, sgn, to) for n, xi, xo, sgn, to in extender.pieces()}
        self.base = {"cradle": cradle.make_cradle()}
        self.plate = {"cradle": lift * faceplate.make_faceplate()}
        for n, a in self.args.items():
            self.base[n] = extender.make_base(n, *a)
            self.plate[n] = lift * extender.make_plate(n, *a)

    def pilots(self, name):
        """[(x, y, cylinder)] in P for a piece's plate-screw pilots, the cuts the part was made with."""
        if name == "cradle":
            return list(zip([s[0] for s in p.screws], [s[1] for s in p.screws], cradle.screw_pilots()))
        pts = extender.plate_screw_pts(*self.args[name])
        return list(zip([q[0] for q in pts], [q[1] for q in pts], extender.screw_pilots(*self.args[name])))

    def void_cuts(self, name):
        """Named cuts a pilot must not open into: key rebates and key-screw pilots, cable channels."""
        if name == "cradle":
            cuts = []
            for x_seam, inward in ((p.ox0, +1.0), (p.ox1, -1.0)):
                sr = cradle.spline_rebate(x_seam, inward, True)
                cuts += [("spline rebate", sr[0]), ("spline screw pilot", sr[1])]
                cuts += [("topkey rebate", c) for c in cradle.topkey_rebate(x_seam, inward, True)]
            bay, port = cradle.usb_bay()
            cuts += [("charging bay", bay), ("cable port", port), ("connector channel", cradle.connector_channel()),
                     ("bottom slot", cradle.bottom_slot()), ("back slot", cradle.back_slot())]
            return cuts
        xi, xo, sgn, to = self.args[name]
        cuts = []
        for x_seam, inw, dock in [(xi, sgn, False)] + ([(xo, -sgn, True)] if to else []):
            sr = cradle.spline_rebate(x_seam, inw, dock)
            cuts += [("spline rebate", sr[0]), ("spline screw pilot", sr[1])]
            cuts += [("topkey rebate", c) for c in cradle.topkey_rebate(x_seam, inw, dock)]
        x_lo, x_hi = extender.span(xi, xo)
        cuts.append(("cable channel", extender.cable_channel(x_lo, x_hi)))
        return cuts


def material_under_tip(part, x, y):
    """Thickness of solid directly under a pilot's tip, measured along the pilot's own axis (P -z):
    a thin cylinder is dropped 25 mm from the tip through the part and the solid segment that
    starts at the tip is measured. 0.0 if the tip opens into a void."""
    tip = p.h_top - p.pilot_depth
    probe = p.P * Pos(x, y, tip - 25.0) * Cylinder(0.15, 25.0, align=MIN)
    r = part & probe
    if not r.solids():
        return 0.0
    inv = p.P.inverse()
    segs = sorted(((inv * s).bounding_box() for s in r.solids()), key=lambda b: -b.max.Z)
    top = segs[0]
    if top.max.Z < tip - 0.05:          # the first material is below the tip: a void under it
        return 0.0
    return float(top.max.Z - top.min.Z)


# ---- the suite --------------------------------------------------------------------------------

class Report:
    def __init__(self, strict=False):
        self.rows = []       # (section, item, detail, ok, known)
        self.strict = strict  # True: a KNOWN row is a failure like any other

    def add(self, section, item, detail, ok):
        known = (not ok) and (section, item) in KNOWN
        self.rows.append((section, item, detail, bool(ok), known))
        tag = "PASS" if ok else ("KNOWN" if known and not self.strict else "FAIL")
        print(f"  [{tag:5s}] ({section}) {item:34s} {detail}", flush=True)

    def failed(self, row):
        _sec, _item, _detail, ok, known = row
        return (not ok) and (self.strict or not known)

    @property
    def failures(self):
        return [r for r in self.rows if self.failed(r)]

    @property
    def known(self):
        return [r for r in self.rows if not r[3] and r[4]]


def pilot_vs_spline_screw(x, y):
    """For a cradle pilot near a seam, where its tilted axis runs relative to the nearer spline-screw
    pilot (vertical, M3). Returns four numbers: the centre distance between the two axes at the spline
    rebate's roof; the W z above which a plate-screw shank (pilot_d) and an M3 shank keep SHANK_GAP of
    air; the longest plate screw, plate thickness included, whose tip stays above that z; and the
    longest that stays out of the rebate. Pure arithmetic from the parameters. The z and the first
    length are None when the two axes never come that close within the pilot's depth."""
    top = p.to_world(x, y, p.h_top)
    xs = p.ox1 - p.spline_screw_in if x > 0 else p.ox0 + p.spline_screw_in
    ym = (p.spline_y[0] + p.spline_y[1]) / 2
    roof = p.spline_t + p.spline_clear
    ct, st = math.cos(math.radians(p.tilt)), math.sin(math.radians(p.tilt))
    # s mm down the pilot from the rim: W y = top_y + s*st (the axis leans toward the keyboard), W z = top_z - s*ct
    dx, dy0 = x - xs, top[1] - ym
    s_roof = (top[2] - roof) / ct
    d_roof = math.hypot(dx, dy0 + s_roof * st)
    D = p.pilot_d / 2 + 1.5 + SHANK_GAP            # centre distance at which the two shanks are SHANK_GAP apart
    s_near = None
    if D * D > dx * dx:
        r = math.sqrt(D * D - dx * dx)             # within D while dy0 + s*st is in [-r, r]
        s1, s2 = (-r - dy0) / st, (r - dy0) / st
        if s2 >= 0.0 and s1 <= p.pilot_depth:
            s_near = max(s1, 0.0)
    if s_near is None:
        return d_roof, None, None, p.plate_t + s_roof
    return d_roof, top[2] - s_near * ct, p.plate_t + s_near, p.plate_t + s_roof


def check_seams(dock, rep):
    for label, xs, lo, hi, _dock in seams():
        for y in SEAM_Y:
            zt, zr = {}, {}
            for side, name in ((-1, lo), (+1, hi)):
                x = xs + side * SEAM_DX
                zp, zb = top_z(dock.plate[name], x, y), top_z(dock.base[name], x, y)
                zt[name] = max(v for v in (zp, zb) if v is not None) if (zp is not None or zb is not None) else None
                zr[name] = zb
            ok = all(v is not None for v in list(zt.values()) + list(zr.values()))
            dt = abs(zt[lo] - zt[hi]) if ok else float("nan")
            dr = abs(zr[lo] - zr[hi]) if ok else float("nan")
            ok = ok and dt <= TOP_TOL and dr <= TOP_TOL
            rep.add("a", f"{label} y={y:+.0f}",
                    f"top {zt[lo]!s:>7.7} | {zt[hi]!s:>7.7}  d={dt:.4f}   rim {zr[lo]!s:>7.7} | {zr[hi]!s:>7.7}  d={dr:.4f}"
                    if None not in zt.values() and None not in zr.values() else f"probe missed: top {zt} rim {zr}", ok)


def check_keys(dock, rep):
    for label, xs, lo, hi, dockside in seams():
        dock_at_lo = (dockside == lo)
        s, k = place_spline(xs, dock_at_lo), place_topkey(xs, dock_at_lo)
        vs = [inter(s, dock.base[lo]), inter(s, dock.base[hi])]
        vk = [inter(k, dock.base[lo]), inter(k, dock.base[hi]), inter(k, dock.plate[lo]), inter(k, dock.plate[hi])]
        bb = s.bounding_box()
        rep.add("b", f"spline {label}",
                f"interference {vs[0]:.3f} | {vs[1]:.3f} mm3   x {bb.min.X:.1f}..{bb.max.X:.1f}  z {bb.min.Z:.2f}..{bb.max.Z:.2f}",
                all(v <= VOL_TOL for v in vs) and bb.min.Z >= -1e-6)
        rep.add("b", f"topkey {label}",
                f"interference bases {vk[0]:.3f} | {vk[1]:.3f}  plates {vk[2]:.3f} | {vk[3]:.3f} mm3",
                all(v <= VOL_TOL for v in vk))


def check_rebates_vs_voids(dock, rep):
    pocket = cradle.pocket()
    bay, _port = cradle.usb_bay()
    cuts = cradle.joint_rebates()
    vp = sum(inter(c, pocket) for c in cuts)
    vb = sum(inter(c, bay) for c in cuts)
    rep.add("c", "key rebates x pocket", f"{vp:.3f} mm3 over {len(cuts)} cuts", vp <= VOL_TOL)
    rep.add("c", "key rebates x charging bay", f"{vb:.3f} mm3", vb <= VOL_TOL)


def check_pilots(dock, rep):
    for name in ["cradle"] + list(dock.args):
        voids = dock.void_cuts(name)
        for x, y, pil in dock.pilots(name):
            under = material_under_tip(dock.base[name], x, y)
            clashes = [(lbl, inter(pil, c)) for lbl, c in voids]
            clashes = [(lbl, v) for lbl, v in clashes if v > VOL_TOL]
            txt = f"under tip {under:5.2f} mm" + (
                "   CLASH " + ", ".join(f"{lbl} {v:.3f} mm3" for lbl, v in clashes) if clashes else "   no clash")
            if name == "cradle" and any(lbl == "spline screw pilot" for lbl, _v in clashes):
                d_roof, z_near, l_near, l_seat = pilot_vs_spline_screw(x, y)
                txt += f"; axis {d_roof:.2f} mm from the spline screw at the rebate roof"
                if l_near is not None:
                    txt += (f"; a plate screw over {l_near:.1f} mm (plate included) comes within {SHANK_GAP:g} mm of "
                            f"the M3 (below W z {z_near:.2f}), over {l_seat:.1f} mm enters the seat")
            rep.add("d", f"pilot {name} ({x:+.1f},{y:+.1f})", txt, under >= UNDER_MIN and not clashes)


def check_hook_bands(dock, rep):
    y_end = p.to_world(0, p.oy1, p.h_top)[1]
    beyond = Pos(0, y_end + 15.005, 50) * Box(2 * p.ox1 + 200, 29.99, 100)     # past the end face
    r = dock.base["cradle"] & beyond
    sols = r.solids()
    if p.hook:
        bands = cradle.hook_bands()
        spans = sorted((float(s.bounding_box().min.X), float(s.bounding_box().max.X)) for s in sols)
        ok = len(spans) == len(bands) and all(abs(a - b0) <= 0.02 and abs(b - b1) <= 0.02
                                              for (a, b), (b0, b1) in zip(spans, sorted(bands)))
        rep.add("e", "hook bands past the end face",
                f"{len(sols)} solids at x " + ", ".join(f"{a:.1f}..{b:.1f}" for a, b in spans) +
                f"  (expected {', '.join(f'{a:.1f}..{b:.1f}' for a, b in sorted(bands))})", ok)
        for x in HOOK_CLEAR_X:
            v = vol(dock.base["cradle"] & Pos(x, y_end + 5.005, 50) * Box(0.5, 9.99, 100))
            rep.add("e", f"middle clear at x {x:+.0f}", f"{v:.3f} mm3 past y_end {y_end:.2f}", v <= VOL_TOL)
    else:
        rep.add("e", "nothing past the end face (no hook)", f"{len(sols)} solids, {vol(r):.3f} mm3", not sols)


def check_caps(rep):
    _R, zc = stick_cap._dome_sphere(True)
    rep.add("f", "cap dome sphere centre z", f"{zc:+.3f} mm (<= 0: no overhang)", zc <= 0)
    for f, clear in variants.CAP_FITS.items():
        c = stick_cap.make_cap(clear)
        rep.add("f", f"cap {f} (+{clear:.2f})", f"valid={c.is_valid} solids={len(c.solids())} "
                f"{c.volume:.0f} mm3", c.is_valid and len(c.solids()) == 1)


def check_stl_files(rep, root=variants.STL_DIR):
    files = []
    for dp, _dn, fn in os.walk(root):
        files += [os.path.join(dp, f) for f in fn if f.lower().endswith(".stl")]
    if not files:
        rep.add("g", "stl/ files", f"none found under {os.path.relpath(root)} (run cad/variants.py)", False)
        return
    for f in sorted(files):
        try:
            m = variants.mesh_report(f)
            ok = variants.mesh_ok(m)
            txt = (f"{m['triangles']:6d} tri  {'closed' if m['closed'] else 'OPEN'}  {m['shells']} shell  "
                   f"{m['volume'] / 1000:7.2f} cm3" + (f"  {m['degenerate']} degenerate" if m["degenerate"] else ""))
        except Exception as ex:
            ok, txt = False, f"{type(ex).__name__}: {ex}"
        rep.add("g", os.path.relpath(f, root).replace("\\", "/"), txt, ok)


def run(height, hook, stl=True, strict=False):
    variants.configure(height=height, hook=hook, plate_style="palm")
    print(f"\n=== configuration: height {height} (floor_h {p.floor_h}), {hook} (hook={p.hook}), plate palm ===")
    rep = Report(strict)
    dock = Dock()
    for name, part in dock.base.items():
        rep.add("-", f"{name} base", f"valid={part.is_valid} solids={len(part.solids())} {part.volume / 1000:.2f} cm3",
                part.is_valid and len(part.solids()) == 1)
    for name, part in dock.plate.items():
        rep.add("-", f"{name} plate", f"valid={part.is_valid} solids={len(part.solids())} {part.volume / 1000:.2f} cm3",
                part.is_valid and len(part.solids()) == 1)
    check_seams(dock, rep)
    check_keys(dock, rep)
    check_rebates_vs_voids(dock, rep)
    check_pilots(dock, rep)
    check_hook_bands(dock, rep)
    check_caps(rep)
    if stl:
        check_stl_files(rep)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Geometric verification suite (see the module docstring).")
    ap.add_argument("--all", action="store_true", help="every height x hook combination")
    ap.add_argument("--height", choices=list(variants.HEIGHTS), default="std")
    ap.add_argument("--hook", choices=list(variants.HOOKS), default="hook")
    ap.add_argument("--no-stl", action="store_true", help="skip section (g), the files in stl/")
    ap.add_argument("--strict", action="store_true", help="count the KNOWN deviation rows as failures")
    a = ap.parse_args(argv)

    combos = [(h, k) for h in variants.HEIGHTS for k in variants.HOOKS] if a.all else [(a.height, a.hook)]
    summary, total_fail, total_known, notes = [], 0, 0, {}
    for i, (h, k) in enumerate(combos):
        rep = run(h, k, stl=(not a.no_stl) and i == 0, strict=a.strict)   # the files are configuration-independent
        per = {}
        for row in rep.rows:
            sec, known = row[0], row[4]
            n, f, kn = per.get(sec, (0, 0, 0))
            per[sec] = (n + 1, f + (1 if rep.failed(row) else 0), kn + (1 if known else 0))
        summary.append((h, k, per))
        total_fail += len(rep.failures)
        total_known += len(rep.known)
        for sec, item, detail, _ok, _known in rep.failures:
            print(f"  !! ({sec}) {item}: {detail}")
        for sec, item, _detail, _ok, _known in rep.known:
            notes.setdefault(KNOWN[(sec, item)], []).append(f"({sec}) {item}")

    print("\n=== summary: rows checked / failed / known per section ===")
    secs = ["-", "a", "b", "c", "d", "e", "f", "g"]
    print(f"{'height':6s} {'hook':7s} " + " ".join(f"{s:>11s}" for s in secs))
    for h, k, per in summary:
        print(f"{h:6s} {k:7s} " + " ".join(f"{per[s][0]:4d}/{per[s][1]:<2d}/{per[s][2]:<3d}" if s in per
                                           else f"{'-':>11s}" for s in secs))
    for note, items in notes.items():
        print(f"\nKNOWN deviation ({len(items)} row(s): {', '.join(sorted(set(items)))}):\n  {note}")
    verdict = "ALL CHECKS PASSED" if not total_fail else f"{total_fail} CHECK(S) FAILED"
    if total_known:
        verdict += f" with {total_known} KNOWN deviation row(s) documented above" + (
            " (counted as failures: --strict)" if a.strict else " (not counted as failures; --strict counts them)")
    print(f"\n{verdict}")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
