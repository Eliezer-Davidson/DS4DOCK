"""Build the whole STL matrix into stl/: every printable part of the dock, in every variant.

    python cad/variants.py                      # everything (34 files, about a minute)
    python cad/variants.py --only cradle        # only files whose path contains "cradle"
    python cad/variants.py --only "*_std_hook"  # or matches a glob (fnmatch on the file stem)
    python cad/variants.py --list               # print the catalogue, build nothing
    python cad/variants.py --out some/dir       # write elsewhere (default: <repo>/stl)

Axes, in dock_params names:
    height       floor_h      low 1.0 | std 2.0 | tall 3.5      the dock's height above the desk
    hook         hook         hook True | nohook False          the lip that hangs on the keyboard
    plate style  plate_style  palm | full                      face buttons filled, or every control open
std + hook + palm is the printed, proven configuration; every other combination is generated from the
same sources and has not been printed.

Files (34):
    stl/cradle/cradle_{low|std|tall}_{hook|nohook}.stl                        6
    stl/faceplate/faceplate_{palm|full}.stl                                   2  height-independent
    stl/extenders/{left|right1|right2}_base_{low|std|tall}_{hook|nohook}.stl 18
    stl/extenders/{left|right1|right2}_plate.stl                              3  height-independent
    stl/joint/spline.stl  stl/joint/topkey.stl                                2
    stl/caps/stick_cap_{tight|nominal|loose}.stl    socket +0.0 / +0.25 / +0.5 mm   3

Every file is binary STL (tolerance 0.05 mm, angular tolerance 0.3 rad) holding ONE solid, in PRINT
ORIENTATION: bottom on the bed (z = 0) and the footprint centred on the origin. The cradle, the
bases, the keys and the caps print as modelled; the plates are flipped face-down - finished face on
the textured sheet, lip rising - exactly as plate v9 was printed. World positions are therefore not
preserved in the files; the Python sources are the assembly reference (checks.py builds the
assembled dock from them, and build() here returns the as-modelled part too).

Every export is verified twice: the B-rep before tessellation (is_valid, exactly one solid) and the
written file after it (closed, consistently oriented, one connected shell, volume within 1 % of the
B-rep's). Exit status is non-zero if any file fails either test.
"""
import argparse
import fnmatch
import os
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build123d import Pos, Rot, export_stl  # noqa: E402

import cradle  # noqa: E402
import dock_params as p  # noqa: E402
import extender  # noqa: E402
import faceplate  # noqa: E402
import stick_cap  # noqa: E402

CAD_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(CAD_DIR)
STL_DIR = os.path.join(REPO_DIR, "stl")

HEIGHTS = {"low": 1.0, "std": 2.0, "tall": 3.5}           # floor_h
HOOKS = {"hook": True, "nohook": False}                     # hook
PLATE_STYLES = ("palm", "full")                             # plate_style
CAP_FITS = {"tight": 0.0, "nominal": 0.25, "loose": 0.5}    # stick_cap.make_cap(clear)
PRINTED = ("std", "hook", "palm")                           # the configuration that exists in PETG
STL_TOLERANCE, STL_ANGULAR = 0.05, 0.3
VOLUME_TOLERANCE = 0.01                                     # mesh volume vs B-rep volume, relative


@dataclass
class Variant:
    path: str                       # relative to the stl/ root, forward slashes
    kind: str                       # cradle | faceplate | base | plate | key | cap
    build: Callable[[], object]     # the part in its modelled frame, after configure()
    config: dict = field(default_factory=dict)   # dock_params overrides for this file
    note: str = ""

    @property
    def stem(self):
        return os.path.splitext(os.path.basename(self.path))[0]


def configure(height="std", hook="hook", plate_style="palm"):
    """Switch dock_params to one cell of the matrix, by the names used in the file names."""
    p.configure(floor_h=HEIGHTS[height], hook=HOOKS[hook], plate_style=plate_style)


def _piece(name):
    for n, xi, xo, sgn, to in extender.pieces():
        if n == name:
            return xi, xo, sgn, to
    raise KeyError(name)


