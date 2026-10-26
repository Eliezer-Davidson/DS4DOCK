#!/usr/bin/env python3
"""
ds4_dock.py - a DualShock 4 as a wrist-rest pointing device and macro pad.

One file: standard library + hidapi (+ evdev on Linux). It reads the pad's USB HID reports at
250 Hz, turns the touchpad into a mouse and the buttons and sticks into keys, and drives the
light bar as a status light. Stock controller firmware - nothing is flashed.

Run:
    python ds4_dock.py                      # mapper + live dashboard; Ctrl+C to quit
    python ds4_dock.py --no-inject          # dashboard only, injects nothing (safe first run)
    python ds4_dock.py --selftest           # no hardware needed: parser, mapper, map file
    python ds4_dock.py --dump-map mapping.json     # write the built-in control map out
    python tools/mapping_editor.py          # edit the map on a drawing of the dock's face plate

Files, all optional, read from next to this script unless a flag says otherwise:
    mapping.json          the control map  (--map FILE; --map - for the built-in defaults)
    tune.json             feel settings    (--tune FILE)
    attention_state.txt   a status word for the light bar  (--attention-file FILE)
mapping.json and tune.json are re-read live whenever they change, so editing them - by hand or
with the editor - needs no restart. --gain N overrides touch_gain from tune.json for the whole
run, live reloads included; every other setting is the file's. A tune value outside its sane
span (TUNE_RANGE below) is refused with a one-line message and the setting keeps its value, so
nothing in the file can take the mapper down.

Default control map (v2, 2026-10-21). docs/CONTROLS.md has the reasoning behind every line.

The shell is cut away, so the ONLY inputs that physically exist are the touchpad and its click,
both sticks and their clicks (L3/R3), Share and Options. Five buttons. One momentary layer -
Fn, which is L3 held - buys back the rest. L2/R2 read pressed for good with the triggers gone
(and R2's analogue value wanders); the mapper refuses to bind them. The d-pad, face-button, L1/R1 and PS entries in the map are kept because
they cost nothing, can never fire, and work again if a shell is ever refitted.

    touchpad 1 finger -> cursor, tap = left click   2 fingers -> scroll, tap = middle click
    pad click         -> right click                Fn + pad click -> screen off (see below)
    right stick       -> arrows, repeating faster the further it is pushed
                         Fn + it -> VS Code pane focus (Ctrl+K Ctrl+arrow), once per push
    left stick flick  -> left/right = previous/next app window (Alt+Shift+Tab / Alt+Tab)
                         up/down = previous/next tab (Ctrl+Shift+Tab / Ctrl+Tab)
                         Fn + up -> Task View (Win+Tab)    Fn + down -> centre the cursor
    L3                -> tap = Esc                  HELD = Fn (layer 2)
    R3                -> Enter                      Fn + it -> voice typing (Win+H)
    Share             -> tap = Ctrl+C   hold = Shift (so the stick selects text)
                         Fn + it -> snip tool (Win+Shift+S)
    Options           -> tap = Ctrl+V   hold = Ctrl  (so the stick moves by word)
                         Fn + it -> Win+X
    light bar         -> suspended red > screen off: dark, or orange if attention is set
                         > attention orange > Fn magenta > in use blue > idle OFF.
                         Battery colour for 2 s on plug-in.

The control map file. mapping.json is plain JSON; the shipped one is exactly the map above.
A binding is {"key": "ctrl+shift+tab"} (a key, a chord joined with +, or chords in sequence
separated by spaces: "ctrl+k ctrl+left"), {"mouse": "left"|"right"|"middle"},
{"action": "screen_off"|"suspend"|"cursor_centre"}, or null. Each button has either "press" (held while
the button is down) or "tap" + "hold" (a short press fires tap on release, a long one engages
hold - a modifier, usually; "hold" on its own is allowed and means a short press does nothing),
plus "fn" for the layer. screen_off and suspend go only on a button's "press" or "fn" slot, so
the same press can always undo them. Sticks take a key per direction - except the left stick's
Fn flicks, which also take a mouse button (it clicks once per flick) or cursor_centre - and the
touchpad its gestures.
Unknown names and bad specs are refused with a message that names the slot, so a typo cannot
silently unbind anything. Start from --dump-map FILE rather than from an empty file: an input
that is missing from the file is unbound.

The attention light. attention_state.txt holds one word: "waiting" turns the light bar
orange, anything else (or no file) is idle. Whatever you wait on can write it. I use it for a
coding agent: Claude Code hooks in ~/.claude/settings.json - Notification and Stop write
"waiting", UserPromptSubmit writes "idle", tools/attention.py does the writing - so the pad
glows when the agent has something for you and clears the moment you answer.

Screen off (Fn + pad click). Every screen goes black and everything else keeps running. It is a
black curtain, not a monitor-off: on Modern Standby laptops Windows treats a monitor-off like the
power button and drops the whole PC into standby, so instead each monitor gets a black topmost
window and the mapper tells Windows the display is in use (tune key screen_off_keep_awake), which
also keeps the PC from sleeping. An OLED panel is then dark; an LCD keeps its backlight. While it
is dark the pad injects nothing, so a palm on the touchpad cannot lift it. A key, the mouse or a
touch on the screen brings it back, and so does the same chord again; the curtain watches the
keyboard and the mouse itself, because Windows' own idle clock counts the pad too (_BlackCurtain
says why). Held keys are let go first and the curtain goes up SCREEN_OFF_DELAY_S later; the chord
again in between calls it off. The light bar goes dark too, except orange while the attention
file says "waiting". Windows only for now. Elsewhere (Linux, and --no-inject) held keys are still
let go and the pad and its light are quiet for SCREEN_OFF_DELAY_S, then the mapper carries on as
normal; Linux prints one line saying so. "suspend" - injection off, screen untouched - is still
an action a map can bind; it is just no longer on a chord by default.

Injection: Windows = SendInput through ctypes (relative mouse motion, high-resolution
wheel, scan codes; standard library only). Linux = a virtual device on /dev/uinput (evdev).

Bluetooth is parsed, but USB is the target for the dock: 250 Hz, no battery, headset jack. The
0x11 input report is converted to the USB layout and output reports get their CRC; on Windows,
though, the padded minimal 0x01 report is mistaken for USB, so the full-report request never
fires (docs/CHANGELOG.md, open items).
"""

import argparse
import json
import math
import os
import platform
import sys
import time
import zlib

VID = 0x054C
PIDS = {0x09CC: "DualShock 4 v2 (CUH-ZCT2)", 0x05C4: "DualShock 4 v1 (CUH-ZCT1)",
        0x0BA0: "DS4 USB wireless adaptor"}

# ------------------------------------------------------------------ mapping
#
# These tables ARE the control map. They hold the built-in defaults; apply_mapping() below
# refills them from a mapping.json, and default_mapping() writes them out in that file's schema.
# A button is unbound when it is in none of the tables for its layer.

KEYMAP = {          # layer 1: button -> key name
    "Cross": "enter", "Circle": "esc", "Triangle": "media_play_pause", "Square": "backspace",
    # v2: Share and Options are tap/hold now - see TAP_KEY and HOLD_MOD. Volume is gone from
    # both layers; there is a dedicated volume controller on the desk.
    "dpad_N": "up", "dpad_S": "down", "dpad_W": "left", "dpad_E": "right",
    "L1": "shift", "R1": "ctrl",
    "R3": "enter",                  # v2: Enter was on Cross, which no longer exists
}
KEYMAP_L2 = {       # layer 2 - momentary, held open by Fn (L3). PS is gone with the shell.
    "Cross": "space", "Circle": "esc", "Triangle": "mute", "Square": "tab",
    # v2, the three I added. In layer 2 these fire on PRESS with no tap/hold wait.
    "Share": "super+shift+s",       # snip tool
    "Options": "super+x",           # Windows quick-link menu
    "R3": "super+h",                # Windows voice typing - works in any focused text field
    "dpad_N": "pageup", "dpad_S": "pagedown", "dpad_W": "home", "dpad_E": "end",
    "L1": "shift", "R1": "ctrl",
}
# v2. The shell is cut away: the only inputs that physically exist are the touchpad and its
# click, both sticks and their clicks (L3/R3), Share and Options. Five buttons. The d-pad, face
# buttons, L1/R1 and PS entries above are kept - they cost nothing, they can never fire, and they
# work again if a shell is ever refitted.
MOUSEMAP = {"Pad": "right"}                    # button -> mouse button, held while pressed
MOUSEMAP_L2 = {}                               # the same under Fn
ACTIONS = {}                                   # button -> one-shot action on press
ACTIONS_L2 = {"Pad": "screen_off"}             # under Fn: the screen goes dark until a key (2026-10-26)
SCREEN_OFF_DELAY_S = 0.4                       # held keys are let go first; the screen goes dark this much later
DARK_GRACE_S = 0.5                             # a key or the mouse this soon after the curtain goes up is a
                                               # hand still settling, and does not lift it
DARK_REASSERT_S = 30.0                         # the keep-awake request is renewed this often while dark
CURTAIN_LOST_S = 5.0                           # unchecked this long, the curtain comes down by itself
BATTERY_GUARD_PCT = 20                         # on battery below this, the PC is no longer held awake
LIFTED_BY = {"input": "a key, the mouse or a touch",            # the mapper's note, by lifted_by()
             "lost": "the curtain stopped hearing from the mapper"}
FN_BUTTON = "L3"                               # HELD = layer 2. Tapped = FN_TAP. None = no layer.
FN_TAP = "esc"                                 # Esc was on Circle, which no longer exists
TAP_KEY = {"Share": "ctrl+c", "Options": "ctrl+v"}   # fired on release, if it was a tap
HOLD_MOD = {"Share": "shift", "Options": "ctrl"}     # engaged once held past hold_s, so the
                                               # right stick selects text / moves by word
rstick_mode = "keys"                           # "keys" (v2) or "cursor" (the old coarse pointer)
RSTICK_KEYS = {"W": "left", "E": "right", "N": "up", "S": "down"}
RSTICK_L2 = {"W": "ctrl+k ctrl+left", "E": "ctrl+k ctrl+right",
             "N": "ctrl+k ctrl+up", "S": "ctrl+k ctrl+down"}   # VS Code pane focus
LSTICK_FLICK = {                               # left stick flick direction -> chord, once per flick
    "W": "alt+shift+tab", "E": "alt+tab",      # previous / next app window
    "N": "ctrl+shift+tab", "S": "ctrl+tab",    # previous / next tab
}
LSTICK_FLICK_L2 = {"N": "super+tab"}           # under Fn: Task View ...
LSTICK_ACTIONS_L2 = {"S": "cursor_centre"}     # ... and a flick down puts the cursor mid-screen
LSTICK_MOUSE_L2 = {}                           # under Fn: direction -> mouse button, clicked once per flick
TOUCHPAD = {"one_finger": "cursor",            # "cursor" or None
            "one_finger_tap": "left",          # mouse button or None
            "two_finger": "scroll",            # "scroll" or None
            "two_finger_tap": "middle"}        # mouse button or None
MODIFIERS = {"ctrl", "shift", "alt", "super"}   # never auto-repeated
# key names: KEY_NAMES below, single letters/digits, f1..f12; chords join them with '+'

# Feel. Every value here can be changed live through --tune (a JSON file with the same
# keys); the file is re-read whenever it changes, so tuning needs no restart. A number is
# accepted only inside its TUNE_RANGE span; outside it the setting keeps its value and one
# line says why, so no edit can take the mapper down.
TUNE = {
    "touch_gain": 0.35,          # one finger: cursor px per pad unit
    "touch_accel": 0.0,          # extra gain per pad-unit/frame of finger speed (0 = linear)
    "touch_scroll_gain": 0.8,    # two fingers: wheel units (1/120 notch) per pad unit
    "natural_scroll": False,     # True: content follows the fingers
    "tap_max_s": 0.18,           # a contact shorter than this ...
    "tap_max_move": 40,          # ... that moved less than this (pad units) is a tap
    "stick_deadzone": 12,        # of 127
    "stick_expo": 2.0,           # right stick response: 1 = linear, 2 = squared
    "stick_max_px": 8.0,         # right stick: cursor px per frame at full deflection (x250 Hz)
    "flick_on": 0.6,             # left stick: deflection (0..1) that fires a flick ...
    "flick_off": 0.3,            # ... and the deflection it must fall back to before the next
    "key_repeat": True,          # held mapped keys repeat at the system keyboard rate
    "hold_s": 0.25,              # a press shorter than this is a tap, longer engages the modifier
    "rstick_rate_min": 4.0,      # right stick as arrows: keys/s just past the deadzone ...
    "rstick_rate_max": 25.0,     # ... and keys/s at full deflection
    "led_idle_s": 2.0,           # the light stays blue this long after the last real input
    "screen_off_keep_awake": True,   # while the screen is blacked out, Windows keeps the display and the
                                     # PC awake (false: its own display and sleep timers apply as usual)
}
TUNE_RANGE = {                   # lo..hi for every number above, inclusive. The ceilings are generous,
    "touch_gain": (0, 20),       # well past any useful value, and inside them every product in
    "touch_accel": (0, 1),       # Mapper.step() stays finite (int() of inf would raise)
    "touch_scroll_gain": (0, 20),
    "tap_max_s": (0, 10),
    "tap_max_move": (0, 2000),
    "stick_deadzone": (0, 126),  # 127 would divide by zero in curve()
    "stick_expo": (0.1, 10),     # a negative expo raises zero or a tiny number to a negative power
    "stick_max_px": (0, 200),
    "flick_on": (0.05, 1),       # 0 would fire a flick at rest, every report
    "flick_off": (0, 1),         # and flick_off < flick_on is checked once a file is merged
    "hold_s": (0, 10),
    "rstick_rate_min": (0.1, 250),   # 0 keys/s would divide by zero; 250 is the report rate
    "rstick_rate_max": (0.1, 250),
    "led_idle_s": (0, 3600),
}
LED_COLOURS = {"good": (0, 140, 30), "mid": (200, 110, 0), "low": (200, 0, 0),
               "layer2": (170, 0, 170), "idle": (0, 0, 60),
               "active": (0, 60, 200), "attention": (255, 90, 0),
               "suspended": (60, 0, 0), "off": (0, 0, 0)}

# ------------------------------------------------------------------ report parsing

DPAD = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", ""]
B5 = {4: "Square", 5: "Cross", 6: "Circle", 7: "Triangle"}
B6 = {0: "L1", 1: "R1", 2: "L2", 3: "R2", 4: "Share", 5: "Options", 6: "L3", 7: "R3"}
B7 = {0: "PS", 1: "Pad"}


def s16(buf, i):
    return int.from_bytes(bytes(buf[i:i + 2]), "little", signed=True)


def parse_usb(r):
    """r: 64-byte USB input report 0x01 (list/bytes). Returns a dict."""
    st = {}
    st["lx"], st["ly"], st["rx"], st["ry"] = r[1], r[2], r[3], r[4]
    st["dpad"] = DPAD[r[5] & 0x0F] if (r[5] & 0x0F) < 8 else ""
    btn = set()
    for bit, name in B5.items():
        if (r[5] >> bit) & 1:
            btn.add(name)
    for bit, name in B6.items():
        if (r[6] >> bit) & 1:
            btn.add(name)
    for bit, name in B7.items():
        if (r[7] >> bit) & 1:
            btn.add(name)
    # d-pad as four pseudo-buttons so it can be mapped like keys
    for d in st["dpad"]:
        btn.add("dpad_" + d)
    st["buttons"] = btn
    st["l2"], st["r2"] = r[8], r[9]
    st["ts"] = r[10] | (r[11] << 8)                 # 16-bit, 5.33 us units
    st["gyro"] = (s16(r, 13), s16(r, 15), s16(r, 17))   # pitch, yaw, roll (raw)
    st["accel"] = (s16(r, 19), s16(r, 21), s16(r, 23))  # raw, ~8192 per g
    st["usb"] = bool(r[30] & 0x10)
    st["headphones"] = bool(r[30] & 0x20)
    st["mic"] = bool(r[30] & 0x40)
    lvl = r[30] & 0x0F
    if st["usb"]:
        st["battery"] = 100 if lvl >= 11 else lvl * 10
    else:
        st["battery"] = 100 if lvl >= 10 else lvl * 10 + 5
    touches = []
    for off in (35, 39):                              # finger 1, finger 2
        active = not (r[off] & 0x80)
        tid = r[off] & 0x7F
        x = ((r[off + 2] & 0x0F) << 8) | r[off + 1]
        y = (r[off + 3] << 4) | (r[off + 2] >> 4)
        touches.append((active, tid, x, y))
    st["touch"] = touches
    return st


def bt_to_usb(r):
    """BT input report 0x11 (78 bytes) -> USB-shaped 64-byte report."""
    return [0x01] + list(r[3:66])


def led_report(rgb, bt=False, flash=(0, 0)):
    """Output report bytes for the light bar. The rumble motors are removed, so the rumble
    bytes (USB [4][5], BT [6][7]) are never written and stay 0."""
    r, g, b = rgb
    if not bt:
        rep = bytearray(32)
        rep[0], rep[1], rep[2] = 0x05, 0x07, 0x04
        rep[6:9] = bytes((r, g, b))
        rep[9], rep[10] = flash
    else:
        rep = bytearray(78)
        rep[0], rep[1], rep[3] = 0x11, 0xC0, 0x07
        rep[8:11] = bytes((r, g, b))
        rep[11], rep[12] = flash
        crc = zlib.crc32(b"\xA2" + bytes(rep[:74])) & 0xFFFFFFFF
        rep[74:78] = crc.to_bytes(4, "little")
    return bytes(rep)


# ------------------------------------------------------------------ injection backends
#
# Common interface:  move(dx, dy) px   scroll(v, h) in wheel units (120 = one notch,
# positive = up / right)   click(button, down)   key(name, down)   centre()   close()
# and five for screen off, real only on Windows (stubs elsewhere):
#   display_off() -> bool   black every screen out; False = cannot, and the mapper stays normal
#   display_on()            lift the curtain     display_dark() -> bool  still up? (also a heartbeat)
#   keep_awake(on)          the display and the PC count as in use while dark, or stop
#   lifted_by() -> str or None   why the curtain came down by itself: "input" (a key, the mouse,
#                           a touch) or "lost" (the mapper stopped checking on it); None if it did not
# repeat_delay / repeat_period: the system keyboard auto-repeat timing, in seconds.

KEY_NAMES = ["enter", "esc", "up", "down", "left", "right", "backspace", "space", "tab",
             "insert", "delete", "media_play_pause", "volume_up", "volume_down", "mute",
             "pageup", "pagedown", "home", "end", "ctrl", "shift", "alt", "super"]
# plus the single characters a-z and 0-9, and f1..f12. validate_key_spec() below is the rule.


class NullInjector:
    """Injects nothing. --no-inject (and a failed injector setup) use it silently; the self-test's
    Recorder subclass turns verbose on, which prints each call."""
    name = "none"
    repeat_delay, repeat_period = 0.5, 1 / 30

    def __init__(self, verbose=False):
        self.verbose = verbose

    def move(self, dx, dy):
        if self.verbose:
            print(f"  move {dx:+d},{dy:+d}")

    def scroll(self, v, h=0):
        if self.verbose:
            print(f"  scroll {v:+d},{h:+d}")

    def click(self, button, down):
        if self.verbose:
            print(f"  mouse {button} {'down' if down else 'up'}")

    def key(self, name, down):
        if self.verbose:
            print(f"  key {name} {'down' if down else 'up'}")

    def centre(self):
        if self.verbose:
            print("  centre cursor")

    def display_off(self):
        """--no-inject changes nothing on the system, so the screen stays on. False tells the
        mapper not to go quiet over a screen that is still lit."""
        if self.verbose:
            print("  screen off (not with --no-inject)")
        return False

    def display_on(self):
        pass

    def display_dark(self):
        return False

    def lifted_by(self):
        return None

    def keep_awake(self, on):
        pass

    def close(self):
        pass


