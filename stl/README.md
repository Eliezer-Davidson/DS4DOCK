# stl/ - the pre-built parts

Every printable part of the dock, in every variant: 34 binary STL files built from the sources in
[`../cad/`](../cad) by `python cad/variants.py` (tolerance 0.05 mm, angular tolerance 0.3 rad).
Each file is one solid, verified twice on the way out - the B-rep before tessellation (valid, exactly
one solid) and the written mesh after it (closed, consistently oriented, one shell, volume within 1 %
of the B-rep) - and once more by `python cad/checks.py` section (g).

**Every file is in print orientation**: lowest point on z = 0, footprint centred on the origin. Drop it
on the plate as it comes. The cradle, the bases, the keys and the caps print as they were modelled;
the plates are already flipped face-down, so their finished face goes on the textured sheet and the
curled lip rises away from the bed. Settings, supports, bed-fit rules and a slicer-estimated time and
grams for every file are in [`../docs/PRINTING.md`](../docs/PRINTING.md).

## The printed configuration

**`std` height + `hook` + `palm` plate is the configuration that was printed, assembled and is in
use** (the v11 set, three plates, 2026-10-12 slices, assembled 2026-10-21): `cradle_std_hook`, the
three `*_base_std_hook` bases, the three extender plates, `spline`, `topkey`, the three caps, and
`faceplate_palm` (as plate v9). Every other file is generated from the same parameters through the
same code and passes the same checks (with the same two documented cradle-pilot rows, see
[`../docs/PRINTING.md`](../docs/PRINTING.md#assembly-notes)), and has never been printed.

## Naming

```
cradle/cradle_{height}_{hook}.stl                 height: low | std | tall   (floor_h 1.0 | 2.0 | 3.5 mm)
extenders/{piece}_base_{height}_{hook}.stl        hook:   hook | nohook
extenders/{piece}_plate.stl                       piece:  left | right1 | right2
faceplate/faceplate_{style}.stl                   style:  palm | full
joint/spline.stl  joint/topkey.stl
caps/stick_cap_{fit}.stl                          fit:    tight | nominal | loose  (socket +0.0 | +0.25 | +0.5 mm)
```

`height` raises the cradle and the bases together (the pocket floor sits 1.0, 2.0 or 3.5 mm above the
desk on the pivot line) and leaves every plate alone, which is why the plates carry no height tag.
`hook` is the lip that hangs over the keyboard's front edge. The plate style changes only the face
plate.

## One complete dock

A cradle, a face plate, three bases **of the same height and hook** with their three plates, three
splines, three top keys and two caps - 16 bodies. Print a spare key of each kind and one cap of each
fit; they are minutes each.

| | pick one of | count |
|---|---|---|
| cradle | `cradle/cradle_{height}_{hook}.stl` | 1 |
| face plate | `faceplate/faceplate_palm.stl` or `faceplate_full.stl` | 1 |
| bases | `extenders/left_base_…`, `right1_base_…`, `right2_base_…` at the same height and hook | 3 |
| plates | `extenders/left_plate.stl`, `right1_plate.stl`, `right2_plate.stl` | 3 |
| splines | `joint/spline.stl` | 3 (one per seam) |
| top keys | `joint/topkey.stl` | 3 (one per seam) |
| stick caps | `caps/stick_cap_{fit}.stl` | 2, after trying the fits |

## The files

Footprint x height are the slicer's bounding box in print orientation, in mm.

### cradle/ - the body that holds the board

**printed** marks the configuration that was built and is in use (v11, 2026-10-21). These exact files were regenerated from the same parameters by `cad/variants.py` on 2026-10-21; the files themselves have not been sliced or printed again - [docs/PRINTING.md](../docs/PRINTING.md) has the detail.

| file | floor_h | hook | size | note |
|---|---|---|---|---|
| `cradle_low_hook.stl` | 1.0 | yes | 149 x 62 x 30.2 | |
| `cradle_low_nohook.stl` | 1.0 | no | 149 x 58 x 30.2 | |
| `cradle_std_hook.stl` | 2.0 | yes | 149 x 62 x 31.2 | **printed** (v11) |
| `cradle_std_nohook.stl` | 2.0 | no | 149 x 58 x 31.2 | |
| `cradle_tall_hook.stl` | 3.5 | yes | 149 x 62 x 32.7 | |
| `cradle_tall_nohook.stl` | 3.5 | no | 149 x 58 x 32.7 | |

The pocket for the board, the finger notch in the user-side wall, the ribbon-connector channel in
the floor, the charging-board bay under it, the LED notch, the keyboard undercut along the whole
keyboard side, the hook on the two side walls (`hook` files), the four plate-screw pilots, and the
cradle's half of both joints at each end: a spline seat in the front wall and a top-key seat in the
rim.

### faceplate/ - the plate over the board

| file | style | size | note |
|---|---|---|---|
| `faceplate_palm.stl` | palm | 149 x 63 x 4.8 | **printed** (plate v9): touchpad, two sticks, Share and Options open; d-pad, face buttons and PS filled, so the right-hand side is a palm rest |
| `faceplate_full.stl` | full | 149 x 63 x 4.8 | every control open - d-pad cross, four face buttons and PS added - for a board that keeps its buttons |

Both are 1.6 mm thick with the 90° curled lip at the keyboard end and the four screw holes (2 mm
through, 4 mm head recess, a 0.2 mm skin to poke through). Height-independent.

![The two face plates side by side, top view, keyboard edge at the top](../docs/images/faceplates.png)

### extenders/ - the wrist rests either side

| file | floor_h | hook | size | note |
|---|---|---|---|---|
| `left_base_{low,std,tall}_{hook,nohook}.stl` | 1.0 / 2.0 / 3.5 | yes / no | 60 x 62 (58) x 30.2-32.7 | `left_base_std_hook` **printed** |
| `right1_base_{low,std,tall}_{hook,nohook}.stl` | 1.0 / 2.0 / 3.5 | yes / no | 115 x 62 (58) x 30.2-32.7 | the inner right half, carries the dock side of the seam to `right2`; `right1_base_std_hook` **printed** |
| `right2_base_{low,std,tall}_{hook,nohook}.stl` | 1.0 / 2.0 / 3.5 | yes / no | 115 x 62 (58) x 30.2-32.7 | the outer right half; `right2_base_std_hook` **printed** |
| `left_plate.stl` | - | - | 60 x 63 x 4.8 | **printed** |
| `right1_plate.stl` | - | - | 115 x 63 x 4.8 | **printed** |
| `right2_plate.stl` | - | - | 115 x 63 x 4.8 | **printed** |

A base is the cradle's own body over that piece's x range - same rim plane, same undercut, same hook
(over its whole length, since nothing is in the way), same lip clearance - with the cable channel
through it, its plate-screw pilots (4 on the left, 6 on each right piece) and its halves of the joints.
A plate is the face plate's outline, thickness, lip and screw spec over the same range with no
openings. Left is 60 mm, the right pair 2 x 115 mm: 60 + 149 + 230 = 439 mm, 2 mm over the K70's 437.

### joint/ - two connectors per seam

| file | size | note |
|---|---|---|
| `spline.stl` | 29 x 9.5 x 8 | the loose key in the front wall: 9 mm into the dock-side piece, 20 into the outboard one, with a counterbored M3 clearance hole each side (3.2 through, 5.6 x 2.2 head). **printed** |
| `topkey.stl` | 21 x 12 x 3 | the flat key in the rim's top face, 7 into the dock side, 14 outboard; no screw, the face plate traps it. **printed** |

Both are asymmetric: the short end goes into the piece nearer the dock. Three of each per dock.

### caps/ - analogue-stick caps

| file | socket | size | note |
|---|---|---|---|
| `stick_cap_tight.stl` | 3.00 x 3.50 | 16 x 16 x 5.2 | **printed** |
| `stick_cap_nominal.stl` | 3.25 x 3.75 | 16 x 16 x 5.2 | **printed** |
| `stick_cap_loose.stl` | 3.50 x 4.00 | 16 x 16 x 5.2 | **printed** |

A bell: a 16 mm skirt that hides the stick opening, a 12 mm top with a thumb dish and twelve grip
flutes, a 4 mm deep socket for the bare post. The post size was not measured, so three socket sizes
exist; six were printed, two at each clearance, so the pair that grips could be kept. My notes do not
record which fit won.

## Regenerating

Change a parameter in `cad/dock_params.py`, then:

```
python cad/variants.py          # rebuilds all 34 files (about a minute); --only PATTERN for some
python cad/checks.py            # measures the assembled result and re-reads every file here
```

The files are a deterministic output of the sources; nothing in this folder is edited by hand.
