"""DS4 dock: shared parameters and frames for the build123d parts (faceplate.py, cradle.py,
dock_fit.py). Units mm. Supersedes ds4_dock.scad for the face plate and the cradle (2026-09-27).

World frame W: the table is z = 0, x right, y toward the keyboard, z up.
Part frame P (the board and the face plate): origin = PS button centre on the pocket floor (the
board's back), x right, y up the slope toward the keyboard, z out of the board face. P is W tilted
`tilt` degrees about x, pivoting on the user-side pocket edge line (y = y_cut, z = floor_h).
"""
import math

from build123d import Pos, Rot

# ---- the part: cut-down DS4 midframe + board, a rectangle (owner's 1:1 tracing) ----------
body_w, body_h = 130.0, 55.0
body_bottom = -11.0        # bottom edge relative to the PS button centre
body_r = 2.0               # corner radius of the rectangle
pocket_clear = 0.5         # per side
stack_h = 15.0             # midframe front face -> rearmost point on the board. ASSUMED: measure it
                           # cradle v11 (2026-10-12, owner): 15 (was 14). Screwed down, the face
                           # plate bowed UPWARDS in the middle - the board + touchpad stack was
                           # still bottoming out against it. +1 mm of pocket depth and nothing
                           # else: the rim rises 1 mm in P, so the walls grow 1 mm, the pilots keep
                           # their depth below the rim, and plate v9 fits unchanged. The extenders
                           # read h_top too, so they stay flush with no extra change.
                           # cradle v5 (2026-10-05): 14, walls 2 mm taller than v4 (floor unchanged)
                           # v4 (2026-10-04): 12, walls 1 mm taller than v3 (floor unchanged)
                           # v3 (2026-10-03): 11 (was 14), walls 3 mm lower at the owner's request

# ---- face plate --------------------------------------------------------------------------
plate_t = 1.6              # v3 (2026-09-27): thinner at the owner's request (v1/v2: 2.5)
plate_gap = 0.6            # midframe face -> plate underside (the button pads sit here)
hole_clear = 0.8           # added to every hole diameter / width
plate_screw = 4.4          # M3 with ~0.7 mm float each way (plates v1-v3)
# plate v6: owner's spec - 2 mm through hole, 4 mm head recess halfway through, from the top face
plate_hole_d, plate_cbore_d, plate_cbore_depth = 2.0, 4.0, 0.8
plate_hole_skin = 0.2      # plate v8: printed upside down, so a one-layer skin closes each 2 mm hole at the
                           # bottom of its recess (prints as a small bridge, no support); poke it through
holes_dx, holes_dy = 0.0, 0.0
touchpad_c, touchpad_wh = (-0.2, 26.0), (52.4, 22.0)
tp_notch_drop = 2.0        # plate v7: touchpad opening's bottom edge 2 mm lower (y 12.6, was 14.6)
stick_l, stick_r, stick_d = (-25.2, -2.5), (24.8, -2.5), 18.6   # v2: 3 mm lower (v1 plate fit); plate v7: 2 mm lower again
stick_travel = 2.6         # extra on the stick holes; plate v6: 2.6 (was 0.6), holes 22.0 (were 20.0)
ps, ps_d = (-0.2, -0.2), 8.0
btn_cross, btn_triangle = (48.6, 10.1), (48.6, 31.3)
btn_circle, btn_square = (60.2, 20.5), (36.9, 19.9)
face_wh = (10.4, 8.0)
dpad_c, dpad_arm, dpad_w = (-49.0, 21.5), 7.5, 9.2
dpad_grow = 0.5            # v3: every d-pad edge 0.5 mm further out, on top of hole_clear
share, options = (-32.1, 34.1), (32.8, 34.1)   # plate v4: 2 mm lower (was y 35.1); plate v7: 1 mm up; plate v8: Options 1 mm right
# plate v5: Share/Options are elongated ovals (stadium slots), not ellipses, and bigger.
# Overall hole size INCLUDING clearance; long axis along y. ASSUMED - measure the buttons.
so_slot_w, so_slot_len, so_tilt = 6.6, 11.0, 0.0   # plate v7: 6.6 x 11.0 (v6 7.0 x 11.0, v5 6.0 x 10.0)
# Plate styles (2026-10-21). "palm" is the printed plate v9: the d-pad, the four face buttons and
# the PS button are filled, so the right-hand side is a palm rest. "full" opens every control for a
# board that keeps its buttons, with the v3 plate's hole geometry (btn_*, face_wh, dpad_*, ps, ps_d).
plate_style = "palm"       # "palm" | "full"; variants.py builds both