def catalogue():
    """Every file of the matrix, in a fixed order. Each entry's config names the dock_params
    overrides it needs; everything else is the module default (the printed configuration)."""
    out = []
    for h in HEIGHTS:
        for k in HOOKS:
            out.append(Variant(f"cradle/cradle_{h}_{k}.stl", "cradle", cradle.make_cradle,
                               {"floor_h": HEIGHTS[h], "hook": HOOKS[k]},
                               f"floor_h {HEIGHTS[h]}, hook {HOOKS[k]}"))
    for s in PLATE_STYLES:
        out.append(Variant(f"faceplate/faceplate_{s}.stl", "faceplate", faceplate.make_faceplate,
                           {"plate_style": s}, f"plate_style {s}"))
    names = [q[0] for q in extender.pieces()]
    for n in names:
        for h in HEIGHTS:
            for k in HOOKS:
                out.append(Variant(f"extenders/{n}_base_{h}_{k}.stl", "base",
                                   lambda n=n: extender.make_base(n, *_piece(n)),
                                   {"floor_h": HEIGHTS[h], "hook": HOOKS[k]},
                                   f"floor_h {HEIGHTS[h]}, hook {HOOKS[k]}"))
    for n in names:
        out.append(Variant(f"extenders/{n}_plate.stl", "plate",
                           lambda n=n: extender.make_plate(n, *_piece(n)), {}, "height-independent"))
    out.append(Variant("joint/spline.stl", "key", cradle.make_spline, {}, "one per seam, 3 seams"))
    out.append(Variant("joint/topkey.stl", "key", cradle.make_topkey, {}, "one per seam, 3 seams"))
    for f, clear in CAP_FITS.items():
        out.append(Variant(f"caps/stick_cap_{f}.stl", "cap", lambda c=clear: stick_cap.make_cap(c), {},
                           f"socket {stick_cap.socket_wl[0] + clear:.2f} x {stick_cap.socket_wl[1] + clear:.2f}"))
    return out


def get(stem_or_path):
    """The catalogue entry for a file stem ("cradle_std_hook") or relative path."""
    for v in catalogue():
        if v.stem == stem_or_path or v.path == stem_or_path.replace("\\", "/"):
            return v
    raise KeyError(stem_or_path)


def select(patterns):
    """Catalogue entries whose path contains any pattern as a substring, or whose stem/path matches
    it as a glob. No patterns = everything."""
    cat = catalogue()
    if not patterns:
        return cat
    out = []
    for v in cat:
        for pat in patterns:
            if pat in v.path or fnmatch.fnmatch(v.stem, pat) or fnmatch.fnmatch(v.path, pat):
                out.append(v)
                break
    return out


def drop(part):
    """Footprint centred on the origin, lowest point on z = 0."""
    b = part.bounding_box()
    return Pos(-b.center().X, -b.center().Y, -b.min.Z) * part


def for_print(part, kind):
    """Print orientation. Plates are modelled in P with the underside at z = 0 and the lip hanging
    below it; printed they go face-down on the textured sheet, so flip them. Everything else is
    modelled the way it prints."""
    if kind in ("faceplate", "plate"):
        part = Rot(X=180) * part
    return drop(part)


def build(v):
    """(as_modelled, printable) for one catalogue entry. Leaves dock_params configured for it."""
    p.configure(**{"floor_h": HEIGHTS["std"], "hook": HOOKS["hook"], "plate_style": "palm", **v.config})
    part = v.build()
    return part, for_print(part, v.kind)


# ---- the written file -------------------------------------------------------------------------

def mesh_report(path):
    """Read a binary STL and measure it without any CAD library: triangle count, signed volume,
    surface area, whether it is closed and consistently oriented (every directed edge used exactly
    once, with its reverse also used exactly once), and the number of connected shells. Vertices
    are matched after rounding to 1e-5 mm. Degenerate (zero-area) triangles are counted and then
    ignored, as a slicer ignores them; they carry no surface."""
    import numpy as np
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 84:
        raise ValueError(f"{path}: too short for a binary STL")
    n = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * n:
        raise ValueError(f"{path}: not a binary STL (declares {n} triangles, size {len(data)})")
    dt = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    tri = np.frombuffer(data, dtype=dt, count=n, offset=84)["v"].astype(np.float64)
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    volume = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)
    area = float(0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1).sum())
    pts = np.round(tri.reshape(-1, 3), 5)
    uniq, inv = np.unique(pts, axis=0, return_inverse=True)
    faces = inv.reshape(-1, 3)
    nv = len(uniq)
    degenerate_mask = ((faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) |
                       (faces[:, 0] == faces[:, 2]))
    degenerate = int(degenerate_mask.sum())
    faces = faces[~degenerate_mask]
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]).astype(np.int64)
    fwd = e[:, 0] * nv + e[:, 1]
    rev = e[:, 1] * nv + e[:, 0]
    duplicates = int(len(fwd) - len(np.unique(fwd)))
    closed = duplicates == 0 and bool(np.array_equal(np.sort(fwd), np.sort(rev)))
    # connected shells: min-label propagation over the vertex graph
    labels = np.arange(nv)
    for _ in range(100000):
        m = np.minimum(labels[e[:, 0]], labels[e[:, 1]])
        new = labels.copy()
        np.minimum.at(new, e[:, 0], m)
        np.minimum.at(new, e[:, 1], m)
        new = new[new]
        if np.array_equal(new, labels):
            break
        labels = new
    shells = int(len(np.unique(labels[faces.ravel()])))
    lo, hi = tri.reshape(-1, 3).min(axis=0), tri.reshape(-1, 3).max(axis=0)
    return {"triangles": int(n), "volume": volume, "area": area, "closed": closed,
            "duplicate_edges": duplicates, "degenerate": degenerate, "shells": shells,
            "size": tuple(float(x) for x in (hi - lo)), "min": tuple(float(x) for x in lo),
            "bytes": len(data)}


