#!/usr/bin/env python3
"""
render_map.py - draw a control map (mapping.json) on a drawing of the dock's face plate.

    python tools/render_map.py mapping.json docs/images/map.svg [--mode bare|full]

Writes a self-contained SVG: the face plate to scale, seen from above with the keyboard edge at
the top (the way you look down at the dock), every bound input called out with its bindings in
two columns (normal layer in grey, the Fn layer in the one accent colour), a legend, no external
fonts, no background - mid greys that read on both a light and a dark page. `--mode bare` (the
default) is this project's hardware on the printed "palm" plate: the touchpad and its click,
the two sticks and their clicks, Share and Options. The controls that went with the shell are
drawn as faint dashed ghosts where the "full" plate would open them, with no callout. `--mode
full` is the full plate: every control open and labelled. L1, R1, L2 and R2 are four dashed
tabs just beyond the keyboard edge - that edge faces the keyboard in every dock variant, so
they are out of reach docked; they stay in the drawing for a complete, undocked controller.

The geometry lives here and nowhere else: tools/mapping_editor.py imports build_scene() for
its canvas, so the picture you click on in the editor and the picture in the README are the
same drawing. A scene is a list of plain primitives (poly / oval / line / text) in one
coordinate space, and each backend - to_svg() here, the tkinter canvas in the editor - just
draws them. The plate's dimensions are copied from cad/dock_params.py (see the block below);
they are not imported because that module imports build123d and this tool must run anywhere.

Standard library only. Python >= 3.11.
"""

import argparse
import math
import os
import sys
from xml.sax.saxutils import escape

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import ds4_dock  # noqa: E402  - the single source of truth for names, actions and validation

# ------------------------------------------------------------------ what exists

MODES = ("bare", "full")
# The five buttons that physically exist on the bare board, as canvas elements. A stick element
# is the stick and its click; "Pad" is the touchpad surface and its click.
BARE_ELEMENTS = ("Pad", "LS", "RS", "Share", "Options")
# Every element the drawing has, and the mapper button each one stands for (the d-pad arms and
# face buttons are their own elements).
ELEMENTS = ("Pad", "LS", "RS", "Share", "Options", "PS",
            "Triangle", "Circle", "Cross", "Square",
            "dpad_N", "dpad_S", "dpad_W", "dpad_E",
            "L1", "R1", "L2", "R2")
ELEMENT_BUTTON = {"LS": "L3", "RS": "R3"}          # element -> the button it clicks as
BUTTON_ELEMENT = {"L3": "LS", "R3": "RS"}          # and back; every other name is itself
ELEMENT_TITLE = {"Pad": "Touchpad", "LS": "Left stick", "RS": "Right stick", "PS": "PS",
                 "dpad_N": "D-pad up", "dpad_S": "D-pad down", "dpad_W": "D-pad left",
                 "dpad_E": "D-pad right"}
ARROW = {"N": "↑", "S": "↓", "W": "←", "E": "→"}
# The shoulder buttons sit on the board's far edge, the one that faces the keyboard in every
# dock variant. They are drawn as tabs beyond the keyboard edge and carry this note.
KEYBOARD_EDGE = ("L1", "R1", "L2", "R2")
KEYBOARD_EDGE_NOTE = ("This edge faces the keyboard in every dock variant - unreachable in the dock. "
                      "Kept for a full, undocked controller.")
KEYBOARD_EDGE_ROW = "keyboard edge: unreachable in the dock"

# ------------------------------------------------------------------ pretty text

PRETTY_KEY = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "super": "Win", "enter": "Enter",
              "esc": "Esc", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
              "backspace": "Backspace", "space": "Space", "tab": "Tab", "insert": "Ins",
              "delete": "Del", "media_play_pause": "Play/Pause", "volume_up": "Vol+",
              "volume_down": "Vol−", "mute": "Mute", "pageup": "PgUp", "pagedown": "PgDn",
              "home": "Home", "end": "End"}
PRETTY_MOUSE = {"left": "Left click", "right": "Right click", "middle": "Middle click"}
PRETTY_ACTION = {"suspend": "Suspend injection", "cursor_centre": "Centre cursor"}


def pretty_key(spec):
    """'ctrl+k ctrl+left' -> 'Ctrl+K Ctrl+←'. Never raises: an invalid spec is shown as typed."""
    if not isinstance(spec, str):
        return str(spec)
    chords = []
    for chord in spec.lower().split():
        chords.append("+".join(PRETTY_KEY.get(k, k.upper() if len(k) <= 3 else k) for k in chord.split("+")))
    return " ".join(chords)


def pretty_binding(b):
    """A binding dict (or None) as the short text the callouts show."""
    if not b:
        return None
    if "key" in b:
        return pretty_key(b["key"])
    if "mouse" in b:
        return PRETTY_MOUSE.get(b["mouse"], str(b["mouse"]))
    name = b.get("action")
    return PRETTY_ACTION.get(name, str(name).replace("_", " "))


# ------------------------------------------------------------------ the face plate, in mm
#
# Part frame P of cad/dock_params.py: x across the plate (0 = the PS button), y up the slope
# toward the keyboard. The drawing keeps P and puts +y at the TOP of the page. Every number here
# is copied from cad/dock_params.py (the derived ones as its _derive() works them out) - it is
# not imported because that module imports build123d, and this tool must run anywhere.
MM = 4.0                                   # drawing units per millimetre