# ---- pose --------------------------------------------------------------------------------
tilt = 17.0                # degrees; the face rises toward the keyboard. v3: 10 (was 15) for a lower base;
                           # cradle v8: 14.5, the keyboard end of the floor 3.5 mm higher relative to the user end
                           # cradle v9: 17.0, a bit steeper again (owner)
floor_h = 2.0              # pocket floor height above the table on the pivot line y = y_cut
                           # cradle v10 (owner, 2026-10-08): 2.0 - "1 mm taller from the base". This one
                           # number raises the cradle AND the extenders, since both drop their top plane
                           # straight to the table; the face plate is unaffected because it is built in P
                           # relative to the rim, so plate v9 does NOT need reprinting.
                           # cradle v8: 1.0 (was 1.6) so the steeper tilt costs less height; ~0.9 mm at the pocket edge
                           # v2 (2026-10-02): 1.6 (was 3.0), as low as the floor can print

# ---- cradle ------------------------------------------------------------------------------
wall, rim, corner_r = 3.0, 6.0, 4.0
pilot_d, pilot_depth = 2.0, 10.0      # pilots, blind, square to the plate; cradle v6: 2.0 (was 2.6 for M3) to match the plate holes
notch_d = 22.0                        # finger notch in the user-side wall: v3 a square-bottomed slot this wide, down to the floor
beyond_plate = 3.5                    # v2: the cradle ends this far past the plate's keyboard edge;
                                      # v5: 3.5 (was 2.5) so the raised Share/Options slots keep 1.3 mm of plate above them;
                                      # no wall on the keyboard side, the pocket runs out open there
# Channel in the pocket floor for the charging-board ribbon connector on the board's back, so the
# board lies flush. Runs the full pocket length out of the open keyboard end; goes through to the
# table where the floor is thinner than it. v3: 30..40 mm right of the PS button (owner).
chan_x = 35.0                         # channel centre, P x
chan_w = 10.0                         # spans P x 30..40
chan_d = 5.0                          # depth below the pocket floor, square to it (ribbon connector)
chan_y0_shift = 10.0                  # cradle v5: channel starts 10 mm further from the user edge (P y)
# cradle v5: the channel's opening in the underside, moved 10 mm toward the keyboard. v4's opening
# (where the channel broke through the 1.5 mm floor) ran W y -11.1..9.1; now an explicit through-slot.
bottom_slot_y = (-1.1, 19.1)          # W y range, same x range as the channel
back_slot_x1 = 45.0                   # cradle v5: channel exit in the keyboard-end face runs to x 45 (was 40)
# cradle v6: undercut along the whole keyboard side so the back of the dock overhangs the K70's
# front lip. Side profile is a right trapezoid: 14 mm along the desk, 10 mm tall at its inner
# (user-side) edge, 18 mm tall at the keyboard-end face, straight top (~29.7 deg). Floor, bay and
# channel inside it are removed; the side rims above it stay as floating arms.
kb_cut_len, kb_cut_h_inner, kb_cut_h_end = 14.0, 10.0, 18.0
# cradle v10 (owner 2026-10-08): the arm above that undercut no longer stops at the end face. It
# carries on hook_ext further along the undercut's OWN top line (so, at the same angle), and the
# last hook_t of that extension drops hook_drop perpendicular to that line, hooking the keyboard's
# front lip. One continuous arm across the cradle and both extenders.
# Built to the traced K70 profile (measurements.md: ~10 mm vertical wall, chamfer ~25-30 deg, top
# at 18-20 mm). That profile is explicitly UNMEASURED - kb_profile_clash() reports the overlap.
hook = True
hook_ext, hook_t, hook_drop = 2.0, 2.0, 4.0
# v11 (owner 2026-10-12): NOT a bar all the way across the cradle - it was in the way of the board
# and the touchpad. It is in the way because the board overhangs the keyboard end face by 3.6 mm
# (the pocket runs out open there), and the hook's 2 mm extension lives in exactly that space: at
# x = 0 it lands at P y 38-41, z 3-11, i.e. inside the board.
# That same fact caps how wide the hook can be: at the end face everything inboard of the side
# walls is pocket, so a band wider than the wall would have nothing to hang off and would print as
# a bar bridging 131 mm in mid-air behind the board. So on the cradle the hook sits on the two side
# walls only. The extenders are solid and keep it over their whole length, so the assembled dock
# still has one continuous hooked arm - 69 mm on the left, 239 mm on the right - with the middle
# 131 mm left clear for the board and the touchpad.
hook_side_w = wall + rim              # 9.0, measured in from each outer face. 0 = full width.
# K70 front edge as traced, for the clash check only - never part of a printed body
kb_wall_h, kb_cham_angle, kb_top_h = 10.0, 30.0, 18.0

