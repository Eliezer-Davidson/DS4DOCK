# Hardware notes

What the controller is, what came off it, what stayed, and the two things that bit: triggers that read pressed forever, and a USB port board that died.

**TL;DR.** A DualShock 4 v2 (CUH-ZCT2, JDM-055 mainboard) with stock firmware. The grips, the rear shell, the triggers, the rumble motors and the battery are gone; the mainboard, the touchpad, both sticks and the Share/Options film stay, as a flat 130 x 55 mm part. Without the triggers L2 and R2 report pressed permanently - L2 at 255, R2 wandering - so the mapper excludes them from everything, and because Windows counts R2's wandering as user activity, screen off watches the keyboard and the mouse itself. The micro-USB port board (JDS-055) is a separate part on a ribbon, which is why the dead USB port this board suffered in October 2026 was a ten-dollar fix with no soldering.

## The controller

| | |
|---|---|
| Model | DualShock 4 v2, CUH-ZCT2 (the one whose light bar also shows through the top edge of the touchpad) |
| Mainboard | JDM-055 |
| USB | VID `0x054C`, PID `0x09CC` (`0x05C4` is the v1 CUH-ZCT1; `0x0BA0` the official USB wireless adaptor - the mapper accepts all three) |
| Firmware | stock. Nothing is flashed; the board does not know anything changed |
| Power | USB only. The LiPo is removed and the board runs without it; the battery nibble in the report then means nothing, so the mapper shows the battery colour only for 2 s after plug-in |

### The sandwich

The teardown guides for the CUH-ZCT2 make one thing clear: the keycaps, d-pad, PS button and their silicone pads are only *located* by the front shell. What clamps them is the **midframe**, the black inner plastic the board screws to. Front to back:

```
front shell -> keycaps -> silicone pads (in shell pockets) -> flex button film (on the midframe face)
  -> midframe (sticks, trigger pivots + springs, motor bays)
  -> mainboard JDM-055 (one 6.4 mm PH00 screw, under the battery bracket)
  -> battery bracket (friction pegs)
  -> rear shell (USB / light-bar port board JDS-055 on a ribbon; L1 / R1)
```

So the unit to keep and cut down is **midframe + board**: nothing fastens them to each other except that one screw and the shell clips, and every tolerance Sony solved stays solved. The touchpad clips into the front shell's own bezel (hinged at its top edge, ribbon through a slot) and is independent of the midframe. L2/R2 pivot on midframe pegs with a spring on the inside peg. The rear shell can go entirely; the cradle replaces it.

## What was removed, what stayed

| Removed | Why / consequence |
|---|---|
| Rear shell, grips | The grips are dead weight: the button field, sticks and touchpad all sit in the central body. The cut line runs through both shells and the midframe together. |
| L1 / R1 | Went with the rear shell. They were Shift and Ctrl; those moved to holding Share and Options. |
| L2 / R2 triggers | Their springs and pivots live in the midframe; with the levers gone nothing stops the sensor, so **both read pressed at rest** - L2 at 255, R2 wandering. See below. |
| Rumble motors | Physically removed. **Never write a non-zero rumble byte** - the output report's two rumble bytes are held at zero and the self-test asserts it. |
| Battery | Optional on USB; removed for thickness. |
| D-pad, face buttons, PS keycaps | Not reachable from a planted palm, and the plate over them is where the palm rests. The `palm` face plate fills them in; the `full` face plate opens them again for a board that keeps its buttons. Their bindings stay in the mapper because they cost nothing and work again if a shell is ever refitted. |