class EvdevInjector:
    """Linux: a virtual mouse+keyboard through /dev/uinput. Works on X11 and Wayland."""
    name = "evdev/uinput"
    repeat_delay, repeat_period = 0.25, 1 / 33     # kernel defaults

    def __init__(self):
        from evdev import UInput, ecodes as e
        self.e = e
        self.codes = {
            "enter": e.KEY_ENTER, "esc": e.KEY_ESC, "up": e.KEY_UP, "down": e.KEY_DOWN,
            "left": e.KEY_LEFT, "right": e.KEY_RIGHT, "backspace": e.KEY_BACKSPACE,
            "space": e.KEY_SPACE, "tab": e.KEY_TAB, "media_play_pause": e.KEY_PLAYPAUSE,
            "volume_up": e.KEY_VOLUMEUP, "volume_down": e.KEY_VOLUMEDOWN, "mute": e.KEY_MUTE,
            "pageup": e.KEY_PAGEUP, "pagedown": e.KEY_PAGEDOWN, "home": e.KEY_HOME,
            "end": e.KEY_END, "insert": e.KEY_INSERT, "delete": e.KEY_DELETE,
            "ctrl": e.KEY_LEFTCTRL, "shift": e.KEY_LEFTSHIFT,
            "alt": e.KEY_LEFTALT, "super": e.KEY_LEFTMETA,
        }
        for ch in "abcdefghijklmnopqrstuvwxyz0123456789":
            self.codes[ch] = getattr(e, "KEY_" + ch.upper())
        for i in range(1, 13):
            self.codes[f"f{i}"] = getattr(e, f"KEY_F{i}")
        self.btn = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
        self.hires = (getattr(e, "REL_WHEEL_HI_RES", None), getattr(e, "REL_HWHEEL_HI_RES", None))
        rel = [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL] + [c for c in self.hires if c is not None]
        cap = {e.EV_KEY: sorted(set(self.codes.values()) | set(self.btn.values())), e.EV_REL: rel}
        self.ui = UInput(cap, name="DS4 dock", vendor=0x054C, product=0x0DCC)
        self.notch = [0, 0]      # wheel units accumulated toward the next whole notch

    def move(self, dx, dy):
        e = self.e
        if dx:
            self.ui.write(e.EV_REL, e.REL_X, int(dx))
        if dy:
            self.ui.write(e.EV_REL, e.REL_Y, int(dy))
        self.ui.syn()

    def scroll(self, v, h=0):
        e = self.e
        for i, (units, hi, lo) in enumerate(((v, self.hires[0], e.REL_WHEEL),
                                             (h, self.hires[1], e.REL_HWHEEL))):
            if not units:
                continue
            if hi is not None:
                self.ui.write(e.EV_REL, hi, int(units))
            self.notch[i] += units
            n = int(self.notch[i] / 120)
            if n:
                self.ui.write(e.EV_REL, lo, n)
                self.notch[i] -= n * 120
        self.ui.syn()

    def click(self, button, down):
        self.ui.write(self.e.EV_KEY, self.btn[button], 1 if down else 0)
        self.ui.syn()

    def key(self, name, down):
        code = self.codes.get(name)
        if code is None:
            return
        self.ui.write(self.e.EV_KEY, code, 1 if down else 0)
        self.ui.syn()

    def centre(self):
        pass        # a relative uinput device has no absolute positioning; not supported on Linux yet

    def display_off(self):
        # X11 has DPMS and GNOME on Wayland has a D-Bus call, but the mapper runs as root here and
        # neither is reachable from root without the user's session. Not yet.
        if not getattr(self, "_said_screen", False):
            print("\n! screen_off: turning the screen off is Windows-only for now")
            self._said_screen = True
        return False

    def display_on(self):
        pass

    def display_dark(self):
        return False

    def lifted_by(self):
        return None

    def keep_awake(self, on):
        pass

    def close(self):
        self.ui.close()


class SendInputInjector:
    """Windows: SendInput through ctypes. Relative mouse motion (so pointer speed,
    acceleration and raw-input apps all behave), wheel in 1/120-notch units, keys sent
    with virtual-key + scan code + the extended-key flag. Standard library only."""
    name = "SendInput"
    VK = {"enter": 0x0D, "esc": 0x1B, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
          "backspace": 0x08, "space": 0x20, "tab": 0x09, "media_play_pause": 0xB3,
          "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "pageup": 0x21, "pagedown": 0x22,
          "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
          "ctrl": 0xA2, "shift": 0xA0, "alt": 0xA4, "super": 0x5B}
    for _i in range(12):
        VK[f"f{_i + 1}"] = 0x70 + _i
    for _ch in "abcdefghijklmnopqrstuvwxyz0123456789":
        VK[_ch] = ord(_ch.upper())
    EXTENDED = {"up", "down", "left", "right", "pageup", "pagedown", "home", "end", "insert",
                "delete", "super", "media_play_pause", "volume_up", "volume_down", "mute"}
    MOUSE = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
    MOVE, WHEEL, HWHEEL, ABSOLUTE = 0x0001, 0x0800, 0x1000, 0x8000
    KEYUP, EXT, SCANCODE = 0x0002, 0x0001, 0x0008
    EXTRA = 0x0D54D0C0         # dwExtraInfo tag so our own events can be recognised

    def __init__(self):
        import ctypes
        from ctypes import wintypes as w
        self.ct = ctypes
        ULONG_PTR = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                        ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                        ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", w.DWORD), ("u", _U)]

        self.INPUT = INPUT
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = (w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self.user32.SendInput.restype = w.UINT
        self.user32.MapVirtualKeyW.argtypes = (w.UINT, w.UINT)
        self.user32.MapVirtualKeyW.restype = w.UINT
        self.scan = {name: self.user32.MapVirtualKeyW(vk, 0) for name, vk in self.VK.items()}
        self.dropped = 0
        # the system keyboard repeat settings (SPI_GETKEYBOARDDELAY 0..3, SPI_GETKEYBOARDSPEED 0..31)
        delay, speed = w.DWORD(1), w.DWORD(31)
        self.user32.SystemParametersInfoW(0x16, 0, ctypes.byref(delay), 0)
        self.user32.SystemParametersInfoW(0x0A, 0, ctypes.byref(speed), 0)
        self.repeat_delay = 0.25 * (delay.value + 1)
        self.repeat_period = 1.0 / (2.5 + 27.5 * speed.value / 31)
        # screen off: the execution-state request that keeps the display and the PC awake while
        # dark, and the battery level that limits it. The curtain itself (_BlackCurtain), which
        # also watches the keyboard and the mouse, is only built the first time it is needed.

        class SYSTEM_POWER_STATUS(ctypes.Structure):          # c_ubyte, not wintypes.BYTE: 255 = unknown
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", w.DWORD), ("BatteryFullLifeTime", w.DWORD)]

        self.SYSTEM_POWER_STATUS = SYSTEM_POWER_STATUS
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.SetThreadExecutionState.argtypes = (w.DWORD,)
        self.kernel32.SetThreadExecutionState.restype = w.DWORD
        self.kernel32.GetSystemPowerStatus.argtypes = (ctypes.POINTER(SYSTEM_POWER_STATUS),)
        self.kernel32.GetSystemPowerStatus.restype = w.BOOL
        self.curtain = None
        self._said_battery = False

    def _send(self, *events):
        arr = (self.INPUT * len(events))(*events)
        sent = self.user32.SendInput(len(events), arr, self.ct.sizeof(self.INPUT))
        if sent != len(events):        # e.g. secure desktop / elevated window: dropped, never raises
            self.dropped += len(events) - sent

    def _mouse(self, flags, dx=0, dy=0, data=0):
        ev = self.INPUT(type=0)
        ev.mi.dx, ev.mi.dy = int(dx), int(dy)
        ev.mi.mouseData = int(data) & 0xFFFFFFFF
        ev.mi.dwFlags, ev.mi.dwExtraInfo = flags, self.EXTRA
        return ev

    def move(self, dx, dy):
        self._send(self._mouse(self.MOVE, dx, dy))

    def scroll(self, v, h=0):
        evs = []
        if v:
            evs.append(self._mouse(self.WHEEL, data=v))
        if h:
            evs.append(self._mouse(self.HWHEEL, data=h))
        if evs:
            self._send(*evs)

    def click(self, button, down):
        self._send(self._mouse(self.MOUSE[button][0 if down else 1]))

    def key(self, name, down):
        vk = self.VK.get(name)
        if vk is None:
            return
        ev = self.INPUT(type=1)
        ev.ki.wVk, ev.ki.wScan = vk, self.scan[name]
        ev.ki.dwFlags = (0 if down else self.KEYUP) | (self.EXT if name in self.EXTENDED else 0)
        ev.ki.dwExtraInfo = self.EXTRA
        self._send(ev)

    def centre(self):
        # absolute coordinates run 0..65535 across the primary monitor
        self._send(self._mouse(self.MOVE | self.ABSOLUTE, 32768, 32768))

    def display_off(self):
        """Black out every screen - see _BlackCurtain for why it is not a monitor-off. True once
        the curtain is up; False if it could not be raised, and then the mapper stays normal."""
        self._said_battery = False
        try:
            if self.curtain is None:
                self.curtain = _BlackCurtain()
            if self.curtain.up():
                return True
            why = self.curtain.error or "no reason given"
        except Exception as ex:          # noqa: BLE001 - a missing API or a failed call: stay normal
            why = str(ex)
        print(f"\n! screen_off: could not black the screen out ({why})", file=sys.stderr)
        return False

    def display_on(self):
        if self.curtain is not None:
            self.curtain.down()

    def display_dark(self):
        """Is the curtain still up? The mapper asks on every report while dark, which doubles as
        a heartbeat: if it stops asking for CURTAIN_LOST_S, the curtain comes down by itself."""
        return self.curtain is not None and self.curtain.still_up()

    def lifted_by(self):
        """Why the curtain came down by itself - "input" or "lost" - or None if it did not."""
        return self.curtain.lifted_by if self.curtain is not None else None

    def keep_awake(self, on):
        """ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED while the screen is blacked
        out: as far as Windows is concerned the display is in use, so neither its display timer
        nor its sleep timer fires and no Modern Standby session ever begins. The mapper renews it
        every DARK_REASSERT_S. On battery below BATTERY_GUARD_PCT it is let go instead and
        Windows' own timers take over - though with the dock plugged in they may never run out,
        since Windows counts the floating R2 as activity (docs/HARDWARE.md; untested). The
        request belongs to this thread and ends with the process, so a crash cannot leave the PC
        held awake."""
        if on and self._battery_low():
            if not self._said_battery:
                print(f"\n! screen_off: battery under {BATTERY_GUARD_PCT}% - no longer keeping the PC awake",
                      file=sys.stderr)
                self._said_battery = True
            on = False
        self.kernel32.SetThreadExecutionState(0x80000003 if on else 0x80000000)

    def _battery_low(self):
        s = self.SYSTEM_POWER_STATUS()
        if not self.kernel32.GetSystemPowerStatus(self.ct.byref(s)):
            return False
        return s.ACLineStatus == 0 and s.BatteryLifePercent < BATTERY_GUARD_PCT   # 255 = unknown: not low

    def close(self):
        self.display_on()
        self.keep_awake(False)


class _BlackCurtain:
    """Windows 'screen off': one black, topmost window over each monitor that never takes focus.

    Why not switch the monitors off: on a Modern Standby laptop, a WM_SYSCOMMAND / SC_MONITORPOWER
    display-off is handled like the power button. Windows begins a standby and cancels every
    keep-awake request any program holds, so downloads, audio and this mapper all stop - reported
    across Lenovo, Framework and ASUS machines, with Kernel-Power 506 'Reason: SC_MONITORPOWER' in
    their event logs. A black window is not a display-off at all, so with ES_DISPLAY_REQUIRED held
    (keep_awake) Windows never begins a standby and everything keeps running. On an OLED panel
    black is off; an LCD keeps its backlight on.

    The windows belong to a thread of their own with its own message loop, because the HID loop
    never pumps messages. That thread also lifts the curtain by itself - on a key, the mouse or a
    touch on the screen, or once the mapper has not checked on it for CURTAIN_LOST_S - so whatever
    the main loop is doing, nobody is left in front of a black screen they cannot get rid of.
    Windows belong to the process, so a crash takes them along.

    The keyboard and the mouse are watched through Raw Input, which reaches the curtain while
    another app has the focus (RIDEV_INPUTSINK), and only while it is up. Not through
    GetLastInputInfo: Windows counts a game controller's input as activity too, and with the
    dock's triggers cut away R2 floats, so that clock moves several times a second with nobody
    there (2026-10-26: 67 moves in 12 s, each within 20 ms of a change in R2's raw value, and
    as many with the mapper suspended). A touch or a pen on the black screen lands on the
    curtain itself, as WM_POINTER messages, and so does a click or a wheel turn - which still
    counts if Windows ever keeps the keyboard and the mouse from reaching the Raw Input sink
    (perhaps while an elevated window has the focus; untested). The curtain keeps all of it: it
    handles the pointer messages itself, so a contact is never turned into a click, and it lifts
    only once every button, finger and pen is up again, so the release lands on the curtain and
    not on the app beneath, where a bare right-button-up would open a context menu and a side
    button go Back. Held longer than HELD_LIFT_S it lifts anyway, and that release then does
    reach the app.

    A display change while it is up (a monitor unplugged or switched off, a new mode) covers the
    monitors anew before the old windows go, and still_up() keeps answering yes throughout: the
    mapper takes a single no for the curtain having come down."""
    CLASS = "ds4dock_black"
    WM_APP_SHOW, WM_APP_HIDE, WM_APP_LAYOUT, WM_APP_LIFT = 0x8001, 0x8002, 0x8003, 0x8004
    WM_CLOSE, WM_SETCURSOR, WM_MOUSEACTIVATE, WM_DISPLAYCHANGE, WM_TIMER = 0x10, 0x20, 0x21, 0x7E, 0x113
    WM_INPUT = 0x00FF
    WM_POINTERUPDATE, WM_POINTERDOWN, WM_POINTERUP = 0x0245, 0x0246, 0x0247
    WM_POINTERACTIVATE, WM_POINTERCAPTURECHANGED, PA_NOACTIVATE = 0x024B, 0x024C, 3
    # what lifts it: Raw Input, a finger or a pen, and the left, right, middle and X buttons and
    # both wheels landing on the curtain. Never WM_MOUSEMOVE: Windows makes those up when a
    # window appears or changes place in the z-order, or the cursor is set.
    LIFT_ON = frozenset((WM_INPUT, WM_POINTERDOWN, 0x0201, 0x0204, 0x0207, 0x020B, 0x020A, 0x020E))
    # and what it swallows: a release on the curtain must not open a menu or go Back
    WM_CONTEXTMENU, WM_APPCOMMAND = 0x007B, 0x0319
    MOUSE_VKS = (0x01, 0x02, 0x04, 0x05, 0x06)           # VK_LBUTTON, RBUTTON, MBUTTON, XBUTTON1, XBUTTON2
    HELD_LIFT_S = 2.0                                    # a button, finger or pen held longer lifts it anyway
    RIDEV_REMOVE, RIDEV_INPUTSINK = 0x00000001, 0x00000100
    MA_NOACTIVATE = 3
    WS_POPUP = 0x80000000
    WS_EX = 0x00000008 | 0x00000080 | 0x08000000        # TOPMOST | TOOLWINDOW (no taskbar) | NOACTIVATE
    SW_SHOWNOACTIVATE = 4
    SWP = 0x0010 | 0x0040                                # NOACTIVATE | SHOWWINDOW
    SWP_RAISE = 0x0001 | 0x0002 | 0x0010                 # NOSIZE | NOMOVE | NOACTIVATE
    TICK_MS = 100                                        # the thread's own timer: heartbeat, z-order

    def __init__(self):
        import ctypes
        import threading
        from ctypes import wintypes as w
        self.ct, self.w = ctypes, w
        u = self.u = ctypes.WinDLL("user32", use_last_error=True)
        k = self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        g = ctypes.WinDLL("gdi32", use_last_error=True)
        LRESULT = w.LPARAM                               # pointer-sized, like WPARAM and LPARAM
        self.WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.MONITORENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HMONITOR, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", self.WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
                        ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                        ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]

        class RAWINPUTDEVICE(ctypes.Structure):
            _fields_ = [("usUsagePage", w.USHORT), ("usUsage", w.USHORT), ("dwFlags", w.DWORD),
                        ("hwndTarget", w.HWND)]

        self.WNDCLASSEXW, self.MONITORINFO, self.RAWINPUTDEVICE = WNDCLASSEXW, MONITORINFO, RAWINPUTDEVICE
        for fn, args, res in (
                (u.DefWindowProcW, (w.HWND, w.UINT, w.WPARAM, w.LPARAM), LRESULT),
                (u.RegisterClassExW, (ctypes.POINTER(WNDCLASSEXW),), w.ATOM),
                (u.CreateWindowExW, (w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID), w.HWND),
                (u.DestroyWindow, (w.HWND,), w.BOOL),
                (u.ShowWindow, (w.HWND, ctypes.c_int), w.BOOL),
                (u.SetWindowPos, (w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT), w.BOOL),
                (u.GetMessageW, (ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT), w.BOOL),
                (u.PeekMessageW, (ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT), w.BOOL),
                (u.TranslateMessage, (ctypes.POINTER(w.MSG),), w.BOOL),
                (u.DispatchMessageW, (ctypes.POINTER(w.MSG),), LRESULT),
                (u.PostThreadMessageW, (w.DWORD, w.UINT, w.WPARAM, w.LPARAM), w.BOOL),
                (u.EnumDisplayMonitors, (w.HDC, ctypes.POINTER(w.RECT), self.MONITORENUMPROC, w.LPARAM), w.BOOL),
                (u.GetMonitorInfoW, (w.HMONITOR, ctypes.POINTER(MONITORINFO)), w.BOOL),
                (u.SetCursor, (w.HANDLE,), w.HANDLE),
                (u.GetCursorPos, (ctypes.POINTER(w.POINT),), w.BOOL),
                (u.SetCursorPos, (ctypes.c_int, ctypes.c_int), w.BOOL),
                (u.SetTimer, (w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID), ctypes.c_size_t),
                (u.KillTimer, (w.HWND, ctypes.c_size_t), w.BOOL),
                (u.RegisterRawInputDevices, (ctypes.POINTER(RAWINPUTDEVICE), w.UINT, w.UINT), w.BOOL),
                (u.GetAsyncKeyState, (ctypes.c_int,), w.SHORT),
                (g.GetStockObject, (ctypes.c_int,), w.HGDIOBJ),
                (k.GetModuleHandleW, (w.LPCWSTR,), w.HMODULE),
                (k.GetCurrentThreadId, (), w.DWORD)):
            fn.argtypes, fn.restype = args, res
        self.black = g.GetStockObject(4)                 # BLACK_BRUSH
        self.wndproc = self.WNDPROC(self._wndproc)       # must outlive every window of the class
        self.thread, self.tid, self.class_ok = None, 0, False
        self.ready, self.shown, self.hidden = threading.Event(), threading.Event(), threading.Event()
        self.threading = threading
        self.windows, self.timer, self.ticks = [], 0, 0
        self.ping = self.grace_until = self.lift_at = 0.0
        self.is_up = False                    # what still_up() answers; only a real lift clears it
        self.contacts = set()                 # fingers and pens down on the curtain, by pointer id
        self.sinking = self.lifting = self.relayout = False   # Raw Input registered; a lift, or a
                                                               # relayout, already on its way
        self.lifted_by = self.error = None    # why it came down by itself; why up() failed

    # -------------------------------------------------- the main thread's side
    def up(self):
        self.lifted_by = self.error = None
        if self.thread is None or not self.thread.is_alive():
            self.ready.clear()
            self.thread = self.threading.Thread(target=self._run, name="ds4dock-curtain", daemon=True)
            self.thread.start()
            if not self.ready.wait(2.0) or not self.class_ok:
                self.error = self.error or "its window thread did not start"
                return False
        self.ping = time.monotonic()
        self.shown.clear()
        if not self.u.PostThreadMessageW(self.tid, self.WM_APP_SHOW, 0, 0) or not self.shown.wait(2.0):
            self.error = "its window thread did not answer"
            return False
        if not self.is_up:
            self.error = self.error or "there was no monitor to cover"
        return self.is_up

    def down(self):
        if self.thread is None or not self.thread.is_alive() or not self.tid:
            return
        self.hidden.clear()
        if self.u.PostThreadMessageW(self.tid, self.WM_APP_HIDE, 0, 0):
            self.hidden.wait(2.0)

    def still_up(self):
        self.ping = time.monotonic()
        return self.is_up

    # -------------------------------------------------- the curtain thread
    def _run(self):
        ct, w, u = self.ct, self.w, self.u
        try:
            try:
                u.SetThreadDpiAwarenessContext.argtypes = (w.HANDLE,)
                u.SetThreadDpiAwarenessContext.restype = w.HANDLE
                u.SetThreadDpiAwarenessContext(ct.c_void_p(-4))   # per-monitor v2: physical pixels
            except AttributeError:
                pass                                     # before Windows 10 1607: logical pixels
            msg = w.MSG()
            u.PeekMessageW(ct.byref(msg), None, 0, 0, 0)          # gives this thread a message queue
            self.tid = self.k.GetCurrentThreadId()
            wc = self.WNDCLASSEXW()
            wc.cbSize = ct.sizeof(wc)
            wc.lpfnWndProc = self.wndproc
            wc.hInstance = self.k.GetModuleHandleW(None)
            wc.hbrBackground = self.black
            wc.lpszClassName = self.CLASS
            self.class_ok = bool(u.RegisterClassExW(ct.byref(wc))) or ct.get_last_error() == 1410   # already there
            if not self.class_ok:
                self.error = f"RegisterClassExW failed (error {ct.get_last_error()})"
        finally:
            self.ready.set()
        if not self.class_ok:
            return
        try:
            while u.GetMessageW(ct.byref(msg), None, 0, 0) > 0:
                if not msg.hWnd and self._dispatch(msg.message):     # ours, and the thread's timer
                    continue
                u.TranslateMessage(ct.byref(msg))
                u.DispatchMessageW(ct.byref(msg))
        finally:
            self._hide()

    def _dispatch(self, message):
        """The curtain thread's own messages, posted to the thread rather than to a window. True
        if it was one of them."""
        if message == self.WM_APP_SHOW:
            self._show(nudge=True)
        elif message == self.WM_APP_HIDE:
            self._hide()
        elif message == self.WM_APP_LIFT:               # from _wndproc: the user is back
            if self.is_up and not self._held():          # still held: _tick lifts it once it is let go
                self.lifted_by = "input"                 # before is_up goes, so the mapper reads why
                self._hide()
        elif message == self.WM_APP_LAYOUT:             # from _wndproc: the monitors changed
            self.relayout = False
            if self.is_up:
                self._relayout()
        elif message == self.WM_TIMER:
            self._tick()
        else:
            return False
        return True

    def _monitors(self):
        rects = []

        def each(hmon, hdc, lprc, data):
            mi = self.MONITORINFO()
            mi.cbSize = self.ct.sizeof(mi)
            if self.u.GetMonitorInfoW(hmon, self.ct.byref(mi)):
                r = mi.rcMonitor
                rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        self.u.EnumDisplayMonitors(None, None, self.MONITORENUMPROC(each), 0)
        return rects

    def _sink(self, hwnd):
        """Raw Input from the keyboard and the mouse, sent to hwnd even while another app has the
        focus (RIDEV_INPUTSINK); None takes it away again (RIDEV_REMOVE). Those two only: the
        gamepad page would bring in the pad itself, 250 reports a second."""
        rid = (self.RAWINPUTDEVICE * 2)()
        for r, usage in zip(rid, (0x06, 0x02)):          # generic desktop page: keyboard, mouse
            r.usUsagePage, r.usUsage = 0x01, usage
            r.dwFlags = self.RIDEV_INPUTSINK if hwnd else self.RIDEV_REMOVE
            r.hwndTarget = hwnd
        return bool(self.u.RegisterRawInputDevices(rid, 2, self.ct.sizeof(self.RAWINPUTDEVICE)))

    def _held(self):
        """Is a mouse button, a finger or a pen still down? Then whatever woke the curtain is not
        over, and lifting now would hand its release to the app beneath, where a bare
        right-button-up opens a context menu and a side button goes Back."""
        return bool(self.contacts) or any(self.u.GetAsyncKeyState(vk) & 0x8000 for vk in self.MOUSE_VKS)

    def _cover(self):
        """One black window over each monitor, on top and shown without taking the focus."""
        ct, u = self.ct, self.u
        hinst = self.k.GetModuleHandleW(None)
        made = []
        for x, y, cx, cy in self._monitors():
            h = u.CreateWindowExW(self.WS_EX, self.CLASS, "", self.WS_POPUP, x, y, cx, cy,
                                  None, None, hinst, None)
            if h:
                made.append(h)
                u.ShowWindow(h, self.SW_SHOWNOACTIVATE)
                u.SetWindowPos(h, ct.c_void_p(-1), x, y, cx, cy, self.SWP)          # HWND_TOPMOST
        return made

    def _show(self, nudge):
        ct, u = self.ct, self.u
        self.grace_until = time.monotonic() + DARK_GRACE_S
        self.lifting, self.contacts = False, set()
        if not self.windows:
            self.windows = self._cover()
            if self.windows and not self._sink(self.windows[0]):
                self.error = f"the keyboard and the mouse could not be watched (error {ct.get_last_error()})"
                self._hide()                             # a curtain nothing could lift is worse than none
            if self.windows:
                self.sinking = True
                self.timer = u.SetTimer(None, 0, self.TICK_MS, None)
                if nudge:                                # a WM_SETCURSOR, so the arrow goes black too
                    p = self.w.POINT()
                    if u.GetCursorPos(ct.byref(p)):
                        u.SetCursorPos(p.x + 1, p.y)
                        u.SetCursorPos(p.x, p.y)
        self.is_up = bool(self.windows)
        self.shown.set()

    def _relayout(self):
        """The monitors changed while it is up: cover them as they are now, move the Raw Input
        sink to the new windows (registering again replaces the target), and only then let the
        old windows go - so no screen shows through, and is_up never drops in between. If no
        new cover can be made, or watched, the old one stays."""
        new = self._cover()
        if not new or not self._sink(new[0]):
            for h in new:
                self.u.DestroyWindow(h)
            return
        old, self.windows = self.windows, new
        for h in old:
            self.u.DestroyWindow(h)

    def _hide(self):
        self.is_up = False
        if self.timer:
            self.u.KillTimer(None, self.timer)
            self.timer = 0
        if self.sinking:                                 # before the window it reports to is gone
            self._sink(None)
            self.sinking = False
        for h in self.windows:
            self.u.DestroyWindow(h)
        self.windows = []
        self.hidden.set()

    def _tick(self):
        """Every TICK_MS while up: the mapper gone quiet, and every 2 s the windows put back on top
        of anything that rose above them. The user coming back arrives as WM_INPUT instead."""
        if not self.is_up:
            return
        if time.monotonic() - self.ping > CURTAIN_LOST_S:
            self.lifted_by = "lost"
            self._hide()
            return
        if self.lifting and (not self._held() or time.monotonic() - self.lift_at > self.HELD_LIFT_S):
            self.lifted_by = "input"                     # the click or the tap that woke it is over
            self._hide()
            return
        self.ticks += 1
        if self.ticks % 20 == 0:
            for h in self.windows:
                self.u.SetWindowPos(h, self.ct.c_void_p(-1), 0, 0, 0, 0, self.SWP_RAISE)

    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg in self.LIFT_ON:
                # a key, the mouse, a finger or a pen: the user is back, unless the curtain has only
                # just gone up. Lifted from the message loop, not from inside one of its own
                # windows' messages; WM_INPUT still goes on to DefWindowProc, which frees its data.
                if self.is_up and not self.lifting and time.monotonic() >= self.grace_until:
                    self.lifting, self.lift_at = True, time.monotonic()
                    self.u.PostThreadMessageW(self.tid, self.WM_APP_LIFT, 0, 0)
            # a finger or a pen: handled here, so Windows never turns the contact into a mouse
            # click, and tracked until it is up (the pointer id is the low word of wParam)
            if msg == self.WM_POINTERDOWN:
                self.contacts.add(wp & 0xFFFF)
                return 0
            if msg == self.WM_POINTERUP or msg == self.WM_POINTERCAPTURECHANGED:
                self.contacts.discard(wp & 0xFFFF)
                return 0
            if msg == self.WM_POINTERUPDATE:
                return 0
            if msg == self.WM_POINTERACTIVATE:
                return self.PA_NOACTIVATE                # a touch never pulls focus off the app beneath
            if msg == self.WM_CONTEXTMENU or msg == self.WM_APPCOMMAND:
                return 1                                 # a release on the curtain does nothing
            if msg == self.WM_SETCURSOR:
                self.u.SetCursor(None)                   # no arrow on a black screen
                return 1
            if msg == self.WM_MOUSEACTIVATE:
                return self.MA_NOACTIVATE                # a click never pulls focus off the app beneath
            if msg == self.WM_DISPLAYCHANGE:
                if not self.relayout:                    # every window gets one; one rebuild serves all
                    self.relayout = True
                    self.u.PostThreadMessageW(self.tid, self.WM_APP_LAYOUT, 0, 0)
                return 0
            if msg == self.WM_CLOSE:
                return 0                                 # only the mapper lifts the curtain
        except Exception:                                # noqa: BLE001 - never raise into Windows
            pass
        return self.u.DefWindowProcW(hwnd, msg, wp, lp)