# ---- cradle <-> extender joint (v10 / extenders v2) ----------------------------------------
# The two 6.2 mm pins were far too wobbly: a pair of small round pins in a flat butt joint resists
# almost nothing in twist. Replaced by a flat tongue on the cradle's side face that slides into a
# rebate cut UP INTO the extender's underside, plus two M3 screws driven up through the tongue.
# The large flat contact kills the twist; the screws stop the two parts separating. Nothing is
# visible on the top face and the screw heads sit in counterbores against the desk.
# Print note: the rebate is open downwards, so face-down it opens towards the sky - no overhang.
# The tongue is a SEPARATE part, not moulded onto either side. A tongue grown off the cradle made
# it 185 mm wide, which does not fit the 180 mm bed; grown off the extender instead it would be an
# 18 mm cantilever hanging in mid-air in a face-down print. As a loose spline both parts get only
# a rebate, so neither grows and neither gains an overhang: the cradle's rebate opens at the bed
# (its roof bridges 18 mm, routine) and the extender's opens towards the sky.
# WHERE it can go is forced by the cradle. Under the pocket the floor is only 1.8-3.1 mm thick, so
# a rebate there breaks straight into the pocket; behind W y 20.4 the keyboard undercut has removed
# the base entirely. The only full-depth material is the FRONT wall, W y about -23.9 to -12, solid
# from the desk to the rim. So the joint lives there - and it is tall rather than wide, because
# height is what stops the extender hinging up at its far end.
# It is also asymmetric: only 9 mm reaches into the dock side, which keeps that half inside the
# 9 mm side wall (x 65.5..74.5) and clear of the pocket; the extender side is solid, so it takes 20.
joint_spline = True
spline_x_in = 9.0          # into the part on the dock side of the seam
spline_x_out = 20.0        # into the part on the outboard side
spline_t = 8.0             # height (z), measured up from the underside
spline_y = (-22.0, -12.5)  # W y span - inside the cradle's solid front wall
spline_clear = 0.25        # per-side clearance of the rebates around the spline
spline_screw_in = 4.5      # M3 into the dock-side part, this far from the seam
spline_screw_out = 10.0    # M3 into the outboard part, this far from the seam
# v11 (owner): the screw holes in the spline were too big. The 6.2 counterbore left only 1.65 mm of
# key each side of it and looked it; 5.6 still swallows a standard M3 cheese or pan head (5.5 across)
# and 2.2 deep sinks a 3 mm head below the face. The pilot goes 2.5 -> 2.4, the tight end of what an
# M3 self-tapper wants in PETG, for more bite without splitting the wall.
screw_clear_d = 3.2        # M3 clearance through the spline (v10: 3.4)
screw_head_d, screw_head_depth = 5.6, 2.2   # counterbore in the spline's underside (v10: 6.2 x 3.0)
screw_pilot_d, screw_pilot_depth = 2.4, 9.0  # self-tapper pilot up into the extender (v10: 2.5)