PLATE_X0, PLATE_X1 = -74.5, 74.5           # ox0, ox1 = -/+(body_w/2 + pocket_clear + wall + rim)
PLATE_Y0, PLATE_Y1 = -20.0, 39.9           # oy0 (the user's edge), oy1 (plate_top + beyond_plate)
PLATE_R = 4.0                              # corner_r
LIP_Y = 37.0                               # lip_y_start: the flat plate ends here and curls 90 deg
                                           # down over the cradle's keyboard end (plate v9's lip)
TOUCHPAD_C, TOUCHPAD_WH = (-0.2, 26.0), (52.4, 22.0)   # touchpad_c, touchpad_wh; open to the keyboard edge
STICKS = {"LS": (-25.2, -2.5), "RS": (24.8, -2.5)}    # stick_l, stick_r
STICK_HOLE_D = 22.0                        # stick_d + hole_clear + stick_travel = 18.6 + 0.8 + 2.6
CAP_D, CAP_TOP_D = 16.0, 12.0              # cad/stick_cap.py: the bell cap, d 16 at its skirt, d 12 on top
SHARE, OPTIONS = (-32.1, 34.1), (32.8, 34.1)           # share, options
SLOT_W, SLOT_LEN = 6.6, 11.0               # so_slot_w, so_slot_len: stadium slots, long axis along y
SCREWS = ((-71.3, -16.5), (71.3, -16.5), (-71.3, 33.9), (71.3, 33.9))   # screws: ox +-3.2, oy0 + 3.5, plate_top - 3.5
PS_C, PS_D = (-0.2, -0.2), 8.0             # ps, ps_d                                     (full plate only)
DPAD_C, DPAD_ARM, DPAD_W = (-49.0, 21.5), 7.5, 9.2     # dpad_c, dpad_arm, dpad_w          (full plate only)
FACE = {"Cross": (48.6, 10.1), "Triangle": (48.6, 31.3), "Circle": (60.2, 20.5), "Square": (36.9, 19.9)}
FACE_D = 10.4                              # btn_*, max(face_wh)                           (full plate only)
EXT_LEFT, EXT_RIGHT = 60.0, (115.0, 115.0)  # ext_len_left; ext_len_right_total in ext_right_split pieces
EXT_SCREW_INSET = 8.0                      # ext_screw_inset: the extender plates' first screw from the seam
STUB = 15.0                                # how much of each extender the drawing shows before a break line
KNEE_X = PLATE_X1 + 4.0                    # a side callout's leader turns horizontal here, over the stub
# The shoulder buttons: four dashed tabs just beyond the keyboard edge, L2/R2 behind L1/R1 as on
# the pad. x0, x1, y0, y1 in P mm - a schematic position, nothing on the plate is there.
TABS = {"L1": (-64.0, -40.0, 41.5, 46.0), "R1": (40.0, 64.0, 41.5, 46.0),
        "L2": (-62.0, -42.0, 47.5, 51.0), "R2": (42.0, 62.0, 47.5, 51.0)}
# the drawing's extent in mm: the plate with its two extender stubs, the tabs and a label above,
# a label below
X_MIN_MM, X_MAX_MM = PLATE_X0 - STUB, PLATE_X1 + STUB
Y_MIN_MM, Y_MAX_MM = PLATE_Y0 - 5.0, 57.0


# ------------------------------------------------------------------ geometry helpers

def round_corners(pts, r, steps=5):
    """Round the corners of a polygon with quadratic curves: `r` is one radius for every corner
    or a sequence with one per vertex (0 = leave that corner sharp)."""
    out = []
    n = len(pts)
    radii = list(r) if isinstance(r, (list, tuple)) else [r] * n
    for i, v in enumerate(pts):
        rv = radii[i]
        if rv <= 0:
            out.append(v)
            continue
        a, b = pts[i - 1], pts[(i + 1) % n]
        da = math.hypot(a[0] - v[0], a[1] - v[1]) or 1.0
        db = math.hypot(b[0] - v[0], b[1] - v[1]) or 1.0
        ra, rb = min(rv, da / 2), min(rv, db / 2)
        p_in = (v[0] + (a[0] - v[0]) * ra / da, v[1] + (a[1] - v[1]) * ra / da)
        p_out = (v[0] + (b[0] - v[0]) * rb / db, v[1] + (b[1] - v[1]) * rb / db)
        for s in range(steps + 1):
            t = s / steps
            out.append(((1 - t) ** 2 * p_in[0] + 2 * (1 - t) * t * v[0] + t ** 2 * p_out[0],
                        (1 - t) ** 2 * p_in[1] + 2 * (1 - t) * t * v[1] + t ** 2 * p_out[1]))
    return out


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def cross(cx, cy, half, w):
    """A plus-shaped polygon: arm half-length `half`, arm half-width `w`."""
    return [(cx - w, cy - half), (cx + w, cy - half), (cx + w, cy - w), (cx + half, cy - w),
            (cx + half, cy + w), (cx + w, cy + w), (cx + w, cy + half), (cx - w, cy + half),
            (cx - w, cy + w), (cx - half, cy + w), (cx - half, cy - w), (cx - w, cy - w)]


def stadium(cx, cy, w, length, n=8):
    """A slot `w` wide and `length` long end to end, its long axis along y: two half circles
    joined by straight sides (build123d's SlotOverall rotated 90 deg)."""
    r, h = w / 2, length / 2 - w / 2
    pts = []
    for i in range(n + 1):                      # the top half circle, left to right
        a = math.pi - math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + h + r * math.sin(a)))
    for i in range(n + 1):                      # the bottom one, right to left
        a = -math.pi * i / n
        pts.append((cx + r * math.cos(a), cy - h + r * math.sin(a)))
    return pts


