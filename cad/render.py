"""Renders and drawings for docs/images/, built straight from the CAD sources (no STL files needed).

    python cad/render.py                       # all six images into docs/images/ (one to two minutes)
    python cad/render.py --only hero plan      # some of: hero exploded variants faceplates seam plan
    python cad/render.py --out DIR             # write elsewhere (default: <repo>/docs/images)
    python cad/render.py --scale 0.4           # quick low-resolution preview of the PNGs

Images:
  hero.png          shaded view of the assembled dock - cradle, face plate, the three extender bases
                    and their plates (std height, hook, palm plate) - from the user's side, 2000 px wide
  exploded.png      the same with the pieces drawn apart at the seams, the plates lifted off their
                    rims, the splines and top keys pulled out of their seats, and the stick caps
  variants.png      the six cradles (low / std / tall x hook / no hook) in a 3 x 2 grid, one scale
  faceplates.png    the palm and the full face plate side by side, top view
  seam_section.svg  a section through the right seam at x = 73, traced from the solids: every
                    0.5 mm of y the z spans of material are listed and drawn as columns; the spline
                    and top-key seats are outlined
  plan.svg          plan view of the four pieces across 439 mm, to scale, both connectors per seam

The shaded images come from a small z-buffer rasteriser written here on numpy: the parts are
tessellated by build123d, projected orthographically, depth-tested per pixel, flat-shaded with one
key light, one fill light and a sky term, given silhouette and crease lines from the id, depth and
normal buffers, a soft ground shadow, and rendered at 2x then downsampled. No external renderer and
no matplotlib 3D (its painter's algorithm mis-sorts the seams between touching parts). Pillow writes
the PNGs; the SVGs are plain text. The assembly itself comes from checks.Dock, so the pictures show
exactly what the check suite measures.

Frames: W is the desk (z = 0, +y toward the keyboard), P the tilted part frame; see dock_params.
"""
import argparse
import copy
import html
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
from build123d import Box, Pos  # noqa: E402

import checks  # noqa: E402
import cradle  # noqa: E402
import dock_params as p  # noqa: E402
import extender  # noqa: E402
import faceplate  # noqa: E402
import stick_cap  # noqa: E402
import variants  # noqa: E402

CAD_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(CAD_DIR)
OUT_DIR = os.path.join(REPO_DIR, "docs", "images")

# palette, 0..1 rgb (PNG) and hex (SVG): neutral greys plus one accent for the joint keys
COL_BASE = (0.60, 0.63, 0.68)
COL_PLATE = (0.86, 0.83, 0.78)
COL_KEY = (0.93, 0.56, 0.20)
COL_CAP = (0.30, 0.31, 0.34)
BG = (1.0, 1.0, 1.0)
LINE = np.array((0.10, 0.11, 0.13))
HEX = {"base": "#9aa3ad", "base_dark": "#7f8894", "plate": "#dcd3c4", "plate_edge": "#8f8470",
       "key": "#e8862a", "key_dark": "#b55f12", "ink": "#2b2f36", "dim": "#5b636e", "faint": "#aab0b8",
       "bg": "#f5f6f8", "hole": "#f5f6f8", "desk": "#6b7280"}
FONT_STACK = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


# ---- meshes ---------------------------------------------------------------------------------

class Mesh:
    """A tessellated part: vertices V (n, 3) in W, triangles T (m, 3) wound outward, one colour."""

    def __init__(self, shape, colour, name="", tolerance=0.02, angular=0.12):
        verts, tris = shape.tessellate(tolerance, angular)
        self.V = np.array([[v.X, v.Y, v.Z] for v in verts], dtype=float)
        self.T = np.array(tris, dtype=np.int64).reshape(-1, 3)
        self.colour = np.array(colour, dtype=float)
        self.name = name
        v0, v1, v2 = self.V[self.T[:, 0]], self.V[self.T[:, 1]], self.V[self.T[:, 2]]
        if np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() < 0:   # guard the back-face cull
            self.T = self.T[:, ::-1]
        bb = shape.bounding_box()
        if np.abs(self.V.min(axis=0) - (bb.min.X, bb.min.Y, bb.min.Z)).max() > 0.5:
            raise RuntimeError(f"{name}: tessellation does not sit on the shape's bounding box")

    def moved(self, dx=0.0, dy=0.0, dz=0.0):
        m = copy.copy(self)
        m.V = self.V + np.array([dx, dy, dz], dtype=float)
        return m


class Camera:
    """Orthographic. azimuth 0 looks from the user's side (-y) toward the keyboard; positive
    azimuth swings the camera toward +x (the right-hand end); elevation lifts it above the desk."""

    def __init__(self, azimuth, elevation, up=(0.0, 0.0, 1.0)):
        az, el = math.radians(azimuth), math.radians(elevation)
        self.d = np.array([math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)])  # to the camera
        f = -self.d
        r = np.cross(f, np.asarray(up, dtype=float))
        if np.linalg.norm(r) < 1e-9:
            r = np.cross(f, (0.0, 1.0, 0.0))
        r = unit(r)
        u = np.cross(r, f)
        self.R = np.vstack([r, u, f])          # rows: screen x, screen y, depth (bigger = farther)

    def project(self, V):
        return V @ self.R.T


def extent_of(meshes, cam):
    P = np.vstack([cam.project(m.V) for m in meshes])
    return (P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max())


def union_extent(extents):
    e = np.array(extents)
    return (e[:, 0].min(), e[:, 1].max(), e[:, 2].min(), e[:, 3].max())


# ---- the rasteriser -------------------------------------------------------------------------