# ---- second connector per seam: the top key (v11) -------------------------------------------
# Owner 2026-10-12: two connectors between each pair of pieces, not one. The spline above sits in
# the front wall at z 0..8, so on its own it fights a wrist pressing down on the far end of a 230 mm
# arm with an 8 mm lever and two screws. A second key up at the rim turns that into a proper couple
# - tension at the top, compression at the bottom, 17 mm apart as built - and it stays invisible:
# lies in a shallow rebate milled into the rim's top face and the face plate screws down over it,
# which is also what traps it, so it needs no screw of its own.
# Printed bottom-down - which the split base now is - that rebate opens straight at the sky: no
# overhang, no bridge. Defined in P so the key is parallel to the plate and prints as a flat bar.
# P y 2..14 puts it between the two plate screw rows (-16.5 and 34.9) and, on the right, in front of
# the charging bay (W y 11.4).
topkey = True
topkey_y = (2.0, 14.0)     # P y span - 12 mm wide
topkey_t = 3.0             # thickness, measured down from the rim
topkey_x_in = 7.0          # into the dock-side part: leaves 2 mm of pocket wall standing full height
topkey_x_out = 14.0        # into the outboard part, which is solid there
topkey_clear = 0.2         # per side; the rebate is also this much DEEPER than the key is thick, so
                           # the key can never stand proud and lift the face plate off its rim
# cradle v8: notch for the charging board's LED end in the wall facing the user, right inside corner,
# through the wall, bottom level with the pocket floor (owner: 10 mm long, 3 mm thick)
led_notch_w, led_notch_h = 10.0, 3.0
led_notch_x_shift = 5.0               # cradle v9: notch moved this far left, in from the pocket's right corner (owner)
# plate v8: the plate's keyboard end curves down like the touchpad's top edge. Measured on the Wesk
# Touchpad scan (centre section, 2026-10-06): flat top for ~21 mm (= the 22 mm window), then a curve
# dropping 5.6 mm over 7.6 mm - close to an 8 mm radius arc through ~73 deg. The arc starts at the
# top of the touchpad window; ASSUMED: the plate's top is flush with the touchpad's flat top.
# plate v9 (owner): the curve has to get SHARPER as it goes and finish as a full 90 deg turn, so the
# end points straight down. It is no longer one radius: the radius shrinks linearly with the turn
# angle, from lip_R at the start (= the touchpad's own 8 mm, so they stay flush where they meet) to
# lip_R_end at the tip. lip_R_end must stay > plate_t or the underside arc inverts.
lip = True
lip_R, lip_R_end, lip_angle = 8.0, 3.0, 90.0
lip_y_start = touchpad_c[1] + touchpad_wh[1] / 2      # 37.0, top of the touchpad window (P y)
# v3: the charging board (JDS-055) bay is back (v1 had it): a cavity under the pocket floor at the
# right of the keyboard end, open up into the pocket (the board bridges it) and joined by the
# channel, with the port hole through the right side face. Board size still ASSUMED.
jds_wh = (33.0, 21.0)                 # bay x, y
jds_z0 = 1.0                          # bay bottom above the table
jds_end_skin = 2.0                    # solid between the bay and the cradle's keyboard end face
cable_w = 9.0                         # port hole width (along y) in the right face
cable_notch_w = 6.0                   # cradle v7: what is left of the port hole after the keyboard-lip cut
                                      # is the charging-cable notch; at least this wide (cable ~3-4.5 mm)
