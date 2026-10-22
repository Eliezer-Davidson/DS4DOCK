"""DS4 dock analogue-stick caps v3 (build123d). Owner 2026-10-12.

v1 was a 8.0 mm tall boss-and-disc. v2 is as short as the 4 mm socket allows and adds the skirt:
the whole cap is now a bell. Its outer surface is a spherical dome sweeping from skirt_d at the
bed up to cap_d at the top, hollow underneath, so it hangs over the stick opening in the face
plate and hides the mechanism without touching the plate as the stick tilts.

Shape, bottom to top (total height TOP = 5.2; v2 was 6.0, v1 8.0):
  z 0.0 - 4.0   the socket, open at the bottom, inside a d 7.0 boss
  z 0.0 - 4.0   the hollow under the skirt, an annulus between the boss and the dome wall
  z 0.0 - 5.2   the dome itself: d 16 at the bed closing to d 12 at the top
  z 4.0 - 5.2   the solid cap: a raised rim, a thumb dish, and twelve flutes round the edge

At d 12 over 5.2 mm the dome is nearly a shallow spherical cap: the solved sphere centre sits 0.09
below the bed, which keeps the surface shrinking monotonically from the first layer up (a centre
ABOVE the bed would bulge the first half-millimetre outward and need support).

Prints socket-down exactly as modelled and needs NO support: the dome tapers inwards all the way
up, the hollow and the socket both open at the bed, and the dish faces the sky.

TWO GUESSES, both parameters:
  * socket size - make_set() prints three pairs, each a step looser, keep the pair that grips.
  * skirt_d - the skirt swings as the stick tilts, and how far depends on how deep the stick's
    pivot sits, which has never been measured. swing_report() does the arithmetic for whatever
    pivot depth and tilt you give it. At d 16 in the plate's d 22 opening it covers most of the
    hole but not all of it; going wider covers more and fouls the plate sooner.
    python cad/stick_cap.py                   # swing_report() + the six-cap test set into cad/out/
    python cad/variants.py --only stick_cap   # stl/caps/stick_cap_{tight,nominal,loose}.stl
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build123d import Align, Box, Cylinder, Pos, Rot, Sphere  # noqa: E402

MIN = (Align.CENTER, Align.CENTER, Align.MIN)

socket_wl = (3.0, 3.5)        # owner's post size: 3 wide (x), 3.5 long (y)
socket_depth = 4.0            # how far the post goes in - this sets the minimum height
boss_d = 7.0                  # keeps >= 1.2 mm of wall at the socket's corners
# v3 (owner 2026-10-12): shorter and wider. The socket stays 4 mm deep - that is the grip on the
# stick and it was the owner's own spec - so the only height left to give back is the cap above it:
# 6.0 -> 5.2 by thinning the solid cap to 1.2 and the dish to 0.35, which still leaves 0.85 mm of
# material over the socket. Wider is free: the top goes 10 -> 12 and the dish 4.0 -> 4.5, so the
# thumb gets a broad shallow pad instead of a narrow crown. The skirt stays at 16 because that is
# the swing limit in plate v9's d 22 opening - see swing_report(); at 16 the edge reaches r 10.9 at
# 20 deg against a limit of 11.0, so there is nothing spare.
TOP = 5.2                     # total height (v2: 6.0)
cap_d = 12.0                  # diameter at the top (v2: 10.0)
skirt_d = 16.0                # diameter at the bottom edge of the skirt - at the swing limit
skirt_wall = 1.2              # dome wall thickness
cap_t = 1.2                   # solid thickness at the top, above the hollow (v2: 1.6)
dish_r, dish_depth = 4.5, 0.35  # thumb dish inside the rim; rim ring is r 4.5 -> 6.0 (v2: 4.0/0.6)
flutes, flute_r = 12, 0.7     # vertical scallops round the edge, for grip
fits = (0.0, 0.25, 0.5)       # socket oversize steps to print, 2 caps of each

plate_hole_d = 22.0           # the stick opening in face plate v9, for the swing check


def _dome_sphere(outer=True):
    """The sphere whose surface is the dome: passes through (skirt_d/2, 0) and (cap_d/2, TOP)."""
    r0, r1 = skirt_d / 2, cap_d / 2
    # r0^2 + zc^2 = r1^2 + (TOP - zc)^2  ->  solve for zc
    zc = (r1 ** 2 + TOP ** 2 - r0 ** 2) / (2 * TOP)
    R = math.hypot(r0, zc)
    return (R, zc) if outer else (R - skirt_wall, zc)


def make_cap(clear=0.0):
    """One cap. `clear` is added to both socket dimensions (total, not per side)."""
    R, zc = _dome_sphere(True)
    Ri, _ = _dome_sphere(False)

    dome = Pos(0, 0, zc) * Sphere(R)
    dome = dome & Pos(0, 0, TOP / 2) * Box(4 * skirt_d, 4 * skirt_d, TOP)
    hollow = Pos(0, 0, zc) * Sphere(Ri)
    hollow = hollow & Pos(0, 0, (TOP - cap_t) / 2 - 0.5) * Box(4 * skirt_d, 4 * skirt_d, TOP - cap_t + 1.0)
    body = (dome - hollow) + Cylinder(boss_d / 2, TOP, align=MIN)

    w, length = socket_wl[0] + clear, socket_wl[1] + clear
    body = body - Box(w, length, socket_depth, align=MIN)

    Rd = (dish_r ** 2 + dish_depth ** 2) / (2 * dish_depth)
    # The dish sphere is turned so its poles lie on the y axis. The dish is a small cap around the
    # sphere's lowest point, and with a pole sitting there the mesher put one degenerate (zero-area)
    # triangle into every STL; same geometry, cleaner file.
    body = body - Pos(0, 0, TOP - dish_depth + Rd) * Rot(X=90) * Sphere(Rd)

    for i in range(flutes):
        a = 2 * math.pi * i / flutes
        body = body - Pos((cap_d / 2) * math.cos(a), (cap_d / 2) * math.sin(a),
                          TOP - cap_t - 0.4) * Cylinder(flute_r, cap_t + 0.8, align=MIN)
    body.label = f"ds4_stick_cap_v3_{clear:.2f}"
    return body


def swing_report(pivots=(8.0, 10.0, 12.0, 14.0), tilts=(15.0, 20.0, 25.0)):
    """How close the skirt's bottom edge comes to the face plate's stick opening as the stick
    tilts. The edge sits at radius skirt_d/2; pivoting by `tilt` about a point `pivot` mm below it
    swings it out to r*cos(t) + pivot*sin(t). Must stay inside plate_hole_d/2."""
    lim = plate_hole_d / 2
    r = skirt_d / 2
    print(f"skirt edge r {r:.1f} in a d {plate_hole_d} opening (limit r {lim:.1f})")
    print(f"{'pivot below':>12s} " + "".join(f"{t:>9.0f} deg" for t in tilts))
    for d in pivots:
        row = []
        for t in tilts:
            a = math.radians(t)
            row.append(r * math.cos(a) + d * math.sin(a))
        print(f"{d:10.1f} mm " + "".join(f"{v:>9.2f}{'!' if v > lim else ' '}" for v in row))
    print("  ! = the skirt would touch the plate at that tilt. Lower skirt_d if yours does.")


def make_set():
    """Two caps of each fit, laid out on the bed: nominal pair first, loosest pair last."""
    out = None
    pitch = skirt_d + 4.0
    for col, clear in enumerate(fits):
        for row in range(2):
            c = Pos((col - (len(fits) - 1) / 2) * pitch, (row - 0.5) * pitch, 0) * make_cap(clear)
            out = c if out is None else out + c
    out.label = "ds4_stick_caps_v3_set"
    return out


OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")   # scratch, gitignored


def export_all(out=None):
    """Scratch export: the six-cap test set and one nominal cap, STL + STEP, into cad/out/ next to
    this file unless `out` is given. The shipped single caps are built by variants.py."""
    from build123d import export_step, export_stl
    out = out or OUT_DIR
    os.makedirs(out, exist_ok=True)
    s = make_set()
    export_stl(s, os.path.join(out, "stick_caps_v3_set.stl"))
    one = make_cap(0.0)
    export_stl(one, os.path.join(out, "stick_cap_v3.stl"))
    export_step(one, os.path.join(out, "stick_cap_v3.step"))
    return s, one


if __name__ == "__main__":
    swing_report()
    export_all()
    print(f"wrote stick_caps_v3_set.stl, stick_cap_v3.stl, stick_cap_v3.step to {OUT_DIR}")
