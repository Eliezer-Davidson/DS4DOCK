"""DS4 dock face plate v3 (build123d). Flat, in the part frame P: origin = PS button centre,
underside at z = 0, prints as modelled. v3 (2026-09-27): 1.6 mm thick (was 2.5), d-pad opening
0.5 mm bigger on every edge and with clearance at the arrow tips too (v2 had none there).
Unchanged from v2: plate ends at the top of the touchpad hole (y 37.4) so the touchpad, Share,
Options and Triangle holes open to that edge; sticks at y -0.5.
    python cad/variants.py --only faceplate        # stl/faceplate/faceplate_{palm,full}.stl

v4 (2026-10-03, owner): runs to the cradle's keyboard end; Share/Options 2 mm lower and fully
enclosed; d-pad, Cross, Circle, Square and Triangle holes filled (palm rest); no screw holes.
v3 sources are in _v2_2026-10-02/.

v5 (2026-10-04, owner): PS hole closed (the button is gone); Share/Options are bigger elongated
ovals (stadium slots 6.0 x 10.0 incl. clearance, were 6.0 x 7.4 ellipses). v4 sources are in
_v3_2026-10-03/.

v6 (2026-10-04, owner): Share/Options slots a bit bigger (7.0 x 11.0); stick holes a bit bigger
(22.0, were 20.0); screw holes back - 2 mm through with a 4 mm head recess halfway (0.8 mm) down
from the top face. v5 sources are in _v5_2026-10-04/.

v7 (2026-10-05, owner): stick holes 2 mm lower (y -2.5); Share/Options slots 1 mm up (y 34.1) and
a hair thinner (6.6 x 11.0); touchpad opening 2 mm deeper (bottom edge y 12.6). Runs to the cradle
v5 end (1 mm longer) so the slots keep 1.3 mm of plastic above them. v6 sources are in
_v4cradle_v6plate_2026-10-04/.

v8 (2026-10-06, owner): Options slot 1 mm right (x 32.8); the plate's keyboard end curves down
like the touchpad's top edge (8 mm radius, 73 deg, from y 37.0 - measured on the touchpad scan),
on both sides of the touchpad opening. Prints upside down (top face on the bed) with supports
under the curve. v7 sources are in _v7cradle_v7plate_2026-10-06/.

v9 (2026-10-06, owner): the end curve gets SHARPER as it goes and finishes as a full 90 deg turn,
so the plate's end points straight down. The radius shrinks linearly with the turn angle, 8 mm at
the start (still the touchpad's own radius, so they stay flush where they meet) down to 3 mm at the
tip. v8 sources are in _v8cradle_v8plate_2026-10-06/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math  # noqa: E402

from build123d import (Align, Box, Circle, Cylinder, Plane, Polygon, Pos, Rectangle, RectangleRounded,  # noqa: E402
                       Rot, SlotOverall, extrude)

import dock_params as p  # noqa: E402


def outline_2d():
    """v4: runs to the cradle's keyboard end (oy1) instead of stopping at the touchpad hole.
    v8 with the lip: the flat part stops square at lip_y_start, where the curved lip takes over."""
    w, h = p.ox1 - p.ox0, p.oy1 - p.oy0
    o = Pos((p.ox0 + p.ox1) / 2, (p.oy0 + p.oy1) / 2) * RectangleRounded(w, h, p.corner_r)
    if p.lip:
        o = o & Pos((p.ox0 + p.ox1) / 2, (p.oy0 - 1 + p.lip_y_start) / 2) * Rectangle(w + 2, p.lip_y_start - p.oy0 + 1)
    return o


def touchpad_x():
    """x edges of the touchpad opening."""
    half = (p.touchpad_wh[0] + p.hole_clear) / 2
    return p.touchpad_c[0] + p.holes_dx - half, p.touchpad_c[0] + p.holes_dx + half


def lip_profile():
    """v9: the lip's cross-section in (P y, P z), bounded by the top surface (dock_params.lip_curve)
    and the underside offset plate_t inside it (lip_inner). v8 was a plain annular sector; the curve
    now tightens as it turns, so there is no single centre and the two edges come from the same
    parametrisation. Closes with the straight end face joining the two tips."""
    n = 48
    outer = [(y, z) for y, z, _ in p.lip_curve(n)]
    inner = list(reversed(p.lip_inner(n)))
    return outer + inner


def lips():
    """v8: the lip on both sides of the touchpad opening (the opening itself stays open)."""
    if not p.lip:
        return []
    x_tp0, x_tp1 = touchpad_x()
    out = []
    for x0, x1 in ((p.ox0, x_tp0), (x_tp1, p.ox1)):
        pl = Plane(origin=(x0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))     # local x = P y, local y = P z
        out.append(extrude(pl * Polygon(*lip_profile(), align=None), amount=x1 - x0, dir=(1, 0, 0)))
    return out


def control_holes_2d():
    """v4 holes: touchpad (still open to the keyboard edge), sticks, Share and Options (2 mm lower
    than v3, so fully enclosed). With plate_style "palm" the d-pad, face-button and PS holes are
    filled: palm rest. With plate_style "full" (2026-10-21) they are open again, using the v3
    plate's geometry: every edge grown by hole_clear, the d-pad cross by dpad_grow on top. Triangle
    is a plain circle here - its top edge (y 36.9) stops just short of the lip's start (37.0), so it
    no longer has to run out through the plate's edge the way it did on the v3 plate."""
    if p.plate_style not in ("palm", "full"):
        raise ValueError(f"plate_style must be 'palm' or 'full', not {p.plate_style!r}")
    top = p.oy1 + 1
    tp_w, tp_h = p.touchpad_wh[0] + p.hole_clear, p.touchpad_wh[1] + p.hole_clear
    tp_y0 = p.touchpad_c[1] - tp_h / 2 - p.tp_notch_drop
    holes = [
        Pos(p.touchpad_c[0], (tp_y0 + top) / 2) * Rectangle(tp_w, top - tp_y0),
        *[Pos(*c) * Circle((p.stick_d + p.hole_clear + p.stick_travel) / 2) for c in (p.stick_l, p.stick_r)],
        *[Pos(*c) * Rot(Z=t) * SlotOverall(p.so_slot_len, p.so_slot_w, rotation=90)
          for c, t in ((p.share, p.so_tilt), (p.options, -p.so_tilt))],
    ]
    if p.plate_style == "full":
        fd = max(p.face_wh) + p.hole_clear                                    # 11.2 round face buttons
        dl = 2 * p.dpad_arm + p.dpad_w + p.hole_clear + 2 * p.dpad_grow      # 26.0 tip to tip
        dw = p.dpad_w + p.hole_clear + 2 * p.dpad_grow                        # 11.0 across a bar
        holes += [
            Pos(*p.ps) * Circle((p.ps_d + p.hole_clear) / 2),
            *[Pos(*c) * Circle(fd / 2) for c in (p.btn_cross, p.btn_triangle, p.btn_circle, p.btn_square)],
            Pos(*p.dpad_c) * Rectangle(dl, dw),
            Pos(*p.dpad_c) * Rectangle(dw, dl),
        ]
    return [Pos(p.holes_dx, p.holes_dy) * h for h in holes]