dowels = False                        # v10: RETIRED - the pins were too wobbly, see joint_tongue below.
                                      # Kept as a switch rather than deleted; the holes were an
                                      # owner-specified feature from v1 to v9.
# holes for the wrist-rest extension (owner needed them v1-v9). Teardrop-shaped
                                      # since cradle v7 so PETG prints them without supports inside.
dowel_teardrop = True                 # 45 deg pointed top over the round hole; a round dowel still fits
dowel_d, dowel_depth, dowel_z = 6.2, 7.5, 9.0
dowel_ys = (-10.0, 14.0)              # W y of the wing dowels; clear of the USB bay on the right

# ---- wrist extenders (v1, 2026-10-07) ------------------------------------------------------
# Solid wrist rests that bolt to the cradle's two side faces with loose pins through the existing
# dowel holes. Same outer envelope as the assembled dock (cradle body + face plate on top), so the
# top is flush with the plate's surface and the back carries the same 90 deg lip and the same
# keyboard undercut. Owner 2026-10-07: left 60 mm, right 80 mm.
# v2 (owner 2026-10-08): left 60, right 230 - and 60 + 149 + 230 = 439, which is the K70's own
# width (437). The right one cannot fit a 180 mm bed, so it prints as two 115 mm halves that join
# with the same tongue joint as the cradle.
ext_len_left = 60.0
ext_len_right_total = 230.0
ext_right_split = 2                   # number of pieces the right extender prints in
# Cable channel, now through BOTH extenders and sized so a micro-USB PLUG threads end to end
# (owner's choice): a bare plug shell is ~6.9 x 1.8, the moulding on a typical cable ~11 x 6.
# The CRADLE's wall is what limits this, not the extenders (those are solid, so the channel could
# be any size there). In the cradle the opening has to fit between the desk and the pocket floor,
# which slopes up at 17 deg, and it has to stay in front of the keyboard undercut, which eats
# everything past W y 20.4. That leaves a window about 12.5 wide and 6 tall at its tightest -
# measure your plug's moulding against that before relying on threading it through.
ext_cable_y = (7.0, 19.5)             # W y - 12.5 wide, ends 0.9 before the undercut
ext_cable_z0, ext_cable_z1 = 0.8, 6.8  # 6.0 tall, on a 0.8 mm floor
ext_cable_gable = 1.4                 # roof peaks this much above z1 at mid-width, so no bridge

# ---- extenders v3: base + its own face plate (owner 2026-10-12) ------------------------------
# v2 was one solid whose top surface WAS the plate's surface. Printed face down it came out smooth
# instead of carrying the textured sheet's finish, and it did not sit flush with the dock.
# v3 splits every piece the way the dock itself is built: a BASE whose top is the rim plane, plus a
# flat FACE PLATE of its own that screws down onto it. The base is cradle.body() over that x range
# and the plate is the face plate's outline and lip over that x range - both straight from the same
# parameters as the real parts - so matching is structural rather than a matter of care. The plate
# then prints face down on the textured sheet exactly like plate v9 (same finish, guaranteed) and
# the base prints bottom-down, which costs no support under the wrist surface at all; v2's face-down
# print needed 1700-2400 s of it. Only the keyboard undercut still needs support, as on the cradle.
ext_plate = True
ext_screw_inset = 8.0      # first and last plate screw this far in from the piece's ends
ext_screw_pitch = 60.0     # intermediate pairs added so no span between screws exceeds this

# ---- derived -----------------------------------------------------------------------------
# Everything in this block is computed from the parameters above by _derive(). variants.py and
# checks.py switch floor_h / hook / plate_style through configure(), which recomputes the block, so
# a module that does `import dock_params as p` and reads p.P (etc.) at call time always sees the
# active variant. Never `from dock_params import P` - that copy would go stale.
_DERIVED = ("y_cut", "ox0", "ox1", "oy0", "plate_top", "oy1", "open_y", "h_top", "screws",
            "ext_screw_ys", "pocket", "P")


