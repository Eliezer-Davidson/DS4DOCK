"""DS4 dock cradle (build123d), in the world frame W: flat bottom on the table, top face tilted
`tilt` (15) degrees rising toward the keyboard. The board lies in a pocket square to that slope;
the face plate screws onto the top face with four M3 self-tappers.

Construction: the top face is the plate-seat rectangle in the part frame P (the frame the board
and plate live in), dropped straight down to the table, so the walls are vertical, the bottom is
flat, and the plate outline, rim and screw pilots all line up in P by construction. This replaces
cradle() in ds4_dock.scad, which set the top a VERTICAL stack_h + plate_gap above the tilted floor
(plate 3.8 mm up-slope of the board, 0.1 mm gap), drilled vertical pilots that missed the tilted
plate holes, and put the right wing dowel inside the USB bay (review 2026-09-24).
    python cad/variants.py --only cradle_std_hook   # stl/cradle/cradle_std_hook.stl (the printed one)
    python cad/checks.py                            # the geometric verification suite

v2 (2026-10-02, owner): as low as possible (floor 1.6 mm, was 3.0); ends 2.5 mm past the face
plate's keyboard edge with no wall on the keyboard side (the pocket runs out open there); the
under-floor USB-board bay and its right-face cable exit are gone; a channel in the pocket floor
takes the plug in the charging-board port on the board's back so the board lies flush, running
out of the open keyboard end. v1 sources are in _v1_2026-09-27/.

v3 (2026-10-03, owner): tilt 10 (was 15) for a lower base; walls 3 mm lower (stack_h 11); the
finger notch is a square-bottomed slot down to the floor; the channel moves to 30..40 mm right of
the PS button (it is for the charging-board ribbon connector) and joins the charging-board bay,
which is back, with its port hole in the right face. v2 sources are in _v2_2026-10-02/.

v4 (2026-10-04, owner): walls 1 mm taller (stack_h 12); the pocket floor is unchanged.
v3 sources are in _v3_2026-10-03/.

v5 (2026-10-05, owner): walls 2 mm taller (stack_h 14); the channel's exit in the keyboard-end
face runs 5 mm further right (x 30..45); the channel's opening in the underside moves 10 mm toward
the keyboard (W y -1.1..19.1, was -11.1..9.1), so the channel starts 10 mm later. The cradle is
1 mm deeper (beyond_plate 3.5) so plate v7's raised Share/Options slots stay enclosed.
v4 sources are in _v4cradle_v6plate_2026-10-04/.

v6 (2026-10-05, owner): pilot holes 2.0 mm (were 2.6) to match the plate's 2 mm screw holes; a
right-trapezoid undercut along the whole keyboard side (14 mm along the desk, 10 mm tall at the
inner edge, 18 mm at the end face) so the dock's back overhangs the keyboard's front lip. The
floor, the keyboard half of the charging bay and the end of the channel go with it; the side rims
float above it. v5 sources are in _v5cradle_v7plate_2026-10-05/.

v7 (2026-10-05, owner): the notch left in the right wall by the cut is the charging-cable exit;
it is now at least 6 mm wide (cable_notch_w; was 3 mm). Printed in PETG Basic with tree supports
from the build plate under the floating arms. The four dowel holes for the wrist-rest extension
are teardrops (45 deg peak) so no support grows inside them. v6 sources are in _v6cradle_2026-10-05/.

v8 (2026-10-06, owner): tilt 14 deg (was 10) so the keyboard end of the floor sits 3.5 mm higher
relative to your end, with the floor lowered to 1.0 mm at the pivot (was 1.6) to give some of that
height back; a 10 x 3 mm notch for the charging board's LED end in the wall facing the user, right
inside corner, at floor level; the rim's keyboard end is rounded under plate v8's curved lip.
v7 sources are in _v7cradle_v7plate_2026-10-06/.

v9 (2026-10-06, owner): tilt 17 deg (was 14.5), a bit steeper again; the LED notch moves 5 mm left,
in from the pocket's right corner; the rim's keyboard end follows plate v9's sharper lip, which now
turns a full 90 deg, so the cut under it is built from the lip's underside points instead of one
arc. v8 sources are in _v8cradle_v8plate_2026-10-06/.

v10 (2026-10-08, owner): 1 mm taller from the base (floor_h 2.0); the two 6.2 mm extender dowel
pins are retired for a loose spline + M3 screws in the solid front wall; the notch in the right
wall is now a micro-USB cable port that runs on through the extenders; and the arm above the
keyboard undercut carries on 2 mm at the same angle then drops 4 mm square to itself, hooking the
keyboard's front lip. v9 sources are in _v9cradle_v9plate_2026-10-06/.

v11 (2026-10-12, owner): the pocket is 1 mm deeper (stack_h 15) because the face plate bowed
upwards over the board + touchpad stack; the hook is no longer a bar across the whole width - it
sits on the two side walls only, leaving the middle 131 mm clear of the board and the touchpad,
which overhang the keyboard end face; every seam gains a SECOND connector, a flat key in a shallow
rebate in the rim's top face, hidden under the face plate; and the spline's screw holes shrink
(clearance 3.2, counterbore 5.6 x 2.2, pilot 2.4).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build123d import Box, Circle, Cylinder, Plane, Polygon, Pos, RectangleRounded, extrude  # noqa: E402
from build123d import Align  # noqa: E402

import dock_params as p  # noqa: E402

MIN = (Align.CENTER, Align.CENTER, Align.MIN)     # cylinder starts at its location, runs +Z


def body():
    """Plate-seat rectangle in P at the rim height, dropped to the table."""
    w, h = p.ox1 - p.ox0, p.oy1 - p.oy0
    top = p.P * Pos(0, 0, p.h_top) * (Pos((p.ox0 + p.ox1) / 2, (p.oy0 + p.oy1) / 2) * RectangleRounded(w, h, p.corner_r))
    prism = extrude(top, amount=80, dir=(0, 0, -1))
    return prism & Pos(0, 0, 100) * Box(400, 400, 200)            # keep z >= 0: the flat bottom


def pocket():
    x0, y0, x1, y1 = p.pocket
    outline = Pos((x0 + x1) / 2, (y0 + y1) / 2) * RectangleRounded(x1 - x0, y1 - y0, p.body_r + p.pocket_clear)
    return p.P * extrude(outline, amount=p.h_top + 10)             # floor at P z = 0, open at the top


def screw_pilots():
    return [p.P * Pos(x, y, p.h_top - p.pilot_depth) * Cylinder(p.pilot_d / 2, p.pilot_depth + 5, align=MIN)
            for x, y in p.screws]


def finger_notch():
    """v3: square-bottomed slot through the user-side wall, notch_d wide, from the pocket floor
    up through the top (v1/v2 had a round notch)."""
    y_front = p.to_world(0, p.oy0, p.h_top)[1] - 1
    y_end = p.y_cut + 2                                             # just inside the pocket
    z0 = p.floor_z(p.pocket[1])
    return Pos(0, (y_front + y_end) / 2, z0 + 50) * Box(p.notch_d, y_end - y_front, 100)


def below_floor():
    """Everything under the pocket floor plane (P z < 0)."""
    return p.P * Pos(0, 0, -100) * Box(600, 600, 200)


def usb_bay():
    """v3: charging-board bay under the floor at the right of the keyboard end, open up into the
    pocket (the main board bridges it), plus the port hole through the right side face."""
    y_end = p.to_world(0, p.oy1, p.h_top)[1]                        # the cradle's keyboard end face
    y1 = y_end - p.jds_end_skin
    y0 = y1 - p.jds_wh[1]
    x1 = p.ox1 - p.wall
    x0 = x1 - p.jds_wh[0]
    bay = Pos((x0 + x1) / 2, (y0 + y1) / 2, p.jds_z0 + 50) * Box(x1 - x0, y1 - y0, 100)
    # v10: the port hole in the right wall IS the extenders' cable channel, so a micro-USB plug can
    # be threaded from the far end of the extenders straight through into the bay. Same rectangle
    # on both sides of the joint, so nothing steps down at the seam.
    cy0, cy1 = p.ext_cable_y
    port = Pos((x1 + p.ox1 + 1) / 2, (cy0 + cy1) / 2, (p.ext_cable_z0 + p.ext_cable_z1) / 2) * \
        Box(p.ox1 + 1 - x1, cy1 - cy0, p.ext_cable_z1 - p.ext_cable_z0)
    return [bay & below_floor(), port]


def connector_channel():
    """Channel square to the pocket floor, chan_d deep, from chan_y0_shift past the user-side pocket
    edge out past the open keyboard end. v5: starts 10 mm later, so the floor in front is closed."""
    y0 = p.pocket[1] + p.chan_y0_shift
    y1 = p.oy1 + 20
    return p.P * Pos(p.chan_x, (y0 + y1) / 2, (1 - p.chan_d) / 2) * Box(p.chan_w, y1 - y0, p.chan_d + 1)


def bottom_slot():
    """v5: the channel's opening through the underside, at bottom_slot_y (W), channel width."""
    y0, y1 = p.bottom_slot_y
    box = Pos(p.chan_x, (y0 + y1) / 2, 49) * Box(p.chan_w, y1 - y0, 100)
    return box & below_floor()


