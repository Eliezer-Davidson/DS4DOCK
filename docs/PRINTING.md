# Printing the frame

How the dock's parts print on a Bambu Lab A1 mini in PETG: material and settings, the orientation
of every part, where supports land and where they must not, the bed-fit rules, the three plates that
were actually printed, and a slicer-estimated time-and-grams table for every file in [`stl/`](../stl).

Contents: [Material and settings](#material-and-settings) · [Orientation and supports](#orientation-and-supports) ·
[Bed-fit rules](#bed-fit-rules) · [What was actually printed](#what-was-actually-printed) ·
[Every variant: time and grams](#every-variant-time-and-grams) · [Printed versus generated](#printed-versus-generated) ·
[Assembly notes](#assembly-notes) · [Assumed dimensions](#assumed-dimensions)

![The six cradle variants, same scale, seen from the keyboard side](images/variants.png)

## Material and settings

| | |
|---|---|
| Printer | Bambu Lab A1 mini, 0.4 mm nozzle, textured PEI plate (the stock sheet) |
| Material | Bambu PETG Basic, filament profile `Bambu PETG Basic @BBL A1M 0.4 nozzle`; bed 70 °C as the profile sets it |
| Process | `0.20mm Standard @BBL A1M`: 0.2 mm layers, 15 % sparse infill, 2 walls |
| Supports | `enable_support=1`, `support_type=tree(auto)`, `support_on_build_plate_only=1` - tree supports, grown from the bed only, never from the part |
| Slicer | Bambu Studio's command-line slicer, driven by a small local wrapper that is not part of this repository; the settings above are the whole recipe |

PETG, not PLA, since cradle v7: the palm rests a warm forearm on this thing for hours and PLA's creep
under that kind of load is not something I wanted to find out about. The design also leans on a few
short bridges that PETG handles: the roof of the cable channel spans the channel's 12.5 mm width, and
the roof of each spline seat, which opens at the bed, spans the seat's 10 mm width (the 9.5 mm key
plus 0.25 mm of clearance a side).

The prototypes that reached the printer between cradle v7 and the v11 set were sliced with **3 walls**
and `bridge_no_support=1` on top of the same profile. The table further down was sliced fresh for
this repository with the profile's own 2 walls, so that every variant is on one like-for-like footing;
expect a 3-wall print of the same file to take a little longer and weigh a little more.

## Orientation and supports

Every file in `stl/` is already in print orientation: lowest point on z = 0, footprint centred on the
origin. Drop it on the plate as it comes.

| part | orientation | support it needs | support it must not get |
|---|---|---|---|
| cradle, extender bases | bottom-down, as modelled: the flat underside on the bed, walls vertical, the 17° rim self-supporting | tree supports under the two floating arms of the **keyboard undercut** - the arm undersides rise from 10 to 18 mm over 14 mm, so the slicer grows support up to about z 17.6; the cradle also collects a few small towers in the charging bay, the LED notch and the cable notch, all reachable through their openings | nothing under the wrist surface (there is none in this orientation, which is why the extenders were split into base + plate); nothing inside the key seats - the spline seat opens at the bed and the top-key seat opens at the sky, by design |
| face plate, extender plates | **face-down**: the finished face on the textured sheet, so it carries the same texture as the dock around it; the curled lip rises away from the bed | a narrow band under the start of the lip, where the curve leaves the bed at a shallow angle (the slicer reports support up to z 0.6; on plate v9 it was an 8 mm wide, 1 mm tall strip) | nothing in the screw recesses: each 2 mm screw hole is closed by a 0.2 mm skin (`plate_hole_skin`) that prints as a tiny bridge, so no support grows into the 4 mm head recess - poke the skin through after printing |
| spline | standing on its underside, as modelled | the auto tree support puts a few blocks inside the two 5.6 mm counterbores (to z 2.0); they are optional - a 5.6 mm circular ceiling bridges fine in PETG | - |
| top key | flat, as modelled | none | - |
| stick caps | socket-down, as modelled; the dome tapers inward all the way up (its sphere centre is 0.09 mm *below* the bed, checked by `cad/checks.py` section f) | none | - |

Why the keyboard undercut needs support at all: it is a right trapezoid cut along the whole keyboard
side (14 mm along the desk, 10 mm tall at its inner edge, 18 mm at the end face, a 29.7° roof), so
the rims above it float. A 30° underside is below the usual 45° threshold and is exactly the kind of
surface tree supports are for. Everything else on the base is vertical or faces up.

## Bed-fit rules

- The nominal bed is 180 x 180 mm. **With tree supports on the plate, keep any one plate within
  149 x 144.5 mm** - that size sliced and printed; a 157 x 149 mm layout failed because the tree
  supports pushed the job off the bed.
- The cradle is 149 mm wide and is the widest single part. That number is also why the joint key is a
  loose spline: a tongue grown onto the cradle would have made it 185 mm wide.
- The right extender is 230 mm long and prints as two 115 mm halves (`ext_right_split = 2`), joined
  to each other exactly as they join the cradle. A 115 mm body and the 60 mm left base cannot share
  a row (they come to 179 mm with the spacing the supports need), which sets the plate count below.
- Three plates is the floor for a whole set: the parts total about 49,400 mm² of footprint against
  roughly 21,000 mm² usable per bed once tree supports have their room.

## What was actually printed

The v11 set went to the printer as three plates on 2026-10-12, every one read back from the printer
with its gcode MD5 matching the local slice and with no slicer warnings. It was printed and assembled
on 2026-10-21 and is in use; the photograph in the [README](../README.md) is that assembly.

| plate | contents | footprint | time | PETG |
|---|---|---|---|---|
| p1 | cradle v11 + left base + left plate + 4 top keys | 149 x 129 mm | 2 h 53 m | 70 g |
| p2 | right1 base + right1 plate + 4 splines + 3 caps | 148 x 129 mm | 2 h 50 m | 70 g |
| p3 | right2 base + right2 plate + 3 caps | 135 x 129 mm | 2 h 30 m | 64 g |
| | **21 bodies** | | **8 h 13 m** | **204.7 g** |

The face plate on it is plate v9, printed earlier from its own slice (face-down, 33 m 43 s, 13.4 g,
3 walls); v11 changed nothing about the plate, so it was not reprinted. Four keys of each kind were
printed for three seams, and six caps - two at each socket clearance - so the pair that grips could be
kept.

Before that, the parts that taught v11 what to fix were printed and handled: cradle v10, plate v9,
the one-piece v2 extenders that reached the printer - the left one, and the outermost right one
(`right2`), which came off without its keyboard undercut because the cut's extrude reach stopped at
x ±200 mm and that piece reaches x 304.5 (see [DESIGN.md](DESIGN.md#the-extrude-reach-bug)) - and
the v10 test plate. A v2 extender was one solid whose top was the wrist surface itself, printed face
down; in that orientation most of the wrist surface sits on support rather than on the sheet, and
the pieces came out smooth where the dock is textured and did not sit flush. That is why v3 split
every extender into a base and its own plate. The support figures that go with this come from the
v1 extender slicing study of 2026-10-07, the only slice of a one-piece extender in my notes, not
from the v2 pieces: 1700-2400 s with the wrist surface on the bed, 700-900 s flat on its underside,
23-25 s stood on end. The split made the orientation question moot. The hook that fouled the board,
the plate that bowed over the board stack, the smooth extender top and the missing undercut all came
from those prints, not from the CAD.

Combining parts on a plate is much faster than the per-file table below suggests: the 21 parts listed
on those three plates, at their one-at-a-time times from the table, add up to 11 h 15 m against
8 h 13 m on the plates, because a small part alone on the bed spends its time waiting for the minimum
layer time.

## Every variant: time and grams

Every file in `stl/` sliced on its own with the settings above (`cad/variants.py` catalogue order).
*Footprint* and *height* are the slicer's bounding box in print orientation; *support* says whether the
auto tree support placed anything and how high it reaches; *time* and *PETG* are the slicer's own
estimates, not stopwatch and scale. The slicer raised no warning on any file.

| file | what | footprint (mm) | height (mm) | layers | support | time | PETG | printed? |
|---|---|---|---|---|---|---|---|---|
| `cradle/cradle_low_hook.stl` | floor_h 1.0, hook | 149 x 62 | 30.2 | 151 | yes, to z 17.6 | 1 h 26 m | 30.3 g | no |
| `cradle/cradle_low_nohook.stl` | floor_h 1.0, no hook | 149 x 58 | 30.2 | 151 | yes, to z 17.6 | 1 h 23 m | 29.8 g | no |
| `cradle/cradle_std_hook.stl` | floor_h 2.0, hook | 149 x 62 | 31.2 | 156 | yes, to z 17.6 | 1 h 35 m | 33.7 g | **yes** (v11) |
| `cradle/cradle_std_nohook.stl` | floor_h 2.0, no hook | 149 x 58 | 31.2 | 156 | yes, to z 17.6 | 1 h 33 m | 33.2 g | no |
| `cradle/cradle_tall_hook.stl` | floor_h 3.5, hook | 149 x 62 | 32.7 | 164 | yes, to z 17.6 | 1 h 50 m | 38.4 g | no |
| `cradle/cradle_tall_nohook.stl` | floor_h 3.5, no hook | 149 x 58 | 32.7 | 164 | yes, to z 17.6 | 1 h 47 m | 38.1 g | no |
| `faceplate/faceplate_palm.stl` | palm rest plate | 149 x 63 | 4.8 | 24 | yes, to z 0.6 | 33 min | 13.3 g | **yes** (plate v9) |
| `faceplate/faceplate_full.stl` | every control open | 149 x 63 | 4.8 | 24 | yes, to z 0.6 | 34 min | 11.6 g | no |
| `extenders/left_base_low_hook.stl` | floor_h 1.0, hook | 60 x 62 | 30.2 | 151 | yes, to z 17.6 | 1 h 15 m | 26.0 g | no |
| `extenders/left_base_low_nohook.stl` | floor_h 1.0, no hook | 60 x 58 | 30.2 | 151 | yes, to z 17.6 | 1 h 09 m | 24.6 g | no |
| `extenders/left_base_std_hook.stl` | floor_h 2.0, hook | 60 x 62 | 31.2 | 156 | yes, to z 17.6 | 1 h 17 m | 26.8 g | **yes** (v11) |
| `extenders/left_base_std_nohook.stl` | floor_h 2.0, no hook | 60 x 58 | 31.2 | 156 | yes, to z 17.6 | 1 h 10 m | 25.4 g | no |
| `extenders/left_base_tall_hook.stl` | floor_h 3.5, hook | 60 x 62 | 32.7 | 164 | yes, to z 17.6 | 1 h 18 m | 28.0 g | no |
| `extenders/left_base_tall_nohook.stl` | floor_h 3.5, no hook | 60 x 58 | 32.7 | 164 | yes, to z 17.6 | 1 h 12 m | 26.6 g | no |
| `extenders/right1_base_low_hook.stl` | floor_h 1.0, hook | 115 x 62 | 30.2 | 151 | yes, to z 17.6 | 2 h 00 m | 47.5 g | no |
| `extenders/right1_base_low_nohook.stl` | floor_h 1.0, no hook | 115 x 58 | 30.2 | 151 | yes, to z 17.6 | 1 h 49 m | 45.0 g | no |
| `extenders/right1_base_std_hook.stl` | floor_h 2.0, hook | 115 x 62 | 31.2 | 156 | yes, to z 17.6 | 2 h 02 m | 49.0 g | **yes** (v11) |
| `extenders/right1_base_std_nohook.stl` | floor_h 2.0, no hook | 115 x 58 | 31.2 | 156 | yes, to z 17.6 | 1 h 52 m | 46.5 g | no |
| `extenders/right1_base_tall_hook.stl` | floor_h 3.5, hook | 115 x 62 | 32.7 | 164 | yes, to z 17.6 | 2 h 04 m | 51.1 g | no |
| `extenders/right1_base_tall_nohook.stl` | floor_h 3.5, no hook | 115 x 58 | 32.7 | 164 | yes, to z 17.6 | 1 h 54 m | 48.7 g | no |
| `extenders/right2_base_low_hook.stl` | floor_h 1.0, hook | 115 x 62 | 30.2 | 151 | yes, to z 17.6 | 1 h 57 m | 47.3 g | no |
| `extenders/right2_base_low_nohook.stl` | floor_h 1.0, no hook | 115 x 58 | 30.2 | 151 | yes, to z 17.6 | 1 h 46 m | 44.8 g | no |
| `extenders/right2_base_std_hook.stl` | floor_h 2.0, hook | 115 x 62 | 31.2 | 156 | yes, to z 17.6 | 1 h 59 m | 48.8 g | **yes** (v11) |
| `extenders/right2_base_std_nohook.stl` | floor_h 2.0, no hook | 115 x 58 | 31.2 | 156 | yes, to z 17.6 | 1 h 48 m | 46.3 g | no |
| `extenders/right2_base_tall_hook.stl` | floor_h 3.5, hook | 115 x 62 | 32.7 | 164 | yes, to z 17.6 | 2 h 01 m | 50.9 g | no |
| `extenders/right2_base_tall_nohook.stl` | floor_h 3.5, no hook | 115 x 58 | 32.7 | 164 | yes, to z 17.6 | 1 h 51 m | 48.5 g | no |
| `extenders/left_plate.stl` | height-independent | 60 x 63 | 4.8 | 24 | yes, to z 0.6 | 22 min | 7.3 g | **yes** (v11) |
| `extenders/right1_plate.stl` | height-independent | 115 x 63 | 4.8 | 24 | yes, to z 0.6 | 32 min | 14.0 g | **yes** (v11) |
| `extenders/right2_plate.stl` | height-independent | 115 x 63 | 4.8 | 24 | yes, to z 0.6 | 32 min | 14.0 g | **yes** (v11) |
| `joint/spline.stl` | one per seam, 3 seams | 29 x 10 | 8.0 | 40 | optional, in the counterbores | 16 min | 1.5 g | **yes** (v11) |
| `joint/topkey.stl` | one per seam, 3 seams | 21 x 12 | 3.0 | 15 | none | 10 min | 0.7 g | **yes** (v11) |
| `caps/stick_cap_tight.stl` | socket 3.00 x 3.50 | 16 x 16 | 5.2 | 26 | none | 12 min | 0.6 g | **yes** (v11) |
| `caps/stick_cap_nominal.stl` | socket 3.25 x 3.75 | 16 x 16 | 5.2 | 26 | none | 12 min | 0.6 g | **yes** (v11) |
| `caps/stick_cap_loose.stl` | socket 3.50 x 4.00 | 16 x 16 | 5.2 | 26 | none | 12 min | 0.6 g | **yes** (v11) |

All 34 files: 43 h 33 m and 999.5 g if each were printed alone, which nobody should do. Every total
on this page is the sum of the rounded per-file figures in the table, so it re-adds from the table.

What one complete dock comes to - a cradle, a face plate, three bases, three plates, three splines,
three top keys and two caps, each part at its one-at-a-time figure from the table:

| height | hook | plate | time | PETG |
|---|---|---|---|---|
| low | hook | palm | 10 h 19 m | 207.5 g |
| low | hook | full | 10 h 20 m | 205.8 g |
| low | no hook | palm | 9 h 48 m | 200.6 g |
| low | no hook | full | 9 h 49 m | 198.9 g |
| **std** | **hook** | **palm** | **10 h 34 m** | **214.7 g** |
| std | hook | full | 10 h 35 m | 213.0 g |
| std | no hook | palm | 10 h 04 m | 207.8 g |
| std | no hook | full | 10 h 05 m | 206.1 g |
| tall | hook | palm | 10 h 54 m | 224.8 g |
| tall | hook | full | 10 h 55 m | 223.1 g |
| tall | no hook | palm | 10 h 25 m | 218.3 g |
| tall | no hook | full | 10 h 26 m | 216.6 g |

The height axis costs more than the hook axis: each millimetre of `floor_h` is a full-footprint
layer under every base, while the hook is two small tabs on the cradle and a 2 mm lip on the
extenders. The `full` plate is lighter than `palm` because it has more holes.

## Printed versus generated

Being clear about which is which is the point of this repository.

**Printed, assembled and in use (2026-10-21):** the `std` height + `hook` + `palm` configuration -
`cradle_std_hook`, the three `*_base_std_hook` bases, the three extender plates, the splines, the top
keys and the stick caps, all from the v11 sources; plus `faceplate_palm` as plate v9.

**Printed earlier and superseded:** cradle v10, the one-piece v2 extenders that reached the printer
(the left one, and the outermost right one, which came off without its keyboard undercut), and the
v10 test plate. They are not in `stl/`; the v11 fixes are what came out of handling them.

**Generated, checked, never printed:** every `low` and `tall` file and every `nohook` file (20 files
between them) plus `faceplate_full` - 21 of the 34. They come from the same parameter file through
the same code paths, and on 2026-10-22 `python cad/checks.py --all` passed every row of sections (a)
to (f) for all six height x hook combinations - seam flushness to three decimals, zero key
interference, pilots, hook bands, caps - except the same two cradle pilot rows, reported as `KNOWN`
in every configuration (see [Assembly notes](#assembly-notes)). But no one has held one.

One more honest detail: the files in `stl/` were regenerated from the sources on 2026-10-21, after
`plate_style` was added and the output paths were made relative, so the std/hook/palm files carry the
v11 geometry that was printed, but these exact files have not themselves been through the slicer and
onto the bed. The slicer run above is the regenerated files.

## Assembly notes

- **Plate screws (20):** 2 mm self-tapping screws through the plates' 2 mm holes (4 mm head recess,
  0.8 mm deep) into 2 mm pilots that are 10 mm deep and square to the plate - four on the cradle, four
  on the left extender, six on each right extender. The plates are 1.6 mm, so a screw of 8-10 mm
  reaches the pilot without bottoming.
- **Joint screws (6):** M3 self-tappers up through the spline from underneath: 3.2 mm clearance
  holes with a 5.6 x 2.2 mm counterbore in the spline's underside, into 2.4 mm pilots 9 mm deep. The
  spline is 8 mm tall, so a 12 mm screw bites about 6 mm. The screw nearer the seam goes into the
  dock-side piece, the farther one into the outboard piece.
- **A clash the check suite found (2026-10-22, not yet checked on the part):** the cradle's two
  front plate-screw pilots, 3.2 mm in from the ends, sit inside the 9 mm that the spline seat
  reaches into the cradle. Each pilot opens into the seat's roof after about 7.4 of its 10 mm, and
  the spline's own dock-side M3 rises beside it, 1.9 mm centre to centre at the roof. So at those two
  stations the plate screw must be short: the suite works out that one longer than 4.6 mm (plate
  included) comes within 0.5 mm of the M3's shank, and one longer than 9.0 mm goes through the roof
  into the spline - a 2 x 4 mm screw there, 8-10 mm everywhere else. The real fix is to move the
  front screw row inboard of x ±65, which changes two holes in a plate that has been printed; I have
  not made that call, so `cad/checks.py` prints the two rows as `KNOWN` instead of failing
  (`python cad/checks.py --strict` fails them).
- **Top keys** need no screw: they lie in a rebate 0.2 mm deeper than they are thick and the face
  plate screwed down over them traps them. Fit them before the plates.
- **Spline clearance** is 0.25 mm per side and the top key's 0.2 mm. A key that comes out tight is
  a few strokes of a file, not a reprint; the clearances have not been adjusted since v11.
- **Stick caps** push onto the bare 3 x 3.5 mm stick posts. Three socket clearances exist; print one
  pair of each (they are 12 minutes and 0.6 g apiece) and keep the pair that grips.
- **Order the geometry implies:** splines into the cradle's seats, extender bases onto the splines
  and screwed from below, top keys into their rebates, then every plate.

## Assumed dimensions

These numbers are in `cad/dock_params.py` and `cad/stick_cap.py`, marked `ASSUMED` or `UNMEASURED`; they were set from photographs, scans or
judgement rather than calipers on the part, and the prints have been the test:

| parameter | value | status |
|---|---|---|
| `stack_h` | 15.0 mm, midframe face to the rearmost point on the board | assumed; raised from 14 in v11 when the plate bowed over the stack |
| `jds_wh` | 33 x 21 mm charging-board bay | assumed |
| `so_slot_w`, `so_slot_len` | 6.6 x 11.0 mm Share/Options slots | assumed from the buttons' look; measure the caps |
| keyboard lip (`kb_wall_h`, `kb_cham_angle`, `kb_top_h`) | 10 mm wall, 30° chamfer, 18 mm top | traced on paper, never measured; used only by the undercut and the hook |
| plate top flush with the touchpad's flat top | - | assumed; the lip curve starts from the touchpad's own 8 mm radius |
| stick cap socket | 3 x 3.5 mm post | three clearances printed instead of measuring |
| stick pivot depth (the cap skirt's swing) | - | unmeasured; `stick_cap.swing_report()` gives the arithmetic for any guess |

The v11 set was assembled and is in use, which is the strongest evidence any of these has; none has
been confirmed with an instrument.