def make_injector(enabled):
    if not enabled:
        return NullInjector()
    system = platform.system()
    if system == "Linux":
        try:
            return EvdevInjector()
        except ImportError:
            print("! python-evdev not installed (pip install evdev); running dashboard only")
        except PermissionError:
            print("! no access to /dev/uinput - run with sudo (see README); running dashboard only")
        except Exception as ex:      # noqa: BLE001
            print(f"! uinput failed ({ex}); running dashboard only")
    elif system == "Windows":
        try:
            return SendInputInjector()
        except Exception as ex:      # noqa: BLE001
            print(f"! SendInput unavailable ({ex}); running dashboard only")
    else:
        print(f"! no injector for {system}; running dashboard only")
    return NullInjector()


def grab_kernel_touchpad():
    """Linux: the kernel already turns the DS4 pad into a system touchpad. Take it
    over so the cursor isn't driven twice. Returns the grabbed devices."""
    if platform.system() != "Linux":
        return []
    try:
        import evdev
    except ImportError:
        return []
    grabbed = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            if d.info.vendor == VID and "touchpad" in d.name.lower():
                d.grab()
                grabbed.append(d)
        except Exception:            # noqa: BLE001
            pass
    return grabbed


# ------------------------------------------------------------------ the mapper

def curve(v, deadzone=12, expo=2.0):
    """Stick value 0..255 -> -1..1, symmetric, with a deadzone and an expo response
    (1 = linear, 2 = squared)."""
    x = (v - 128) / (127.0 if v >= 128 else 128.0)
    dz = deadzone / 127.0
    if abs(x) < dz:
        return 0.0
    m = (abs(x) - dz) / (1 - dz)
    return math.copysign(m ** expo, x)


class Mapper:
    def __init__(self, inj, tune=None, pad_mouse=True, stick_mouse=True, clock=time.monotonic):
        self.inj = inj
        self.tune = TUNE if tune is None else tune
        self.pad_mouse = pad_mouse
        self.stick_mouse = stick_mouse
        self.clock = clock
        self.layer2 = False
        self.held = {}          # button -> [kind, name, t_pressed, t_last_repeat]
        self.prev_buttons = set()
        self.prev_pos = {}      # touch id -> (x, y) last frame
        self.fingers = 0        # fingers down last frame
        self.session = None     # while any finger is down: [t_start, max_fingers, max_move, cancelled]
        self.start_pos = {}     # touch id -> (x, y) where it landed
        self.flick = {"x": 0, "y": 0}   # left stick: -1/0/+1 = direction already fired
        self.rs_flick = {"x": 0, "y": 0}  # right stick, same, for the Fn pane-focus flicks
        self.rs_dir, self.rs_next = None, 0.0   # right stick as arrows: direction and next fire
        self.rs_armed = True            # False after a settle until the right stick has been back at rest
        self.fn_t, self.fn_used = 0.0, False    # Fn press time; whether anything used the layer
        self.suspended = False          # the "suspend" action: inject nothing at all
        self.dark = False               # the "screen_off" action: the screen is dark, the pad silent
        self.dark_at = None             # when the screen goes off - held keys are let go first
        self.dark_since = 0.0           # when the curtain went up
        self.dark_awake_at = 0.0        # when the keep-awake request is next renewed
        self.note = None                # main() points this at stderr: a line when the screen goes and comes
        self.last_input = 0.0           # last real input, for the light bar
        self.attention_mtime, self.attention = 0.0, "idle"    # 'waiting' = something wants you
        self.attention_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "attention_state.txt")
        self.acc = [0.0, 0.0]   # fractional cursor accumulator
        self.wheel = [0.0, 0.0]  # fractional wheel accumulator (v, h)

    def keymap(self):
        return KEYMAP_L2 if self.layer2 else KEYMAP

    def poll_attention(self):
        """One word, 'waiting' or 'idle', written by whatever you wait on (the docstring has the
        Claude Code hooks I use). Same mtime-guarded read as the tune file. A missing or unreadable
        file simply means idle. Called from the main loop rather than step(), so a filesystem stat
        stays out of the 250 Hz hot path."""
        try:
            mt = os.path.getmtime(self.attention_file)
            if mt != self.attention_mtime:
                self.attention_mtime = mt
                with open(self.attention_file, encoding="utf-8") as f:
                    self.attention = "waiting" if f.read().strip() == "waiting" else "idle"
        except (OSError, ValueError):          # unreadable, or not text: idle, never a crash
            self.attention = "idle"

    def _key(self, name, down):
        """A single key, or a chord like 'ctrl+shift+tab' (pressed in order, released in reverse),
        or a SEQUENCE of chords separated by spaces: 'ctrl+k ctrl+left' is ctrl+k, then ctrl+left.
        A sequence is fired whole on the press and is a no-op on the release - it cannot be held,
        which is why the auto-repeat below skips anything containing a space."""
        chords = name.split()
        if len(chords) > 1:
            if down:
                for c in chords:
                    self._key(c, True)
                    self._key(c, False)
            return
        parts = name.split("+")
        for p in (parts if down else reversed(parts)):
            self.inj.key(p, down)

    def _action(self, action):
        """One-shot actions. "suspend" and "screen_off" are not here: they are handled at the top
        of step(), because they have to keep working while everything else is switched off."""
        if action == "cursor_centre":
            self.inj.centre()

    def _settle(self, st, now):
        """Take the pad as it is right now as the new reference, as if this report were the
        first one: no cursor jump from motion made while the mapper was not looking, no tap from
        a finger that was already down, no flick or arrows from a stick that is already pushed,
        no Esc from an Fn press that began while the mapper was not listening. Used on the way
        into and out of the two quiet modes."""
        fingers = [(tid, x, y) for active, tid, x, y in st["touch"] if active]
        self.prev_pos = {tid: (x, y) for tid, x, y in fingers}
        self.start_pos = dict(self.prev_pos)
        self.fingers = min(len(fingers), 2)
        self.session = [now, len(fingers), 0.0, True] if fingers else None    # cancelled: no tap
        self.acc, self.wheel = [0.0, 0.0], [0.0, 0.0]
        self.rs_dir, self.rs_next = None, 0.0
        self.rs_armed = False               # the right stick fires again once it has been back at rest
        self.flick = {"x": 1, "y": 1}       # re-armed only once each stick is back inside flick_off
        self.rs_flick = {"x": 1, "y": 1}
        if FN_BUTTON is not None and FN_BUTTON in st["buttons"]:
            self.fn_used = True             # its release is not a tap, whatever the time

    def _can_toggle(self, action):
        """Whether a button in the map as it stands can still press `action`. A live reload can
        take it away, and a quiet mode left with no way back would never end."""
        return action in ACTIONS.values() or (FN_BUTTON is not None and action in ACTIONS_L2.values())

    def _tend_dark(self, st, now):
        """While the screen is dark, or about to be. The curtain goes up SCREEN_OFF_DELAY_S after
        the chord, once held keys are let go. From then on the curtain watches the keyboard and the
        mouse itself (_BlackCurtain says why not the idle clock), so what is left here is renewing
        the keep-awake request every DARK_REASSERT_S and noticing when the curtain came down by
        itself. Asking whether it is still up, on every report, is also its heartbeat."""
        if self.dark_at is not None:            # not up yet
            if now < self.dark_at:
                return
            self.dark_at = None
            if not self.inj.display_off():      # nothing can black this screen out: stay normal
                self.dark = False
                self._settle(st, now)
                return
            self.dark_since, self.dark_awake_at = now, now
            self._note("screen off")
        elif not self.inj.display_dark():       # lifted on its own: the user is back, or it lost us
            self._leave_dark(st, now, LIFTED_BY.get(self.inj.lifted_by(), "the curtain came down"))
            return
        if self.tune.get("screen_off_keep_awake", True) and now >= self.dark_awake_at:
            self.inj.keep_awake(True)           # and renewed every DARK_REASSERT_S
            self.dark_awake_at = now + DARK_REASSERT_S

    def _leave_dark(self, st, now, why):
        """Back to normal: the curtain down if it had gone up (if not, the switch-off is simply
        called off), the keep-awake request let go, and the pad's current state taken as the new
        reference."""
        was_up = self.dark_at is None
        self.dark, self.dark_at = False, None
        if was_up:
            self.inj.display_on()
            self._note(f"screen back after {now - self.dark_since:.0f} s ({why})")
        self.inj.keep_awake(False)
        self._settle(st, now)

    def _note(self, text):
        if self.note:
            self.note(text)

    def step(self, st):
        t = self.tune
        now = self.clock()
        b = st["buttons"]
        pressed = b - self.prev_buttons
        # --- buttons: edge detection, layer-safe release. Fn first, so a button that goes down
        # in the same report as it already sees layer 2.
        # v2: Fn is MOMENTARY - layer 2 lasts exactly as long as L3 is held, and engages on the
        # press with no delay so Fn + stick responds at once. A short L3 press with nothing else
        # touched during it is Esc instead. PS used to toggle this; PS no longer exists.
        if FN_BUTTON in pressed:
            self.layer2, self.fn_t, self.fn_used = True, now, False
        if FN_BUTTON in self.prev_buttons - b:
            self.layer2 = False
            if (FN_TAP and not self.fn_used and not self.suspended and not self.dark
                    and now - self.fn_t < t["hold_s"]):
                self._key(FN_TAP, True)
                self._key(FN_TAP, False)
        if self.layer2 and (pressed - {FN_BUTTON}):
            self.fn_used = True
        # The two mode actions - "screen_off" (Fn + pad click by default) and "suspend" - have to
        # keep working while everything else is switched off, which is why they run here, before
        # the early return and outside _action(). Going into either lets go of everything held
        # first; going into or out of either takes the pad's current state as the new reference.
        for name in sorted(pressed):
            act = (ACTIONS_L2 if self.layer2 else ACTIONS).get(name)
            if act == "suspend":
                self.suspended = not self.suspended
                self.fn_used = True
                self.release_all()
                self._settle(st, now)
                pressed = pressed - {name}
            elif act == "screen_off":
                self.fn_used = True
                pressed = pressed - {name}
                if self.dark:
                    self._leave_dark(st, now, "the chord")
                else:
                    self.release_all()
                    self.dark, self.dark_at = True, now + SCREEN_OFF_DELAY_S
                    self._settle(st, now)
        # a live reload can take the way back away: a quiet mode the map can no longer toggle ends
        if self.suspended and not self._can_toggle("suspend"):
            self.suspended = False
            self._settle(st, now)
        if self.dark and not self._can_toggle("screen_off"):
            self._leave_dark(st, now, "the map no longer has a way back")
        if self.dark:
            self._tend_dark(st, now)
        if self.suspended or self.dark:
            self.prev_buttons = set(b)
            return
        # --- activity, for the light bar. Buttons, touch, or deflection PAST the deadzone only:
        # the sticks jitter a unit or two at rest, and L2/R2 read pressed for good with the
        # triggers gone (R2 wandering besides), so neither raw value can be allowed to count as use.
        if ((b - {"L2", "R2"}) or any(a for a, *_ in st["touch"])
                or curve(st["lx"], t["stick_deadzone"], 1.0) or curve(st["ly"], t["stick_deadzone"], 1.0)
                or curve(st["rx"], t["stick_deadzone"], 1.0) or curve(st["ry"], t["stick_deadzone"], 1.0)):
            self.last_input = now
        # Each layer has its own three tables (action / mouse / key); a button that is in none of
        # them for the current layer does nothing. sorted() so two buttons landing in the same
        # report are handled in the same order every run.
        actions, mice, keys = ((ACTIONS_L2, MOUSEMAP_L2, KEYMAP_L2) if self.layer2
                               else (ACTIONS, MOUSEMAP, KEYMAP))
        for name in sorted(pressed):
            if not self.layer2 and (name in TAP_KEY or name in HOLD_MOD):
                # tap or hold is not knowable yet: record it and decide on release or at hold_s
                self.held[name] = ["tap", TAP_KEY.get(name), now, now]
            elif name in actions:
                self._action(actions[name])
            elif name in mice:
                self.held[name] = ["mouse", mice[name], now, now]
                self.inj.click(mice[name], True)
            elif name in keys:
                k = keys[name]
                self.held[name] = ["key", k, now, now]
                self._key(k, True)
        # a held tap/hold button that has outlasted hold_s becomes its modifier, and from then on
        # it is an ordinary held key, so the release path below lets it go as usual
        for name, entry in list(self.held.items()):
            if entry[0] == "tap" and name in HOLD_MOD and now - entry[2] >= t["hold_s"]:
                entry[0], entry[1] = "key", HOLD_MOD[name]
                self._key(HOLD_MOD[name], True)
        for name in self.prev_buttons - b:
            kind, k = self.held.pop(name, (None, None, 0, 0))[:2]
            if kind == "mouse":
                self.inj.click(k, False)
            elif kind == "key":
                self._key(k, False)
            elif kind == "tap" and k:           # released before hold_s: it was a tap
                self._key(k, True)
                self._key(k, False)
        self.prev_buttons = set(b)

        # --- auto-repeat for held single keys, like a real keyboard (modifiers and chords excepted)
        if t["key_repeat"]:
            for entry in self.held.values():
                kind, k, t0, t1 = entry
                if (kind == "key" and k not in MODIFIERS and "+" not in k and " " not in k
                        and now - t0 >= self.inj.repeat_delay and now - t1 >= self.inj.repeat_period):
                    self.inj.key(k, True)
                    entry[3] = now

        # --- touchpad: one finger = cursor, two fingers = scroll. Motion is taken per
        # contact id, so it doesn't matter which slot a finger sits in, and the first frame
        # after the finger count changes is a reference frame (no jump).
        fingers = [(tid, x, y) for active, tid, x, y in st["touch"] if active]
        # A touch session runs from the first finger down to the last finger up. A short,
        # still session is a tap: 1 finger = left click, 2 fingers = right click. The
        # mechanical click during the session cancels the tap.
        if fingers and self.session is None:
            self.session = [now, 0, 0.0, False]
        if self.session is not None:
            self.session[1] = max(self.session[1], len(fingers))
            for tid, x, y in fingers:
                sx, sy = self.start_pos.setdefault(tid, (x, y))
                self.session[2] = max(self.session[2], abs(x - sx), abs(y - sy))
            if "Pad" in b:
                self.session[3] = True
            if not fingers:
                t0, max_fingers, moved, cancelled = self.session
                self.session, self.start_pos = None, {}
                if not cancelled and now - t0 <= t["tap_max_s"] and moved <= t["tap_max_move"]:
                    # v2: two fingers used to tap a right click, but the pad's mechanical
                    # click is right click now - three ways to right-click was one too many
                    btn = {1: TOUCHPAD["one_finger_tap"], 2: TOUCHPAD["two_finger_tap"]}.get(max_fingers)
                    if btn:
                        self.inj.click(btn, True)
                        self.inj.click(btn, False)
        deltas = []
        for tid, x, y in fingers:
            p = self.prev_pos.get(tid)
            if p is not None:
                deltas.append((x - p[0], y - p[1]))
        n = min(len(fingers), 2)
        if (n == 1 and self.fingers == 1 and self.pad_mouse and deltas
                and TOUCHPAD["one_finger"] == "cursor"):
            dx, dy = deltas[0]
            g = t["touch_gain"] * (1.0 + t["touch_accel"] * math.hypot(dx, dy))
            self.acc[0] += dx * g
            self.acc[1] += dy * g
        elif n == 2 and self.fingers == 2 and len(deltas) == 2 and TOUCHPAD["two_finger"] == "scroll":
            dx = (deltas[0][0] + deltas[1][0]) / 2.0
            dy = (deltas[0][1] + deltas[1][1]) / 2.0
            s = 1.0 if t["natural_scroll"] else -1.0
            self.wheel[0] += s * dy * t["touch_scroll_gain"]
            self.wheel[1] += -s * dx * t["touch_scroll_gain"]
        self.fingers = n
        self.prev_pos = {tid: (x, y) for tid, x, y in fingers}

        # --- right stick. v2: arrow keys, repeating faster the further it is pushed, so it
        # drives focus and the caret. Under Fn it is VS Code's pane focus instead, once per push.
        # rstick_mode = "cursor" restores the old coarse pointer; nothing was deleted.
        if rstick_mode == "keys":
            rx = curve(st["rx"], t["stick_deadzone"], t["stick_expo"])
            ry = curve(st["ry"], t["stick_deadzone"], t["stick_expo"])
            mag = max(abs(rx), abs(ry))
            if mag <= 0:
                self.rs_armed = True            # back at rest, so a settle no longer holds the arrows
            if self.layer2:
                self.rs_dir, self.rs_next = None, 0.0
                for axis, v, other, neg, pos in (("x", rx, ry, "W", "E"), ("y", ry, rx, "N", "S")):
                    if self.rs_flick[axis] == 0:
                        if abs(v) >= t["flick_on"] and abs(v) >= abs(other):
                            self.rs_flick[axis] = 1 if v > 0 else -1
                            seq = RSTICK_L2.get(pos if v > 0 else neg)
                            if seq:
                                self.fn_used = True
                                self._key(seq, True)
                    elif abs(v) <= t["flick_off"]:
                        self.rs_flick[axis] = 0
            elif mag <= 0:
                self.rs_dir, self.rs_next = None, 0.0
            elif self.rs_armed:                 # not while still pushed from before a settle
                # dominant axis, so a diagonal push resolves to one arrow and not two
                d = ("E" if rx > 0 else "W") if abs(rx) >= abs(ry) else ("S" if ry > 0 else "N")
                if d != self.rs_dir or now >= self.rs_next:
                    k = RSTICK_KEYS.get(d)
                    if k:
                        self._key(k, True)
                        self._key(k, False)
                    rate = t["rstick_rate_min"] + (t["rstick_rate_max"] - t["rstick_rate_min"]) * mag
                    self.rs_dir, self.rs_next = d, now + 1.0 / rate
        elif self.stick_mouse:
            dz, ex = t["stick_deadzone"], t["stick_expo"]
            cx, cy = curve(st["rx"], dz, ex), curve(st["ry"], dz, ex)
            if not (cx or cy):
                self.rs_armed = True
            elif self.rs_armed:                 # the same hold-off after a settle as the arrows
                self.acc[0] += cx * t["stick_max_px"]
                self.acc[1] += cy * t["stick_max_px"]
        dx, dy = int(self.acc[0]), int(self.acc[1])
        if dx or dy:
            self.inj.move(dx, dy)
            self.acc[0] -= dx
            self.acc[1] -= dy

        v, h = int(self.wheel[0]), int(self.wheel[1])
        if v or h:
            self.inj.scroll(v, h)
            self.wheel[0] -= v
            self.wheel[1] -= h

        # --- left stick -> flicks: one chord per push past flick_on on the dominant axis,
        # re-armed once the stick comes back inside flick_off
        x = curve(st["lx"], t["stick_deadzone"], 1.0)
        y = curve(st["ly"], t["stick_deadzone"], 1.0)
        for axis, v, other, neg, pos in (("x", x, y, "W", "E"), ("y", y, x, "N", "S")):
            if self.flick[axis] == 0:
                if abs(v) >= t["flick_on"] and abs(v) >= abs(other):
                    self.flick[axis] = 1 if v > 0 else -1
                    way = pos if v > 0 else neg
                    if self.layer2:                     # Fn: by default N = Task View, S = centre
                        self.fn_used = True
                        if way in LSTICK_ACTIONS_L2:
                            self._action(LSTICK_ACTIONS_L2[way])
                        if way in LSTICK_MOUSE_L2:      # a flick is an edge: a mouse binding clicks once
                            self.inj.click(LSTICK_MOUSE_L2[way], True)
                            self.inj.click(LSTICK_MOUSE_L2[way], False)
                        chord = LSTICK_FLICK_L2.get(way)
                    else:
                        chord = LSTICK_FLICK.get(way)
                    if chord:
                        self._key(chord, True)
                        self._key(chord, False)
            elif abs(v) <= t["flick_off"]:
                self.flick[axis] = 0

    def release_all(self):
        for name, (kind, k, _, _) in list(self.held.items()):
            if kind == "tap":
                continue                        # an unpromoted tap has pressed nothing yet
            (self.inj.click if kind == "mouse" else self._key)(k, False)
        self.held.clear()