def back_slot():
    """v5: widen the channel's exit in the keyboard-end face to the right, out to back_slot_x1,
    at the channel's depth (the bay sits just behind the end skin)."""
    x0 = p.chan_x + p.chan_w / 2 - 0.01
    y0, y1 = p.oy1 - 6, p.oy1 + 20
    return p.P * Pos((x0 + p.back_slot_x1) / 2, (y0 + y1) / 2, (1 - p.chan_d) / 2) * Box(p.back_slot_x1 - x0, y1 - y0, p.chan_d + 1)


def dowel_holes():
    """v1-v9: 6.2 mm teardrop holes in both side faces for the extension's dowel pins. RETIRED in
    v10 at the owner's request - two small round pins in a flat butt joint resisted almost nothing
    in twist and the extenders were badly wobbly. Replaced by joint_tongues() + two M3 screws.
    Kept (behind `dowels`, now False) because the holes were an owner-specified feature once."""
    if not p.dowels:
        return []
    r = p.dowel_d / 2
    k = r / math.sqrt(2)
    holes = []
    for y in p.dowel_ys:
        for x0 in (p.ox0 - 1, p.ox1 - p.dowel_depth):
            # sketch plane: local x = world y, local y = world z, normal = world +x
            pl = Plane(origin=(x0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
            prof = Pos(y, p.dowel_z) * Circle(r)
            if p.dowel_teardrop:
                prof = prof + Pos(y, p.dowel_z) * Polygon((-k, k), (k, k), (0, r * math.sqrt(2)), align=None)
            holes.append(extrude(pl * prof, amount=p.dowel_depth + 1))
    return holes


def arm_frame():
    """The undercut's own top line at the keyboard-end face, and unit vectors along it.
    Returns (P0y, P0z, along, down) where `along` runs up-slope toward the keyboard and `down`
    is perpendicular to it. Everything about the hook is expressed in this frame."""
    y_end = p.to_world(0, p.oy1, p.h_top)[1]
    a = math.atan2(p.kb_cut_h_end - p.kb_cut_h_inner, p.kb_cut_len)
    ca, sa = math.cos(a), math.sin(a)
    return y_end, p.kb_cut_h_end, (ca, sa), (sa, -ca), a


def keyboard_hook(x0, x1, top_z_p):
    """v10: solid to ADD at the keyboard end, spanning x0..x1.

    The arm carries on `hook_ext` past the end face along the undercut's own line, and the last
    `hook_t` of that drops `hook_drop` perpendicular to the line. `top_z_p` is the P-height of the
    part's top surface, so the extension is clipped flush to whatever that part's top is."""
    if not p.hook:
        return None
    P0y, P0z, u, v, _ = arm_frame()

    def pt(du, dv):
        return (P0y + du * u[0] + dv * v[0], P0z + du * u[1] + dv * v[1])

    BIG = 60.0
    ext = [pt(0, 0), pt(p.hook_ext, 0), pt(p.hook_ext, -BIG), pt(0, -BIG)]
    leg = [pt(p.hook_ext - p.hook_t, 0), pt(p.hook_ext, 0),
           pt(p.hook_ext, p.hook_drop), pt(p.hook_ext - p.hook_t, p.hook_drop)]
    span = Pos((x0 + x1) / 2, 0, 0) * Box(x1 - x0, 1200, 1200)
    body = extrude(Plane.YZ * Polygon(*ext, align=None), amount=600, both=True)
    body = body & (p.P * Pos(0, 0, top_z_p - 100) * Box(1600, 1600, 200))   # flush with the top
    tab = extrude(Plane.YZ * Polygon(*leg, align=None), amount=600, both=True)
    return (body + tab) & span


def hook_bands():
    """v11: the x bands of the CRADLE that carry the keyboard hook. The two side walls only.

    Inboard of them the keyboard end face is all pocket - the board overhangs that face by 3.6 mm
    and the hook's extension lands inside the board - so a wider band would both foul the board and
    print as a bar bridging 131 mm in mid-air behind it. hook_side_w = 0 restores v10's full-width
    bar. The extenders are solid and keep the hook over their whole length, so each side of the
    assembled dock still ends up with one continuous hooked arm."""
    w = p.hook_side_w
    if not w or 2 * w >= p.ox1 - p.ox0:
        return [(p.ox0, p.ox1)]
    return [(p.ox0, p.ox0 + w), (p.ox1 - w, p.ox1)]


def spline_rebate(x_seam, inward, dock_side):
    """Cuts for ONE side of a spline joint: the pocket its half of the spline sits in, open at the
    seam face and open downwards, plus the pilot for the M3 that comes up through the spline into
    this part. `inward` is +1 when this part's body lies at larger x than the seam; `dock_side` is
    True for the part nearer the dock, which gets the shallower 9 mm half.

    Shared by the cradle and every extender piece, so both halves of any seam come from the same
    numbers and cannot drift apart."""
    if not p.joint_spline:
        return []
    c = p.spline_clear
    depth = p.spline_x_in if dock_side else p.spline_x_out
    sx = p.spline_screw_in if dock_side else p.spline_screw_out
    y0, y1 = p.spline_y[0] - c, p.spline_y[1] + c
    ym = (p.spline_y[0] + p.spline_y[1]) / 2
    xa, xb = sorted((x_seam - inward * 1.0, x_seam + inward * (depth + c)))
    rebate = Pos((xa + xb) / 2, (y0 + y1) / 2, (p.spline_t + c) / 2 - 0.5) * \
        Box(xb - xa, y1 - y0, p.spline_t + c + 1.0)
    pilot = Pos(x_seam + inward * sx, ym, p.spline_t + c) * \
        Cylinder(p.screw_pilot_d / 2, p.screw_pilot_depth, align=MIN)
    return [rebate, pilot]


def topkey_rebate(x_seam, inward, dock_side):
    """v11: the second connector's seat - a shallow rebate in the rim's TOP face, open upwards and
    open at the seam face. Built in P so its floor is parallel to the face plate, which screws down
    over it and is what traps the key. Same argument convention as spline_rebate()."""
    if not p.topkey:
        return []
    c = p.topkey_clear
    depth = p.topkey_x_in if dock_side else p.topkey_x_out
    y0, y1 = p.topkey_y[0] - c, p.topkey_y[1] + c
    xa, xb = sorted((x_seam - inward * 1.0, x_seam + inward * (depth + c)))
    t = p.topkey_t + c                                      # deeper than the key is thick
    return [p.P * Pos((xa + xb) / 2, (y0 + y1) / 2, p.h_top - t / 2 + 0.5) *
            Box(xb - xa, y1 - y0, t + 1.0)]


def make_topkey():
    """The top key itself: a plain flat bar bridging the seam, no screw - the face plate holds it
    down. Modelled lying flat at the origin, prints as modelled, seconds each."""
    y0, y1 = p.topkey_y
    s = Pos((p.topkey_x_out - p.topkey_x_in) / 2, (y0 + y1) / 2, p.topkey_t / 2) *         Box(p.topkey_x_in + p.topkey_x_out, y1 - y0, p.topkey_t)
    s.label = "ds4_joint_topkey_v1"
    return s


def joint_rebates():
    """The cradle's half of both side joints - spline and top key. The cradle is the dock side."""
    out = []
    for x_seam, inward in ((p.ox0, +1.0), (p.ox1, -1.0)):
        out += spline_rebate(x_seam, inward, True) + topkey_rebate(x_seam, inward, True)
    return out


def make_spline():
    """The loose spline itself: a tall flat key bridging the seam, with a counterbored M3 clearance
    hole each side. Asymmetric - the short end goes into the dock side. Prints standing on the bed
    exactly as modelled, several to a plate, seconds each."""
    y0, y1 = p.spline_y
    ym = (y0 + y1) / 2
    s = Pos((p.spline_x_out - p.spline_x_in) / 2, ym, p.spline_t / 2) * \
        Box(p.spline_x_in + p.spline_x_out, y1 - y0, p.spline_t)
    for sx in (-p.spline_screw_in, +p.spline_screw_out):
        s = s - Pos(sx, ym, -1) * Cylinder(p.screw_clear_d / 2, p.spline_t + 2, align=MIN)
        s = s - Pos(sx, ym, -0.01) * Cylinder(p.screw_head_d / 2, p.screw_head_depth, align=MIN)
    s.label = "ds4_joint_spline_v1"
    return s


def keyboard_lip_cut():
    """v6: right-trapezoid undercut along the whole keyboard side (see kb_cut_* in dock_params).
    Drawn on the YZ plane (local x = world y, local y = world z) and extruded across the full width."""
    y_end = p.to_world(0, p.oy1, p.h_top)[1]          # the cradle's keyboard-end face
    y0 = y_end - p.kb_cut_len
    slope = (p.kb_cut_h_end - p.kb_cut_h_inner) / p.kb_cut_len
    pts = [(y0, -1.0), (y_end + 2, -1.0), (y_end + 2, p.kb_cut_h_end + 2 * slope), (y0, p.kb_cut_h_inner)]
    # 600, not 200: the extenders now reach x 304.5, and at 200 the outermost piece simply never
    # got the undercut - it came out with a solid full-height keyboard wall and 21 cm3 too much.
    return extrude(Plane.YZ * Polygon(*pts, align=None), amount=600, both=True)


def led_notch():
    """v8: notch for the charging board's LED end, in the wall facing the user at the pocket's right
    inside corner, straight through the wall. Its flat bottom is level with the pocket floor where
    the floor meets the wall (the floor plane dips below the desk in front of the pocket)."""
    x1 = p.pocket[2] - p.led_notch_x_shift          # v9: moved in from the right corner (owner)
    x0 = x1 - p.led_notch_w
    y_in = p.pocket[1] + 0.5                                   # just inside the pocket
    y_out = p.to_world(0, p.oy0, p.h_top)[1] - 1              # past the front face
    z0 = p.floor_z(p.pocket[1])
    return Pos((x0 + x1) / 2, (y_out + y_in) / 2, z0 + p.led_notch_h / 2) * Box(x1 - x0, y_in - y_out, p.led_notch_h)


def _above_lip_curve(curve, z_base):
    """Solid covering everything ABOVE a lip curve given in plate-local (P y, z) points, with the
    plate's underside at P z = z_base. Past the curve's tip it runs on flat."""
    pts2 = [(y, z_base + z) for y, z in curve]
    y1, z1 = p.oy1 + 30, p.h_top + 40
    pts2 = pts2 + [(y1, pts2[-1][1]), (y1, z1), (pts2[0][0], z1)]
    return p.P * extrude(Plane.YZ * Polygon(*pts2, align=None), amount=800, both=True)


def plate_lip_clearance():
    """Room for the plate's curved keyboard end: everything above the lip's UNDERSIDE, from
    lip_y_start on, is cut away so the cradle stays clear of it. v8 did this as a box minus a
    cylinder, which only works for one radius; v9's curve tightens as it turns, so the cut is
    built straight from the underside points."""
    if not p.lip:
        return []
    return [_above_lip_curve(p.lip_inner(48), p.h_top)]


def top_surface_clip():
    """Everything above the face plate's TOP surface. The extenders carry the plate's shape in
    their own envelope, so they must be trimmed to the lip's OUTER curve, not its underside -
    using plate_lip_clearance() on them cuts the lip clean off, which is exactly what it did on
    the first v10 build (their lip vanished and they came out 0.33 mm shorter than the dock)."""
    if not p.lip:
        return []
    return [_above_lip_curve([(y, z) for y, z, _ in p.lip_curve(48)], p.h_top)]


def make_cradle():
    c = body() - pocket()
    for cut in screw_pilots() + [finger_notch(), connector_channel(), bottom_slot(), back_slot()] + usb_bay() + dowel_holes():
        c = c - cut
    c = c - keyboard_lip_cut()
    # v10: the hook goes on AFTER the undercut (which would eat its leg) but BEFORE the plate-lip
    # clearance, so the clearance still trims the arm's top flush under the face plate's lip.
    for bx0, bx1 in hook_bands():
        hk = keyboard_hook(bx0, bx1, p.h_top)
        if hk is not None:
            c = c + hk
    for cut in [led_notch()] + plate_lip_clearance():
        c = c - cut
    for s in joint_rebates():
        c = c - s
    return c


def gen_step():
    cradle = make_cradle()
    cradle.label = "ds4_cradle"
    return cradle
