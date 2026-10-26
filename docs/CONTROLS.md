# Control map v2 - design (2026-10-21)

Settled on 2026-10-21; one binding changed on 2026-10-26, when `Fn` + pad click became screen off instead of suspend. This is the reference for what each input does and why; the shipped defaults in [`../mapping.json`](../mapping.json) and the docstring of [`../ds4_dock.py`](../ds4_dock.py) implement exactly this map, and [`tools/mapping_editor.py`](../tools/mapping_editor.py) edits it. The picture of it is [`images/map.svg`](images/map.svg).

## The hardware reality that drives all of this

The controller was cut down for the dock. **The only inputs that physically exist are:**

- the **touchpad** surface (two contacts) and its **mechanical click**
- **both analogue sticks** and their clicks, **L3** and **R3**
- **Share** and **Options**

That is five discrete buttons. Gone with the shell: L1/R1 (which were Shift and Ctrl), Cross
(Enter), Circle (Esc), Square (Backspace), Triangle (play/pause), the whole d-pad (arrows), and
PS (which toggled layer 2). L2/R2 report permanently pressed with the triggers removed (L2 at
255; R2's analogue value wanders); nothing is bound to them and nothing should be - the mapping
loader refuses to bind them.

![The same map drawn on the full face plate, with every control open](images/map_full.svg)

*[`images/map_full.svg`](images/map_full.svg): the same `mapping.json` in the editor's **Full controller**
mode - the dock's `full` face plate, to scale, with the d-pad, the face buttons and PS open - so the
dormant bindings, the ones a board that keeps its buttons would bring back, are visible too. L1, R1,
L2 and R2 are drawn along the keyboard edge but marked unreachable: that edge faces the keyboard in
every dock variant. Regenerate it with
`python tools/render_map.py mapping.json docs/images/map_full.svg --mode full`.*

Two consequences shape the design:

1. **Fixed chords need no physical modifier.** The mapper synthesises `ctrl+c` as a keystroke, so
   Share can send it with no Ctrl button in existence. Only *live* modification of the stick -
   "select while I move" - needs a genuinely held key, and that needs exactly one.
2. **One momentary layer buys back everything else.** Holding L3 is `Fn`. This rides the layer
   mechanism that was already in the file (`KEYMAP_L2`), momentary instead of toggled.

## The map

| Input | Alone | Held | **Fn** (hold L3) + it |
|---|---|---|---|
| **Pad click** | right click | - | **screen off** (the same chord again wakes it) |
| Pad, 1 finger | cursor; tap = left click | - | - |
| Pad, 2 fingers | scroll; tap = **middle** click | - | - |
| **Right stick** | **arrows**, repeat rate by deflection | - | **pane focus** `ctrl+k ctrl+<arrow>` |
| **Left stick** | flick W/E = prev/next window, N/S = prev/next tab | - | **flick N = Task View** (`super+tab`)<br>**flick S = `cursor_centre`** |
| **L3** | **Esc** | **Fn** | - |
| **R3** | **Enter** | - | **voice typing** (`super+h`) |
| **Share** | `ctrl+c` | **Shift** - the stick selects text | **snipping tool** (`super+shift+s`) |
| **Options** | `ctrl+v` | **Ctrl** - the stick jumps by word | **`super+x`** |

Share + Options held together give Shift+Ctrl, so the stick selects by word.

### Why these three, and why they fit

Task View, `Win+X` and right-click's context menu are all **menus driven by arrows and Enter** -
which is exactly what the right stick and R3 now are. Open, steer, confirm, with both thumbs
already on the sticks and never a reach for the keyboard.

Enter and Esc go on the stick clicks because they are the two keys every dialog and prompt needs
and they were lost with Cross and Circle.

## Mechanisms

**Tap vs hold** (Share, Options, L3). The modifier engages at `hold_s` (0.25 s), *not* on press.
Release before `hold_s` fires the tap action instead. This way a tap never leaves a stray Shift
press behind - which matters, because five stray Shift presses trip Windows Sticky Keys.

**Fn has zero latency.** Layer 2 engages the instant L3 goes down, so `Fn + stick` responds at
once. Esc fires on L3 *release*, and only when the press was shorter than `hold_s` **and** nothing
else was pressed during it. So holding L3 to use `Fn + Share` never also sends Esc.

**In layer 2 the tap/hold split does not apply.** Share, Options and R3 fire their layer-2 action
on press. Otherwise `Fn + Share` would wait 0.25 s to find out whether it was a tap, for a layer
that has no tap meaning. A modifier already held when Fn engages - Shift from Share, say - stays
held until that button is released; Fn does not disturb it.

**Right stick as arrows.** The dominant axis wins, so diagonals resolve to one arrow rather than
two. The first key fires the moment the stick leaves the deadzone, then repeats at a rate that
scales with deflection through `stick_expo`: `rstick_rate_min` just past the deadzone up to
`rstick_rate_max` at full travel. This is the usual key-repeat feel, with the push distance acting
as the speed control.

**Right stick under Fn** uses the existing flick mechanism (`flick_on` / `flick_off` hysteresis),
so it fires once per push rather than repeating - a pane jump should not machine-gun.

**Screen off.** `Fn + pad click` blacks out every screen and leaves everything else running.
Going in, `release_all()` lets go of anything held - Shift from Share, say - at once, and
`SCREEN_OFF_DELAY_S` = 0.4 s later each monitor gets a black, topmost window that never takes the
focus: a curtain, not a monitor-off. On Modern Standby laptops like mine, a `WM_SYSCOMMAND` /
`SC_MONITORPOWER` monitor-off has been reported to behave like the power button - Windows starts a
standby and cancels every keep-awake request, so downloads, audio and the mapper itself would stop -
and a black window is not a display-off at all. While it is dark the mapper holds
`SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)` and renews it
every 30 s (`screen_off_keep_awake` in `tune.json`, default true), so neither Windows' screen
timeout nor its sleep timer fires. On battery below 20 % it lets go and Windows' own timers take
over - though with the dock plugged in they may never run out, since Windows counts R2's wandering
as activity ([HARDWARE.md](HARDWARE.md#l2--r2-without-triggers); untested). A crash cannot leave
the PC held awake, because the request ends with the process. An
OLED panel is then dark; an LCD keeps its backlight.

While it is dark the pad injects nothing - no cursor, no clicks, no keys, not even the Esc of a
quick L3 tap - so a palm on the touchpad cannot lift the curtain. A key, the mouse, or a touch or a
pen on the screen lifts it, and so does the same chord again; pressed before the 0.4 s are up, the
chord simply calls the switch-off off. The curtain runs on a thread of its own with its own message
loop, and that thread does the watching: Raw Input from the keyboard and the mouse, delivered to it
while another app has the focus (`RIDEV_INPUTSINK`), plus whatever lands on the curtain itself -
`WM_POINTERDOWN` for a finger or a pen, and mouse-button and wheel messages, which still work if
Windows ever keeps the keyboard and the mouse from the sink (perhaps while an elevated window has
the focus; not tried). A click or a tap lifts it only once the button, the finger or the pen is up
again, so none of it reaches the app beneath: a bare right-button release there would open a
context menu, and a side button's would go Back. The curtain handles a finger's or a pen's pointer
messages itself, so Windows never turns the contact into a mouse click. Held longer than 2 s, it
lifts anyway, and that release does reach the app. A mouse move landing on the curtain does not
count, because Windows makes those up whenever a window appears or changes place. Input in the first 0.5 s after it goes up
does not count either. If the monitors change while it is dark - one unplugged or switched off at
its own button, a new mode - the curtain covers them anew before the old windows go, so nothing
shows through and the mapper never takes the rebuild for a lift. It deliberately does not
use the computer's idle clock (`GetLastInputInfo`), and that was learned the hard way: with the
triggers gone R2 floats, and Windows counts its wandering as activity, so the idle clock moves
several times a second with nobody at the desk ([HARDWARE.md](HARDWARE.md#l2--r2-without-triggers)).
The same thread lifts the curtain if the mapper has not checked on it for 5 s, and puts it back on
top every 2 s. The way in and the way out both go through `_settle()`, which takes the pad as it is
at that moment as the new reference: no cursor jump, no tap from a finger already down, no flick
from a stick already pushed. The light goes out with the screen, except orange while the attention
file says `waiting`. In `mapping.json` this is the `{"action": "screen_off"}` binding under
`Pad`'s `fn` slot, so the editor can move it.

It is Windows only. Where nothing can black the screen out - on Linux, where it is not written
yet (see [Open](#open)), and with `--no-inject` - the chord still lets go of anything held, and the
pad goes quiet (no injection; the light bar off, or orange for attention) until `display_off()`
answers no, 0.4 s after the chord. From then on the mapper carries on as normal rather than staying
quiet over a screen that is still lit. Linux prints one line saying screen off is Windows-only for
now.

Three things to know. The key that lifts the curtain also reaches whatever has the focus, so
Shift, Ctrl, the mouse or the chord is the safe way back. Notifications, the volume overlay and
other always-on-top system UI can still draw above the curtain. And so far the curtain has been
raised for real only as a 60 x 60 px test square in a corner - up, held while the idle clock moved,
rebuilt after a display-change message, lifted by an injected mouse event, by a lost heartbeat and
on request; full-screen, from the real chord, with the real keyboard, mouse, touchpad, touchscreen
or pen, it has not been tried yet. The self-test drives the curtain's own logic - the grace, one
lift per burst of input, the wait for a click or a tap to end, the rebuild, the heartbeat -
against a stand-in for Windows.

From 2026-10-21 to 2026-10-26 this chord was **suspend**: `release_all()`, then no injection at
all, the light dim red, the same chord to resume. I wanted a button that blanks the screen while
everything keeps running instead. Suspend is still an action any button's `press` or `fn` slot can
take, `{"action": "suspend"}`; the default map just no longer binds it. It went on a two-handed
chord in the first place because my first choice, Share+Options, collides with Shift+Ctrl -
pausing mid-selection would have suspended the mapper.

## The light bar

Not on all the time. Highest priority wins:

| Priority | State | Colour |
|---|---|---|
| 1 | suspended (the `suspend` action; no button has it by default) | dim red |
| 2 | screen off (`Fn` + pad click) | **off** - orange, steady, while attention is requested |
| 3 | attention requested | orange, steady |
| 4 | Fn held (layer 2) | magenta |
| 5 | first 2 s after plug-in | battery colour |
| 6 | any input within `led_idle_s` | blue |
| 7 | idle | **off** |

**"Input" has to be defined carefully or the blue never goes out.** The sticks idle off centre -
LS 128,125 / RS 129,123 on the phase-1 checklist - and jitter by a unit or two constantly, so raw
stick values cannot count as activity. Activity means: a button edge, a touchpad contact, or stick deflection **past the
deadzone**. L2 and R2 are excluded - they read pressed for good with the triggers gone (R2
wandering besides) and would otherwise read as permanently active.

`led_report()` already does the work and already holds the rumble bytes at zero, with a self-test
asserting it. **The motors are physically removed: never write a non-zero rumble byte.**

**No flashing** (decided 2026-10-21). The pad can pulse in hardware through the report's flash
bytes, and the orange state originally did. It was tried on the bench and rejected: every state is
a steady colour, and the flash bytes stay at zero.

The light is visible in the dock: this is a v2 controller, whose light strip sits above the
touchpad, and the face plate's touchpad opening runs out past the plate's keyboard edge.

## The attention signal

For the orange state the mapper has to learn when something is waiting for me. Mechanism:

- a one-word file `attention_state.txt` next to the mapper (or wherever `--attention-file`
  points): `waiting` or `idle`; a missing file means idle
- the mapper polls its mtime every 0.25 s from the main loop, the same way it already polls the
  tune file, so the 250 Hz hot path never touches the filesystem

Anything that can write a file can drive it. The example this was built for is Claude Code, with
three hooks: `Notification` and `Stop` write `waiting` (a question is up, or a reply is waiting
to be read); `UserPromptSubmit` writes `idle`. The README's
[How it works](../README.md#how-it-works) has them as they go in `settings.json`, calling
`tools/attention.py`. A hook that calls a shell directly can flash a console window on Windows; if
yours does, launch it through `pythonw.exe` with `CREATE_NO_WINDOW` rather than through a shell.

## What this took in the code (`ds4_dock.py`)

1. `MOUSEMAP["Pad"] = "right"`; `ACTIONS["Pad"]` dropped.
2. Two-finger tap: `{1: "left", 2: "right"}` became `{1: "left", 2: "middle"}`.
3. A momentary layer on L3 replacing the PS toggle, with the tap/hold rules above.
4. Tap-vs-hold for Share and Options, with the modifier engaging at `hold_s`.
5. Right-stick key mode: dominant axis, deflection-scaled repeat. The old cursor behaviour stays
   behind `rstick_mode = "keys" | "cursor"` rather than being deleted.
6. **Key sequences in the parser.** `_key()` used to split on `+` only, so it could not send VS
   Code's `Ctrl+K Ctrl+Left`. Now a space separates chords in sequence and `+` joins keys pressed
   together: `"ctrl+k ctrl+left"` is press-release `ctrl+k`, then press-release `ctrl+left`.
7. `led_for()` rewritten to the priority table, plus an activity timestamp and the plug-in grace.
8. Suspend state, the attention-file poller, and the new tune knobs:
   `hold_s`, `rstick_rate_min`, `rstick_rate_max`, `led_idle_s`.
9. (2026-10-26) Screen off: the `screen_off` action; five more injector calls (`display_off`,
   `display_on`, `display_dark`, `keep_awake`, `lifted_by` - stubs everywhere but Windows); on
   Windows `_BlackCurtain`, a thread with its own message loop, its black windows and its Raw Input
   watch; `Mapper._settle()` for the way into and out of both quiet modes; a `dark` argument to
   `led_for()`; and one more tune knob, `screen_off_keep_awake`.

Still one file - the mapper is deliberately a single script with no dependency beyond `hidapi` (+ `evdev` on Linux).

## Nothing was removed without a home

| Was | Now |
|---|---|
| `cursor_centre` on pad click | `Fn` + left stick flick south |
| right click on R3 | pad click (my preference) |
| middle click on L3 | two-finger tap |
| right click on two-finger tap | middle click (three ways to right-click was one too many) |
| right stick as a coarse cursor | retired by choice; kept behind `rstick_mode` |
| battery colour always on | shown for 2 s on plug-in (it reads 100 % forever on USB) |
| volume on Share/Options | dropped: a dedicated volume controller already sits on the desk |
| suspend on `Fn` + pad click (2026-10-21 to 2026-10-26) | not bound by default; still an action any button's `press` or `fn` slot can take |

## Open

- `Fn` + left stick flick **W** and **E** are unassigned. Backspace and Delete are the obvious
  candidates once the stick is driving the caret, but I have not needed them yet.
- Deferred, not rejected: a touchpad scroll strip along the right edge, two-finger tap to Back,
  and knock detection on the live accelerometer.
- The repeat rates are guesses. They are tune knobs precisely so they can be set on the bench
  without a restart.
- Screen off has been raised for real only as a test square. Still to try at the desk: the real
  chord at full screen; the real keyboard, mouse and touchpad, and a touch or a pen on the screen,
  bringing it back; the LCD switched off at its own button while dark; a long dark spell with a
  download and audio running; and the battery guard, on battery below 20 %.
- Screen off on Linux. X11 has DPMS and GNOME on Wayland a D-Bus call, but both belong to the
  user's desktop session, and the mapper often runs as root (`sudo`) or outside that session,
  where it reaches neither. Not written yet.
