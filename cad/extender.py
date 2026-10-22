"""DS4 dock wrist extenders v3 (build123d), world frame W, same frames as cradle.py.

Wrist rests that carry the assembled dock's profile outward: the same 17 deg top plane, the top at
the FACE PLATE's surface (so nothing steps under the palm), the same curled back edge, the same
keyboard undercut and the same hook on the end of that arm.

v3 (owner 2026-10-12) splits every piece into TWO printed parts, exactly the way the dock itself is
built:
  * a BASE whose top is the rim plane - literally cradle.body() over this piece's x range, with the
    same keyboard undercut, hook, lip clearance and cable channel;
  * its own flat FACE PLATE - the real face plate's outline and lip over the same x range - which
    screws down onto that base through the same two screw rows the cradle uses.
Why: v2 was one solid whose top surface WAS the plate's surface. Printed face down it came out
smooth instead of carrying the textured sheet's finish, and it did not sit flush with the dock. Now
the plate prints face down on the textured sheet like plate v9 - same finish, guaranteed - and the
base prints bottom-down, which needs no support at all under the wrist surface where v2 needed
1700-2400 s of it. Flushness stops being a matter of care: both parts are generated from the same
parameters as the real cradle and the real plate, so the mating surface is the same plane by
construction and the total height is the same h_top + plate_t.
v3 also gets the second connector per seam (cradle.topkey_rebate) and the smaller joint screws.

v2 (owner 2026-10-08), kept for the record: left 60, right 230 - and 60 + 149 + 230 = 439, the K70's
own width. The right one prints as two 115 mm halves (ext_right_split), joined to each other the
same way they join the cradle. The 6.2 mm dowel pins went; the cable channel started running through
both extenders, sized so a micro-USB plug threads end to end.

    python cad/variants.py --only _base     # stl/extenders/{left,right1,right2}_base_{height}_{hook}.stl
    python cad/variants.py --only _plate    # stl/extenders/{left,right1,right2}_plate.stl
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build123d import (Align, Box, Cylinder, Plane, Polygon, Pos, Rectangle,  # noqa: E402
                       RectangleRounded, Rot, extrude)

import cradle  # noqa: E402
import dock_params as p  # noqa: E402
import faceplate  # noqa: E402

MIN = (Align.CENTER, Align.CENTER, Align.MIN)
BIG = 800.0


def pieces():
    """Every extender piece, inner-to-outer: (name, x_inner, x_outer, grows_outward, tongue_out).

    x_inner is always the face that mates with the piece before it (the cradle, for the first).
    `grows_outward` is +1 when the piece extends toward +x. A piece carries the DOCK side of a seam
    on its outer face only when another piece follows it."""
    out = [("left", p.ox0, p.ox0 - p.ext_len_left, -1.0, False)]
    seg = p.ext_len_right_total / p.ext_right_split
    x = p.ox1
    for i in range(p.ext_right_split):
        last = (i == p.ext_right_split - 1)
        name = "right" if p.ext_right_split == 1 else f"right{i + 1}"
        out.append((name, x, x + seg, +1.0, not last))
        x += seg
    return out


def span(x_inner, x_outer):
    return min(x_inner, x_outer), max(x_inner, x_outer)


def base_body(x_lo, x_hi):
    """The dock's own body over [x_lo, x_hi]: the plate-seat rectangle in P at the rim height,
    dropped straight down to the table. Same three lines as cradle.body(), so the walls, the slope
    and the rim plane cannot drift from the real dock's.

    The rounded rectangle spans exactly the piece, so its ends carry the same corner_r the cradle
    has. That is not cosmetic: the cradle's outline is rounded by corner_r, so its side wall pinches
    right at the seam face; rounding the piece's inner end the same way makes the two cross-sections
    mirror each other and meet with nothing overhanging."""
    w, h = x_hi - x_lo, p.oy1 - p.oy0
    cx, cy = (x_lo + x_hi) / 2, (p.oy0 + p.oy1) / 2
    top = p.P * Pos(0, 0, p.h_top) * (Pos(cx, cy) * RectangleRounded(w, h, p.corner_r))
    prism = extrude(top, amount=120, dir=(0, 0, -1))
    return prism & Pos(0, 0, 100) * Box(BIG, BIG, 200)           # keep z >= 0: the flat bottom


def cable_channel(x_lo, x_hi):
    """The cable run, identical in section to the cradle's wall port so nothing steps at a seam.
    A plain rectangle: printed bottom-down its roof bridges 12.5 mm, routine in PETG, and the
    section stays matched to the cradle's."""
    y0, y1 = p.ext_cable_y
    z0, z1 = p.ext_cable_z0, p.ext_cable_z1
    return Pos((x_lo + x_hi) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * \
        Box(x_hi - x_lo + 4.0, y1 - y0, z1 - z0)


def rebate_x_ranges(x_inner, x_outer, sgn, tongue_out):
    """x spans this piece's SPLINE rebates occupy, for keeping plate screws out of them. The top
    key needs no entry: it lives at P y 2..14, between the two screw rows, so it can never clash."""
    seams = [(x_inner, sgn, False)]
    if tongue_out:
        seams.append((x_outer, -sgn, True))
    out = []
    for x_seam, inw, dock in seams:
        d = p.spline_x_in if dock else p.spline_x_out
        out.append(tuple(sorted((x_seam - inw * 1.0, x_seam + inw * (d + p.spline_clear)))))
    return out


def plate_screw_pts(x_inner, x_outer, sgn, tongue_out):
    """Where this piece's face plate screws go, in P. Two rows at the cradle's own y values so the
    dock's screw line runs straight across all four pieces; x stations inset ext_screw_inset from
    each end with intermediate pairs so no span exceeds ext_screw_pitch.

    A station that lands in a spline rebate is pushed clear of it rather than dropped: the front row
    sits at W y -21.5 and its pilot bottoms out at W y -18.6, z 5.0, which is inside the rebate
    (W y -22.3..-12.3, z 0..8.2). Shifting the whole station keeps the two rows aligned."""
    x_lo, x_hi = span(x_inner, x_outer)
    bad = rebate_x_ranges(x_inner, x_outer, sgn, tongue_out)
    reach = x_hi - x_lo - 2 * p.ext_screw_inset
    n = max(2, int(math.ceil(reach / p.ext_screw_pitch)) + 1)
    xs = []
    for i in range(n):
        x = x_lo + p.ext_screw_inset + reach * i / (n - 1)
        for a, b in bad:
            if a - 2.0 < x < b + 2.0:
                cands = [c for c in (a - 3.0, b + 3.0) if x_lo + 3.0 <= c <= x_hi - 3.0]
                x = min(cands, key=lambda c: abs(c - x)) if cands else None
                break
        if x is not None:
            xs.append(round(x, 3))
    return [(x, y) for x in sorted(set(xs)) for y in p.ext_screw_ys]


def joint_cuts(x_inner, x_outer, sgn, tongue_out):
    """This piece's half of the joint with whatever is inboard of it, and - when another piece
    follows - its half of the joint with that one. Both come from cradle.spline_rebate() and
    cradle.topkey_rebate(), so the two halves of every seam are cut from identical numbers.
    Exposed on its own so checks.py tests exactly the cuts the part was made with."""
    # inboard seam: this piece is the OUTBOARD side, so it takes the deep halves.
    cuts = cradle.spline_rebate(x_inner, sgn, False) + cradle.topkey_rebate(x_inner, sgn, False)
    # outboard seam (only when another piece follows): here this piece is the DOCK side.
    if tongue_out:
        cuts += cradle.spline_rebate(x_outer, -sgn, True) + cradle.topkey_rebate(x_outer, -sgn, True)
    return cuts


def screw_pilots(x_inner, x_outer, sgn, tongue_out):
    """The plate-screw pilots of this piece's base: the cradle's own pilot spec at plate_screw_pts()."""
    return [p.P * Pos(x, y, p.h_top - p.pilot_depth) * Cylinder(p.pilot_d / 2, p.pilot_depth + 5, align=MIN)
            for x, y in plate_screw_pts(x_inner, x_outer, sgn, tongue_out)]


def make_base(name, x_inner, x_outer, sgn, tongue_out):
    x_lo, x_hi = span(x_inner, x_outer)
    e = base_body(x_lo, x_hi)
    e = e - cradle.keyboard_lip_cut()
    # solid all the way along here, so the hook runs the whole length - there is no board in the way
    hk = cradle.keyboard_hook(x_lo, x_hi, p.h_top)
    if hk is not None:
        e = e + hk
    # room for THIS piece's own plate lip, from the lip's underside - exactly the cut the cradle
    # takes. (v2 used top_surface_clip() here instead, because its top WAS the plate's surface.)
    for cut in cradle.plate_lip_clearance():
        e = e - cut
    for cut in joint_cuts(x_inner, x_outer, sgn, tongue_out):
        e = e - cut
    e = e - cable_channel(x_lo, x_hi)
    for cut in screw_pilots(x_inner, x_outer, sgn, tongue_out):
        e = e - cut
    e.label = f"ds4_extbase_{name}_v3"
    return e


def make_plate(name, x_inner, x_outer, sgn, tongue_out):
    """This piece's face plate: the real plate's outline, thickness, lip and screw-hole spec over
    this x range, with no control openings - it is a wrist rest. Built in the same local frame as
    faceplate.py (underside at z = 0), so it drops onto the base's rim plane as modelled."""
    x_lo, x_hi = span(x_inner, x_outer)
    w, h = x_hi - x_lo, p.oy1 - p.oy0
    cx = (x_lo + x_hi) / 2
    o = Pos(cx, (p.oy0 + p.oy1) / 2) * RectangleRounded(w, h, p.corner_r)
    if p.lip:
        # flat part stops square where the lip takes over, same as faceplate.outline_2d()
        o = o & Pos(cx, (p.oy0 - 1 + p.lip_y_start) / 2) * \
            Rectangle(w + 2, p.lip_y_start - p.oy0 + 1)
    plate = extrude(o, p.plate_t)
    if p.lip:
        pl = Plane(origin=(x_lo, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))   # local x = P y, y = P z
        plate = plate + extrude(pl * Polygon(*faceplate.lip_profile(), align=None),
                                amount=w, dir=(1, 0, 0))
    for x, y in plate_screw_pts(x_inner, x_outer, sgn, tongue_out):
        skin = p.plate_hole_skin if p.lip else 0.0        # upside-down print: a skin bridges the hole
        hole_top = p.plate_t - p.plate_cbore_depth - skin
        plate = plate - Pos(x, y, -1) * Cylinder(p.plate_hole_d / 2, hole_top + 1, align=MIN)
        plate = plate - Pos(x, y, p.plate_t - p.plate_cbore_depth) * \
            Cylinder(p.plate_cbore_d / 2, p.plate_cbore_depth + 1, align=MIN)
    plate.label = f"ds4_extplate_{name}_v3"
    return plate


def make_piece(name):
    """(base, plate) for one named piece."""
    for n, xi, xo, sgn, to in pieces():
        if n == name:
            return make_base(n, xi, xo, sgn, to), make_plate(n, xi, xo, sgn, to)
    raise ValueError(f"no piece called {name!r}; have {[q[0] for q in pieces()]}")


def drop(part):
    b = part.bounding_box()
    return Pos(-b.center().X, -b.center().Y, -b.min.Z) * part


def base_for_print(part):
    """The base prints exactly as modelled: flat bottom on the bed, vertical walls, and the rim's
    17 deg top self-supporting. Only the keyboard undercut needs support, as on the cradle."""
    return drop(part)


def plate_for_print(part):
    """Face down, like plate v9: the top face on the textured sheet - which is the whole point of
    the split - the lip rising away from the bed, and each screw recess facing the bed where
    plate_hole_skin bridges it."""
    return drop(Rot(X=180) * part)


OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")   # scratch, gitignored


def export_all(out=None):
    """Scratch export of every piece, as modelled and in print orientation, plus STEP. Writes to
    cad/out/ next to this file unless `out` is given. The shipped matrix is built by variants.py."""
    from build123d import export_step, export_stl
    out = out or OUT_DIR
    os.makedirs(out, exist_ok=True)
    made = {}
    for n, xi, xo, sgn, to in pieces():
        b = make_base(n, xi, xo, sgn, to)
        pl = make_plate(n, xi, xo, sgn, to)
        made[n] = (b, pl)
        export_stl(b, os.path.join(out, f"extbase_{n}_v3.stl"))
        export_stl(base_for_print(b), os.path.join(out, f"extbase_{n}_v3_print.stl"))
        export_stl(pl, os.path.join(out, f"extplate_{n}_v3.stl"))
        export_stl(plate_for_print(pl), os.path.join(out, f"extplate_{n}_v3_print.stl"))
        export_step(b, os.path.join(out, f"extbase_{n}_v3.step"))
        export_step(pl, os.path.join(out, f"extplate_{n}_v3.step"))
    return made