| Kept | Notes |
|---|---|
| Mainboard JDM-055 | The part is a plain rectangle: **130 x 55 mm** to the inner bottom line, 2 mm corners, measured 2026-09-22 by counting millimetre ticks on a 1:1 tracing (an earlier ruler reading said 135; it was 5 mm off). Sticks 49-50 mm apart, PS centred ~11 mm above the bottom edge. |
| Touchpad module | 55 x 33 x 12 mm including its click mechanism; two contacts, 1920 x 942 units over roughly 52 x 25 mm (about 37 units/mm); on the real part x reads 21..1883 and y 0..941. Also the mechanical click (`Pad`). |
| Both sticks + L3 / R3 | Bare posts (the rubber caps are gone), so the frame includes printed caps with a 3 x 3.5 mm socket, 4 mm deep - see `cad/stick_cap.py`. Rest positions on this board: LS 128,125, RS 129,123 - a unit or two off centre and jittering, which matters for the light bar. |
| Share / Options | Through the button film on the midframe; the face plate has a 6.6 x 11 mm stadium slot for each. |
| Port board JDS-055 | The micro-USB socket and the light bar's LEDs on a short 12-pin ribbon - a near-passive pass-through; the charging IC is on the mainboard. The cradle gives it a bay under the pocket floor (the CAD still calls it the charging-board bay, a name from before the port died) and a notch for its LED end. |
| Gyro, accelerometer | Read and shown on the dashboard, unmapped. Accelerometer rest magnitude 8218 (about 8192 counts per g). |

### L2 / R2 without triggers

With the rear shell off the analogue triggers lost their levers and springs. On the hardware checklist both sat at 255 - full travel - permanently, and they still swept 0..255 (148 and 247 distinct values), so the sensors are fine and it is purely mechanical. By 2026-10-26, in the frame, L2 still read 255 but R2 no longer rested anywhere: untouched, its analogue value wandered between 96 and 255 (28 distinct values, about 150 changes in 12 s), while both digital bits stayed set. Four consequences in the software:

- nothing is bound to them, and the mapping loader **refuses** to bind them (`L2` and `R2` are reserved in `mapping.json`; the editor shows them disabled with this explanation);
- they are excluded from "activity" for the light bar, or the blue light would never go out;
- the dashboard shows them as they are: `L2 255`, and R2 anywhere from about 96 to 255;
- **Windows counts R2's wandering as user activity.** With the dock plugged in and nobody at the desk, the session's idle clock (`GetLastInputInfo`) moved 67 times in 12 s, each move within 20 ms of a change in R2's raw value, and it moved just as often with the mapper process suspended. In a separate 30 s spell the idle clock moved 115 times while low-level keyboard and mouse hooks saw no events at all (and none in another 6 s run). So the moves come from Windows' handling of the controller, not from the mapper, and nothing about them looks like a key or the mouse. Screen off therefore watches the keyboard and the mouse itself, through Raw Input ([CONTROLS.md](CONTROLS.md#mechanisms)). It probably also means Windows never sees the PC as idle while the dock is plugged in, so its own screen and sleep timeouts would never run out; that is untested (on mains power this laptop never sleeps anyway).

A cradle could give the levers a stop and make them usable again - and a stop that parks R2 at the end of its travel, as L2 already is, should also quiet it; on this build they were cut off with the grips.

## The USB port board swap

The micro-USB socket is the board's weak point. During the phase-1 run on 2026-09-22 the cable flapped three times before the connection went stable, and the cradle design has carried a strain-relief requirement ever since: the port board sits in a bay under the pocket floor and the cable leaves through a channel in the right extenders rather than hanging off the socket in free air. Around 2026-10-05 the port died altogether, and the pad stayed dead until 2026-10-20.

**The symptom** was the one you least want: nothing. No device appeared, Windows did not complain, nothing sat in a failed state in Device Manager, and the event log showed **no Kernel-PnP events at all** when the cable went in; `hidapi` counted 30 HID devices and no Sony where it had counted 31 and one. That is a different failure from a bad descriptor, where the device at least enumerates and Windows logs a "Device Descriptor Request Failed". Nothing arriving at the host means the physical link is dead before any firmware is involved - the power side, most likely a cracked joint or a lifted pad at the socket, rather than a data line. The launcher, the USB hub, a device conflict and the cable were ruled out first. Two physical hints agreed: the socket had flapped during phase 1, and that board's indicator LED had fallen off.

**The diagnosis** followed from that. The socket is not on the mainboard - it is on the **JDS-055 port board**, connected to the JDM-055 by a 12-pin flex ribbon. So the mainboard, with the touchpad, the sticks and everything the project relies on, was very probably fine, and the suspect was the one cheap part.

**The fix:** a replacement JDS-055 port board with a new ribbon (sold as a two-pack, about $10), plugged in on 2026-10-20. No soldering. The port board is a near-passive pass-through - the charging IC is on the mainboard - so the part is chosen by controller revision (JDS-055 for a CUH-ZCT2 with a JDM-055 board), not by any rating. Confirmed the same evening: one Sony device again, all four of its device nodes healthy including the audio endpoint, the mapper streaming at 250 Hz with sticks, touchpad, gyro and accelerometer reporting - and the autostart watcher, which had been polling for the pad the whole time, started the mapper on its own 2 s after the new board enumerated.

The lesson that went into the project's process: before building anything on top of the board, run a checklist that proves every input end to end through the exact code that will use it. A hardware fault that shows up as "nothing" is much cheaper to find on day one than inside a cradle.

## The phase-1 hardware checklist

The project's first milestone was not the mapper - it was proving that every input is readable, at full rate, through `ds4_dock.py`'s own `open_device` / `read_state` / `parse_usb` / `Mapper` / `led_report` functions, with the board bare (no rear shell, front shell laid on loosely, LiPo removed). Passed on **2026-09-22**:

| Input | Result | Evidence |
|---|---|---|
| Report rate | pass | device timestamp step 3.989 ms, 0 gaps in 20 000 samples; host-side median 250.0 reports/s over 357 s |
| Left / right stick | pass | both axes 0..255; rest 128,125 / 129,123 |
| L3 / R3, d-pad 8 ways, Cross Circle Square Triangle, Share Options PS, L1 R1 | pass | |
| L2 / R2 analogue | pass | 0..255, 148 / 247 distinct values; **rest at 255 without the rear shell** |
| Touchpad, 1 + 2 fingers, click, edges | pass | x 21..1883, y 0..941 |
| Gyro / accelerometer | pass | all three axes move; accelerometer rest magnitude 8218 |
| USB flag + battery byte | info | flag on, 100 %; the battery nibble is meaningless with no battery fitted |
| Light bar | pass | 14 writes, 0 failures, colour cycle confirmed by eye; rumble bytes 0 |

CPU cost of the read + parse loop: 5.3 % of one core.

Lessons from that evening, all still true:

- **The pad serves one host.** A Bluetooth pairing with a phone shows a blue light bar and blocks USB - forget the pad on the phone.
- **The micro-USB socket is fragile.** Strain-relieve the cable; it flapped three times before going stable.
- **No battery is fine** for USB use.

## Protocol facts the code relies on

| | |
|---|---|
| USB input report | id `0x01`, 64 bytes at 250 Hz: sticks at bytes 1-4; buttons 5-7 (d-pad as a 4-bit hat in the low nibble of byte 5); L2/R2 at 8-9; 16-bit timestamp at 10-11 in 5.33 us units; gyro 13-18 and accelerometer 19-24 as signed 16-bit; cable / battery byte 30 (bit 4 = USB, bit 5 = headphones, low nibble = level); two touch slots at 35 and 39, each 4 bytes: id with the high bit set when the slot is empty, then 12-bit x and y |
| Bluetooth input report | id `0x11`, 78 bytes; the same payload offset by 2, with a CRC-32 over `0xA2` + the first 74 bytes. The pad sends minimal `0x01` reports over Bluetooth until feature report `0x02` is requested |
| Output report | USB id `0x05`, 32 bytes: RGB at 6-8, flash on/off times at 9-10 (left at zero - every state is a steady colour), rumble at 4-5 (**always zero**). Bluetooth id `0x11`, 78 bytes with the CRC |
| Touchpad | 1920 x 942 units; a short contact (< `tap_max_s`) that moved less than `tap_max_move` is a tap |
| Accelerometer | about 8192 counts per g |

## In the dock

The board lies on the cradle's pocket floor on its back; the touchpad's top edge sits at the face plate's curled keyboard end, so the v2 light strip is visible in the dock. The charging ribbon's connector sits in a channel in the floor so the board lies flat. The port board lives in a bay under the floor at the right of the keyboard end; its LED end looks out through a 10 x 3 mm notch in the wall facing the user. The micro-USB plug threads through the right extenders' cable channel into that bay: the window is about 12.5 mm wide and 6 mm tall at its tightest, inside the cradle wall, so measure your cable's moulding before relying on threading it through end to end. The cut-down part's thickness over the pocket floor, `stack_h`, is **15 mm by assumption** - the face plate bowed upward on the 14 mm pocket, which is why v11 added a millimetre; nobody has put calipers on it yet.