def make_faceplate():
    """v6: screw holes are back at the four cradle pilot positions: plate_hole_d through, with a
    plate_cbore_d head recess plate_cbore_depth deep from the top face (prints with no overhang)."""
    sk = outline_2d()
    for h in control_holes_2d():
        sk = sk - h
    plate = extrude(sk, p.plate_t)
    for lp in lips():
        plate = plate + lp
    if p.lip:                         # Share/Options slots reach into the start of the curve: cut them through it
        for c, t in ((p.share, p.so_tilt), (p.options, -p.so_tilt)):
            plate = plate - Pos(c[0] + p.holes_dx, c[1] + p.holes_dy, -20) * extrude(
                Rot(Z=t) * SlotOverall(p.so_slot_len, p.so_slot_w, rotation=90), 40)
    MIN = (Align.CENTER, Align.CENTER, Align.MIN)
    for x, y in p.screws:
        skin = p.plate_hole_skin if p.lip else 0.0          # upside-down print: bridge skin over the hole
        hole_top = p.plate_t - p.plate_cbore_depth - skin
        plate = plate - Pos(x, y, -1) * Cylinder(p.plate_hole_d / 2, hole_top + 1, align=MIN)
        plate = plate - Pos(x, y, p.plate_t - p.plate_cbore_depth) * Cylinder(p.plate_cbore_d / 2, p.plate_cbore_depth + 1, align=MIN)
    return plate


def gen_step():
    plate = make_faceplate()
    plate.label = "ds4_faceplate_v9"
    return plate