def led_for(st, layer2, active=False, attention=False, suspended=False, grace=False, dark=False):
    """v2: the light is not on all the time. Highest priority wins; idle is off. Every state is
    a STEADY colour - I ruled out flashing on 2026-10-21, so the report's flash bytes are
    left at their default of zero.

    `attention` is the attention file saying "waiting". `grace` is the first couple of seconds
    after the pad is opened, where the battery colour still shows - on USB the battery reads 100%
    forever, so it says nothing after that."""
    if suspended:
        return LED_COLOURS["suspended"]
    if dark:                    # the screen is off, and so is the light - unless something wants you
        return LED_COLOURS["attention"] if attention else LED_COLOURS["off"]
    if attention:
        return LED_COLOURS["attention"]
    if layer2:
        return LED_COLOURS["layer2"]
    if grace:
        b = st["battery"]
        return (LED_COLOURS["good"] if b >= 60 else
                LED_COLOURS["mid"] if b >= 30 else LED_COLOURS["low"])
    if active:
        return LED_COLOURS["active"]
    return LED_COLOURS["off"]


# one fixed slot per button, laid out left side / centre / right side of the pad:
# d-pad ^v<>, L1 L2 L3, Share, PS, touchpad click, Options, R1 R2 R3, Square Cross Circle Triangle
BTN_SLOTS = [("dpad_N", "^"), ("dpad_S", "v"), ("dpad_W", "<"), ("dpad_E", ">"),
             ("L1", "1"), ("L2", "2"), ("L3", "3"), ("Share", "s"), ("PS", "P"), ("Pad", "T"),
             ("Options", "o"), ("R1", "1"), ("R2", "2"), ("R3", "3"),
             ("Square", "#"), ("Cross", "X"), ("Circle", "O"), ("Triangle", "A")]
DASHBOARD_WIDTH = 119        # stays on one row of a default 120-column Windows console


def dashboard_line(st, hz, buttons=None):
    """buttons: everything pressed since the last print, so short taps still show."""
    buttons = st["buttons"] if buttons is None else buttons
    t = []
    for active, tid, x, y in st["touch"]:
        t.append(f"{x:4d},{y:3d}" if active else "   -,-  ")
    slots = "".join(ch if name in buttons else "." for name, ch in BTN_SLOTS)
    g = ",".join(f"{int(v / 100):4d}" for v in st["gyro"])     # raw / 100
    a = ",".join(f"{int(v / 100):4d}" for v in st["accel"])
    line = (f"{hz:3.0f}Hz {st['battery']:3d}%{'U' if st['usb'] else 'B'}{'H' if st['headphones'] else ' '} "
            f"LS{st['lx']:3d},{st['ly']:3d} RS{st['rx']:3d},{st['ry']:3d} "
            f"L2 {st['l2']:3d} R2 {st['r2']:3d} [{slots}] T{t[0]} {t[1]} G{g} A{a}")
    return line[:DASHBOARD_WIDTH].ljust(DASHBOARD_WIDTH)


# ------------------------------------------------------------------ config files
#
# mapping.json and tune.json both come in through read_json(): UTF-8 (a BOM is fine - PowerShell
# writes one), a key that appears twice in one object is an error, and whatever is wrong is a
# ValueError that says what, so a caller prints one line and carries on. Neither file can take a
# running mapper down: a bad map is refused whole (the previous one stays), a bad tune value is
# refused on its own (the setting keeps its value).

def _json_object(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"the key {k!r} appears twice in one object")
        d[k] = v
    return d


def read_json(path):
    """A JSON file as Python objects. OSError if it cannot be read; ValueError if it is not UTF-8
    text, not JSON, or lists the same key twice in one object."""
    with open(path, encoding="utf-8-sig") as f:
        try:
            text = f.read()
        except UnicodeDecodeError as ex:
            raise ValueError(f"not UTF-8 text ({ex.reason} at byte {ex.start}). PowerShell 5's > "
                             "redirection writes UTF-16: use --dump-map FILE, or save as UTF-8") from None
    try:
        return json.loads(text, object_pairs_hook=_json_object)
    except json.JSONDecodeError as ex:
        raise ValueError(f"not valid JSON: {ex}") from None
    except RecursionError:              # brackets nested thousands deep: the parser gives up
        raise ValueError("not valid JSON: nested too deeply") from None


def _show(v):
    """repr(v) for a message, cut to one short piece: a 400-digit number stays on one line."""
    s = repr(v)
    return s if len(s) <= 40 else s[:37] + "..."


def _tune_value(key, v):
    """One tune.json value for TUNE[key], checked against the built-in setting it replaces: a
    true/false setting takes true or false, a number takes a finite number inside TUNE_RANGE[key]
    (a whole one where the default is whole). Raises ValueError saying what was expected. The
    range is what keeps Mapper.step() clear of ZeroDivisionError and OverflowError."""
    current = TUNE[key]
    if isinstance(current, bool):
        if not isinstance(v, bool):
            raise ValueError(f"expected true or false, not {_show(v)}")
        return v
    if (isinstance(v, bool) or not isinstance(v, (int, float))
            or (isinstance(v, float) and not math.isfinite(v))):
        raise ValueError(f"expected a number, not {_show(v)}")
    lo, hi = TUNE_RANGE[key]
    if not lo <= v <= hi:          # an int compares exactly however long; float() of it could overflow
        raise ValueError(f"{_show(v)} is outside {lo}..{hi}")
    if isinstance(current, int):
        if v != int(v):
            raise ValueError(f"expected a whole number, not {_show(v)}")
        return int(v)
    return float(v)


def load_tune(path, log=print):
    """Merge a JSON file into TUNE. Nothing in it can stop the mapper: an unknown key, or a value of
    the wrong kind or outside its range, is reported through `log` and skipped - that setting keeps
    its value - and a file that is not JSON changes nothing. Returns the file's mtime (also when
    the contents were refused, so the caller waits for the next edit), or None if the file could
    not be read."""
    mtime = None
    try:
        mtime = os.stat(path).st_mtime
        data = read_json(path)
    except OSError as ex:
        log(f"\n! tune file {path}: {ex}")
        return None
    except ValueError as ex:
        log(f"\n! tune file {path}: {ex} - keeping the current settings")
        return mtime
    if not isinstance(data, dict):
        log(f"\n! tune file {path}: expected an object of settings, not {type(data).__name__} - "
            "keeping the current settings")
        return mtime
    prev_on, prev_off = TUNE["flick_on"], TUNE["flick_off"]
    for k, v in data.items():
        if k not in TUNE:
            log(f"\n! tune file: unknown key {_show(k)} ignored")
            continue
        try:
            TUNE[k] = _tune_value(k, v)
        except ValueError as ex:
            log(f"\n! tune file: {k}: {ex}, keeping {TUNE[k]!r}")
    # the one rule between two keys, judged once the whole file is in so both can move in one edit
    if TUNE["flick_off"] >= TUNE["flick_on"]:
        log(f"\n! tune file: flick_off {TUNE['flick_off']} is not below flick_on {TUNE['flick_on']} (a flick "
            f"would re-arm at once and repeat every report), keeping {prev_on} and {prev_off}")
        TUNE["flick_on"], TUNE["flick_off"] = prev_on, prev_off
    return mtime


def tune_summary():
    return "  ".join(f"{k}={v}" for k, v in TUNE.items())


# ------------------------------------------------------------------ control map file
#
# mapping.json (schema 1) is the tables above written out, so the shipped file and the built-in
# defaults are one and the same. load_mapping() validates a file and returns it normalised (every
# input listed, every slot present, null where unbound); apply_mapping() pours such a dict into
# the tables; current_mapping() reads them back out; default_mapping() is the built-in map;
# format_mapping() lays a map out one input per line. The editor in tools/ uses nothing but these,
# so the rules exist exactly once. Everything raises ValueError with the path of the bad entry.

MAP_SCHEMA = 1
MAP_NAME = "Five buttons (v2)"
MAP_NOTES = "Default map for the bare-board dock (five buttons). Hold L3 for the Fn layer. See docs/CONTROLS.md."
BUTTONS = ("Pad", "L3", "R3", "Share", "Options", "Cross", "Circle", "Triangle", "Square",
           "dpad_N", "dpad_S", "dpad_W", "dpad_E", "L1", "R1", "L2", "R2", "PS")
RESERVED_BUTTONS = {        # refused by the loader; the text is the reason the editor shows
    "L2": "L2 reads as fully pressed all the time once its trigger is removed, so it cannot be bound",
    "R2": "R2 reads as pressed all the time once its trigger is removed, and its analogue value wanders, "
          "so it cannot be bound",
}
DIRECTIONS = ("N", "S", "W", "E")
MOUSE_BUTTONS = ("left", "right", "middle")
ACTION_NAMES = {            # action -> what it does
    "screen_off": "black out every screen while everything keeps running (Windows only; elsewhere the pad "
                  "just goes quiet for 0.4 s); any key or mouse input brings it back, and so does the same "
                  "press again. The pad is silent while it is dark",
    "suspend": "switch all injection off; the same press switches it back on. "
               "A button's press or fn slot only, so there is always a way back",
    "cursor_centre": "put the cursor in the middle of the primary screen",
}
SLOT_KINDS = {              # the binding kinds each slot accepts; null is always allowed
    "press": ("key", "mouse", "action"), "fn": ("key", "mouse", "action"),
    "tap": ("key",), "hold": ("key",),
    "fn_tap": ("key",),                     # fn.tap: the Fn button's own short press
    "left_stick_fn": ("key", "mouse", "action"),   # a flick is an edge, so a mouse binding clicks once
    # right_stick.keys / .fn and left_stick.flick are key specs, not bindings
    "touchpad_tap": ("mouse",),
}
_SECTIONS = ("schema", "name", "notes", "fn", "buttons", "right_stick", "left_stick", "touchpad")


_F_KEYS = frozenset(f"f{i}" for i in range(1, 13))     # these spellings only: 'f01' is not a key


def _key_name_ok(k):
    return k in KEY_NAMES or k in _F_KEYS or (len(k) == 1 and k in "abcdefghijklmnopqrstuvwxyz0123456789")


def validate_key_spec(spec, where="key"):
    """A key spec is a key name, a chord joined with '+' (ctrl+shift+tab), or chords in sequence
    separated by spaces (ctrl+k ctrl+left). Returns it tidied (lower case, single spaces);
    raises ValueError naming the offending part."""
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError(f"{where}: a key spec must be a non-empty string, not {spec!r}")
    chords = spec.lower().split()
    for chord in chords:
        for k in chord.split("+"):
            if not k:
                raise ValueError(f"{where}: {chord!r} has an empty key around a '+'")
            if not _key_name_ok(k):
                raise ValueError(f"{where}: unknown key {k!r} (valid: {', '.join(KEY_NAMES)}, "
                                 "a-z, 0-9, f1-f12)")
    return " ".join(chords)


def _check_keys(d, where, allowed):
    if not isinstance(d, dict):
        raise ValueError(f"{where}: expected an object with {', '.join(allowed)}, not {d!r}")
    for k in d:
        if k not in allowed:
            raise ValueError(f"{where}: unknown key {k!r} (expected one of {', '.join(allowed)})")


def _binding(b, where, kinds, actions=tuple(ACTION_NAMES)):
    """One binding, normalised: None, {"key": spec}, {"mouse": button} or {"action": name}."""
    if b is None:
        return None
    if not isinstance(b, dict) or len(b) != 1:
        raise ValueError(f'{where}: a binding is null, {{"key": ...}}, {{"mouse": ...}} or '
                         f'{{"action": ...}}, not {b!r}')
    (kind, value), = b.items()
    if kind not in ("key", "mouse", "action"):
        raise ValueError(f"{where}: unknown binding kind {kind!r} (key, mouse or action)")
    if kind not in kinds:
        raise ValueError(f"{where}: a {kind} binding cannot go here; this slot takes {' or '.join(kinds)}")
    if kind == "key":
        return {"key": validate_key_spec(value, where + ".key")}
    if not isinstance(value, str):          # before any lookup: a list or an object cannot be a dict key
        raise ValueError(f"{where}.{kind}: expected a name in quotes, not {value!r}")
    if kind == "mouse":
        if value not in MOUSE_BUTTONS:
            raise ValueError(f"{where}.mouse: unknown mouse button {value!r} ({', '.join(MOUSE_BUTTONS)})")
        return {"mouse": value}
    if value not in ACTION_NAMES:
        raise ValueError(f"{where}.action: unknown action {value!r} (valid: {', '.join(ACTION_NAMES)})")
    if value not in actions:
        raise ValueError(f"{where}.action: {value} can only be bound to a button's press or fn slot "
                         "(the same press has to be able to undo it)")
    return {"action": value}


def _directions(d, where, binding=False):
    d = {} if d is None else d
    _check_keys(d, where, DIRECTIONS)
    out = {}
    for way in DIRECTIONS:
        v = d.get(way)
        if binding:
            out[way] = _binding(v, f"{where}.{way}", SLOT_KINDS["left_stick_fn"], actions=("cursor_centre",))
        else:
            out[way] = None if v is None else validate_key_spec(v, f"{where}.{way}")
    return out