def _fill(P, T, zbuf=None, col=None, nbuf=None, idbuf=None, rgb=None, N=None, mid=0, mask=None):
    """Scan-convert triangles T over projected pixel coordinates P (x, y, depth). With `mask`
    given, only paint the coverage mask (used for the shadow); otherwise depth-test into the
    buffers and write colour, normal and part id."""
    H, W = (mask.shape if mask is not None else zbuf.shape)
    for k in range(len(T)):
        i0, i1, i2 = T[k]
        x0, y0, d0 = P[i0]
        x1, y1, d1 = P[i1]
        x2, y2, d2 = P[i2]
        xmin, xmax = max(int(math.floor(min(x0, x1, x2))), 0), min(int(math.ceil(max(x0, x1, x2))), W - 1)
        ymin, ymax = max(int(math.floor(min(y0, y1, y2))), 0), min(int(math.ceil(max(y0, y1, y2))), H - 1)
        if xmax < xmin or ymax < ymin:
            continue
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-12:
            continue
        X = (np.arange(xmin, xmax + 1) + 0.5)[None, :]
        Y = (np.arange(ymin, ymax + 1) + 0.5)[:, None]
        w0 = ((x1 - X) * (y2 - Y) - (x2 - X) * (y1 - Y)) / area
        w1 = ((X - x0) * (y2 - y0) - (x2 - x0) * (Y - y0)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        if mask is not None:
            mask[ymin:ymax + 1, xmin:xmax + 1] |= inside
            continue
        depth = w0 * d0 + w1 * d1 + w2 * d2
        zs = zbuf[ymin:ymax + 1, xmin:xmax + 1]
        upd = inside & (depth < zs)
        if not upd.any():
            continue
        zs[upd] = depth[upd]
        col[ymin:ymax + 1, xmin:xmax + 1][upd] = rgb[k]
        nbuf[ymin:ymax + 1, xmin:xmax + 1][upd] = N[k]
        idbuf[ymin:ymax + 1, xmin:xmax + 1][upd] = mid


def _lines(idbuf, nbuf, zbuf, cam, px_per_mm, crease_deg=28.0, jump_mm=0.8):
    """(strong, weak) boolean masks: silhouettes (part id changes, depth jumps) and creases
    (normal turns by more than crease_deg between neighbouring pixels of one part)."""
    strong = np.zeros(idbuf.shape, bool)
    weak = np.zeros(idbuf.shape, bool)
    cosc = math.cos(math.radians(crease_deg))
    nd = np.abs(nbuf @ cam.d)                                    # cos(angle between normal and view)
    slope = np.tan(np.arccos(np.clip(nd, math.cos(math.radians(85.0)), 1.0))) / px_per_mm   # mm per px
    zfin = np.where(np.isfinite(zbuf), zbuf, 0.0)                # background is +inf; keep the maths finite
    for ax in (0, 1):
        b_id = np.roll(idbuf, -1, axis=ax)
        both = (idbuf >= 0) & (b_id >= 0)
        s = (idbuf != b_id)
        ndot = (nbuf * np.roll(nbuf, -1, axis=ax)).sum(-1)
        w = both & (ndot < cosc)
        dz = np.abs(zfin - np.roll(zfin, -1, axis=ax))
        thr = jump_mm + 2.0 * np.maximum(slope, np.roll(slope, -1, axis=ax))
        s |= both & (dz > thr)
        strong |= s | np.roll(s, 1, axis=ax)
        weak |= w | np.roll(w, 1, axis=ax)
    for m in (strong, weak):
        m[0, :] = m[-1, :] = False
        m[:, 0] = m[:, -1] = False
    return strong, weak & ~strong


def render(meshes, cam, width_px, extent=None, light=(-0.35, -0.55, 0.76), fill=(0.7, 0.2, 0.25),
           ss=2, margin=0.05, shadow=0.16, lines=(0.62, 0.30), bg=BG):
    """Shaded orthographic image of `meshes`, `width_px` wide, as a PIL image. `extent` is
    (sx0, sx1, sy0, sy1) in screen mm, so several images can share one framing and scale."""
    L, F = unit(light), unit(fill)
    Hv = unit(L + cam.d)                                         # half vector for the highlight
    sx0, sx1, sy0, sy1 = extent if extent is not None else extent_of(meshes, cam)
    pad = margin * (sx1 - sx0)
    Wpx = int(round(width_px * ss))
    s = Wpx / (sx1 - sx0 + 2 * pad)                              # px per mm
    Hpx = int(math.ceil((sy1 - sy0 + 2 * pad) * s))

    def to_px(P):
        return np.column_stack([(P[:, 0] - sx0 + pad) * s, (sy1 + pad - P[:, 1]) * s, P[:, 2]])

    col = np.empty((Hpx, Wpx, 3), dtype=float)
    col[:] = bg
    if shadow and L[2] > 0.05:
        mask = np.zeros((Hpx, Wpx), bool)
        for m in meshes:
            Vs = m.V - L[None, :] * (m.V[:, 2:3] / L[2])        # along the light down to the desk
            _fill(to_px(cam.project(Vs)), m.T, mask=mask)
        blur = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius=float(0.9 * s)))
        col *= (1.0 - shadow * (np.asarray(blur, dtype=float) / 255.0))[..., None]

    zbuf = np.full((Hpx, Wpx), np.inf)
    nbuf = np.zeros((Hpx, Wpx, 3))
    idbuf = np.full((Hpx, Wpx), -1, dtype=np.int32)
    for mi, m in enumerate(meshes):
        v0, v1, v2 = m.V[m.T[:, 0]], m.V[m.T[:, 1]], m.V[m.T[:, 2]]
        N = np.cross(v1 - v0, v2 - v0)
        a2 = np.linalg.norm(N, axis=1)
        keep = (a2 > 1e-12)
        N[keep] /= a2[keep][:, None]
        front = keep & (N @ cam.d > 1e-9)                          # back-face cull: closed solids
        sky = 0.32 + 0.12 * (0.5 + 0.5 * N[:, 2])
        dif = 0.60 * np.clip(N @ L, 0, None)
        fil = 0.14 * np.clip(N @ F, 0, None)
        spec = 0.08 * np.clip(N @ Hv, 0, None) ** 48
        rgb = np.clip(m.colour[None, :] * (sky + dif + fil)[:, None] + spec[:, None], 0, 1)
        _fill(to_px(cam.project(m.V)), m.T[front], zbuf, col, nbuf, idbuf, rgb[front], N[front], mi)

    strong, weak = _lines(idbuf, nbuf, zbuf, cam, s)
    col[strong] = col[strong] * (1 - lines[0]) + LINE * lines[0]
    col[weak] = col[weak] * (1 - lines[1]) + LINE * lines[1]
    img = Image.fromarray((np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8))
    return img.resize((Wpx // ss, Hpx // ss), Image.LANCZOS) if ss > 1 else img


# ---- scenes ---------------------------------------------------------------------------------

def dock_std():
    """The assembled dock (bases and plates in W) in the printed configuration."""
    variants.configure("std", "hook", "palm")
    return checks.Dock()


def hero_meshes(dock):
    ms = [Mesh(part, COL_BASE, f"{n} base") for n, part in dock.base.items()]
    ms += [Mesh(part, COL_PLATE, f"{n} plate") for n, part in dock.plate.items()]
    return ms


def exploded_meshes(dock, gap=14.0, lift=30.0, key_lift=14.0, spline_pull=34.0, cap_gap=6.0):
    """Pieces drawn apart at the seams by `gap`, plates lifted `lift` along P z (square to the
    rim), top keys lifted `key_lift`, splines pulled toward the user, caps over the stick holes."""
    nz = np.array([0.0, -math.sin(math.radians(p.tilt)), math.cos(math.radians(p.tilt))])
    shift, count = {"cradle": 0.0}, {-1: 0, 1: 0}
    for n, _xi, _xo, sgn, _to in extender.pieces():
        count[int(sgn)] += 1
        shift[n] = sgn * gap * count[int(sgn)]
    ms = []
    for n, part in dock.base.items():
        ms.append(Mesh(part, COL_BASE, f"{n} base").moved(shift[n], 0, 0))
    for n, part in dock.plate.items():
        ms.append(Mesh(part, COL_PLATE, f"{n} plate").moved(*(np.array([shift[n], 0, 0]) + lift * nz)))
    for label, xs, lo, hi, dockside in checks.seams():
        mid = (shift[lo] + shift[hi]) / 2
        spline = checks.place_spline(xs, dockside == lo)
        key = checks.place_topkey(xs, dockside == lo)
        ms.append(Mesh(spline, COL_KEY, f"spline {label}").moved(mid, -spline_pull, 0))
        ms.append(Mesh(key, COL_KEY, f"top key {label}").moved(*(np.array([mid, 0, 0]) + key_lift * nz)))
    for x, y in (p.stick_l, p.stick_r):
        cap = p.P * Pos(x, y, p.h_top + p.plate_t + cap_gap) * stick_cap.make_cap(0.25)
        ms.append(Mesh(cap, COL_CAP, "stick cap").moved(*(lift * nz)))
    return ms


def font(size):
    """DejaVu Sans from matplotlib's own bundle (found at run time, no path in the code), or
    Pillow's built-in font if that is not there."""
    try:
        from matplotlib import font_manager
        return ImageFont.truetype(font_manager.findfont("DejaVu Sans", fallback_to_default=True), size)
    except Exception:                                   # pragma: no cover - fallback only
        try:
            return ImageFont.load_default(size)
        except TypeError:
            return ImageFont.load_default()


def label(draw, xy, text, size, fill=(43, 47, 54), anchor="la"):
    draw.text(xy, text, font=font(size), fill=fill, anchor=anchor)


def variants_image(width_px, scale=1.0):
    """The six cradles, one scale, 3 columns (heights) x 2 rows (hook, no hook), seen from the
    keyboard side so the hook tabs, the undercut and the open pocket end are in view."""
    cam = Camera(180 + 38, 30)
    cells = []
    for k in variants.HOOKS:
        for h in variants.HEIGHTS:
            variants.configure(h, k, "palm")
            part = cradle.make_cradle()
            bb = part.bounding_box()
            cells.append((h, k, Mesh(part, COL_BASE, f"cradle {h} {k}"), float(bb.max.Z)))
    ext = union_extent([extent_of([c[2]], cam) for c in cells])
    cols, rows = len(variants.HEIGHTS), len(variants.HOOKS)
    cw = width_px // cols
    tiles = [render([c[2]], cam, cw, extent=ext, light=(0.35, 0.55, 0.76), fill=(-0.6, -0.3, 0.3)) for c in cells]
    th = tiles[0].height
    head, cap_h, foot = int(96 * scale), int(74 * scale), int(44 * scale)
    img = Image.new("RGB", (cw * cols, head + rows * (th + cap_h) + foot), (255, 255, 255))
    d = ImageDraw.Draw(img)
    label(d, (int(28 * scale), int(26 * scale)), "Cradle variants - three heights, with and without the keyboard hook",
          int(34 * scale))
    label(d, (int(28 * scale), int(66 * scale)),
          "Same scale throughout, seen from the keyboard side (the hook tabs hang over the keyboard's front lip). "
          "Only cradle_std_hook has been printed.", int(20 * scale), fill=(100, 106, 116))
    for i, (h, k, _m, zmax) in enumerate(cells):
        r, c = divmod(i, cols)
        x, y = c * cw, head + r * (th + cap_h)
        img.paste(tiles[i], (x, y))
        name = f"cradle_{h}_{k}.stl"
        sub = (f"floor_h {variants.HEIGHTS[h]:.1f} mm  ·  {'hook' if variants.HOOKS[k] else 'no hook'}  ·  "
               f"{zmax:.1f} mm tall at the keyboard end")
        if (h, k) == variants.PRINTED[:2]:
            sub += "  ·  PRINTED (v11)"
        label(d, (x + cw // 2, y + th + int(8 * scale)), name, int(26 * scale), anchor="ma")
        label(d, (x + cw // 2, y + th + int(42 * scale)), sub, int(18 * scale), fill=(100, 106, 116), anchor="ma")
    variants.configure("std", "hook", "palm")
    return img


def faceplates_image(width_px, scale=1.0):
    """palm and full face plates side by side, straight down onto the face (P +z), keyboard edge up."""
    cam = Camera(0, 90, up=(0.0, 1.0, 0.0))
    plates = []
    for style in variants.PLATE_STYLES:
        variants.configure("std", "hook", style)
        plates.append((style, Mesh(faceplate.make_faceplate(), COL_PLATE, f"faceplate {style}")))
    ext = union_extent([extent_of([m], cam) for _s, m in plates])
    cw = width_px // 2
    tiles = [render([m], cam, cw, extent=ext, light=(-0.45, 0.35, 0.82), fill=(0.5, -0.4, 0.3), shadow=0.0)
             for _s, m in plates]
    th = tiles[0].height
    head, cap_h = int(96 * scale), int(104 * scale)
    img = Image.new("RGB", (cw * 2, head + th + cap_h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    label(d, (int(28 * scale), int(26 * scale)), "Face plates - top view, keyboard edge at the top", int(34 * scale))
    label(d, (int(28 * scale), int(66 * scale)),
          f"Both {p.ox1 - p.ox0:.0f} mm wide, {p.plate_t} mm thick, same screw holes, same curled lip; "
          "they differ only in which openings exist.", int(20 * scale), fill=(100, 106, 116))
    text = {
        "palm": ("faceplate_palm.stl", "touchpad, two sticks, Share and Options open; d-pad, face buttons and PS "
                                       "filled - a palm rest. PRINTED (plate v9)."),
        "full": ("faceplate_full.stl", "every control open, for a board that keeps its buttons: d-pad cross, four "
                                       "face buttons and PS added. Generated, not printed."),
    }
    for i, (style, _m) in enumerate(plates):
        x = i * cw
        img.paste(tiles[i], (x, head))
        name, sub = text[style]
        label(d, (x + cw // 2, head + th + int(8 * scale)), name, int(26 * scale), anchor="ma")
        words, line, lines = sub.split(), "", []
        for w in words:
            if d.textlength(line + " " + w, font=font(int(18 * scale))) > cw - int(60 * scale):
                lines.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        lines.append(line)
        for j, ln in enumerate(lines):
            label(d, (x + cw // 2, head + th + int((42 + 24 * j) * scale)), ln, int(18 * scale),
                  fill=(100, 106, 116), anchor="ma")
    variants.configure("std", "hook", "palm")
    return img


# ---- SVG drawings ---------------------------------------------------------------------------

class SVG:
    def __init__(self, w, h, title):
        self.w, self.h = w, h
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
                      f'font-family="{FONT_STACK}" font-size="13">',
                      f"<title>{html.escape(title)}</title>",
                      f'<rect width="100%" height="100%" fill="{HEX["bg"]}"/>']

    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill="none", stroke=None, sw=1.0, dash=None, rx=0.0, opacity=None):
        a = f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}"'
        if rx:
            a += f' rx="{rx:.2f}"'
        a += self._stroke(stroke, sw, dash) + self._op(opacity) + "/>"
        self.add(a)

    def path(self, d, fill="none", stroke=None, sw=1.0, dash=None, opacity=None):
        self.add(f'<path d="{d}" fill="{fill}"' + self._stroke(stroke, sw, dash) + self._op(opacity) + "/>")

    def line(self, x1, y1, x2, y2, stroke, sw=1.0, dash=None, opacity=None):
        self.add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"' + self._stroke(stroke, sw, dash)
                 + self._op(opacity) + "/>")

    def circle(self, cx, cy, r, fill="none", stroke=None, sw=1.0):
        self.add(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}"' + self._stroke(stroke, sw) + "/>")

    def ellipse(self, cx, cy, rx, ry, fill="none", stroke=None, sw=1.0):
        self.add(f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{fill}"'
                 + self._stroke(stroke, sw) + "/>")

    def text(self, x, y, s, size=13, fill=None, anchor="start", weight=None, italic=False, rotate=None):
        a = f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill or HEX["ink"]}" text-anchor="{anchor}"'
        if weight:
            a += f' font-weight="{weight}"'
        if italic:
            a += ' font-style="italic"'
        if rotate is not None:
            a += f' transform="rotate({rotate:.1f} {x:.2f} {y:.2f})"'
        self.add(a + f">{html.escape(s)}</text>")

    @staticmethod
    def _stroke(stroke, sw, dash=None):
        if not stroke:
            return ""
        a = f' stroke="{stroke}" stroke-width="{sw}"'
        if dash:
            a += f' stroke-dasharray="{dash}"'
        return a

    @staticmethod
    def _op(opacity):
        return f' opacity="{opacity}"' if opacity is not None else ""

    def dim_h(self, x1, x2, y, label, size=12, tick=5, above=True, fill=None):
        c = fill or HEX["dim"]
        self.line(x1, y, x2, y, c, 1)
        for x in (x1, x2):
            self.line(x, y - tick, x, y + tick, c, 1)
        self.text((x1 + x2) / 2, y - 4 if above else y + size + 2, label, size, c, "middle")

    def dim_v(self, x, y1, y2, label, size=12, tick=5, fill=None, side=1):
        c = fill or HEX["dim"]
        self.line(x, y1, x, y2, c, 1)
        for y in (y1, y2):
            self.line(x - tick, y, x + tick, y, c, 1)
        self.text(x + side * 7, (y1 + y2) / 2, label, size, c, "start" if side > 0 else "end", rotate=None)

    def leader(self, x1, y1, x2, y2, label, size=12, anchor="start", fill=None, dot=True):
        c = fill or HEX["ink"]
        self.line(x1, y1, x2, y2, HEX["dim"], 0.9)
        if dot:
            self.circle(x1, y1, 2.0, HEX["dim"])
        dx = 4 if anchor == "start" else (-4 if anchor == "end" else 0)
        self.text(x2 + dx, y2 + 4, label, size, c, anchor)

    def save(self, path):
        self.add("</svg>")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(self.parts) + "\n")


def section_columns(part, x, y0, y1, step=0.5, probe_w=0.2):
    """Trace a section of `part` at W x: for every `step` of y, the z spans of material inside a
    probe_w x step column, as (y_lo, y_hi, z_lo, z_hi). Comes straight from the solids."""
    out = []
    n = int(round((y1 - y0) / step))
    for i in range(n):
        y = y0 + (i + 0.5) * step
        r = part & Pos(x, y, 0) * Box(probe_w, step, 400)
        for s in r.solids():
            bb = s.bounding_box()
            out.append((y - step / 2, y + step / 2, float(bb.min.Z), float(bb.max.Z)))
    # the boolean returns a column's solids in no fixed order; sort so the SVG is the same bytes every run
    out.sort(key=lambda c: (c[0], c[2]))
    return out


def seam_section_svg(dock, path, x_cut=73.0, step=0.5):
    """Section through the cradle at W x = x_cut: inside the right side wall, 1.5 mm from the
    seam, where the spline seat (bottom) and the top-key seat (rim) both cut through."""
    base, plate = dock.base["cradle"], dock.plate["cradle"]
    bb_b, bb_p = base.bounding_box(), plate.bounding_box()
    y0 = math.floor(min(bb_b.min.Y, bb_p.min.Y)) - 1.0
    y1 = math.ceil(max(bb_b.max.Y, bb_p.max.Y)) + 1.0
    zmax = math.ceil(max(bb_b.max.Z, bb_p.max.Z)) + 1.0
    cols_b = section_columns(base, x_cut, y0, y1, step)
    cols_p = section_columns(plate, x_cut, y0, y1, step)

    S = 9.0                                                     # px per mm
    ox, oy = 330.0, 150.0                                       # room for a label column each side
    zlo = -3.0
    dw, dh = (y1 - y0) * S, (zmax - zlo) * S
    W, H = int(ox + dw + 360), int(oy + dh + 150)
    svg = SVG(W, H, f"Section through the dock at x = {x_cut:g} (the right seam)")

    def X(yw):
        return ox + (yw - y0) * S

    def Y(zw):
        return oy + (zmax - zw) * S

    svg.text(ox - 200, 32, f"Section through the right seam at x = {x_cut:g}", 20, weight="600")
    svg.text(ox - 200, 54, f"Inside the cradle's right side wall (x {p.ox1 - p.wall - p.rim:g}..{p.ox1:g}), "
             f"{p.ox1 - x_cut:.1f} mm from the seam face, so the spline seat at the bottom and the top-key seat in the rim "
             "both cut through.", 12, HEX["dim"])
    svg.text(ox - 200, 70, f"Traced from the solids: every {step} mm of y, every z span of material becomes one column. "
             "The staircase on the slopes is the trace, not the part.", 12, HEX["dim"])
    # desk
    svg.rect(X(y0), Y(0), dw, Y(zlo) - Y(0), HEX["faint"], opacity=0.35)
    svg.line(X(y0), Y(0), X(y1), Y(0), HEX["desk"], 1.2)
    svg.text(X(y0) + 4, Y(0) + 15, "desk (W z = 0)", 11, HEX["desk"])
    # columns
    for ya, yb, za, zb in cols_b:
        svg.rect(X(ya), Y(zb), (yb - ya) * S + 0.3, (zb - za) * S, HEX["base"])
    for ya, yb, za, zb in cols_p:
        svg.rect(X(ya), Y(zb), (yb - ya) * S + 0.3, (zb - za) * S, HEX["plate_edge"])
    # the seats, outlined, and the keys inside them
    c = p.spline_clear
    sy0, sy1, sz1 = p.spline_y[0] - c, p.spline_y[1] + c, p.spline_t + c
    svg.rect(X(sy0), Y(sz1), (sy1 - sy0) * S, (sz1 - 0) * S, "none", HEX["key_dark"], 1.4, "5 3")
    svg.rect(X(p.spline_y[0]), Y(p.spline_t), (p.spline_y[1] - p.spline_y[0]) * S, p.spline_t * S, HEX["key"],
             opacity=0.9)
    kc = p.topkey_clear
    t = p.topkey_t + kc
    corners = [p.to_world(x_cut, y, z)[1:] for y, z in ((p.topkey_y[0] - kc, p.h_top - t), (p.topkey_y[1] + kc, p.h_top - t),
                                                         (p.topkey_y[1] + kc, p.h_top), (p.topkey_y[0] - kc, p.h_top))]
    svg.path("M " + " L ".join(f"{X(y):.2f} {Y(z):.2f}" for y, z in corners) + " Z", "none", HEX["key_dark"], 1.4, "5 3")
    kz0 = p.h_top - p.topkey_t - kc
    key = [p.to_world(x_cut, y, z)[1:] for y, z in ((p.topkey_y[0], kz0), (p.topkey_y[1], kz0),
                                                    (p.topkey_y[1], kz0 + p.topkey_t), (p.topkey_y[0], kz0 + p.topkey_t))]
    svg.path("M " + " L ".join(f"{X(y):.2f} {Y(z):.2f}" for y, z in key) + " Z", HEX["key"], opacity=0.9)
    # cable port
    cy0, cy1 = p.ext_cable_y
    svg.rect(X(cy0), Y(p.ext_cable_z1), (cy1 - cy0) * S, (p.ext_cable_z1 - p.ext_cable_z0) * S, "none", HEX["dim"],
             0.9, "3 3")

    # labels: a column each side (anchored at xl / xr), two on the top row
    y_end = p.to_world(0, p.oy1, p.h_top)[1]
    y_front = p.to_world(0, p.oy0, p.h_top)[1]
    top_front = p.to_world(0, p.oy0, p.h_top + p.plate_t)
    xl, xr, yt = X(y0) - 12, X(y1) + 12, oy - 16

    def left(z_row, lines, size=12):
        for i, s in enumerate(lines):
            svg.text(xl, Y(z_row) + 4 + 14 * i, s, size if i == 0 else 10.5, HEX["ink"] if i == 0 else HEX["dim"], "end")

    def right(z_row, lines, size=12):
        for i, s in enumerate(lines):
            svg.text(xr, Y(z_row) + 4 + 14 * i, s, size if i == 0 else 10.5, HEX["ink"] if i == 0 else HEX["dim"], "start")

    # left column
    sc = p.screws[0]
    scw = p.to_world(sc[0], sc[1], p.h_top + p.plate_t)
    svg.leader(X(scw[1]), Y(scw[2]) - 1, xl + 4, Y(22.0), "", dot=True)
    left(22.0, [f"plate screw recess, {p.plate_cbore_d:g} dia x {p.plate_cbore_depth:g} deep",
                f"over a {p.plate_hole_d:g} mm hole and a {p.pilot_d:g} mm pilot"])
    svg.leader(X(y_front + 1.2), Y(12.5), xl + 4, Y(13.5), "", dot=True)
    left(13.5, ["front wall: the only full-depth material", "from the desk to the rim, so both joints live here"])
    svg.leader(X((p.spline_y[0] + p.spline_y[1]) / 2), Y(p.spline_t / 2), xl + 4, Y(5.0), "", dot=True)
    left(5.0, [f"spline, {p.spline_t:g} tall, {p.spline_clear:g} clearance all round",
               f"seat W y {sy0:g}..{sy1:g}, z 0..{sz1:g}",
               f"{p.spline_x_in:g} mm into the cradle, {p.spline_x_out:g} into the extender"])
    # top row
    kyc, kzc = p.to_world(x_cut, (p.topkey_y[0] + p.topkey_y[1]) / 2, kz0 + p.topkey_t / 2)[1:]
    svg.leader(X(kyc), Y(kzc), X(kyc) - 24, yt + 4, "", dot=True)
    svg.text(X(kyc) - 28, yt + 4, f"top key, {p.topkey_t:g} thick, {p.topkey_clear:g} clearance all round", 12, HEX["ink"], "end")
    svg.text(X(kyc) - 28, yt + 18, f"seat P y {p.topkey_y[0] - kc:g}..{p.topkey_y[1] + kc:g}, {t:g} deep, trapped by the plate",
             10.5, HEX["dim"], "end")
    yp, zp = 22.0, p.h_top + p.plate_t * 0.5                    # a point inside the plate at W y = 22
    ct, st = math.cos(math.radians(p.tilt)), math.sin(math.radians(p.tilt))
    pz = p.to_world(0, p.y_cut + (yp - p.y_cut + zp * st) / ct, zp)[2]
    svg.leader(X(yp), Y(pz), X(yp) + 24, yt + 4, "", dot=True)
    svg.text(X(yp) + 28, yt + 4, f"face plate, {p.plate_t:g} mm, screwed to the rim", 12, HEX["ink"], "start")
    svg.text(X(yp) + 28, yt + 18, f"rim = plate underside = P z {p.h_top:g}, tilted {p.tilt:g} deg", 10.5, HEX["dim"], "start")
    # right column
    tip_y, tip_z = p.to_world(0, p.lip_curve(48)[-1][0], p.h_top + p.lip_curve(48)[-1][1])[1:]
    svg.leader(X(tip_y), Y(tip_z), xr - 4, Y(27.0), "", dot=True)
    right(27.0, [f"plate lip: {p.lip_angle:g} deg turn, R {p.lip_R:g} -> {p.lip_R_end:g}",
                 f"tip {y_end - tip_y:+.1f} mm from the end face"])
    svg.leader(X(y_end + 1.0), Y(p.kb_cut_h_end - 2.0), xr - 4, Y(19.5), "", dot=True)
    right(19.5, [f"hook: +{p.hook_ext:g} along the arm, {p.hook_drop:g} drop, {p.hook_t:g} thick",
                 f"on this cradle only over the side walls ({p.hook_side_w:g} mm)"])
    svg.leader(X(y_end - 6.0), Y(4.0), xr - 4, Y(12.0), "", dot=True)
    right(12.0, [f"keyboard undercut, {p.kb_cut_len:g} along the desk",
                 f"{p.kb_cut_h_inner:g} tall inside, {p.kb_cut_h_end:g} at the end face (traced K70 lip)"])
    svg.leader(X((cy0 + cy1) / 2), Y((p.ext_cable_z0 + p.ext_cable_z1) / 2), xr - 4, Y(4.5), "", dot=True)
    right(4.5, [f"cable port {cy1 - cy0:g} x {p.ext_cable_z1 - p.ext_cable_z0:g}",
                "same section runs on through the extenders"])
    # dims
    svg.dim_v(X(y1) + 300, Y(bb_b.max.Z), Y(0), f"{bb_b.max.Z:.1f} top", 11, side=1)
    svg.dim_v(X(y0) - 300, Y(top_front[2]), Y(0), f"{top_front[2]:.1f} front", 11, side=1)
    svg.dim_h(X(y_front), X(y_end), Y(zlo) + 34, f"{y_end - y_front:.1f} rim, user edge to keyboard end face", 11, above=False)
    svg.text(X(y0), Y(zlo) + 78, "<- user side", 12, HEX["dim"])
    svg.text(X(y1), Y(zlo) + 78, "keyboard ->", 12, HEX["dim"], "end")
    svg.text(X((y0 + y1) / 2), Y(zlo) + 78, f"W y (mm), x = {x_cut:g}; tilt {p.tilt:g} deg", 12, HEX["dim"], "middle")
    # legend
    lx, ly = ox, H - 24
    svg.rect(lx, ly - 11, 14, 11, HEX["base"])
    svg.text(lx + 20, ly - 1, "cradle (base)", 12)
    svg.rect(lx + 130, ly - 11, 14, 11, HEX["plate_edge"])
    svg.text(lx + 150, ly - 1, "face plate", 12)
    svg.rect(lx + 240, ly - 11, 14, 11, HEX["key"])
    svg.text(lx + 260, ly - 1, "joint keys, in their seats", 12)
    svg.rect(lx + 430, ly - 11, 14, 11, "none", HEX["key_dark"], 1.2, "4 2")
    svg.text(lx + 450, ly - 1, "seat (rebate) outline", 12)
    svg.rect(lx + 610, ly - 11, 14, 11, "none", HEX["dim"], 0.9, "3 3")
    svg.text(lx + 630, ly - 1, "cable port", 12)
    svg.save(path)
    return len(cols_b), len(cols_p)


def plan_svg(dock, path):
    """Plan view (W, from above) of the four pieces, to scale, with both connectors at each seam."""
    S = 3.0
    pieces = {n: extender.span(xi, xo) for n, xi, xo, _s, _t in extender.pieces()}
    pieces["cradle"] = (p.ox0, p.ox1)
    xmin = min(v[0] for v in pieces.values())
    xmax = max(v[1] for v in pieces.values())
    ymin = min(float(b.bounding_box().min.Y) for b in list(dock.base.values()) + list(dock.plate.values()))
    ymax = max(float(b.bounding_box().max.Y) for b in list(dock.base.values()) + list(dock.plate.values()))
    ox, oy = 70.0, 150.0
    W = int(ox * 2 + (xmax - xmin) * S)
    H = int(oy + (ymax - ymin) * S + 300)
    svg = SVG(W, H, "Plan view of the dock: four pieces across 439 mm")

    def X(xw):
        return ox + (xw - xmin) * S

    def Y(yw):
        return oy + (ymax - yw) * S

    cos_t = math.cos(math.radians(p.tilt))
    y_rim_front = p.to_world(0, p.oy0, p.h_top)[1]
    y_rim_end = p.to_world(0, p.oy1, p.h_top)[1]
    y_plate_front = p.to_world(0, p.oy0, p.h_top + p.plate_t)[1]
    svg.text(ox, 34, f"Plan view - the four pieces across {xmax - xmin:.0f} mm, to scale", 20, weight="600")
    svg.text(ox, 54, "std height, hook, palm plate. Plates drawn translucent so the joints under them show; "
             "dashed = hidden (under the plate or inside the base).", 12, HEX["dim"])

    def rounded(x0, x1, ya, yb, r):
        rx, ry = r * S, r * cos_t * S
        X0, X1, Ya, Yb = X(x0), X(x1), Y(yb), Y(ya)          # Ya is the top (keyboard) edge in px
        return (f"M {X0 + rx:.2f} {Ya:.2f} L {X1 - rx:.2f} {Ya:.2f} A {rx:.2f} {ry:.2f} 0 0 1 {X1:.2f} {Ya + ry:.2f} "
                f"L {X1:.2f} {Yb - ry:.2f} A {rx:.2f} {ry:.2f} 0 0 1 {X1 - rx:.2f} {Yb:.2f} L {X0 + rx:.2f} {Yb:.2f} "
                f"A {rx:.2f} {ry:.2f} 0 0 1 {X0:.2f} {Yb - ry:.2f} L {X0:.2f} {Ya + ry:.2f} A {rx:.2f} {ry:.2f} 0 0 1 "
                f"{X0 + rx:.2f} {Ya:.2f} Z")

    # bases: body outline + hook beyond the end face
    for n, (x0, x1) in pieces.items():
        svg.path(rounded(x0, x1, y_rim_front, y_rim_end, p.corner_r), HEX["base"], HEX["ink"], 0.8)
        bb = dock.base[n].bounding_box()
        bands = cradle.hook_bands() if n == "cradle" else [(x0, x1)]
        for bx0, bx1 in bands:
            svg.rect(X(bx0), Y(float(bb.max.Y)), (bx1 - bx0) * S, (float(bb.max.Y) - y_rim_end) * S, HEX["base_dark"],
                     HEX["ink"], 0.8)
    # hidden features of the cradle
    px0, py0, px1, py1 = p.pocket
    pocket_y0 = p.to_world(0, py0, 0)[1]
    svg.rect(X(px0), Y(y_rim_end), (px1 - px0) * S, (y_rim_end - pocket_y0) * S, "none", HEX["ink"], 0.7, "4 3")
    svg.rect(X(-p.notch_d / 2), Y(pocket_y0), p.notch_d * S, (pocket_y0 - y_rim_front) * S, "none", HEX["ink"], 0.7, "4 3")
    bay_x1 = p.ox1 - p.wall
    bay_x0 = bay_x1 - p.jds_wh[0]
    bay_y1 = min(y_rim_end - p.jds_end_skin, y_rim_end - p.kb_cut_len)
    bay_y0 = y_rim_end - p.jds_end_skin - p.jds_wh[1]
    svg.rect(X(bay_x0), Y(bay_y1), (bay_x1 - bay_x0) * S, (bay_y1 - bay_y0) * S, "none", HEX["ink"], 0.7, "2 3")
    cy0, cy1 = p.ext_cable_y
    for x0, x1 in ((pieces["left"][0], p.ox0), (bay_x1, xmax)):
        for yy in (cy0, cy1):
            svg.line(X(x0), Y(yy), X(x1), Y(yy), HEX["ink"], 0.7, "2 3")
    # plates
    for n, (x0, x1) in pieces.items():
        bb = dock.plate[n].bounding_box()
        svg.path(rounded(x0, x1, y_plate_front, float(bb.max.Y), p.corner_r), HEX["plate"], HEX["plate_edge"], 0.8,
                 opacity=0.78)
    # plate openings (palm plate) in W
    def wy(yp, z=p.h_top + p.plate_t):
        return p.to_world(0, yp, z)[1]
    tp_w = p.touchpad_wh[0] + p.hole_clear
    tp_y0 = p.touchpad_c[1] - (p.touchpad_wh[1] + p.hole_clear) / 2 - p.tp_notch_drop
    svg.rect(X(p.touchpad_c[0] - tp_w / 2), Y(float(dock.plate["cradle"].bounding_box().max.Y)), tp_w * S,
             (float(dock.plate["cradle"].bounding_box().max.Y) - wy(tp_y0)) * S, HEX["hole"], HEX["plate_edge"], 0.8)
    r_st = (p.stick_d + p.hole_clear + p.stick_travel) / 2
    for cx, cy in (p.stick_l, p.stick_r):
        svg.ellipse(X(cx), Y(wy(cy)), r_st * S, r_st * cos_t * S, HEX["hole"], HEX["plate_edge"], 0.8)
    for cx, cy in (p.share, p.options):
        svg.rect(X(cx - p.so_slot_w / 2), Y(wy(cy + p.so_slot_len / 2)), p.so_slot_w * S, p.so_slot_len * cos_t * S,
                 HEX["hole"], HEX["plate_edge"], 0.8, rx=p.so_slot_w / 2 * S)
    # plate screws
    for n in pieces:
        for x, y, _c in dock.pilots(n):
            svg.circle(X(x), Y(p.to_world(x, y, p.h_top)[1]), 1.6, HEX["bg"], HEX["ink"], 0.8)
    # connectors at each seam
    kz = p.h_top - p.topkey_t - p.topkey_clear
    for label_, xs, lo, hi, dockside in checks.seams():
        dock_lo = (dockside == lo)
        sx0, sx1 = (xs - p.spline_x_in, xs + p.spline_x_out) if dock_lo else (xs - p.spline_x_out, xs + p.spline_x_in)
        kx0, kx1 = (xs - p.topkey_x_in, xs + p.topkey_x_out) if dock_lo else (xs - p.topkey_x_out, xs + p.topkey_x_in)
        svg.rect(X(sx0), Y(p.spline_y[1]), (sx1 - sx0) * S, (p.spline_y[1] - p.spline_y[0]) * S, HEX["key"],
                 HEX["key_dark"], 0.9, "3 2", opacity=0.9)
        ky1, ky0 = p.to_world(0, p.topkey_y[1], kz)[1], p.to_world(0, p.topkey_y[0], kz)[1]
        svg.rect(X(kx0), Y(ky1), (kx1 - kx0) * S, (ky1 - ky0) * S, HEX["key"], HEX["key_dark"], 0.9, "3 2", opacity=0.9)
        ym = (p.spline_y[0] + p.spline_y[1]) / 2
        for sxx in ((xs - p.spline_screw_in, xs + p.spline_screw_out) if dock_lo else
                    (xs + p.spline_screw_in, xs - p.spline_screw_out)):
            svg.circle(X(sxx), Y(ym), 1.9, HEX["bg"], HEX["key_dark"], 0.9)
            svg.line(X(sxx) - 1.3, Y(ym) - 1.3, X(sxx) + 1.3, Y(ym) + 1.3, HEX["key_dark"], 0.7)
            svg.line(X(sxx) - 1.3, Y(ym) + 1.3, X(sxx) + 1.3, Y(ym) - 1.3, HEX["key_dark"], 0.7)
        svg.line(X(xs), Y(ymax) - 8, X(xs), Y(ymin) + 8, HEX["ink"], 1.0)
    # labels: two rows above the drawing, two below, the touchpad named inside its own window
    top = oy - 8
    seam_r = p.ox1
    row1, row2 = top - 20, top - 44
    svg.leader(X(pieces["left"][0] + 40), Y(float(dock.base["left"].bounding_box().max.Y) - 1.5), X(pieces["left"][0] + 40), row1,
               f"hook: {p.hook_t:g} thick, {p.hook_drop:g} drop - the whole length of the extenders, "
               f"the side walls only ({p.hook_side_w:g} mm) on the cradle", 12, "start")
    svg.leader(X(xmax - 40), Y((cy0 + cy1) / 2), X(xmax - 40), row1,
               f"cable channel {cy1 - cy0:g} x {p.ext_cable_z1 - p.ext_cable_z0:g}, right end to the bay", 12, "end")
    svg.leader(X(seam_r + 5), Y(p.to_world(0, (p.topkey_y[0] + p.topkey_y[1]) / 2, kz)[1]), X(seam_r + 5), row2,
               f"top key {p.topkey_x_in + p.topkey_x_out:g} x {p.topkey_y[1] - p.topkey_y[0]:g} x {p.topkey_t:g}, "
               f"in a rebate in the rim, under the plate - one per seam, no screw", 12, "start")
    svg.text(X(p.touchpad_c[0]), Y(wy(p.touchpad_c[1] + 2.0)) + 4, "touchpad window", 11, HEX["dim"], "middle")
    rowb1, rowb2 = Y(ymin) + 46, Y(ymin) + 72
    svg.leader(X(0), Y((pocket_y0 + y_rim_front) / 2), X(0), rowb1, f"finger notch, {p.notch_d:g} wide", 12, "middle")
    svg.leader(X(seam_r + 10), Y((p.spline_y[0] + p.spline_y[1]) / 2), X(seam_r + 60), rowb1,
               f"spline {p.spline_x_in + p.spline_x_out:g} x {p.spline_y[1] - p.spline_y[0]:g} x {p.spline_t:g} in the front wall, "
               f"2 x M3 up from the desk (x = seam {-p.spline_screw_in:+g} / {p.spline_screw_out:+g}) - one per seam", 12, "start")
    svg.leader(X((bay_x0 + bay_x1) / 2), Y((bay_y0 + bay_y1) / 2), X(bay_x1 - 10), rowb2,
               f"charging-board bay under the floor ({p.jds_wh[0]:g} x {p.jds_wh[1]:g} is ASSUMED; the undercut takes its keyboard end)",
               12, "end")
    # dimensions below
    yd = Y(ymin) + 104
    for n, (x0, x1) in sorted(pieces.items(), key=lambda kv: kv[1][0]):
        svg.dim_h(X(x0), X(x1), yd, f"{x1 - x0:g}", 12, above=False)
        svg.text(X((x0 + x1) / 2), yd + 32, n, 12, HEX["ink"], "middle", weight="600")
    svg.dim_h(X(xmin), X(xmax), yd + 60, f"{xmax - xmin:g} mm overall (the K70 is 437)", 12, above=False)
    svg.dim_v(X(xmax) + 24, Y(ymax), Y(ymin), f"{ymax - ymin:.1f}", 11, side=1)
    svg.text(X(xmax) + 24, Y(ymin) + 18, "depth incl. hook", 10.5, HEX["dim"], "end")
    svg.text(ox, Y(ymax) - 10, "keyboard side", 11, HEX["dim"])
    svg.text(ox, Y(ymin) + 16, "user side", 11, HEX["dim"])
    # scale bar + legend
    sb_y = H - 30
    svg.line(ox, sb_y, ox + 50 * S, sb_y, HEX["ink"], 2)
    for xx in (ox, ox + 50 * S):
        svg.line(xx, sb_y - 5, xx, sb_y + 5, HEX["ink"], 1)
    svg.text(ox + 25 * S, sb_y - 8, "50 mm", 11, HEX["ink"], "middle")
    lx = ox + 230
    svg.rect(lx, sb_y - 10, 14, 11, HEX["base"], HEX["ink"], 0.6)
    svg.text(lx + 20, sb_y, "base (hook darker)", 12)
    svg.rect(lx + 160, sb_y - 10, 14, 11, HEX["plate"], HEX["plate_edge"], 0.8)
    svg.text(lx + 180, sb_y, "face plate", 12)
    svg.rect(lx + 270, sb_y - 10, 14, 11, HEX["key"], HEX["key_dark"], 0.8)
    svg.text(lx + 290, sb_y, "joint keys (two per seam)", 12)
    svg.circle(lx + 480, sb_y - 4.5, 2.2, HEX["bg"], HEX["ink"], 0.8)
    svg.text(lx + 490, sb_y, f"plate screws, {sum(len(dock.pilots(n)) for n in pieces)} off", 12)
    svg.rect(lx + 660, sb_y - 10, 14, 11, "none", HEX["ink"], 0.7, "4 3")
    svg.text(lx + 680, sb_y, "hidden: pocket, notch, bay, cable channel", 12)
    svg.save(path)


# ---- main -----------------------------------------------------------------------------------

ALL = ("hero", "exploded", "variants", "faceplates", "seam", "plan")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the docs images from the CAD sources (see the module docstring).")
    ap.add_argument("--only", nargs="*", choices=ALL, default=list(ALL), metavar="NAME",
                    help="which images: " + " ".join(ALL))
    ap.add_argument("--out", default=OUT_DIR, help="output folder (default: the repo's docs/images)")
    ap.add_argument("--scale", type=float, default=1.0, help="PNG size factor, for quick previews")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    want = set(a.only)
    t0 = time.time()

    def done(name, extra=""):
        path = os.path.join(a.out, name)
        print(f"  {name:18s} {os.path.getsize(path) / 1e3:7.1f} kB  {extra}  ({time.time() - t0:.0f} s)", flush=True)

    dock = None
    if want & {"hero", "exploded", "seam", "plan"}:
        print("building the assembled dock (std, hook, palm) ...", flush=True)
        dock = dock_std()
    if "hero" in want:
        img = render(hero_meshes(dock), Camera(32, 27), int(2000 * a.scale))
        img.save(os.path.join(a.out, "hero.png"))
        done("hero.png", f"{img.width} x {img.height}")
    if "exploded" in want:
        img = render(exploded_meshes(dock), Camera(32, 33), int(2000 * a.scale))
        img.save(os.path.join(a.out, "exploded.png"))
        done("exploded.png", f"{img.width} x {img.height}")
    if "seam" in want:
        nb, npl = seam_section_svg(dock, os.path.join(a.out, "seam_section.svg"))
        done("seam_section.svg", f"{nb} base + {npl} plate columns")
    if "plan" in want:
        plan_svg(dock, os.path.join(a.out, "plan.svg"))
        done("plan.svg")
    if "variants" in want:
        img = variants_image(int(2000 * a.scale), a.scale)
        img.save(os.path.join(a.out, "variants.png"))
        done("variants.png", f"{img.width} x {img.height}")
    if "faceplates" in want:
        img = faceplates_image(int(2000 * a.scale), a.scale)
        img.save(os.path.join(a.out, "faceplates.png"))
        done("faceplates.png", f"{img.width} x {img.height}")
    print(f"done in {time.time() - t0:.0f} s -> {os.path.relpath(a.out, os.getcwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