def _touchpad_notch():
    """x0, x1, y0 of the touchpad opening; it runs out through the keyboard edge."""
    return (TOUCHPAD_C[0] - TOUCHPAD_WH[0] / 2, TOUCHPAD_C[0] + TOUCHPAD_WH[0] / 2,
            TOUCHPAD_C[1] - TOUCHPAD_WH[1] / 2)


def _plate_outline():
    """The plate seen from above: the rounded rectangle with the touchpad opening notched out of
    its keyboard edge (the opening is open there, so the touchpad's own curved edge clears it)."""
    nx0, nx1, ny = _touchpad_notch()
    pts = [(PLATE_X0, PLATE_Y0), (PLATE_X1, PLATE_Y0), (PLATE_X1, PLATE_Y1), (nx1, PLATE_Y1),
           (nx1, ny), (nx0, ny), (nx0, PLATE_Y1), (PLATE_X0, PLATE_Y1)]
    return round_corners(pts, [PLATE_R, PLATE_R, PLATE_R, 0, 0, 0, 0, PLATE_R], 6)


def _stub(side):
    """STUB mm of the extender next to the plate - the same outline and lip as the plate - ended
    by a zigzag break line, so the 439 mm of the assembled dock is implied without being drawn."""
    sgn = -1 if side == "L" else 1
    x_seam = PLATE_X0 if side == "L" else PLATE_X1
    x_end = x_seam + sgn * STUB
    teeth, amp = 8, 0.9
    pts = [(x_seam, PLATE_Y0), (x_seam, PLATE_Y1)]
    for i in range(teeth + 1):                  # down the outer end, top to bottom
        y = PLATE_Y1 - (PLATE_Y1 - PLATE_Y0) * i / teeth
        off = 0.0 if i in (0, teeth) else (amp if i % 2 else -amp)
        pts.append((x_end + sgn * off, y))
    return pts


# primitive constructors - everything the two backends know how to draw
def P(pts, cls, **kw):
    d = {"kind": "poly", "pts": pts, "cls": cls}
    d.update(kw)
    return d


def O(cx, cy, rx, cls, ry=None, **kw):
    d = {"kind": "oval", "cx": cx, "cy": cy, "rx": rx, "ry": rx if ry is None else ry, "cls": cls}
    d.update(kw)
    return d


def L(pts, cls, **kw):
    d = {"kind": "line", "pts": pts, "cls": cls}
    d.update(kw)
    return d


def T(x, y, segs, cls, size=14, anchor="start", weight="normal", angle=0, **kw):
    """Text: `segs` is a list of (text, class) runs drawn one after another on one line.
    (x, y) is the start/middle/end of the line at its vertical centre. `angle` turns the whole
    line anticlockwise about (x, y), in degrees (90 = reads bottom to top)."""
    d = {"kind": "text", "x": x, "y": y, "segs": segs, "cls": cls, "size": size,
         "anchor": anchor, "weight": weight, "angle": angle}
    d.update(kw)
    return d