def normalise_mapping(data):
    """Validate a control map (a dict in the mapping.json schema) and return it normalised: every
    button and direction listed, every slot present, None where unbound, key specs tidied. A
    missing input is unbound. Raises ValueError with the path to the offending entry. Idempotent:
    a normalised map comes back unchanged, which is what makes the round-trip test meaningful."""
    _check_keys(data, "mapping", _SECTIONS)
    schema = data.get("schema", MAP_SCHEMA)
    if type(schema) is not int or schema != MAP_SCHEMA:     # exactly the integer 1: not 1.0, not true
        raise ValueError(f"mapping.schema: {schema!r} is not understood (this mapper reads schema {MAP_SCHEMA})")
    out = {"schema": MAP_SCHEMA}
    for k in ("name", "notes"):
        v = data.get(k, "")
        if not isinstance(v, str):
            raise ValueError(f"mapping.{k}: expected text, not {v!r}")
        out[k] = v

    fn, fn_button = data.get("fn"), None
    if fn is not None:
        _check_keys(fn, "fn", ("button", "tap"))
        fn_button = fn.get("button")
        if fn_button is None:
            raise ValueError("fn.button: name the button that is the Fn layer, or set fn to null for no layer")
        if fn_button not in BUTTONS:
            raise ValueError(f"fn.button: unknown input {fn_button!r} (one of {', '.join(BUTTONS)})")
        if fn_button in RESERVED_BUTTONS:
            raise ValueError(f"fn.button: {RESERVED_BUTTONS[fn_button]}")
        out["fn"] = {"button": fn_button, "tap": _binding(fn.get("tap"), "fn.tap", SLOT_KINDS["fn_tap"])}
    else:
        out["fn"] = None

    buttons = data.get("buttons")
    buttons = {} if buttons is None else buttons
    _check_keys(buttons, "buttons", BUTTONS)
    out["buttons"] = {}
    for name in BUTTONS:
        slots, where = buttons.get(name), f"buttons.{name}"
        if slots is None:
            out["buttons"][name] = None
            continue
        _check_keys(slots, where, ("press", "tap", "hold", "fn"))
        norm = {s: _binding(slots.get(s), f"{where}.{s}", SLOT_KINDS[s]) for s in ("press", "tap", "hold", "fn")}
        if not any(norm.values()):
            out["buttons"][name] = None
            continue
        if name in RESERVED_BUTTONS:
            raise ValueError(f"{where}: {RESERVED_BUTTONS[name]}")
        if name == fn_button:
            raise ValueError(f"{where}: {name} is the Fn button (fn.button); it cannot have bindings of its own")
        if norm["press"] and (norm["tap"] or norm["hold"]):
            raise ValueError(f"{where}: a button has either press or tap + hold, not both")
        if norm["tap"] and not norm["hold"]:
            raise ValueError(f"{where}: tap needs a hold as well (a short press is the tap, a long one the hold)")
        out["buttons"][name] = norm

    rs = data.get("right_stick")
    rs = {} if rs is None else rs
    _check_keys(rs, "right_stick", ("mode", "keys", "fn"))
    mode = rs.get("mode", "keys")
    if mode not in ("keys", "cursor"):
        raise ValueError(f"right_stick.mode: {mode!r} is not 'keys' or 'cursor'")
    out["right_stick"] = {"mode": mode, "keys": _directions(rs.get("keys"), "right_stick.keys"),
                          "fn": _directions(rs.get("fn"), "right_stick.fn")}

    ls = data.get("left_stick")
    ls = {} if ls is None else ls
    _check_keys(ls, "left_stick", ("flick", "fn"))
    out["left_stick"] = {"flick": _directions(ls.get("flick"), "left_stick.flick"),
                         "fn": _directions(ls.get("fn"), "left_stick.fn", binding=True)}

    tp = data.get("touchpad")
    tp = {} if tp is None else tp
    _check_keys(tp, "touchpad", ("one_finger", "one_finger_tap", "two_finger", "two_finger_tap"))
    for k, want in (("one_finger", "cursor"), ("two_finger", "scroll")):
        if tp.get(k) not in (want, None):
            raise ValueError(f"touchpad.{k}: {tp.get(k)!r} is not {want!r} or null")
    out["touchpad"] = {
        "one_finger": tp.get("one_finger"),
        "one_finger_tap": _binding(tp.get("one_finger_tap"), "touchpad.one_finger_tap", SLOT_KINDS["touchpad_tap"]),
        "two_finger": tp.get("two_finger"),
        "two_finger_tap": _binding(tp.get("two_finger_tap"), "touchpad.two_finger_tap", SLOT_KINDS["touchpad_tap"]),
    }
    return out


def mapping_warnings(m):
    """Notes about a VALID map that still cannot do what it says, one line each, for the console.
    The loader does not refuse these - every one is harmless - but a reader should hear about them:
    fn bindings with no Fn button, stick keys in cursor mode. `m` is a normalised map."""
    notes = []
    if m["fn"] is None:
        n = (sum(1 for slots in m["buttons"].values() if slots and slots["fn"])
             + sum(1 for v in m["right_stick"]["fn"].values() if v)
             + sum(1 for v in m["left_stick"]["fn"].values() if v))
        if n:
            notes.append(f"fn is null, so the {n} fn binding{'s' if n != 1 else ''} can never fire")
    rs = m["right_stick"]
    if rs["mode"] == "cursor" and (any(rs["keys"].values()) or any(rs["fn"].values())):
        notes.append("right_stick.mode is cursor, so right_stick.keys and right_stick.fn are ignored")
    return notes


def load_mapping(path):
    """Read and validate a mapping.json. Returns the normalised dict (see normalise_mapping).
    OSError if the file cannot be read, ValueError - naming the entry - if it is not a valid map."""
    data = read_json(path)
    try:
        return normalise_mapping(data)
    except RecursionError:      # a value nested as deep as the parser allows: its repr in a message
        raise ValueError("nested too deeply to be a control map") from None    # could overflow too


def current_mapping():
    """The tables as they stand right now, in the mapping.json schema (normalised form)."""
    def binding_for(name, layer2):
        actions, mice, keys = ((ACTIONS_L2, MOUSEMAP_L2, KEYMAP_L2) if layer2
                               else (ACTIONS, MOUSEMAP, KEYMAP))
        if name in actions:
            return {"action": actions[name]}
        if name in mice:
            return {"mouse": mice[name]}
        if name in keys:
            return {"key": keys[name]}
        return None

    buttons = {}
    for name in BUTTONS:
        tap_hold = name in TAP_KEY or name in HOLD_MOD        # the mapper checks these first
        slots = {"press": None if tap_hold else binding_for(name, False),
                 "tap": {"key": TAP_KEY[name]} if name in TAP_KEY else None,
                 "hold": {"key": HOLD_MOD[name]} if name in HOLD_MOD else None,
                 "fn": binding_for(name, True)}
        buttons[name] = slots if any(slots.values()) else None
    fn = None if FN_BUTTON is None else {"button": FN_BUTTON, "tap": {"key": FN_TAP} if FN_TAP else None}
    ls_fn = {w: ({"action": LSTICK_ACTIONS_L2[w]} if w in LSTICK_ACTIONS_L2 else
                 {"mouse": LSTICK_MOUSE_L2[w]} if w in LSTICK_MOUSE_L2 else
                 {"key": LSTICK_FLICK_L2[w]} if w in LSTICK_FLICK_L2 else None) for w in DIRECTIONS}
    tp = TOUCHPAD
    return {
        "schema": MAP_SCHEMA, "name": MAP_NAME, "notes": MAP_NOTES, "fn": fn, "buttons": buttons,
        "right_stick": {"mode": rstick_mode, "keys": {w: RSTICK_KEYS.get(w) for w in DIRECTIONS},
                        "fn": {w: RSTICK_L2.get(w) for w in DIRECTIONS}},
        "left_stick": {"flick": {w: LSTICK_FLICK.get(w) for w in DIRECTIONS}, "fn": ls_fn},
        "touchpad": {"one_finger": tp["one_finger"],
                     "one_finger_tap": {"mouse": tp["one_finger_tap"]} if tp["one_finger_tap"] else None,
                     "two_finger": tp["two_finger"],
                     "two_finger_tap": {"mouse": tp["two_finger_tap"]} if tp["two_finger_tap"] else None},
    }


def apply_mapping(mapping):
    """Pour a control map into the tables the mapper reads. The map is normalised first, so a raw
    dict straight from json.load works; a bad map raises ValueError and changes nothing. Returns
    the normalised map. Read the tables through the module (ds4_dock.FN_BUTTON), not from-imports:
    the strings are rebound, the dicts refilled in place."""
    global FN_BUTTON, FN_TAP, rstick_mode, MAP_NAME, MAP_NOTES
    m = normalise_mapping(mapping)
    for table in (KEYMAP, KEYMAP_L2, MOUSEMAP, MOUSEMAP_L2, ACTIONS, ACTIONS_L2, TAP_KEY, HOLD_MOD,
                  RSTICK_KEYS, RSTICK_L2, LSTICK_FLICK, LSTICK_FLICK_L2, LSTICK_ACTIONS_L2, LSTICK_MOUSE_L2):
        table.clear()
    MAP_NAME, MAP_NOTES = m["name"], m["notes"]
    fn = m["fn"]
    FN_BUTTON = fn["button"] if fn else None
    FN_TAP = fn["tap"]["key"] if fn and fn["tap"] else None
    by_kind = {"key": (KEYMAP, KEYMAP_L2), "mouse": (MOUSEMAP, MOUSEMAP_L2), "action": (ACTIONS, ACTIONS_L2)}
    for name, slots in m["buttons"].items():
        if not slots:
            continue
        for slot, layer in (("press", 0), ("fn", 1)):
            if slots[slot]:
                (kind, value), = slots[slot].items()
                by_kind[kind][layer][name] = value
        if slots["tap"]:
            TAP_KEY[name] = slots["tap"]["key"]
        if slots["hold"]:
            HOLD_MOD[name] = slots["hold"]["key"]
    rs, ls, tp = m["right_stick"], m["left_stick"], m["touchpad"]
    rstick_mode = rs["mode"]
    RSTICK_KEYS.update({w: k for w, k in rs["keys"].items() if k})
    RSTICK_L2.update({w: k for w, k in rs["fn"].items() if k})
    LSTICK_FLICK.update({w: k for w, k in ls["flick"].items() if k})
    ls_tables = {"key": LSTICK_FLICK_L2, "mouse": LSTICK_MOUSE_L2, "action": LSTICK_ACTIONS_L2}
    for w, b in ls["fn"].items():
        if b:
            (kind, value), = b.items()
            ls_tables[kind][w] = value
    TOUCHPAD.update({"one_finger": tp["one_finger"], "two_finger": tp["two_finger"],
                     "one_finger_tap": tp["one_finger_tap"]["mouse"] if tp["one_finger_tap"] else None,
                     "two_finger_tap": tp["two_finger_tap"]["mouse"] if tp["two_finger_tap"] else None})
    return m


def format_mapping(m):
    """A control map as JSON text laid out one input per line, so the file reads like the table
    in the docstring. Plain json.loads reads it back; the layout is only for people."""
    def j(v):
        return json.dumps(v, separators=(", ", ": "))

    def block(title, items, indent="  "):
        lines = [f'{indent}"{title}": {{']
        width = max(len(j(k)) for k in items) + 1
        for i, (k, v) in enumerate(items.items()):
            comma = "," if i < len(items) - 1 else ""
            lines.append(f"{indent}  {(j(k) + ':').ljust(width)} {j(v)}{comma}")
        lines.append(indent + "}")
        return lines

    out = ["{"]
    for k in ("schema", "name", "notes", "fn"):
        out.append(f"  {j(k)}: {j(m[k])},")
    out += [line for line in block("buttons", m["buttons"])]
    out[-1] += ","
    for section in ("right_stick", "left_stick", "touchpad"):
        out += block(section, m[section])
        if section != "touchpad":
            out[-1] += ","
    out.append("}")
    return "\n".join(out) + "\n"


_DEFAULT_MAPPING_JSON = json.dumps(current_mapping())     # captured at import, before any apply


def default_mapping():
    """The built-in control map - the tables as shipped - whatever has been applied since."""
    return json.loads(_DEFAULT_MAPPING_JSON)


def resolve_mapping(arg, here):
    """Which map to run. --map FILE loads FILE; --map - is the built-in map; with no flag, a
    mapping.json next to the script is loaded if there is one. Returns (path or None, map)."""
    if arg == "-":
        return None, default_mapping()
    path = arg or os.path.join(here, "mapping.json")
    if arg is None and not os.path.exists(path):
        return None, default_mapping()
    return path, load_mapping(path)


# ------------------------------------------------------------------ device I/O

def open_device():
    try:
        import hid
    except ImportError:
        sys.exit("hidapi not installed:  pip install hidapi")
    if not hasattr(hid, "device"):
        sys.exit("wrong 'hid' package - uninstall it and:  pip install hidapi")
    last = None
    for pid, label in PIDS.items():
        for info in hid.enumerate(VID, pid):
            try:
                d = hid.device()
                d.open_path(info["path"])
                d.set_nonblocking(0)
                print(f"opened {label} ({info.get('product_string') or '?'})")
                return d
            except OSError as ex:
                last = ex
    if last is not None:
        sys.exit(f"found a DualShock 4 but could not open it ({last}).\n"
                 "Linux: run with sudo, or add the udev rule from the README.\n"
                 "Windows: close DS4Windows / Steam, they hold the device.")
    sys.exit("no DualShock 4 found. Plug it in over USB (or pair over Bluetooth).")


def read_state(dev, mode):
    """mode: dict with 'bt' flag, filled in on the first report."""
    r = dev.read(78, 100)
    if not r:
        return None
    if r[0] == 0x01 and len(r) >= 64:
        mode["bt"] = False
        return parse_usb(r)
    if r[0] == 0x11 and len(r) >= 78:
        mode["bt"] = True
        return parse_usb(bt_to_usb(r))
    if r[0] == 0x01:                      # BT minimal report: ask for the full one
        mode["bt"] = True
        try:
            dev.get_feature_report(0x02, 37)
        except OSError:
            pass
    return None


def mtime_or(path, fallback):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return fallback