def _derive():
    global y_cut, ox0, ox1, oy0, plate_top, oy1, open_y, h_top, screws, ext_screw_ys, pocket, P
    y_cut = body_bottom
    ox0 = -body_w / 2 - pocket_clear - wall - rim                  # -74.5
    ox1 = -ox0
    oy0 = y_cut - wall - rim                                       # -20.0 (P)
    # v2: was body top + clear + wall + rim = 53.5; now 2.5 past the plate edge (37.4) = 39.9
    plate_top = touchpad_c[1] + holes_dy + (touchpad_wh[1] + hole_clear) / 2   # 37.4: top of the touchpad hole
    oy1 = plate_top + beyond_plate                                 #  39.9 (P)
    open_y = plate_top - holes_dy + 1                              # openings run past the plate edge
    h_top = stack_h + plate_gap                                    # rim = plate underside, P z
    screws = [(ox0 + 3.2, oy0 + 3.5), (ox1 - 3.2, oy0 + 3.5),
              (ox0 + 3.2, plate_top - 3.5), (ox1 - 3.2, plate_top - 3.5)]
    # v11: the extender plates use the SAME two rows, so the dock's screw line runs straight across
    ext_screw_ys = (oy0 + 3.5, plate_top - 3.5)
    pocket = (-body_w / 2 - pocket_clear, body_bottom - pocket_clear,
              body_w / 2 + pocket_clear, body_bottom + body_h + pocket_clear)   # P x0, y0, x1, y1
    P = Pos(0, y_cut, floor_h) * Rot(X=tilt) * Pos(0, -y_cut, 0)   # P -> W


_derive()


def configure(**overrides):
    """Set parameters by name (floor_h=1.0, hook=False, plate_style="full", ...) and recompute the
    derived block. The module's own values are the printed configuration: floor_h 2.0 ("std"), hook
    True, plate_style "palm". Only existing parameters can be set; derived names are refused."""
    g = globals()
    for k, v in overrides.items():
        if k.startswith("_") or k in _DERIVED or k not in g or callable(g[k]) or k == "math":
            raise KeyError(f"{k!r} is not a settable dock parameter")
        g[k] = v
    _derive()


def variant():
    """The three parameters the STL matrix varies, as currently configured."""
    return {"floor_h": floor_h, "hook": hook, "plate_style": plate_style}


def to_world(x, y, z):
    """P point -> W point (plain math, for checks and derived W positions)."""
    c, s = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
    return (x, y_cut + (y - y_cut) * c - z * s, floor_h + (y - y_cut) * s + z * c)


def floor_z(yw):
    """W height of the pocket floor plane at W y."""
    return floor_h + (yw - y_cut) * math.tan(math.radians(tilt))


def lip_curve(n=48):
    """plate v9: the lip's TOP surface as (P y, P z, turn angle) points. Starts at
    (lip_y_start, plate_t) tangent to the flat top and turns down through lip_angle. The radius
    shrinks linearly with the turn angle, lip_R -> lip_R_end, so the curve gets sharper as it goes
    (a constant radius when the two are equal). Closed form of the arc integral for R(a) linear:
        dy = int R(a) cos a da,  dz = int R(a) sin a da.
    """
    A = math.radians(lip_angle)
    k = (lip_R_end - lip_R) / A if A else 0.0
    pts = []
    for i in range(n + 1):
        a = A * i / n
        dy = lip_R * math.sin(a) + k * (a * math.sin(a) + math.cos(a) - 1.0)
        dz = lip_R * (1.0 - math.cos(a)) + k * (math.sin(a) - a * math.cos(a))
        pts.append((lip_y_start + dy, plate_t - dz, a))
    return pts


def lip_inner(n=48):
    """The lip's UNDERSIDE: the top surface offset plate_t toward the centre of curvature,
    i.e. along (-sin a, -cos a). Starts at (lip_y_start, 0), the plate's underside."""
    return [(y - plate_t * math.sin(a), z - plate_t * math.cos(a)) for y, z, a in lip_curve(n)]