def _elements_mm():
    """Every element's primitives in mm. The primitive flagged main=True is the one the editor
    outlines on selection and lights up on a live press; `anchor` is where a side callout's
    leader attaches: (left point, right point). `top` / `bottom` are where a leader that comes
    in over the keyboard edge, or up from the user's edge, attaches instead."""
    E = {}
    nx0, nx1, ny = _touchpad_notch()
    gap = 0.6                                    # the opening's clearance round the pad shows as a seam
    pad = round_corners([(nx0 + gap, ny + gap), (nx1 - gap, ny + gap), (nx1 - gap, LIP_Y), (nx0 + gap, LIP_Y)],
                        [1.5, 1.5, 0, 0], 4)
    bar_y = LIP_Y - 1.8                          # the light bar slit along the pad's keyboard edge
    E["Pad"] = {"shapes": [P(pad, "input", main=True),
                           L([(TOUCHPAD_C[0] - 20.0, bar_y), (TOUCHPAD_C[0] + 20.0, bar_y)], "bar")],
                "anchor": ((nx0, TOUCHPAD_C[1]), (nx1, TOUCHPAD_C[1])),
                "top": (TOUCHPAD_C[0] - 20.0, LIP_Y)}
    for name, txt in (("LS", "L3"), ("RS", "R3")):
        cx, cy = STICKS[name]
        E[name] = {"shapes": [O(cx, cy, STICK_HOLE_D / 2, "well"), O(cx, cy, CAP_D / 2, "input", main=True),
                              O(cx, cy, CAP_TOP_D / 2, "glyph"),
                              T(cx, cy, [(txt, "name")], "name", size=2.3 * MM, anchor="middle")],
                   "anchor": ((cx - STICK_HOLE_D / 2, cy), (cx + STICK_HOLE_D / 2, cy))}
    for name, (cx, cy) in (("Share", SHARE), ("Options", OPTIONS)):
        side_y = cy + SLOT_LEN / 2 - SLOT_W / 2 - 0.3            # on the straight side, near the top
        E[name] = {"shapes": [P(stadium(cx, cy, SLOT_W, SLOT_LEN), "input", main=True),
                              T(cx, cy - SLOT_LEN / 2 - 1.6, [(name, "name")], "name", size=2.0 * MM, anchor="middle")],
                   "anchor": ((cx - SLOT_W / 2, side_y), (cx + SLOT_W / 2, side_y)),
                   "top": (cx, cy + SLOT_LEN / 2)}
    E["PS"] = {"shapes": [O(PS_C[0], PS_C[1], PS_D / 2, "input", main=True),
                          T(PS_C[0], PS_C[1], [("PS", "name")], "name", size=1.9 * MM, anchor="middle")],
               "anchor": ((PS_C[0] - PS_D / 2, PS_C[1]), (PS_C[0] + PS_D / 2, PS_C[1])),
               "bottom": (PS_C[0], PS_C[1] - PS_D / 2)}
    r, g = FACE_D / 2, 2.4
    for name, (cx, cy) in FACE.items():
        shapes = [O(cx, cy, r, "input", main=True)]
        if name == "Triangle":
            shapes.append(P([(cx, cy + g), (cx + g * 0.95, cy - g * 0.65), (cx - g * 0.95, cy - g * 0.65)], "glyph"))
        elif name == "Circle":
            shapes.append(O(cx, cy, g * 0.9, "glyph"))
        elif name == "Cross":
            shapes += [L([(cx - g * 0.8, cy - g * 0.8), (cx + g * 0.8, cy + g * 0.8)], "glyph"),
                       L([(cx - g * 0.8, cy + g * 0.8), (cx + g * 0.8, cy - g * 0.8)], "glyph")]
        else:
            shapes.append(P(rect(cx - g * 0.8, cy - g * 0.8, g * 1.6, g * 1.6), "glyph"))
        E[name] = {"shapes": shapes, "anchor": ((cx - r, cy), (cx + r, cy))}
    dx, dy = DPAD_C
    half, w = DPAD_ARM + DPAD_W / 2, DPAD_W / 2            # tip to centre 12.1, half a bar 4.6
    arms = {"dpad_N": [(dx - w, dy + w), (dx + w, dy + w), (dx + w, dy + half), (dx - w, dy + half)],
            "dpad_S": [(dx - w, dy - half), (dx + w, dy - half), (dx + w, dy - w), (dx - w, dy - w)],
            "dpad_W": [(dx - half, dy - w), (dx - w, dy - w), (dx - w, dy + w), (dx - half, dy + w)],
            "dpad_E": [(dx + w, dy - w), (dx + half, dy - w), (dx + half, dy + w), (dx + w, dy + w)]}
    tips = {"dpad_N": (0, 1), "dpad_S": (0, -1), "dpad_W": (-1, 0), "dpad_E": (1, 0)}   # +y = the keyboard = up
    for name, pts in arms.items():
        ux, uy = tips[name]
        tx, ty = dx + ux * (half - 3.4), dy + uy * (half - 3.4)        # a small arrow in the arm
        px, py = -uy, ux
        tri = [(tx + ux * 1.5, ty + uy * 1.5), (tx - ux * 0.9 + px * 1.4, ty - uy * 0.9 + py * 1.4),
               (tx - ux * 0.9 - px * 1.4, ty - uy * 0.9 - py * 1.4)]
        E[name] = {"shapes": [P(round_corners(pts, 1.0, 3), "input", main=True), P(tri, "glyph-fill")],
                   "anchor": ((dx - half, dy), (dx + half, dy))}
    # the whole cross is one opening, drawn once under the four arms
    E["dpad_N"]["shapes"].insert(0, P(round_corners(cross(dx, dy, half, w), 1.0, 3), "well"))
    for name, (x0, x1, y0, y1) in TABS.items():
        E[name] = {"shapes": [P(round_corners(rect(x0, y0, x1 - x0, y1 - y0), 1.2, 3), "tab", main=True),
                              T((x0 + x1) / 2, (y0 + y1) / 2, [(name, "name")], "name", size=2.0 * MM, anchor="middle")],
                   "anchor": ((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2))}
    return E


def _furniture_mm():
    """Everything that is not an input, drawn under the elements: the two extender stubs, the
    plate, the lip line that makes the keyboard edge a double line, the plate screws, labels."""
    out = []
    screw_ys = sorted({y for _, y in SCREWS})
    for side in ("L", "R"):
        sgn = -1 if side == "L" else 1
        x_seam = PLATE_X0 if side == "L" else PLATE_X1
        out.append(P(_stub(side), "ext"))
        out.append(L([(x_seam, LIP_Y), (x_seam + sgn * STUB, LIP_Y)], "edge-faint"))
        for y in screw_ys:                       # the extender plate's first screw, 8 mm in from the seam
            out.append(O(x_seam + sgn * EXT_SCREW_INSET, y, 1.0, "detail-faint"))
        label = (f"extender {EXT_LEFT:g} mm" if side == "L"
                 else f"extenders {EXT_RIGHT[0]:g} + {EXT_RIGHT[1]:g} mm")
        # turned, in the stub's outer half and low down: the side leaders cross the stubs on
        # their way in, but never below the sticks' line or outboard of the knee
        out.append(T(x_seam + sgn * (STUB - 3.5), -9.0, [(label, "label")], "label",
                     size=9, anchor="middle", angle=90))
    out.append(P(_plate_outline(), "body"))
    nx0, nx1, _ = _touchpad_notch()
    out += [L([(PLATE_X0, LIP_Y), (nx0, LIP_Y)], "edge"), L([(nx1, LIP_Y), (PLATE_X1, LIP_Y)], "edge")]
    for x, y in SCREWS:
        out += [O(x, y, 2.0, "screw"), O(x, y, 1.0, "detail")]
    out.append(T(0.0, PLATE_Y1 + 2.4, [("keyboard edge", "label")], "label", size=11, anchor="middle"))
    out.append(T(-45.0, PLATE_Y0 - 2.6, [("user's edge", "label")], "label", size=11, anchor="middle"))
    return out