def _safe_console():
    """A key name quoted back from a config file may not exist in the console's code page (a
    redirected stdout is strict cp1252 on Windows, which is how the autostart runs the mapper).
    Have prints escape such characters instead of raising: a message must never take the mapper
    down."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):      # no stream (pythonw), or not a text file
            pass


def main():
    _safe_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", metavar="FILE", help="control map JSON (default: mapping.json next to this "
                    "script, if present; '-' = the built-in map). Re-read live when it changes")
    ap.add_argument("--dump-map", nargs="?", const="-", metavar="FILE",
                    help="print the built-in control map as JSON and exit (with --map FILE: that file, "
                    "validated and normalised). Give FILE to write it there instead of printing")
    ap.add_argument("--tune", metavar="FILE", help="JSON with feel settings (default: tune.json next to "
                    "this script, if present). Re-read live when it changes")
    ap.add_argument("--attention-file", metavar="FILE", help="one-word status file that turns the light bar "
                    "orange while it says 'waiting' (default: attention_state.txt next to this script)")
    ap.add_argument("--no-inject", action="store_true", help="dashboard only, no mouse/keys")
    ap.add_argument("--no-pad-mouse", action="store_true", help="don't drive the cursor from the touchpad")
    ap.add_argument("--no-stick-mouse", action="store_true", help="don't drive the cursor from the right stick "
                    "(right_stick.mode = cursor only)")
    ap.add_argument("--gain", type=float, metavar="N", help="touchpad px per pad unit; overrides touch_gain from "
                    "the tune file for the whole run, live reloads included (default 0.35)")
    ap.add_argument("--selftest", action="store_true", help="run the built-in tests without hardware and exit "
                    "(with --map FILE: also check that file)")
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    if args.gain is not None:
        try:
            args.gain = _tune_value("touch_gain", args.gain)    # the same finite, in-range rule as the file
        except ValueError as ex:
            ap.error(f"--gain: {ex}")

    if args.dump_map is not None:
        try:
            m = load_mapping(args.map) if args.map not in (None, "-") else default_mapping()
        except (OSError, ValueError) as ex:
            sys.exit(f"control map {args.map}: {ex}")
        for note in mapping_warnings(m):
            print(f"! control map: {note}", file=sys.stderr)
        text = format_mapping(m)
        if args.dump_map == "-":
            sys.stdout.flush()
            sys.stdout.buffer.write(text.encode("utf-8"))     # LF on every platform, so files diff clean
        else:
            try:
                with open(args.dump_map, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            except OSError as ex:
                sys.exit(f"--dump-map: cannot write {args.dump_map} ({ex.strerror or ex})")
            print(f"wrote {args.dump_map} ({m['name']})")
        return
    if args.selftest:
        return selftest(args.map if args.map not in (None, "-") else None)

    try:
        map_path, mapping = resolve_mapping(args.map, here)
    except (OSError, ValueError) as ex:
        sys.exit(f"control map {args.map or 'mapping.json'}: {ex}")
    apply_mapping(mapping)
    for note in mapping_warnings(mapping):
        print(f"! control map: {note}")
    map_mtime = mtime_or(map_path, None) if map_path else None
    tune_path = args.tune or os.path.join(here, "tune.json")
    tune_mtime = load_tune(tune_path) if (args.tune or os.path.exists(tune_path)) else None
    if args.gain is not None:
        TUNE["touch_gain"] = args.gain      # the flag beats the file, now and after every reload below

    dev = open_device()
    grabbed = grab_kernel_touchpad()
    if grabbed:
        print(f"grabbed the kernel touchpad device ({len(grabbed)}) so the cursor is driven once")
    inj = make_injector(not args.no_inject)
    print(f"injection: {inj.name}   (Ctrl+C to quit)")
    print(f"control map: {MAP_NAME}" + (f"  [{map_path}, live]" if map_path else "  [built-in]"))
    if tune_mtime is not None:
        print(f"tune file: {tune_path} (live)")
    print("feel:", tune_summary())
    mapper = Mapper(inj, pad_mouse=not args.no_pad_mouse, stick_mouse=not args.no_stick_mouse)
    mapper.note = lambda s: print(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} {s}", file=sys.stderr, flush=True)
    if args.attention_file:
        mapper.attention_file = args.attention_file
    mode = {"bt": None}
    last_led, last_print, n, t0 = None, 0.0, 0, time.time()
    last_file_check = 0.0
    t_opened = time.time()           # battery colour shows for 2 s from here, then hands over
    attention_check = 0.0
    hz = 0.0
    seen = set()                 # buttons pressed since the last dashboard print
    try:
        while True:
            st = read_state(dev, mode)
            if st is None:
                continue
            n += 1
            now = time.time()
            if now - t0 >= 1.0:
                hz, n, t0 = n / (now - t0), 0, now
            mapper.step(st)
            seen |= st["buttons"]
            if now - attention_check >= 0.25:
                attention_check = now
                mapper.poll_attention()
            led = led_for(st, mapper.layer2,
                          # mapper.last_input is in the Mapper's own clock (monotonic);
                          # `now` here is time.time(), so comparing them would put the
                          # gap at ~1.7e9 s and the light would never once go blue
                          active=mapper.clock() - mapper.last_input < mapper.tune["led_idle_s"],
                          attention=mapper.attention == "waiting",
                          suspended=mapper.suspended, dark=mapper.dark,
                          grace=now - t_opened < 2.0)
            if led != last_led:
                # hidapi's write() returns -1 on failure instead of raising. Report it once
                # per colour change; retrying every report would stall the loop (1 s timeout).
                try:
                    if dev.write(led_report(led, bt=mode["bt"])) < 0:
                        print(f"\n! light bar write failed: {dev.error()}")
                except (OSError, ValueError) as ex:
                    print(f"\n! light bar write failed: {ex}")
                last_led = led
            if now - last_print >= 0.1:
                print("\r" + dashboard_line(st, hz, seen), end="", flush=True)
                seen = set()
                last_print = now
            # the two config files are watched by mtime, twice a second, so an edit - by hand or
            # from the editor's Save - takes effect without a restart
            if now - last_file_check >= 0.5:
                last_file_check = now
                if tune_mtime is not None and mtime_or(tune_path, tune_mtime) != tune_mtime:
                    tune_mtime = load_tune(tune_path) or tune_mtime
                    if args.gain is not None:
                        TUNE["touch_gain"] = args.gain
                    print("\nfeel:", tune_summary())
                if map_path and mtime_or(map_path, map_mtime) != map_mtime:
                    map_mtime = mtime_or(map_path, map_mtime)
                    try:
                        new_map = load_mapping(map_path)
                    except Exception as ex:      # noqa: BLE001
                        # the loader raises ValueError for anything wrong with the file; catching
                        # wider here is deliberate - a reload must never take a live mapper down
                        print(f"\n! control map {map_path}: {ex} - keeping the previous map")
                    else:
                        mapper.release_all()            # nothing from the old map stays held down
                        mapper.layer2 = False
                        apply_mapping(new_map)
                        print(f"\ncontrol map: {MAP_NAME} reloaded")
                        for note in mapping_warnings(new_map):
                            print(f"! control map: {note}")
    except KeyboardInterrupt:
        pass
    finally:
        print()
        mapper.release_all()
        try:
            dev.write(led_report(LED_COLOURS["idle"], bt=bool(mode["bt"])))
        except Exception:            # noqa: BLE001
            pass
        for d in grabbed:
            try:
                d.ungrab()
            except Exception:        # noqa: BLE001
                pass
        inj.close()
        dev.close()
        if getattr(inj, "dropped", 0):
            print(f"note: {inj.dropped} injected events were refused by Windows "
                  "(elevated window or secure desktop in front)")


# ------------------------------------------------------------------ self-test

def selftest(map_file=None):
    """Runs without hardware and without a display. `map_file` (from --selftest --map FILE) is
    loaded first, so a bad file fails in one line, and checked at the end: it must round-trip
    through the tables."""
    file_map = None
    if map_file:
        try:
            file_map = load_mapping(map_file)
        except (OSError, ValueError) as ex:
            sys.exit(f"control map {map_file}: {ex}")
    apply_mapping(default_mapping())          # the behavioural tests below assume the built-in map

    def report(lx=128, ly=128, rx=128, ry=128, dpad=8, b5=0, b6=0, b7=0, l2=0, r2=0,
               bat=0x1A, t1=None, t2=None):
        r = [0] * 64
        r[0] = 0x01
        r[1:5] = [lx, ly, rx, ry]
        r[5] = (b5 << 4) | dpad
        r[6], r[7], r[8], r[9] = b6, b7, l2, r2
        r[13:19] = [0x10, 0x00, 0xF0, 0xFF, 0x00, 0x00]    # gyro 16, -16, 0
        r[19:25] = [0x00, 0x20, 0x00, 0x00, 0x00, 0x00]    # accel 8192, 0, 0
        r[30] = bat
        r[33], r[34] = 1, 7
        for off, t in ((35, t1), (39, t2)):
            if t is None:
                r[off] = 0x80
            else:
                tid, x, y = t
                r[off] = tid & 0x7F
                r[off + 1] = x & 0xFF
                r[off + 2] = ((x >> 8) & 0x0F) | ((y & 0x0F) << 4)
                r[off + 3] = (y >> 4) & 0xFF
        return r

    st = parse_usb(report(lx=200, dpad=1, b5=0b0010, b6=0b1000_0001, b7=0b10, l2=77,
                          t1=(5, 1500, 700)))
    assert st["lx"] == 200 and st["dpad"] == "NE"
    assert st["buttons"] == {"Cross", "L1", "R3", "Pad", "dpad_N", "dpad_E"}, st["buttons"]
    assert st["l2"] == 77 and st["gyro"] == (16, -16, 0) and st["accel"] == (8192, 0, 0)
    assert st["usb"] and st["battery"] == 100
    assert st["touch"][0] == (True, 5, 1500, 700) and st["touch"][1][0] is False
    print("parse_usb            ok")

    bt = [0x11, 0xC0, 0x00] + report(rx=30)[1:] + [0] * 14
    stb = parse_usb(bt_to_usb(bt))
    assert stb["rx"] == 30
    print("bt_to_usb            ok")

    u, b = led_report((1, 2, 3)), led_report((1, 2, 3), bt=True)
    assert len(u) == 32 and u[0] == 0x05 and u[6:9] == b"\x01\x02\x03"
    assert len(b) == 78 and b[0] == 0x11 and b[8:11] == b"\x01\x02\x03"
    assert int.from_bytes(b[74:78], "little") == (zlib.crc32(b"\xA2" + b[:74]) & 0xFFFFFFFF)
    assert u[4:6] == b"\x00\x00" and b[6:8] == b"\x00\x00"      # rumble motors are removed
    print("led_report + CRC     ok")

    idle = dashboard_line(parse_usb(report()), 250.0)
    busy = parse_usb(report(lx=0, ly=255, dpad=5, b5=0xF, b6=0xFF, b7=0b11, l2=255, r2=255, bat=0x3B,
                            t1=(1, 1919, 941), t2=(2, 0, 0)))
    busy["gyro"], busy["accel"] = (-32768, 32767, -32768), (-32768, -32768, 32767)   # widest values
    full = dashboard_line(busy, 250.0)
    assert len(idle) == len(full) == DASHBOARD_WIDTH, (len(idle), len(full))
    assert full.rstrip() == full[:len(full.rstrip())] and len(full.rstrip()) <= DASHBOARD_WIDTH
    assert "[..................]" in idle and "T   -,-      -,-   " in idle
    assert "100%UH" in full and "[.v<.123sPTo123#XOA]" in full and "T1919,941    0,  0" in full
    assert "[...............X..]" in dashboard_line(parse_usb(report()), 250.0, buttons={"Cross"})
    print("dashboard_line       ok")

    assert curve(0) == -1.0 and curve(255) == 1.0 and curve(128) == 0.0 and curve(140) == 0.0
    assert abs(curve(200, expo=1.0) - (72 / 127 - 12 / 127) / (1 - 12 / 127)) < 1e-9
    assert abs(curve(60) + curve(196)) < 0.01, (curve(60), curve(196))   # near-mirror: 0..127 vs 128..255
    print("curve                ok")

    class Recorder(NullInjector):
        """Logs every call. In the screen-off tests it also stands in for the curtain: wake() is a
        key on the computer, which lifts the curtain from its own thread, as _BlackCurtain does."""
        repeat_delay, repeat_period = 0.5, 0.1
        screen = True                   # what display_off() answers

        def __init__(self):
            super().__init__(verbose=True)
            self.log = []
            self.why = None             # what lifted_by() answers

        def _input(self, *event):
            self.log.append(event)

        def scroll(self, v, h=0):
            self._input("scroll", v, h)
            super().scroll(v, h)

        def key(self, name, down):
            self._input("key", name, down)
            super().key(name, down)

        def move(self, dx, dy):
            self._input("move", dx, dy)
            super().move(dx, dy)

        def click(self, button, down):
            self._input("click", button, down)
            super().click(button, down)

        def centre(self):
            self._input("centre")
            super().centre()

        up = False                      # is the curtain up, as display_dark() reports it

        def display_off(self):
            self.log.append(("display_off",))
            self.up, self.why = self.screen, None
            return self.screen

        def display_on(self):
            self.log.append(("display_on",))
            self.up = False

        def display_dark(self):
            return self.up

        def lifted_by(self):
            return self.why

        def wake(self, why="input"):    # the curtain comes down by itself, the way a key makes it
            if self.up:
                self.up, self.why = False, why

        def keep_awake(self, on):
            self.log.append(("awake", on))

    clock = [0.0]
    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    print("mapper: press Cross, touch moves + tap, release, L3 held -> layer 2, dpad N, stick flick")
    m.step(parse_usb(report(b5=0b0010, t1=(1, 1000, 500))))
    m.step(parse_usb(report(b5=0b0010, t1=(1, 1020, 490))))
    assert ("move", 7, -3) in inj.log, inj.log
    m.step(parse_usb(report()))                # finger up after a short, small contact = tap
    assert inj.log[-2:] == [("click", "left", True), ("click", "left", False)], inj.log[-3:]
    m.step(parse_usb(report(b6=0b0100_0000)))             # L3 HELD = Fn = layer 2
    m.step(parse_usb(report(b6=0b0100_0000, dpad=0)))     # d-pad up on layer 2 = pageup
    assert m.layer2 and m.held["dpad_N"][:2] == ["key", "pageup"], m.held
    m.step(parse_usb(report()))                # d-pad and Fn released together
    assert not m.layer2 and ("key", "esc", True) not in inj.log, inj.log   # used, so no Esc tap
    inj.log.clear()
    for _ in range(25):                        # left stick held full up: ONE flick, not 25
        m.step(parse_usb(report(ly=0)))
    assert not m.held and inj.log == [("key", "ctrl", True), ("key", "shift", True), ("key", "tab", True),
                                      ("key", "tab", False), ("key", "shift", False), ("key", "ctrl", False)], inj.log
    m.step(parse_usb(report(ly=100)))          # back inside flick_off: re-armed
    m.step(parse_usb(report(lx=255)))          # flick right = alt+tab
    assert inj.log[6:] == [("key", "alt", True), ("key", "tab", True), ("key", "tab", False),
                           ("key", "alt", False)], inj.log[6:]
    m.step(parse_usb(report(lx=200)))          # still past flick_off: nothing more
    assert len(inj.log) == 10
    m.release_all()
    print("mapper               ok")

    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    clock[0] = 0.0
    m.step(parse_usb(report(t1=(1, 500, 500))))
    m.step(parse_usb(report(t1=(1, 500, 500), t2=(2, 700, 500))))
    clock[0] = 0.10
    m.step(parse_usb(report()))                # both up quickly, no motion = MIDDLE click now
    assert inj.log == [("click", "middle", True), ("click", "middle", False)], inj.log
    inj.log.clear()
    m.step(parse_usb(report(t1=(3, 500, 500))))
    clock[0] = 0.5                             # held too long
    m.step(parse_usb(report()))
    assert inj.log == [], inj.log
    m.step(parse_usb(report(t1=(4, 500, 500))))
    m.step(parse_usb(report(t1=(4, 500, 500), b7=0b10)))    # mechanical click while touching
    clock[0] = 0.55
    m.step(parse_usb(report()))
    assert inj.log == [("click", "right", True), ("click", "right", False)], inj.log
    print("taps + pad click     ok")

    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    clock[0] = 0.0
    m.step(parse_usb(report(b6=0b0100_0000, b5=0b0010)))   # Fn and Cross in the same report
    assert m.layer2 and m.held["Cross"][:2] == ["key", "space"], m.held   # Cross saw layer 2
    m.step(parse_usb(report(b5=0b0010)))           # Fn released, Cross still held
    clock[0] = 0.55                                 # past the repeat delay
    m.step(parse_usb(report(b5=0b0010)))
    clock[0] = 0.60
    m.step(parse_usb(report(b5=0b0010)))
    clock[0] = 0.66
    m.step(parse_usb(report(b5=0b0010)))
    downs = [e for e in inj.log if e == ("key", "space", True)]
    assert len(downs) == 3, inj.log                 # press + two repeats (0.55, 0.66)
    m.step(parse_usb(report()))
    assert ("key", "space", False) in inj.log and not m.held
    print("layer order + repeat ok")

    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    m.step(parse_usb(report(t1=(3, 800, 400), t2=(4, 900, 400))))     # two fingers land
    m.step(parse_usb(report(t1=(3, 800, 440), t2=(4, 900, 440))))     # both move down 40
    m.step(parse_usb(report(t1=(3, 800, 480), t2=(4, 900, 480))))
    scrolls = [e for e in inj.log if e[0] == "scroll"]
    moves = [e for e in inj.log if e[0] == "move"]
    assert scrolls and all(e[1] < 0 for e in scrolls) and not moves, inj.log   # fingers down = page down
    m.step(parse_usb(report(t2=(4, 900, 480))))                       # finger 3 lifts, 4 stays (slot 2)
    m.step(parse_usb(report(t2=(4, 920, 480))))                       # reference frame, then move
    m.step(parse_usb(report(t2=(4, 940, 480))))
    moves = [e for e in inj.log if e[0] == "move"]
    assert moves == [("move", 7, 0)] * 2, moves     # two 20-unit steps at 0.35 = 7 px each, no jump
    TUNE["natural_scroll"] = True
    inj.log.clear()
    m.step(parse_usb(report(t1=(5, 800, 400), t2=(6, 900, 400))))
    m.step(parse_usb(report(t1=(5, 800, 440), t2=(6, 900, 440))))
    assert all(e[1] > 0 for e in inj.log if e[0] == "scroll"), inj.log
    TUNE["natural_scroll"] = False
    print("two-finger scroll    ok")

    # ---- control map v2 (docs/CONTROLS.md) -----------------------------------------------
    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    clock[0] = 0.0

    # a key SEQUENCE is chord-after-chord, not every key at once
    m._key("ctrl+k ctrl+left", True)
    assert inj.log == [("key", "ctrl", True), ("key", "k", True),
                       ("key", "k", False), ("key", "ctrl", False),
                       ("key", "ctrl", True), ("key", "left", True),
                       ("key", "left", False), ("key", "ctrl", False)], inj.log
    inj.log.clear()
    m._key("ctrl+k ctrl+left", False)              # a sequence cannot be held
    assert inj.log == [], inj.log

    # Fn: a short L3 press is Esc; a long one is the layer and sends nothing
    m.step(parse_usb(report(b6=0b0100_0000)))
    assert m.layer2 and inj.log == [], inj.log     # engages at once, silently
    clock[0] = 0.1
    m.step(parse_usb(report()))
    assert inj.log == [("key", "esc", True), ("key", "esc", False)] and not m.layer2, inj.log
    inj.log.clear()
    clock[0] = 1.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    clock[0] = 1.5                                 # held well past hold_s
    m.step(parse_usb(report()))
    assert inj.log == [], inj.log                  # a hold sends no Esc

    # Share: tap = ctrl+c, hold = shift
    clock[0] = 2.0
    m.step(parse_usb(report(b6=0b0001_0000)))
    assert inj.log == [], inj.log                  # tap or hold is not knowable yet
    clock[0] = 2.1
    m.step(parse_usb(report()))
    assert inj.log == [("key", "ctrl", True), ("key", "c", True),
                       ("key", "c", False), ("key", "ctrl", False)], inj.log
    inj.log.clear()
    clock[0] = 3.0
    m.step(parse_usb(report(b6=0b0001_0000)))
    clock[0] = 3.4                                 # past hold_s: promoted to the modifier
    m.step(parse_usb(report(b6=0b0001_0000)))
    assert inj.log == [("key", "shift", True)], inj.log
    m.step(parse_usb(report()))
    assert inj.log[-1] == ("key", "shift", False), inj.log

    # right stick = arrows, repeat rate by deflection, dominant axis only
    inj.log.clear()
    clock[0] = 4.0
    m.step(parse_usb(report(rx=255)))
    assert inj.log == [("key", "right", True), ("key", "right", False)], inj.log
    inj.log.clear()
    clock[0] = 4.001                               # far too soon to repeat
    m.step(parse_usb(report(rx=255)))
    assert inj.log == [], inj.log
    clock[0] = 4.5                                 # past an interval even at the fastest rate
    m.step(parse_usb(report(rx=255)))
    assert inj.log == [("key", "right", True), ("key", "right", False)], inj.log
    inj.log.clear()
    clock[0] = 5.0
    m.step(parse_usb(report()))                    # centre: direction cleared
    m.step(parse_usb(report(rx=255, ry=200)))      # diagonal -> ONE arrow, x dominates
    assert inj.log == [("key", "right", True), ("key", "right", False)], inj.log

    # Fn + right stick = VS Code pane focus, once per push
    inj.log.clear()
    clock[0] = 6.0
    m.step(parse_usb(report()))
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, rx=255)))
    assert ("key", "k", True) in inj.log and ("key", "right", True) in inj.log, inj.log
    before = len(inj.log)
    for _ in range(10):
        m.step(parse_usb(report(b6=0b0100_0000, rx=255)))      # held: still just the one
    assert len(inj.log) == before, inj.log

    # Fn + left stick: north = Task View, south = centre the cursor
    inj.log.clear()
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, ly=0)))
    assert ("key", "super", True) in inj.log and ("key", "tab", True) in inj.log, inj.log
    inj.log.clear()
    m.step(parse_usb(report(b6=0b0100_0000)))      # re-arm
    m.step(parse_usb(report(b6=0b0100_0000, ly=255)))
    assert ("centre",) in inj.log, inj.log

    # R3 is Enter, and Fn + R3 is voice typing
    inj.log.clear()
    m.step(parse_usb(report(b6=0b1000_0000)))                  # R3 alone
    assert inj.log == [("key", "enter", True)], inj.log
    m.step(parse_usb(report()))
    assert inj.log[-1] == ("key", "enter", False), inj.log
    inj.log.clear()
    m.step(parse_usb(report(b6=0b0100_0000)))                  # Fn ...
    m.step(parse_usb(report(b6=0b1100_0000)))                  # ... + R3 = super+h
    assert ("key", "super", True) in inj.log and ("key", "h", True) in inj.log, inj.log
    m.step(parse_usb(report()))

    # Fn + pad click blacks the screen out. A held Shift is let go at once; the curtain goes up
    # SCREEN_OFF_DELAY_S later; nothing at all gets out while it is dark - not the finger that
    # pressed the pad, not the stick, not an L3 tap; and a key on the computer, which lifts the
    # curtain from its own thread, brings everything back without a cursor jump.
    m.step(parse_usb(report()))
    inj.log.clear()
    notes = []
    m.note = notes.append
    clock[0] = 6.0
    m.step(parse_usb(report(b6=0b0001_0000)))                   # Share ...
    clock[0] = 6.4
    m.step(parse_usb(report(b6=0b0001_0000)))                   # ... held: Shift engages
    assert inj.log == [("key", "shift", True)], inj.log
    m.step(parse_usb(report(b6=0b0101_0000)))                   # + Fn
    clock[0] = 6.5
    m.step(parse_usb(report(b6=0b0101_0000, b7=0b10, t1=(9, 900, 400))))   # + pad click
    assert m.dark and inj.log[-1] == ("key", "shift", False), inj.log      # let go first ...
    assert ("display_off",) not in inj.log, inj.log                         # ... not dark yet
    inj.log.clear()
    clock[0] = 6.6
    m.step(parse_usb(report(b6=0b0101_0000, b7=0b10, t1=(9, 990, 450), rx=255)))   # finger, stick
    assert inj.log == [], inj.log
    clock[0] = 6.95
    m.step(parse_usb(report(t1=(9, 990, 450))))                 # everything let go but the finger
    assert inj.log == [("display_off",), ("awake", True)] and m.dark, inj.log
    clock[0] = 7.0
    m.step(parse_usb(report()))
    m.step(parse_usb(report(b6=0b0100_0000)))                   # a bare L3 tap ...
    clock[0] = 7.05
    m.step(parse_usb(report()))
    assert inj.log == [("display_off",), ("awake", True)] and m.dark, inj.log   # ... no Esc, nothing
    assert led_for(dict(battery=100), True, active=True, dark=True) == LED_COLOURS["off"]
    assert led_for(dict(battery=100), False, attention=True, dark=True) == LED_COLOURS["attention"]
    clock[0] = 38.0                                             # half a minute later ...
    m.step(parse_usb(report()))
    assert inj.log[-1] == ("awake", True) and len(inj.log) == 3, inj.log    # ... renewed, once
    inj.log.clear()
    m.step(parse_usb(report(t1=(10, 500, 500))))                # a palm on the pad, still dark
    inj.wake()                                                  # a key on the computer
    clock[0] = 38.2
    m.step(parse_usb(report(t1=(10, 500, 500))))
    assert not m.dark and inj.log == [("display_on",), ("awake", False)], inj.log
    assert notes == ["screen off", "screen back after 31 s (a key, the mouse or a touch)"], notes
    m.step(parse_usb(report(t1=(10, 520, 500))))                # and the pad works again,
    assert inj.log[-1] == ("move", 7, 0), inj.log               # from where the finger was
    m.step(parse_usb(report()))
    assert not any(e[0] == "click" for e in inj.log), inj.log   # and the palm that was down is no tap

    # the same chord again: before the curtain is up it simply calls the switch-off off; once it
    # is up, it lifts it on purpose
    inj.log.clear()
    clock[0] = 40.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))          # dark ...
    m.step(parse_usb(report(b6=0b0100_0000)))
    clock[0] = 40.1
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))          # ... called off at once
    assert not m.dark and inj.log == [("awake", False)], inj.log
    m.step(parse_usb(report()))
    inj.log.clear()
    clock[0] = 41.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))
    m.step(parse_usb(report()))
    clock[0] = 41.5
    m.step(parse_usb(report()))                                 # curtain up
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))          # chord: lift it
    assert inj.log == [("display_off",), ("awake", True), ("display_on",), ("awake", False)], inj.log
    assert not m.dark
    m.step(parse_usb(report()))

    # the curtain can also come down because it stopped hearing from the mapper; the mapper
    # notices that too, says so, and goes back to normal
    inj.log.clear()
    clock[0] = 42.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))
    m.step(parse_usb(report()))
    clock[0] = 42.5
    m.step(parse_usb(report()))                                 # curtain up
    inj.wake("lost")
    clock[0] = 42.6
    m.step(parse_usb(report()))
    assert not m.dark, inj.log
    assert inj.log == [("display_off",), ("awake", True), ("display_on",), ("awake", False)], inj.log
    assert notes[-1] == "screen back after 0 s (the curtain stopped hearing from the mapper)", notes
    m.note = None

    # where nothing can black the screen out (Linux, --no-inject) the mapper does not go quiet
    inj.log.clear()
    inj.screen = False
    clock[0] = 43.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))
    m.step(parse_usb(report()))
    clock[0] = 43.5
    m.step(parse_usb(report()))
    assert not m.dark and inj.log == [("display_off",)], inj.log
    inj.screen = True
    # and screen_off_keep_awake = false leaves Windows' own timers alone
    TUNE["screen_off_keep_awake"] = False
    inj.log.clear()
    clock[0] = 44.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))
    m.step(parse_usb(report()))
    clock[0] = 44.5
    m.step(parse_usb(report()))
    assert m.dark and inj.log == [("display_off",)], inj.log
    inj.wake()
    clock[0] = 45.1
    m.step(parse_usb(report()))
    assert not m.dark
    TUNE["screen_off_keep_awake"] = True

    # suspend is still an action a map can bind: the same rules, injection off, screen untouched
    saved_l2 = dict(ACTIONS_L2)
    ACTIONS_L2["Pad"] = "suspend"
    inj.log.clear()
    clock[0] = 46.0
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))
    assert m.suspended is True and not m.dark
    m.step(parse_usb(report(rx=255)))
    clock[0] = 47.0
    m.step(parse_usb(report(b6=0b0100_0000)))      # a bare L3 tap while suspended ...
    clock[0] = 47.05
    m.step(parse_usb(report()))
    assert inj.log == [], inj.log                  # ... is swallowed too, not an Esc
    m.step(parse_usb(report(b6=0b0100_0000)))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))
    assert m.suspended is False
    m.step(parse_usb(report()))
    # a finger kept down into suspend, moved while it lasts and still down when it ends is taken
    # as it is then: no cursor jump on the way back
    inj.log.clear()
    clock[0] = 48.0
    m.step(parse_usb(report(t1=(11, 500, 500))))
    m.step(parse_usb(report(b6=0b0100_0000, t1=(11, 500, 500))))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10, t1=(11, 500, 500))))     # suspend
    m.step(parse_usb(report(t1=(11, 500, 500))))
    assert m.suspended is True
    m.step(parse_usb(report(t1=(11, 900, 500))))                               # moved meanwhile
    m.step(parse_usb(report(b6=0b0100_0000, t1=(11, 900, 500))))
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10, t1=(11, 900, 500))))     # resume
    m.step(parse_usb(report(t1=(11, 900, 500))))
    assert m.suspended is False and not any(e[0] == "move" for e in inj.log), inj.log
    m.step(parse_usb(report()))
    ACTIONS_L2.clear()
    ACTIONS_L2.update(saved_l2)
    print("map v2               ok")

    # screen off, the edges. Fn + pad click here goes down at `at` and lets go 10 ms later.
    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    fn_bit, pad_bit = 0b0100_0000, 0b10

    def screen_chord(at):
        clock[0] = at
        m.step(parse_usb(report(b6=fn_bit)))
        m.step(parse_usb(report(b6=fn_bit, b7=pad_bit)))
        clock[0] = at + 0.01
        m.step(parse_usb(report()))
        assert m.dark, inj.log

    # the curtain goes up SCREEN_OFF_DELAY_S after the chord, not before; the mapper has no idle
    # clock to consult (the Recorder has no last_input at all, so a call would fail the test), and
    # a key that lifts the curtain ends the dark on the next report
    screen_chord(0.0)
    clock[0] = SCREEN_OFF_DELAY_S - 0.05
    m.step(parse_usb(report()))
    assert m.dark and inj.log == [], inj.log
    clock[0] = SCREEN_OFF_DELAY_S + 0.01
    m.step(parse_usb(report()))
    assert inj.log == [("display_off",), ("awake", True)], inj.log
    inj.wake()
    clock[0] += 0.01
    m.step(parse_usb(report()))
    assert not m.dark and inj.log[2:] == [("display_on",), ("awake", False)], inj.log
    clock[0] = 1.0
    m.step(parse_usb(report()))
    assert len(inj.log) == 4, inj.log
    # an L3 press that starts while it is dark and ends after a key has woken everything is not
    # an Esc, however short: it began while the mapper was not listening
    inj.log.clear()
    screen_chord(2.0)
    clock[0] = 2.5
    m.step(parse_usb(report()))
    assert inj.log == [("display_off",), ("awake", True)], inj.log
    clock[0] = 3.1
    m.step(parse_usb(report(b6=fn_bit)))                        # L3 down in the dark ...
    inj.wake()                                                  # ... a key on the computer ...
    clock[0] = 3.13
    m.step(parse_usb(report(b6=fn_bit)))
    clock[0] = 3.15
    m.step(parse_usb(report()))                                 # ... L3 up 50 ms after it went down
    assert not m.dark and inj.log[2:] == [("display_on",), ("awake", False)], inj.log
    # the same where nothing can black the screen out: L3 down inside the 0.4 s, up 0.18 s later,
    # once the mapper is back to normal
    inj.log.clear()
    inj.screen = False
    screen_chord(4.0)
    clock[0] = 4.3
    m.step(parse_usb(report(b6=fn_bit)))
    clock[0] = 4.42
    m.step(parse_usb(report(b6=fn_bit)))
    assert not m.dark and inj.log == [("display_off",)], inj.log
    clock[0] = 4.48
    m.step(parse_usb(report()))
    assert inj.log == [("display_off",)], inj.log
    inj.screen = True
    # a right stick still pushed when everything comes back sends no arrows until it has been
    # back at rest - the arrows' version of the flick re-arm
    inj.log.clear()
    screen_chord(5.0)
    clock[0] = 5.5
    m.step(parse_usb(report(rx=255)))                           # curtain up, the stick pushed in the dark
    inj.wake()
    clock[0] = 6.1
    m.step(parse_usb(report(rx=255)))                           # a key: back, the stick still pushed ...
    clock[0] = 7.0
    m.step(parse_usb(report(rx=255)))                           # ... for most of a second
    assert not m.dark, inj.log
    assert inj.log == [("display_off",), ("awake", True), ("display_on",), ("awake", False)], inj.log
    m.step(parse_usb(report()))
    m.step(parse_usb(report(rx=255)))                           # at rest, pushed again: arrows
    assert inj.log[4:] == [("key", "right", True), ("key", "right", False)], inj.log
    m.step(parse_usb(report()))
    # a quiet mode the map can no longer toggle ends: a live reload (done here as main() does it)
    # can take the chord away, and the dark must not outlive it; the same goes for suspend
    inj.log.clear()
    screen_chord(8.0)
    clock[0] = 8.5
    m.step(parse_usb(report()))
    m.release_all()
    m.layer2 = False
    apply_mapping({"schema": 1, "fn": {"button": "L3", "tap": {"key": "esc"}}})
    clock[0] = 8.6
    m.step(parse_usb(report()))
    assert not m.dark, inj.log
    assert inj.log == [("display_off",), ("awake", True), ("display_on",), ("awake", False)], inj.log
    apply_mapping({"schema": 1, "fn": {"button": "L3", "tap": {"key": "esc"}},
                   "buttons": {"Pad": {"fn": {"action": "suspend"}}}})
    clock[0] = 9.0
    m.step(parse_usb(report(t1=(12, 500, 500))))                # a finger down, tracked ...
    m.step(parse_usb(report(b6=fn_bit, t1=(12, 500, 500))))
    m.step(parse_usb(report(b6=fn_bit, b7=pad_bit, t1=(12, 500, 500))))
    m.step(parse_usb(report(t1=(12, 500, 500))))
    assert m.suspended
    m.step(parse_usb(report(t1=(12, 900, 500))))                # ... and moved while suspended
    m.release_all()
    m.layer2 = False
    apply_mapping(default_mapping())                            # suspend is on no button by default
    inj.log.clear()
    m.step(parse_usb(report(t1=(12, 900, 500))))
    assert not m.suspended
    m.step(parse_usb(report(t1=(12, 900, 500))))
    assert not any(e[0] == "move" for e in inj.log), inj.log   # that way out settles too: no jump
    m.step(parse_usb(report()))
    # the left stick's flicks get the right stick's hold-off: pushed through a wake, nothing;
    # back inside flick_off and pushed again, the flick
    inj.log.clear()
    screen_chord(11.0)
    clock[0] = 11.5
    m.step(parse_usb(report(lx=255)))                           # curtain up, the stick pushed in the dark
    inj.wake()
    clock[0] = 11.6
    m.step(parse_usb(report(lx=255)))                           # back, the stick still pushed
    m.step(parse_usb(report(lx=255)))
    assert ("key", "alt", True) not in inj.log, inj.log
    m.step(parse_usb(report()))
    m.step(parse_usb(report(lx=255)))
    assert inj.log[-4:] == [("key", "alt", True), ("key", "tab", True), ("key", "tab", False),
                            ("key", "alt", False)], inj.log
    m.step(parse_usb(report()))
    # Fn and the right stick (pane focus) both held through a wake: no pane jump, and that L3,
    # pressed in the dark, is no Esc when it is let go
    inj.log.clear()
    screen_chord(13.0)
    clock[0] = 13.5
    m.step(parse_usb(report()))                                 # curtain up
    m.step(parse_usb(report(b6=fn_bit)))                        # Fn down in the dark ...
    m.step(parse_usb(report(b6=fn_bit, rx=255)))                # ... and the right stick pushed
    inj.wake()
    clock[0] = 13.6
    m.step(parse_usb(report(b6=fn_bit, rx=255)))                # back, both still held
    m.step(parse_usb(report(b6=fn_bit, rx=255)))
    clock[0] = 13.7
    m.step(parse_usb(report()))
    assert inj.log == [("display_off",), ("awake", True), ("display_on",), ("awake", False)], inj.log
    # the old coarse pointer (right_stick.mode = cursor) holds off the same way
    dm = default_mapping()
    dm["right_stick"]["mode"] = "cursor"
    apply_mapping(dm)
    inj.log.clear()
    screen_chord(15.0)
    clock[0] = 15.5
    m.step(parse_usb(report(rx=255)))                           # curtain up, the stick pushed in the dark
    inj.wake()
    clock[0] = 15.6
    m.step(parse_usb(report(rx=255)))
    m.step(parse_usb(report(rx=255)))
    assert not any(e[0] == "move" for e in inj.log), inj.log
    m.step(parse_usb(report()))
    m.step(parse_usb(report(rx=255)))                           # at rest, pushed again: it moves
    assert ("move", 8, 0) in inj.log, inj.log
    m.step(parse_usb(report()))
    apply_mapping(default_mapping())
    print("screen off edges     ok")

    # light bar: highest priority wins, idle is off
    bat = dict(battery=100)
    assert led_for(bat, False) == LED_COLOURS["off"]
    assert led_for(bat, False, active=True) == LED_COLOURS["active"]
    assert led_for(bat, True, active=True) == LED_COLOURS["layer2"]
    assert led_for(bat, True, active=True, attention=True) == LED_COLOURS["attention"]
    assert led_for(bat, True, True, True, suspended=True) == LED_COLOURS["suspended"]
    assert led_for(bat, True, True, True, suspended=True, dark=True) == LED_COLOURS["suspended"]
    assert led_for(bat, False, grace=True) == LED_COLOURS["good"]
    # steady, never flashing: led_report must leave the flash bytes at zero
    assert led_report(LED_COLOURS["attention"])[9:11] == bytearray(b"\x00\x00")
    # and it must not latch on by itself: the pad rests a unit or two off centre and the
    # triggers are stuck pressed, so neither can count as use
    m2 = Mapper(Recorder(), clock=lambda: clock[0])
    clock[0] = 10.0
    m2.step(parse_usb(report(lx=130, ly=126, rx=126, ry=123, b6=0b0000_1100)))
    assert m2.last_input == 0.0, m2.last_input
    m2.step(parse_usb(report(rx=255)))
    assert m2.last_input == 10.0, m2.last_input
    print("light bar            ok")

    # the attention file: one word, mtime-guarded, missing means idle
    import tempfile
    d = tempfile.mkdtemp()
    m2.attention_file = os.path.join(d, "attention_state.txt")
    with open(m2.attention_file, "w", encoding="utf-8") as f:
        f.write("waiting\n")
    m2.poll_attention()
    assert m2.attention == "waiting", m2.attention
    with open(m2.attention_file, "w", encoding="utf-8") as f:
        f.write("idle\n")
    m2.attention_mtime = 0.0
    m2.poll_attention()
    assert m2.attention == "idle", m2.attention
    m2.attention_file = os.path.join(d, "not_there.txt")
    m2.attention_mtime = 0.0
    m2.poll_attention()
    assert m2.attention == "idle"                  # missing file is idle, never a crash
    print("attention file       ok")

    # ---- the control map file -----------------------------------------------------------
    # the built-in map survives dump -> load -> apply with no change to any table
    d0 = default_mapping()
    assert d0 == current_mapping(), "the tables are not at their defaults"
    text = format_mapping(d0)
    assert json.loads(text) == d0                  # the one-line-per-input layout is still JSON
    assert max(len(line) for line in text.splitlines()) <= 120, "mapping.json has an over-wide line"
    tmp = os.path.join(d, "mapping.json")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    d1 = load_mapping(tmp)
    assert d1 == d0, "dump -> load changed the map"
    tables = (KEYMAP, KEYMAP_L2, MOUSEMAP, MOUSEMAP_L2, ACTIONS, ACTIONS_L2, TAP_KEY, HOLD_MOD,
              RSTICK_KEYS, RSTICK_L2, LSTICK_FLICK, LSTICK_FLICK_L2, LSTICK_ACTIONS_L2, LSTICK_MOUSE_L2, TOUCHPAD)
    before = [dict(tb) for tb in tables] + [FN_BUTTON, FN_TAP, rstick_mode]
    apply_mapping(d1)
    after = [dict(tb) for tb in tables] + [FN_BUTTON, FN_TAP, rstick_mode]
    assert before == after, "dump -> load -> apply changed a table"
    assert current_mapping() == d0
    assert validate_key_spec(" Ctrl+K   ctrl+Left ") == "ctrl+k ctrl+left"      # tidied, not rejected
    print("map round-trip       ok")

    # the compact form loads too: inputs and slots left out are simply unbound
    d2 = normalise_mapping({"schema": 1, "fn": {"button": "L3", "tap": {"key": "esc"}},
                            "buttons": {"Share": {"press": {"key": "a"}}, "L2": None},
                            "right_stick": {"mode": "cursor"},
                            "touchpad": {"one_finger": "cursor", "one_finger_tap": {"mouse": "left"}}})
    assert d2["buttons"]["Share"] == {"press": {"key": "a"}, "tap": None, "hold": None, "fn": None}
    assert d2["buttons"]["Options"] is None and d2["left_stick"]["flick"]["N"] is None
    assert d2["touchpad"]["two_finger"] is None and d2["right_stick"]["mode"] == "cursor"
    assert normalise_mapping(d2) == d2             # idempotent
    assert normalise_mapping({})["fn"] is None     # the empty map is legal, and inert

    def rejects(data, *needles):
        try:
            normalise_mapping(data)
        except ValueError as ex:
            for needle in needles:
                assert needle in str(ex), (needle, str(ex))
            return str(ex)
        raise AssertionError(f"accepted: {data}")

    def base(**buttons):
        return {"schema": 1, "buttons": buttons}

    msg = rejects(base(Share={"press": {"key": "ctrl+bogus"}}), "buttons.Share.press.key", "bogus", "valid:")
    rejects(base(L2={"press": {"key": "a"}}), "buttons.L2", "trigger")
    rejects(base(Share={"tap": {"key": "ctrl+c"}}), "buttons.Share", "hold")
    rejects(base(Share={"press": {"key": "a"}, "tap": {"key": "b"}, "hold": {"key": "ctrl"}}), "not both")
    rejects(base(Shaer={"press": {"key": "a"}}), "buttons", "Shaer")            # unknown input
    rejects(base(Share={"pres": {"key": "a"}}), "buttons.Share", "pres")        # unknown slot
    rejects(base(Share={"press": {"action": "reboot"}}), "action", "reboot")
    rejects(base(Share={"hold": {"mouse": "left"}}), "buttons.Share.hold", "mouse")   # hold takes a key
    rejects(base(Share={"press": {"key": "ctrl+"}}), "empty key")
    rejects(base(Share={"press": {"mouse": "back"}}), "mouse", "back")
    rejects({"schema": 2}, "schema")
    for loose in (1.0, True, "1"):                 # exactly the integer 1, as strict as the rest
        rejects({"schema": loose}, "schema")
    rejects({"schema": 1, "fn": {"button": "L3"}, "buttons": {"L3": {"press": {"key": "a"}}}}, "Fn button")
    rejects({"schema": 1, "fn": {"button": "R2"}}, "fn.button", "trigger")
    rejects({"schema": 1, "left_stick": {"fn": {"N": {"action": "suspend"}}}}, "left_stick.fn.N", "suspend")
    rejects({"schema": 1, "right_stick": {"mode": "arrows"}}, "right_stick.mode")
    rejects({"schema": 1, "touchpad": {"one_finger_tap": {"key": "enter"}}}, "touchpad.one_finger_tap", "mouse")
    rejects({"schema": 1, "buttons": []}, "buttons", "expected an object")
    print("map validation       ok   e.g.", msg)

    # the wrong KIND of value raises ValueError naming the slot, never a TypeError: a list or an
    # object where a name belongs would otherwise blow up a dict lookup, and a live reload with it
    for bad in ([1], {"x": 1}, 5, True):
        rejects(base(Share={"press": {"key": bad}}), "buttons.Share.press.key")
        rejects(base(Share={"press": {"mouse": bad}}), "buttons.Share.press.mouse")
        rejects(base(Share={"press": {"action": bad}}), "buttons.Share.press.action")
        rejects(base(Share={"fn": {"action": bad}}), "buttons.Share.fn.action")
        rejects({"schema": 1, "fn": {"button": bad}}, "fn.button")
        rejects({"schema": 1, "right_stick": {"keys": {"N": bad}}}, "right_stick.keys.N")
        rejects({"schema": 1, "left_stick": {"flick": {"N": bad}}}, "left_stick.flick.N")
        rejects({"schema": 1, "left_stick": {"fn": {"N": {"action": bad}}}}, "left_stick.fn.N")
        rejects({"schema": 1, "touchpad": {"one_finger_tap": {"mouse": bad}}}, "touchpad.one_finger_tap")
    rejects(base(Share={"press": {"action": None}}), "buttons.Share.press.action")
    # F keys are exactly f1..f12: 'f01', 'f13' and digits from other scripts are unknown keys
    for spec in ("f0", "f13", "f01", "f²", "f٣"):
        rejects(base(Share={"press": {"key": spec}}), "buttons.Share.press.key", "unknown key")
    assert validate_key_spec("F1 f12") == "f1 f12"
    # advisory notes for a valid map that cannot do all it says; the built-in map has none
    assert mapping_warnings(d0) == [], mapping_warnings(d0)
    notes = mapping_warnings(normalise_mapping({
        "schema": 1, "fn": None, "buttons": {"Share": {"fn": {"key": "a"}}, "R3": {"fn": {"mouse": "left"}}},
        "right_stick": {"mode": "cursor", "keys": {"N": "up"}}}))
    assert len(notes) == 2 and "fn is null" in notes[0] and "2 fn bindings" in notes[0], notes
    assert "cursor" in notes[1], notes
    # the file layer: a duplicate key and a UTF-16 file are refused with a reason, not a traceback
    dup = os.path.join(d, "dup.json")
    with open(dup, "w", encoding="utf-8") as f:
        f.write('{"schema": 1, "buttons": {"Share": {"press": {"key": "a"}}, '
                '"Share": {"press": {"key": "b"}}}}')
    u16 = os.path.join(d, "u16.json")
    with open(u16, "w", encoding="utf-16") as f:
        f.write('{"schema": 1}')
    missing = os.path.join(d, "missing.json")
    for path, needle in ((dup, "'Share' appears twice"), (u16, "UTF-8"), (missing, None)):
        try:
            load_mapping(path)
        except ValueError as ex:
            assert needle and needle in str(ex), (needle, str(ex))
        except OSError:
            assert needle is None, path
        else:
            raise AssertionError(f"accepted: {path}")
    # brackets nested thousands deep are "not valid JSON" from both loaders, not a RecursionError
    deep = os.path.join(d, "deep.json")
    with open(deep, "w", encoding="utf-8") as f:
        f.write("[" * 20000 + "]" * 20000)
    try:
        load_mapping(deep)
    except ValueError as ex:
        assert "nested too deeply" in str(ex), str(ex)
    else:
        raise AssertionError("accepted a file nested 20000 deep")
    deep_msgs = []
    assert load_tune(deep, log=deep_msgs.append) is not None
    assert len(deep_msgs) == 1 and "nested too deeply" in deep_msgs[0], deep_msgs
    print("map file errors      ok")

    # tune.json: nothing in it can stop the mapper. A value of the wrong kind is refused on its own
    # and reported, the rest of the file still applies; a file that is not JSON keeps every setting
    saved, msgs = dict(TUNE), []
    tf = os.path.join(d, "tune.json")
    with open(tf, "w", encoding="utf-8") as f:
        f.write('\ufeff{"touch_gain": "fast", "stick_deadzone": null, "natural_scroll": "false", '
                '"tap_max_move": 12.5, "touch_gainz": 1, "hold_s": 0.3, "key_repeat": false}')
    assert load_tune(tf, log=msgs.append) is not None
    assert TUNE["touch_gain"] == saved["touch_gain"] and TUNE["stick_deadzone"] == saved["stick_deadzone"]
    assert TUNE["natural_scroll"] is False and TUNE["tap_max_move"] == saved["tap_max_move"]
    assert TUNE["hold_s"] == 0.3 and TUNE["key_repeat"] is False
    assert len(msgs) == 5 and all("keeping" in msg or "ignored" in msg for msg in msgs), msgs
    with open(tf, "w", encoding="utf-8") as f:
        f.write('{"hold_s": 0.25,}')
    msgs.clear()
    assert load_tune(tf, log=msgs.append) is not None and TUNE["hold_s"] == 0.3    # kept, no crash
    assert len(msgs) == 1 and "not valid JSON" in msgs[0], msgs
    assert load_tune(missing, log=msgs.append) is None
    TUNE.update(saved)
    assert TUNE == saved
    print("tune file            ok")

    # out-of-range numbers are refused with the span named and the setting kept: each of these would
    # otherwise crash step() - 127 divides by zero in curve(), a negative expo overflows, rates of 0
    # divide by zero, 1e300 px per unit makes int() of inf - and the 400-digit int used to overflow
    # the loader itself in math.isfinite()
    with open(tf, "w", encoding="utf-8") as f:
        f.write('{"stick_deadzone": 127, "stick_expo": -2, "rstick_rate_min": 0, "rstick_rate_max": 0, '
                '"touch_gain": 1e300, "flick_on": 0, "tap_max_move": 1' + "0" * 400 + ', "hold_s": 0.5}')
    msgs.clear()
    assert load_tune(tf, log=msgs.append) is not None
    assert TUNE["hold_s"] == 0.5 and all(TUNE[k] == saved[k] for k in saved if k != "hold_s"), TUNE
    assert len(msgs) == 7 and all("outside" in msg and "keeping" in msg for msg in msgs), msgs
    assert max(len(msg) for msg in msgs) < 120, msgs            # the 400-digit number is cut short
    # flick_off has to stay below flick_on, or a flick would re-arm at once and repeat every report;
    # the pair is judged after the whole file is merged, so lowering both in one edit is fine
    with open(tf, "w", encoding="utf-8") as f:
        f.write('{"flick_on": 0.2}')
    msgs.clear()
    load_tune(tf, log=msgs.append)
    assert TUNE["flick_on"] == saved["flick_on"] and TUNE["flick_off"] == saved["flick_off"], TUNE
    assert len(msgs) == 1 and "flick_off" in msgs[0] and "keeping" in msgs[0], msgs
    with open(tf, "w", encoding="utf-8") as f:
        f.write('{"flick_on": 0.2, "flick_off": 0.1}')
    msgs.clear()
    load_tune(tf, log=msgs.append)
    assert msgs == [] and TUNE["flick_on"] == 0.2 and TUNE["flick_off"] == 0.1, (msgs, TUNE)
    assert set(TUNE_RANGE) == {k for k, v in saved.items() if not isinstance(v, bool)}
    # and the extremes the ranges DO allow get through step() at every deflection - the stick exactly
    # on the deadzone edge included - in both right-stick modes, without an exception

    def sweep():
        rec = Recorder()
        rec.verbose = False                 # hundreds of moves and keys; only an exception matters here
        mx = Mapper(rec, clock=lambda: clock[0])
        dz = TUNE["stick_deadzone"]
        for v in (0, 1, 2, 126, 127, 128, 129, 130, 254, 255, 128 + dz, 128 - dz):
            for _ in range(3):
                clock[0] += 0.01
                mx.step(parse_usb(report(lx=v, ly=255 - v, rx=v, ry=v, b6=0b0100_0000 if v % 2 else 0,
                                         t1=(1, 900 + 4 * v, 400 + v))))
        clock[0] += 1.0
        mx.step(parse_usb(report()))
        mx.release_all()

    for pick in (0, 1):
        for k, span in TUNE_RANGE.items():
            TUNE[k] = type(saved[k])(span[pick])
        TUNE["flick_off"] = min(TUNE["flick_off"], TUNE["flick_on"] / 2)
        sweep()
        apply_mapping({"schema": 1, "right_stick": {"mode": "cursor"}})
        sweep()
        apply_mapping(default_mapping())
    TUNE.update(saved)
    assert TUNE == saved
    print("tune ranges          ok")

    # a custom map drives the mapper: Share = a plain held 'a', suspend moved to Fn + R3,
    # Fn + pad click = cursor_centre, right stick E = f5 and nothing else, Fn + flick left = a
    # middle click, touchpad off
    custom = normalise_mapping({
        "schema": 1, "name": "test", "fn": {"button": "L3", "tap": None},
        "buttons": {"Share": {"press": {"key": "a"}}, "R3": {"fn": {"action": "suspend"}},
                    "Pad": {"press": {"mouse": "left"}, "fn": {"action": "cursor_centre"}}},
        "right_stick": {"mode": "keys", "keys": {"E": "f5"}},
        "left_stick": {"fn": {"W": {"mouse": "middle"}}}})
    apply_mapping(custom)
    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    clock[0] = 20.0
    m.step(parse_usb(report(b6=0b0001_0000)))                # Share: a plain held key, no tap wait
    assert inj.log == [("key", "a", True)], inj.log
    m.step(parse_usb(report()))
    assert inj.log[-1] == ("key", "a", False), inj.log
    inj.log.clear()
    m.step(parse_usb(report(b6=0b0100_0000, b7=0b10)))       # Fn + pad click = centre, not suspend
    assert inj.log == [("centre",)] and not m.suspended, inj.log
    m.step(parse_usb(report()))
    inj.log.clear()
    m.step(parse_usb(report(b6=0b1100_0000)))                # Fn + R3 = suspend ...
    assert m.suspended and inj.log == [], inj.log
    m.step(parse_usb(report()))
    m.step(parse_usb(report(b6=0b0001_0000)))                # Share does nothing while suspended
    m.step(parse_usb(report()))
    assert inj.log == [], inj.log
    m.step(parse_usb(report(b6=0b1100_0000)))                # ... and the same chord resumes
    assert not m.suspended
    m.step(parse_usb(report()))
    inj.log.clear()
    m.step(parse_usb(report(rx=255)))                         # right stick E = f5
    assert inj.log == [("key", "f5", True), ("key", "f5", False)], inj.log
    inj.log.clear()
    m.step(parse_usb(report()))
    m.step(parse_usb(report(ry=0)))                           # N is unbound: silent, no crash
    m.step(parse_usb(report()))
    m.step(parse_usb(report(b6=0b0100_0000)))                 # Fn + flick left = ONE middle click
    m.step(parse_usb(report(b6=0b0100_0000, lx=0)))
    assert inj.log == [("click", "middle", True), ("click", "middle", False)], inj.log
    for _ in range(5):
        m.step(parse_usb(report(b6=0b0100_0000, lx=0)))      # held past flick_on: still just the one
    assert len(inj.log) == 2, inj.log
    m.step(parse_usb(report()))
    inj.log.clear()
    m.step(parse_usb(report(t1=(1, 1000, 500))))              # touchpad: no cursor in this map
    m.step(parse_usb(report(t1=(1, 1100, 500))))
    m.step(parse_usb(report(b5=0b0010)))                      # Cross is unbound here
    assert inj.log == [], inj.log
    m.release_all()
    assert current_mapping() == custom
    apply_mapping(default_mapping())
    assert current_mapping() == d0
    print("map applied          ok")

    # hold on its own (allowed, see the docstring): a short press does nothing at all, a long one
    # is the modifier from hold_s until release
    apply_mapping({"schema": 1, "fn": None, "buttons": {"Share": {"hold": {"key": "shift"}}}})
    inj = Recorder()
    m = Mapper(inj, clock=lambda: clock[0])
    clock[0] = 30.0
    m.step(parse_usb(report(b6=0b0001_0000)))
    clock[0] = 30.1
    m.step(parse_usb(report()))
    assert inj.log == [], inj.log
    clock[0] = 31.0
    m.step(parse_usb(report(b6=0b0001_0000)))
    clock[0] = 31.4
    m.step(parse_usb(report(b6=0b0001_0000)))
    m.step(parse_usb(report()))
    assert inj.log == [("key", "shift", True), ("key", "shift", False)], inj.log
    apply_mapping(default_mapping())
    print("hold without tap     ok")

    if file_map is not None:
        dm = file_map
        apply_mapping(dm)
        assert current_mapping() == dm, "the map file does not round-trip through the tables"
        same = dm == d0
        apply_mapping(default_mapping())
        print(f"map file             ok   {os.path.basename(map_file)}: {dm['name']!r}, "
              f"{'identical to' if same else 'differs from'} the built-in map")

    if platform.system() == "Windows":
        import ctypes
        si = SendInputInjector()
        assert ctypes.sizeof(si.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        assert si.scan["enter"] == 0x1C and si.scan["up"] == 0x48 and si.scan["a"] == 0x1E
        assert 0.25 <= si.repeat_delay <= 1.0 and 1 / 31 <= si.repeat_period <= 0.41
        assert si.lifted_by() is None
        curtain = _BlackCurtain()                       # the prototypes only: no thread, no window
        assert isinstance(curtain._monitors(), list)   # read-only; the curtain is never raised here
        assert ctypes.sizeof(curtain.RAWINPUTDEVICE) == (16 if ctypes.sizeof(ctypes.c_void_p) == 8 else 12)
        print(f"SendInput            ok (repeat delay {si.repeat_delay:.2f} s, "
              f"{1 / si.repeat_period:.0f}/s)")

        # the curtain's own logic, driven on this thread against a stand-in for user32: no window
        # is ever made, no Raw Input registered, nothing appears on the screen
        class FakeUser32:
            def __init__(self):
                self.calls, self.hwnd, self.sink_ok, self.held = [], 1000, True, set()
                self.timers, self.killed = [], []
                self.up_while_creating, self.up_while_destroying, self.why_while_destroying = [], [], []

            def CreateWindowExW(self, *a):
                self.up_while_creating.append(c.still_up())
                self.hwnd += 1
                self.calls.append(("create", self.hwnd))
                return self.hwnd

            def DestroyWindow(self, h):
                self.up_while_destroying.append(c.still_up())    # what the mapper would read by then
                self.why_while_destroying.append(c.lifted_by)
                self.calls.append(("destroy", h))
                return 1

            def SetTimer(self, hwnd, ident, ms, proc):
                self.timers.append(ms)
                return 7

            def KillTimer(self, hwnd, ident):
                self.killed.append(ident)
                return 1

            def GetAsyncKeyState(self, vk):
                return -0x8000 if vk in self.held else 0   # a SHORT: the top bit set = down right now

            def DefWindowProcW(self, *a):
                return 0x5EED                           # so a message the curtain swallows is told apart

            def RegisterRawInputDevices(self, rid, n, size):
                self.calls.append(("sink", [(r.usUsagePage, r.usUsage, r.dwFlags, r.hwndTarget) for r in rid[:n]]))
                return 1 if self.sink_ok else 0

            def PostThreadMessageW(self, tid, msg, wp, lp):
                self.calls.append(("post", msg))
                return 1

            def __getattr__(self, name):                # everything else simply succeeds
                return lambda *a: 1

        c = _BlackCurtain()
        # Win32's own values, written out, so a typo in one of the constants cannot hide behind itself
        assert (c.RIDEV_INPUTSINK, c.RIDEV_REMOVE, c.WM_INPUT, c.WM_POINTERDOWN, c.WM_DISPLAYCHANGE,
                c.WM_SETCURSOR, c.WM_MOUSEACTIVATE, c.MA_NOACTIVATE, c.WM_CONTEXTMENU, c.WM_APPCOMMAND,
                c.WM_TIMER, c.WS_POPUP, c.WS_EX, c.SW_SHOWNOACTIVATE, c.WM_POINTERUPDATE, c.WM_POINTERUP,
                c.WM_POINTERACTIVATE, c.WM_POINTERCAPTURECHANGED, c.PA_NOACTIVATE) == (
                0x100, 0x1, 0xFF, 0x246, 0x7E, 0x20, 0x21, 3, 0x7B, 0x319, 0x113, 0x80000000, 0x08000088, 4,
                0x245, 0x247, 0x24B, 0x24C, 3)
        assert c.LIFT_ON == {0xFF, 0x246, 0x201, 0x204, 0x207, 0x20B, 0x20A, 0x20E} and c.MOUSE_VKS == (1, 2, 4, 5, 6)
        fake = c.u = FakeUser32()
        c.tid = 1
        c._monitors = lambda: [(0, 0, 100, 100), (100, 0, 50, 50)]
        sink_on = lambda h: ("sink", [(1, 6, 0x100, h), (1, 2, 0x100, h)])  # noqa: E731  INPUTSINK, to h
        sink_off = ("sink", [(1, 6, 0x1, None), (1, 2, 0x1, None)])        # REMOVE, NULL target
        # up: a window per monitor, keyboard + mouse sent to the first one and nothing else, the
        # thread's timer armed, and DARK_GRACE_S of grace from now
        c._show(nudge=True)
        w1 = list(c.windows)
        assert len(w1) == 2 and c.still_up() and sink_on(w1[0]) in fake.calls, fake.calls
        assert fake.timers == [c.TICK_MS] and 0 < c.grace_until - time.monotonic() <= DARK_GRACE_S, fake.timers
        # still_up() is the mapper's heartbeat: asked in time, the timer never lifts it
        c.ping = time.monotonic() - CURTAIN_LOST_S - 1
        assert c.still_up()
        c._tick()
        assert c.still_up() and c.lifted_by is None
        # inside DARK_GRACE_S nothing lifts it; after it a burst posts ONE lift, and a mouse move
        # landing on the curtain never does (Windows makes those up)
        fake.calls.clear()
        c._wndproc(w1[0], c.WM_INPUT, 1, 0)
        assert fake.calls == [], fake.calls
        c.grace_until = 0.0
        c._wndproc(w1[1], 0x0200, 0, 0)                 # WM_MOUSEMOVE
        assert fake.calls == [], fake.calls
        for m_ in (c.WM_INPUT, c.WM_INPUT, 0x0201, 0x020A):
            c._wndproc(w1[0], m_, 1, 0)
        assert fake.calls == [("post", c.WM_APP_LIFT)], fake.calls
        # the lift: the reason set and still_up() already no before any window goes, the sink taken
        # away (REMOVE wants a NULL target) before its window goes, and the timer killed
        fake.calls.clear()
        fake.why_while_destroying.clear()
        fake.up_while_destroying.clear()
        assert c._dispatch(c.WM_APP_LIFT)
        assert c.lifted_by == "input" and not c.still_up() and c.windows == []
        assert fake.calls == [sink_off, ("destroy", w1[0]), ("destroy", w1[1])], fake.calls
        assert fake.why_while_destroying == ["input", "input"], fake.why_while_destroying
        assert fake.up_while_destroying == [False, False] and fake.killed == [7], fake.up_while_destroying
        c.lifted_by, n = None, len(fake.calls)
        assert c._dispatch(c.WM_APP_LIFT) and c.lifted_by is None and len(fake.calls) == n   # a late one: nothing
        # a click lifts it only once every button is let go, so its release lands on the curtain -
        # where a context menu or a Back does nothing - and a button held past HELD_LIFT_S lifts it anyway
        c._show(nudge=False)
        c.ping, c.grace_until = time.monotonic(), 0.0
        fake.calls.clear()
        fake.held = {0x02}                              # the right button, still down
        c._wndproc(c.windows[1], 0x0204, 2, 0)          # WM_RBUTTONDOWN
        assert fake.calls == [("post", c.WM_APP_LIFT)], fake.calls
        c._dispatch(c.WM_APP_LIFT)
        c._tick()
        assert c.still_up() and c.lifted_by is None
        assert c._wndproc(c.windows[0], c.WM_CONTEXTMENU, 0, 0) == 1
        assert c._wndproc(c.windows[0], c.WM_APPCOMMAND, 0, 0) == 1
        fake.held = set()                               # let go
        c._tick()
        assert not c.still_up() and c.lifted_by == "input"
        c.lifted_by = None
        c._show(nudge=False)
        c.ping, c.grace_until = time.monotonic(), 0.0
        fake.held = {0x05}                              # a side button, held on and on
        c._wndproc(c.windows[0], 0x020B, 0x10000, 0)    # WM_XBUTTONDOWN
        c._dispatch(c.WM_APP_LIFT)
        c._tick()
        assert c.still_up()
        c.lift_at -= c.HELD_LIFT_S + 0.1
        c._tick()
        assert not c.still_up() and c.lifted_by == "input"
        fake.held = set()
        # a finger or a pen: the curtain keeps the whole contact - handled, so it is never turned into
        # a click on the app beneath, and it never takes the focus - and lifts once every contact is
        # up; one that ends by losing capture counts as up too
        c.lifted_by = None
        c._show(nudge=False)
        c.ping, c.grace_until = time.monotonic(), 0.0
        fake.calls.clear()
        assert c._wndproc(c.windows[0], c.WM_POINTERDOWN, 7, 0) == 0
        assert fake.calls == [("post", c.WM_APP_LIFT)], fake.calls
        assert c._wndproc(c.windows[0], c.WM_POINTERACTIVATE, 7, 0) == c.PA_NOACTIVATE
        assert c._wndproc(c.windows[0], c.WM_POINTERUPDATE, 7, 0) == 0
        assert c._wndproc(c.windows[1], c.WM_POINTERDOWN, 8, 0) == 0     # a second finger
        c._dispatch(c.WM_APP_LIFT)
        c._tick()
        assert c.still_up() and c.lifted_by is None
        assert c._wndproc(c.windows[0], c.WM_POINTERUP, 7, 0) == 0
        c._tick()
        assert c.still_up()                                               # one still down
        assert c._wndproc(c.windows[1], c.WM_POINTERCAPTURECHANGED, 8, 0) == 0
        c._tick()
        assert not c.still_up() and c.lifted_by == "input"
        c.contacts.add(9)                                                 # one whose up never came
        c._show(nudge=False)
        assert c.contacts == set()                                        # a new dark spell starts clean
        c._dispatch(c.WM_APP_HIDE)
        # a display change: every window hears of it, ONE rebuild runs, the new cover and its sink
        # come before the old windows go, and it reads as up all the way through
        c.lifted_by = None
        c._show(nudge=False)
        w2 = list(c.windows)
        fake.calls.clear()
        fake.up_while_creating.clear()
        for h in w2:
            c._wndproc(h, c.WM_DISPLAYCHANGE, 32, 0)
        assert fake.calls == [("post", c.WM_APP_LAYOUT)], fake.calls
        fake.calls.clear()
        assert c._dispatch(c.WM_APP_LAYOUT)
        w3 = list(c.windows)
        assert len(w3) == 2 and not set(w3) & set(w2) and c.still_up() and c.lifted_by is None
        assert fake.up_while_creating == [True, True], fake.up_while_creating
        assert fake.calls == [("create", w3[0]), ("create", w3[1]), sink_on(w3[0]),
                              ("destroy", w2[0]), ("destroy", w2[1])], fake.calls
        # the next display change is heard again; a new cover that cannot be watched is destroyed
        # again, and the old one stays
        fake.sink_ok = False
        fake.calls.clear()
        c._wndproc(w3[0], c.WM_DISPLAYCHANGE, 32, 0)
        assert fake.calls == [("post", c.WM_APP_LAYOUT)], fake.calls
        fake.calls.clear()
        a, b = fake.hwnd + 1, fake.hwnd + 2
        c._dispatch(c.WM_APP_LAYOUT)
        assert fake.calls == [("create", a), ("create", b), sink_on(a), ("destroy", a), ("destroy", b)], fake.calls
        assert c.windows == w3 and c.still_up(), c.windows
        fake.sink_ok = True
        # the heartbeat: unchecked for CURTAIN_LOST_S, it lifts itself and says why
        fake.why_while_destroying.clear()
        fake.up_while_destroying.clear()
        c.ping = time.monotonic() - CURTAIN_LOST_S - 1
        c._tick()
        assert c.lifted_by == "lost" and not c.still_up() and c.windows == []
        assert fake.why_while_destroying == ["lost", "lost"], fake.why_while_destroying
        assert fake.up_while_destroying == [False, False], fake.up_while_destroying
        # no sink, no curtain: _show takes its windows away again, and says why
        fake.sink_ok, c.error = False, None
        c._show(nudge=False)
        assert c.windows == [] and not c.still_up() and "could not be watched" in c.error, c.error
        fake.sink_ok = True
        # the mapper's own lift leaves no reason behind, and a stray display change after it is ignored
        c.lifted_by = None
        c._show(nudge=False)
        assert c._dispatch(c.WM_APP_HIDE) and c.lifted_by is None and not c.still_up()
        fake.calls.clear()
        c._dispatch(c.WM_APP_LAYOUT)
        assert fake.calls == [] and not c._dispatch(0x0400), fake.calls     # WM_USER: not ours
        print("curtain logic        ok   (user32 stood in for; nothing shown)")

        # SendInputInjector's side of screen off, against stand-ins for kernel32 and the curtain:
        # the exact execution-state flags, the battery guard, and the hand-offs
        import contextlib
        import io

        class FakeKernel32:
            def __init__(self):
                self.states, self.ac, self.pct = [], 1, 100

            def SetThreadExecutionState(self, flags):
                self.states.append(flags)
                return 0x80000000

            def GetSystemPowerStatus(self, p):
                s = p._obj                              # byref() keeps the structure it points at
                s.ACLineStatus, s.BatteryLifePercent = self.ac, self.pct
                return 1

        class FakeCurtain:
            def __init__(self, ok):
                self.ok, self.error, self.lifted_by, self.calls = ok, "no monitor", None, []

            def up(self):
                self.calls.append("up")
                return self.ok

            def down(self):
                self.calls.append("down")

            def still_up(self):
                self.calls.append("still_up")
                return self.ok

        fk = si.kernel32 = FakeKernel32()
        si.keep_awake(True)
        si.keep_awake(False)
        assert fk.states == [0x80000003, 0x80000000], fk.states  # CONTINUOUS|SYSTEM|DISPLAY, then let go
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fk.ac, fk.pct = 0, BATTERY_GUARD_PCT - 1  # on battery, under the guard: let go instead
            si.keep_awake(True)
            si.keep_awake(True)
        assert fk.states[-2:] == [0x80000000, 0x80000000], fk.states
        assert err.getvalue().count("battery under") == 1, err.getvalue()   # said once
        fk.pct = BATTERY_GUARD_PCT                    # at the line: still held
        si.keep_awake(True)
        fk.pct = 255                                  # level unknown: not low
        si.keep_awake(True)
        fk.ac, fk.pct = 1, 5                          # on mains, however low: held
        si.keep_awake(True)
        assert fk.states[-3:] == [0x80000003] * 3, fk.states
        si.curtain = FakeCurtain(True)
        assert si.display_off() is True and si.display_dark() is True and si.lifted_by() is None
        si.curtain.lifted_by = "lost"
        assert si.lifted_by() == "lost"
        si.display_on()
        assert si.curtain.calls == ["up", "still_up", "down"], si.curtain.calls
        si.curtain = FakeCurtain(False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert si.display_off() is False
        assert "could not black the screen out (no monitor)" in err.getvalue(), err.getvalue()
        si.close()
        assert si.curtain.calls[-1] == "down" and fk.states[-1] == 0x80000000
        si.curtain = None
        print("screen-off injector  ok   (kernel32 and the curtain stood in for)")
    print("selftest passed")


if __name__ == "__main__":
    main()
