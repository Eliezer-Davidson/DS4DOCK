"""DS4 dock fit check (view/validation only, not printed): the cradle, the face plate on its rim
and the board as a 130 x 55 x stack_h block on the pocket floor, assembled in the world frame W.

Plain build123d, one process:
    python cad/dock_fit.py            # prints the interference volumes and the fit numbers
    python cad/dock_fit.py --step     # also writes cad/out/dock_fit.step (gitignored scratch)

The plate is built in P with its underside at z = 0 and the board block has its back at P z = 0,
so both are placed with the same P -> W transform the cradle was built with (dock_params.P), the
plate lifted to the rim (h_top). If anything here intersects, the real parts will too.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build123d import Box, Compound, Pos, RectangleRounded, extrude  # noqa: E402

import dock_params as p  # noqa: E402
from cradle import make_cradle  # noqa: E402
from faceplate import make_faceplate  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def make_board():
    """The board + midframe envelope: a rounded rectangle, stack_h tall, back face at P z = 0."""
    x0, y0 = -p.body_w / 2, p.body_bottom
    return extrude(Pos(x0 + p.body_w / 2, y0 + p.body_h / 2) * RectangleRounded(p.body_w, p.body_h, p.body_r),
                   p.stack_h)


def _vol(shape):
    return sum(s.volume for s in shape.solids()) if shape.solids() else 0.0


def make_assembly():
    """(cradle, plate, board) placed in W, plus a labelled Compound of the three."""
    cradle = make_cradle()
    plate = p.P * Pos(0, 0, p.h_top) * make_faceplate()
    board = p.P * make_board()
    cradle.label, plate.label, board.label = "cradle", "faceplate", "board_envelope_assumed"
    return cradle, plate, board, Compound(children=[cradle, plate, board], label="ds4_dock_fit")


def report(cradle, plate, board):
    print(f"configuration: {p.variant()}")
    print(f"plate x cradle interference          : {_vol(plate & cradle):8.3f} mm3")
    print(f"board x cradle interference          : {_vol(board & cradle):8.3f} mm3   "
          f"(pocket clearance {p.pocket_clear} mm per side)")
    # The block is a crude envelope, stack_h tall everywhere. The real touchpad's top curves down
    # over its last ~7 mm - that curve is what the plate's lip follows - so only the flat part of
    # the plate is a meaningful comparison; under the lip the block is known to be too tall.
    flat = p.P * Pos(0, (p.oy0 - 50 + p.lip_y_start) / 2, 0) * Box(400, p.lip_y_start - p.oy0 + 50, 200)
    print(f"board x plate, flat plate (P y < {p.lip_y_start:.0f}) : {_vol((board & flat) & plate):8.3f} mm3   "
          f"(must be 0; plate_gap {p.plate_gap} mm above the stack)")
    print(f"board x plate, under the lip         : {_vol((board - flat) & plate):8.3f} mm3   "
          f"(block ignores the touchpad's own curve; informational)")
    bb = Compound(children=[cradle, plate]).bounding_box()
    print(f"assembled dock envelope              : {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm "
          f"(x {bb.min.X:.1f}..{bb.max.X:.1f}, y {bb.min.Y:.1f}..{bb.max.Y:.1f})")


if __name__ == "__main__":
    cradle, plate, board, asm = make_assembly()
    report(cradle, plate, board)
    if "--step" in sys.argv[1:]:
        from build123d import export_step
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, "dock_fit.step")
        export_step(asm, path)
        print(f"wrote {os.path.relpath(path, os.path.dirname(OUT_DIR))}")