# ------------------------------------------------------------------ layout

PAD_X = 16               # outer margin
COL_W = 262              # a callout column
GAP = 20                 # column to drawing
TOP = 70                 # y of the drawing's top (mm Y_MAX_MM)
TITLE_SIZE, ROW_SIZE, NAME_SIZE = 15, 14, 11
TITLE_H, ROW_H, ENTRY_PAD, ENTRY_GAP = 22, 19, 6, 11
LEGEND_H = 46
SCENE_W = 2 * (PAD_X + COL_W + GAP) + int(round((X_MAX_MM - X_MIN_MM) * MM))

# which callout column an element's entry goes in
SIDE = {"Pad": "L", "LS": "L", "Share": "L", "dpad": "L", "L1": "L", "L2": "L",
        "RS": "R", "Options": "R", "face": "R", "PS": "R", "R1": "R", "R2": "R"}
# how an entry's leader reaches its input. "side": out over the extender stub, then straight in
# at the input's height. "top": along the entry's own line, then straight down over the keyboard
# edge - the touchpad and the two slots are walled in by the d-pad and the face buttons, and
# the opening is open at that edge anyway. "bottom": the same from the user's edge, for PS
# between the two sticks. A top entry goes first in its column, a bottom entry last.
ROUTE = {"Pad": "top", "Options": "top", "PS": "bottom"}
_ROUTE_ORDER = {"top": 0, "side": 1, "bottom": 2}


def mm_to_px(x_mm, y_mm):
    """P mm -> scene units: x across, +y (toward the keyboard) UP the page."""
    return (PAD_X + COL_W + GAP + (x_mm - X_MIN_MM) * MM, TOP + (Y_MAX_MM - y_mm) * MM)


_ELEMENTS = _elements_mm()
_FURNITURE = _furniture_mm()


def _scale_prim(p, f):
    """A primitive in mm -> scene units (a new dict; shapes are shared and never mutated)."""
    q = dict(p)
    if p["kind"] in ("poly", "line"):
        q["pts"] = [f(x, y) for x, y in p["pts"]]
    elif p["kind"] == "oval":
        q["cx"], q["cy"] = f(p["cx"], p["cy"])
        q["rx"], q["ry"] = p["rx"] * MM, p["ry"] * MM
    else:
        q["x"], q["y"] = f(p["x"], p["y"])
    return q


def _button_rows(slots, lead=None):
    """Callout rows for one button's slots: [(segments)], segments = [(text, cls), ...]."""
    rows = []
    fn = pretty_binding(slots["fn"]) if slots else None
    if not slots:
        row = [(lead + "  ", "lead")] if lead else []
        rows.append(row + [("unbound", "unbound")])
        return rows
    first = [(lead + "  ", "lead")] if lead else []
    if slots["tap"] or slots["hold"]:
        row = list(first)
        if slots["tap"]:
            row += [("tap ", "lead"), (pretty_binding(slots["tap"]), "row")]
        if slots["hold"]:
            row += [("   hold " if slots["tap"] else "hold ", "lead"), (pretty_binding(slots["hold"]), "row")]
        rows.append(row)
        if fn:
            rows.append(([(lead + "  ", "lead")] if lead else []) + [("Fn ", "fnlead"), (fn, "fn")])
    else:
        row = list(first)
        if slots["press"]:
            row.append((pretty_binding(slots["press"]), "row"))
        if fn:
            row += [("   Fn " if slots["press"] else "Fn ", "fnlead"), (fn, "fn")]
        if len(row) == len(first):
            row.append(("unbound", "unbound"))
        rows.append(row)
    return rows


def _stick_rows(mapping, which):
    """Four direction rows (+ a click row) for a stick."""
    rows = []
    if which == "LS":
        sec, fn = mapping["left_stick"]["flick"], mapping["left_stick"]["fn"]
        for d in ds4_dock.DIRECTIONS:
            row = [(ARROW[d] + "  ", "lead")]
            if sec.get(d):
                row.append((pretty_key(sec[d]), "row"))
            if fn.get(d):
                row += [("   Fn " if sec.get(d) else "Fn ", "fnlead"), (pretty_binding(fn[d]), "fn")]
            if len(row) == 1:
                row.append(("unbound", "unbound"))
            rows.append(row)
        click = "L3"
    else:
        rs = mapping["right_stick"]
        if rs["mode"] == "cursor":
            rows.append([("moves the cursor (right_stick.mode = cursor)", "unbound")])
        else:
            for d in ds4_dock.DIRECTIONS:
                row = [(ARROW[d] + "  ", "lead")]
                if rs["keys"].get(d):
                    row.append((pretty_key(rs["keys"][d]), "row"))
                if rs["fn"].get(d):
                    row += [("   Fn " if rs["keys"].get(d) else "Fn ", "fnlead"), (pretty_key(rs["fn"][d]), "fn")]
                if len(row) == 1:
                    row.append(("unbound", "unbound"))
                rows.append(row)
        click = "R3"
    fnb = mapping.get("fn")
    if fnb and fnb["button"] == click:
        row = [("click  ", "lead"), ("hold = Fn layer", "fn")]
        if fnb["tap"]:
            row += [("   tap ", "lead"), (pretty_binding(fnb["tap"]), "row")]
        rows.append(row)
    else:
        rows += _button_rows(mapping["buttons"].get(click), lead="click")
    return rows