def mesh_ok(rep, brep_volume=None):
    """One closed, consistently oriented shell; optionally within VOLUME_TOLERANCE of the B-rep."""
    ok = rep["closed"] and rep["shells"] == 1 and rep["volume"] > 0
    if brep_volume is not None and brep_volume > 0:
        ok = ok and abs(rep["volume"] - brep_volume) / brep_volume <= VOLUME_TOLERANCE
    return ok


# ---- building ---------------------------------------------------------------------------------

def export(v, out_root=STL_DIR):
    """Build one entry, verify the B-rep, write the STL, verify the file. Returns a result dict."""
    t0 = time.time()
    path = os.path.join(out_root, *v.path.split("/"))
    try:
        part, printable = build(v)
    except Exception as ex:                          # report, never abort the matrix
        return {"variant": v, "path": path, "valid": False, "solids": 0, "brep_volume": 0.0, "mesh": None,
                "error": f"build failed: {type(ex).__name__}: {ex}", "ok": False, "seconds": time.time() - t0}
    valid, nsol = bool(printable.is_valid), len(printable.solids())
    brep_vol = float(printable.volume)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rep, err = None, None
    if valid and nsol == 1:
        try:
            export_stl(printable, path, tolerance=STL_TOLERANCE, angular_tolerance=STL_ANGULAR)
            rep = mesh_report(path)
        except Exception as ex:                      # report, never abort the matrix
            err = f"{type(ex).__name__}: {ex}"
    else:
        err = f"B-rep not exportable: valid={valid} solids={nsol}"
    ok = err is None and mesh_ok(rep, brep_vol)
    return {"variant": v, "path": path, "valid": valid, "solids": nsol, "brep_volume": brep_vol,
            "mesh": rep, "error": err, "ok": ok, "seconds": time.time() - t0}


def _fmt_row(r):
    v, rep = r["variant"], r["mesh"]
    if rep is None:
        return f"{v.path:44s} FAIL  {r['error']}"
    sx, sy, sz = rep["size"]
    dv = (rep["volume"] - r["brep_volume"]) / r["brep_volume"] * 100 if r["brep_volume"] else 0.0
    flag = "ok  " if r["ok"] else "FAIL"
    mesh = "closed" if rep["closed"] else f"OPEN({rep['duplicate_edges']} dup edges)"
    if rep["degenerate"]:
        mesh += f", {rep['degenerate']} degenerate"
    return (f"{v.path:44s} {flag}  {rep['triangles']:7d} tri  {rep['bytes'] / 1e6:5.2f} MB  "
            f"{sx:6.1f} x {sy:5.1f} x {sz:5.1f} mm  {r['brep_volume'] / 1000:7.2f} cm3 ({dv:+.2f}%)  "
            f"{mesh}, {rep['shells']} shell  {r['seconds']:4.1f}s")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the dock's STL matrix (see the module docstring).")
    ap.add_argument("--only", action="append", default=[], metavar="PATTERN",
                    help="build only files whose path contains PATTERN, or whose stem matches it as a glob; "
                         "repeatable")
    ap.add_argument("--out", default=STL_DIR, help="output root (default: the repo's stl/ folder)")
    ap.add_argument("--list", action="store_true", help="print the catalogue and exit")
    a = ap.parse_args(argv)

    chosen = select(a.only)
    if a.list or not chosen:
        for v in catalogue():
            print(f"{v.path:44s} {v.kind:9s} {v.note}")
        if not chosen and a.only:
            print(f"\nnothing matches {a.only}", file=sys.stderr)
            return 2
        return 0

    print(f"building {len(chosen)} file(s) into {os.path.relpath(a.out, os.getcwd()) or '.'}  "
          f"(STL tolerance {STL_TOLERANCE}, angular {STL_ANGULAR})\n")
    results = []
    for v in chosen:
        r = export(v, a.out)
        results.append(r)
        print(_fmt_row(r), flush=True)
    bad = [r for r in results if not r["ok"]]
    total = sum((r["mesh"] or {}).get("bytes", 0) for r in results)
    print(f"\n{len(results) - len(bad)} of {len(results)} files ok, {total / 1e6:.1f} MB, "
          f"{sum(r['seconds'] for r in results):.0f} s")
    for r in bad:
        print(f"  FAILED {r['variant'].path}: {r['error'] or 'mesh check failed: ' + str(r['mesh'])}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