def _pad_rows(mapping):
    tp = mapping["touchpad"]
    rows = []
    for lead, move, tap in (("1 finger  ", tp["one_finger"], tp["one_finger_tap"]),
                            ("2 fingers  ", tp["two_finger"], tp["two_finger_tap"])):
        row = [(lead, "lead")]
        if move:
            row.append((move, "row"))
        if tap:
            row += [("   tap " if move else "tap ", "lead"), (pretty_binding(tap), "row")]
        if len(row) == 1:
            row.append(("off", "unbound"))
        rows.append(row)
    fnb = mapping.get("fn")
    if fnb and fnb["button"] == "Pad":
        row = [("click  ", "lead"), ("hold = Fn layer", "fn")]
        if fnb["tap"]:
            row += [("   tap ", "lead"), (pretty_binding(fnb["tap"]), "row")]
        rows.append(row)
    else:
        rows += _button_rows(mapping["buttons"].get("Pad"), lead="click")
    return rows


def _simple_rows(mapping, button):
    fnb = mapping.get("fn")
    if fnb and fnb["button"] == button:
        row = [("hold = Fn layer", "fn")]
        if fnb["tap"]:
            row += [("   tap ", "lead"), (pretty_binding(fnb["tap"]), "row")]
        return [row]
    if button in ds4_dock.RESERVED_BUTTONS:
        return [[("reserved", "unbound")], [("reads pressed with no trigger fitted", "unbound")]]
    return _button_rows(mapping["buttons"].get(button))


def entries(mapping, mode):
    """The callouts: a list of dicts {id, title, rows, side, route, anchor_mm} in drawing order."""
    out = []

    def add(eid, title, rows, anchor_of):
        side, route = SIDE[eid], ROUTE.get(eid, "side")
        el = _ELEMENTS[anchor_of]
        if route == "side":
            a = el["anchor"][0] if side == "L" else el["anchor"][1]
        else:
            a = el[route]
        out.append({"id": eid, "title": title, "rows": rows, "side": side, "route": route, "anchor": a})

    add("Pad", "Touchpad", _pad_rows(mapping), "Pad")
    add("LS", "Left stick", _stick_rows(mapping, "LS"), "LS")
    add("RS", "Right stick", _stick_rows(mapping, "RS"), "RS")
    add("Share", "Share", _simple_rows(mapping, "Share"), "Share")
    add("Options", "Options", _simple_rows(mapping, "Options"), "Options")
    if mode == "full":
        rows = []
        for d in ds4_dock.DIRECTIONS:
            rows += _button_rows(mapping["buttons"].get("dpad_" + d), lead=ARROW[d])
        add("dpad", "D-pad", rows, "dpad_W")
        rows = []
        for b in ("Triangle", "Circle", "Cross", "Square"):
            rows += _button_rows(mapping["buttons"].get(b), lead=b)
        add("face", "Face buttons", rows, "Circle")
        for b in ("L1", "L2", "R1", "R2", "PS"):
            rows = _simple_rows(mapping, b)
            if b in KEYBOARD_EDGE:
                rows = rows + [[(KEYBOARD_EDGE_ROW, "unbound")]]
            add(b, b, rows, b)
    return out


def _entry_h(e):
    return ENTRY_PAD + TITLE_H + ROW_H * len(e["rows"])


def _place(col, y_top, y_bottom_min):
    """Stack a column's entries top to bottom in the order of their inputs (a top-routed entry
    first, a bottom-routed one last); centre the stack on its anchors when it is shorter than
    the drawing. A top-routed entry pins the stack to the top so its leader runs over the
    keyboard edge, clear of the tabs. Returns the y below the last entry."""
    col.sort(key=lambda e: (_ROUTE_ORDER[e["route"]], -e["anchor"][1], e["anchor"][0]))
    total = sum(_entry_h(e) for e in col) + ENTRY_GAP * max(0, len(col) - 1)
    if not col:
        return y_top
    mean = sum(mm_to_px(*e["anchor"])[1] for e in col) / len(col)
    y = max(y_top, min(mean - total / 2, y_bottom_min - total))
    y = max(y_top, y)
    if col[0]["route"] == "top":
        y = y_top
    for e in col:
        e["y"] = y
        y += _entry_h(e) + ENTRY_GAP
    return y - ENTRY_GAP


def _leader(e, x_text, ty, w):
    """The leader polyline from an entry's title line to its input, in scene units."""
    side = e["side"]
    ax, ay = mm_to_px(*e["anchor"])
    lx = x_text + 8 if side == "L" else x_text - 8
    start = [(lx, ty), (lx + (10 if side == "L" else -10), ty)]
    route = e["route"]
    plate_top, plate_bottom = mm_to_px(0, PLATE_Y1)[1], mm_to_px(0, PLATE_Y0)[1]
    if route == "top" and ty < plate_top - 8:
        return start + [(ax, ty), (ax, ay)]
    if route == "bottom" and ty > plate_bottom + 8:
        return start + [(ax, ty), (ax, ay)]
    kx = mm_to_px(-KNEE_X if side == "L" else KNEE_X, 0)[0]
    return start + [(kx, ay), (ax, ay)]


def build_scene(mapping, mode="bare", state=None, legend=True):
    """The whole picture as primitives. `state` maps element -> a set of flags out of 'sel',
    'hover', 'lit' (the editor's selection, hover and live-press highlights). Returns
    {"w", "h", "prims", "entries"}; every primitive that belongs to an element carries
    "el": name, so a canvas can hit-test."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    state = {k: ({v} if isinstance(v, str) else set(v)) for k, v in (state or {}).items()}
    prims = []
    live = set(ELEMENTS) if mode == "full" else set(BARE_ELEMENTS)
    ents = entries(mapping, mode)
    ctrl_bottom = mm_to_px(0, Y_MIN_MM)[1]
    yl = _place([e for e in ents if e["side"] == "L"], TOP, ctrl_bottom)
    yr = _place([e for e in ents if e["side"] == "R"], TOP, ctrl_bottom)
    h = int(max(ctrl_bottom, yl, yr) + 24 + (LEGEND_H if legend else 0))
    w = SCENE_W

    # title
    prims.append(T(PAD_X, 26, [(mapping.get("name") or "control map", "title")], "title",
                   size=TITLE_SIZE + 2, weight="bold"))
    sub = ("the printed palm plate from above, keyboard edge up: touchpad, two sticks, Share, Options"
           " - faint controls are not on this board"
           if mode == "bare" else
           "the full plate from above, keyboard edge up: every control open - L1 R1 L2 R2 sit on the"
           " edge that faces the keyboard, out of reach docked")
    prims.append(T(PAD_X, 48, [(sub, "lead")], "lead", size=ROW_SIZE - 1))

    # the plate and its surroundings, then the inputs on it
    prims += [_scale_prim(p, mm_to_px) for p in _FURNITURE]
    for name in ELEMENTS:
        ghost = name not in live
        st = state.get(name, set())
        for p in _ELEMENTS[name]["shapes"]:
            q = _scale_prim(p, mm_to_px)
            cls = q["cls"]
            if ghost:
                cls = cls + "-ghost"
            elif q.get("main"):
                if "lit" in st:
                    cls = "input-lit"
                elif "hover" in st:
                    cls = "input-hover"
            q["cls"] = cls
            q["el"] = name
            q["ghost"] = ghost
            if q["kind"] == "text":
                q["segs"] = [(t, cls) for t, _ in q["segs"]]
            prims.append(q)
        if "sel" in st and not ghost:
            main = next(p for p in _ELEMENTS[name]["shapes"] if p.get("main"))
            q = _scale_prim(main, mm_to_px)
            q["cls"], q["el"], q["ghost"] = "sel-outline", name, False
            q.pop("main", None)
            prims.append(q)

    # callouts
    for e in ents:
        side = e["side"]
        x_text = PAD_X + COL_W if side == "L" else w - PAD_X - COL_W
        anchor = "end" if side == "L" else "start"
        y = e["y"] + ENTRY_PAD
        ty = y + TITLE_H / 2
        prims.append(T(x_text, ty, [(e["title"], "etitle")], "etitle", size=TITLE_SIZE,
                       anchor=anchor, weight="bold", el=e["id"]))
        pts = _leader(e, x_text, ty, w)
        prims.append(L(pts, "leader", el=e["id"]))
        prims.append(O(pts[-1][0], pts[-1][1], 2.6, "leader-dot", el=e["id"]))
        y += TITLE_H
        for row in e["rows"]:
            prims.append(T(x_text, y + ROW_H / 2, row, "row", size=ROW_SIZE, anchor=anchor, el=e["id"]))
            y += ROW_H

    if legend:
        ly = h - LEGEND_H + 14
        x = PAD_X
        prims.append(P(round_corners(rect(x, ly - 7, 26, 14), 3), "input"))
        prims.append(T(x + 34, ly, [("input on this board", "lead")], "lead", size=ROW_SIZE - 1))
        x += 180
        if mode == "bare":
            prims.append(P(round_corners(rect(x, ly - 7, 26, 14), 3), "input-ghost"))
            prims.append(T(x + 34, ly, [("not on this board (bare)", "lead")], "lead", size=ROW_SIZE - 1))
            x += 210
        fn = mapping.get("fn")
        if fn:
            prims.append(T(x, ly, [("Fn", "fn"), (f"  = layer 2, hold {ELEMENT_TITLE.get(BUTTON_ELEMENT.get(fn['button'], ''), fn['button'])}"
                                                  + (" click" if fn["button"] in ("L3", "R3") else ""), "lead")],
                           "lead", size=ROW_SIZE - 1))
        prims.append(T(w - PAD_X, ly, [("mapping.json  →  tools/render_map.py", "lead")], "lead",
                       size=ROW_SIZE - 1, anchor="end"))
    return {"w": w, "h": h, "prims": prims, "entries": ents}


# ------------------------------------------------------------------ SVG backend

ACCENT = "#d8651a"                 # the one accent: the light bar's attention orange, toned down
GREY, MID, DARK = "#8b949e", "#6e7781", "#57606a"
# class -> (fill, stroke, stroke width, dash, extra). Mid greys read on a light and a dark page;
# the plate is a translucent tint so it takes the page's tone.
STYLE = {
    "body":        (GREY, MID, 1.6, None, 'fill-opacity="0.16"'),
    "ext":         (GREY, GREY, 1.0, None, 'fill-opacity="0.07" stroke-opacity="0.55"'),
    "edge":        ("none", MID, 1.0, None, 'stroke-opacity="0.75"'),
    "edge-faint":  ("none", GREY, 0.9, None, 'stroke-opacity="0.45"'),
    "well":        (GREY, MID, 1.2, None, 'fill-opacity="0.22"'),
    "well-ghost":  ("none", GREY, 1.0, "4 3", 'stroke-opacity="0.6"'),
    "input":       (GREY, MID, 1.6, None, 'fill-opacity="0.32"'),
    "input-ghost": ("none", GREY, 1.1, "4 3", 'stroke-opacity="0.7"'),
    "input-hover": (ACCENT, ACCENT, 1.8, None, 'fill-opacity="0.18"'),
    "input-lit":   (ACCENT, ACCENT, 1.8, None, 'fill-opacity="0.55"'),
    "sel-outline": ("none", ACCENT, 3.0, None, ""),
    "tab":         (GREY, MID, 1.3, "5 3", 'fill-opacity="0.16"'),
    "tab-ghost":   ("none", GREY, 1.0, "4 3", 'stroke-opacity="0.55"'),
    "bar":         ("none", ACCENT, 2.2, None, 'stroke-linecap="round" stroke-opacity="0.9"'),
    "bar-ghost":   ("none", GREY, 1.0, "4 3", ""),
    "glyph":       ("none", MID, 1.4, None, 'stroke-linecap="round" stroke-linejoin="round"'),
    "glyph-ghost": ("none", GREY, 1.0, "3 2", 'stroke-opacity="0.6"'),
    "glyph-fill":  (MID, "none", 0, None, ""),
    "glyph-fill-ghost": (GREY, "none", 0, None, 'fill-opacity="0.5"'),
    "screw":       ("none", MID, 0.9, None, 'stroke-opacity="0.7"'),
    "detail":      (MID, "none", 0, None, 'fill-opacity="0.7"'),
    "detail-faint": (GREY, "none", 0, None, 'fill-opacity="0.45"'),
    "leader":      ("none", GREY, 1.1, None, 'stroke-linejoin="round"'),
    "leader-dot":  (ACCENT, "none", 0, None, ""),
}
TEXT = {           # text class -> (fill, extra)
    "title": (MID, ""), "etitle": (MID, ""), "row": (MID, ""), "lead": (GREY, ""),
    "fn": (ACCENT, ""), "fnlead": (ACCENT, 'fill-opacity="0.8"'),
    "unbound": (GREY, 'font-style="italic" fill-opacity="0.9"'),
    "name": (MID, ""), "name-ghost": (GREY, 'fill-opacity="0.65"'),
    "label": (GREY, 'fill-opacity="0.95"'),
}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _style_attrs(cls):
    fill, stroke, width, dash, extra = STYLE[cls]
    a = f'fill="{fill}" stroke="{stroke}"'
    if stroke != "none":
        a += f' stroke-width="{_f(width)}"'
    if dash:
        a += f' stroke-dasharray="{dash}"'
    if extra:
        a += " " + extra
    return a


def to_svg(scene, title="control map"):
    w, h = scene["w"], scene["h"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
           f'font-family="{FONT}">',
           f"<title>{escape(title)}</title>"]
    for p in scene["prims"]:
        k = p["kind"]
        if k == "poly":
            pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in p["pts"])
            out.append(f'<polygon points="{pts}" {_style_attrs(p["cls"])}/>')
        elif k == "line":
            pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in p["pts"])
            out.append(f'<polyline points="{pts}" {_style_attrs(p["cls"])}/>')
        elif k == "oval":
            out.append(f'<ellipse cx="{_f(p["cx"])}" cy="{_f(p["cy"])}" rx="{_f(p["rx"])}" ry="{_f(p["ry"])}" '
                       f'{_style_attrs(p["cls"])}/>')
        else:
            weight = ' font-weight="bold"' if p["weight"] == "bold" else ""
            # the primitive's angle is anticlockwise; SVG's rotate() is clockwise on a y-down page
            rot = (f' transform="rotate({_f(-p["angle"])} {_f(p["x"])} {_f(p["y"])})"'
                   if p.get("angle") else "")
            segs = []
            for text, cls in p["segs"]:
                fill, extra = TEXT.get(cls, TEXT["row"])
                extra = (" " + extra) if extra else ""
                segs.append(f'<tspan fill="{fill}"{extra}>{escape(text)}</tspan>')
            out.append(f'<text x="{_f(p["x"])}" y="{_f(p["y"])}" font-size="{_f(p["size"])}" '
                       f'text-anchor="{p["anchor"]}" dominant-baseline="central"{weight}{rot}>{"".join(segs)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_svg(mapping, mode="bare"):
    """A validated map (any dict in the schema) -> SVG text."""
    m = ds4_dock.normalise_mapping(mapping)
    scene = build_scene(m, mode)
    return to_svg(scene, title=f"{m.get('name') or 'control map'} ({mode})")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draw a control map on a drawing of the dock's face plate, as SVG.")
    ap.add_argument("mapping", help="mapping.json to draw ('-' = the mapper's built-in map)")
    ap.add_argument("out", help="SVG file to write")
    ap.add_argument("--mode", choices=MODES, default="bare",
                    help="bare (default): the five-button board on the palm plate, the rest ghosted; "
                         "full: the full plate, every input")
    args = ap.parse_args(argv)
    try:
        m = ds4_dock.default_mapping() if args.mapping == "-" else ds4_dock.load_mapping(args.mapping)
    except (OSError, ValueError) as ex:
        sys.exit(f"{args.mapping}: {ex}")
    scene = build_scene(m, args.mode)
    svg = to_svg(scene, title=f"{m.get('name') or 'control map'} ({args.mode})")
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print(f"wrote {args.out}  ({scene['w']} x {scene['h']}, {args.mode}, {m.get('name')!r}, "
          f"{len(svg)} bytes)")


if __name__ == "__main__":
    main()
