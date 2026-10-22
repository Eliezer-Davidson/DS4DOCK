#!/usr/bin/env python3
"""
mapping_editor.py - a point-and-click editor for the dock's control map (mapping.json).

    python tools/mapping_editor.py                  # edits mapping.json next to ds4_dock.py
    python tools/mapping_editor.py my_map.json
    python tools/mapping_editor.py --selftest       # logic tests, no window (what CI runs)

The thing emulators have: a to-scale drawing of the dock's face plate, click an input, choose what it does,
save. tkinter only - no other dependency. The picture comes from tools/render_map.py, so the
canvas you click on is the same drawing as docs/images/map.svg; every rule - the input names,
the key names, what each slot may hold - comes from ds4_dock.py, so the editor cannot write a
file the mapper would refuse.

Left: the dock's face plate, to scale, seen from above with the keyboard edge at the top - the
drawing is the plate rather than a controller, because that is what sits in front of you.
"Bare board - five buttons" is this project's hardware on the printed palm plate: the touchpad
and its click, the two sticks and their clicks, Share and Options; everything else is a faint
ghost where the full plate would open it. "Full controller" makes every input editable. L1,
R1, L2 and R2 are four dashed tabs beyond the keyboard edge: that edge faces the keyboard in
every dock variant, so they are out of reach docked and are kept for a complete, undocked
controller. The labels beside the inputs are the map.

Right: the selected input. A button has Press (held while the button is down) or Tap + Hold,
plus Fn - what it does while the Fn button is held. Sticks get a direction table for both
layers, the touchpad its gestures. A binding is a Key, a Mouse button, an Action or Nothing.
Capture records a chord from real key presses; a second Capture appends a chord, which makes a
sequence (ctrl+k ctrl+left). An invalid spec turns red and blocks Save.

If hidapi is installed and a DualShock 4 is plugged in, the inputs you press light up on the
picture - press the button to find it. The editor only ever reads reports from the pad; it
writes nothing to it and injects nothing. Without hidapi or a pad the feature is simply absent.

Save writes the file in the mapper's own layout, and a running mapper picks it up within a
second. Ctrl+S saves; Ctrl + mouse wheel zooms the picture. Python >= 3.11.
"""

import argparse
import os
import platform
import queue
import re
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import ds4_dock     # noqa: E402  - names, validation, load/save: the single source of truth
import render_map   # noqa: E402  - the drawing, shared with the SVG

MODIFIERS = ds4_dock.MODIFIERS
MOD_ORDER = ("ctrl", "shift", "alt", "super")

# ------------------------------------------------------------------ keys: tkinter -> mapper names

KEYSYM = {
    "Control_L": "ctrl", "Control_R": "ctrl", "Shift_L": "shift", "Shift_R": "shift",
    "Alt_L": "alt", "Alt_R": "alt",
    "Super_L": "super", "Super_R": "super", "Win_L": "super", "Win_R": "super",
    "Return": "enter", "KP_Enter": "enter", "Escape": "esc", "BackSpace": "backspace",
    "space": "space", "Tab": "tab", "ISO_Left_Tab": "tab", "Insert": "insert", "Delete": "delete",
    "Prior": "pageup", "Next": "pagedown", "Home": "home", "End": "end",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "KP_Up": "up", "KP_Down": "down", "KP_Left": "left", "KP_Right": "right",
    "KP_Prior": "pageup", "KP_Next": "pagedown", "KP_Home": "home", "KP_End": "end",
    "KP_Insert": "insert", "KP_Delete": "delete",
    "XF86AudioPlay": "media_play_pause", "XF86AudioRaiseVolume": "volume_up",
    "XF86AudioLowerVolume": "volume_down", "XF86AudioMute": "mute",
}
# On Windows tkinter has no keysym for the media keys (it reports '??'); the keycode is the
# virtual-key code, which is stable. The digit row with Shift held comes through as 'exclam'
# etc., and a letter on a non-Latin layout as that layout's keysym - the keycode is still the
# physical key's, so it names the digit or letter.
WIN_VK = {0xB3: "media_play_pause", 0xAD: "mute", 0xAE: "volume_down", 0xAF: "volume_up"}
# On X11 the same fallback uses X keycodes: every current Linux (and XWayland) takes them from
# evdev as scancode + 8, so the digit row is 10..19 and the three letter rows start at 24, 38
# and 52. Only keys the mapper has a name for are listed.
X11_KEYCODE = {first + i: ch
               for row, first in (("1234567890", 10), ("qwertyuiop", 24), ("asdfghjkl", 38), ("zxcvbnm", 52))
               for i, ch in enumerate(row)}
# Without a usable keycode (macOS, or no keycode at all) a shifted digit is still a digit: the
# keysyms of the US layout's digit row. Another layout puts other symbols there, which is why
# a keycode fallback decides first wherever there is one.
SHIFTED_DIGIT = {"exclam": "1", "at": "2", "numbersign": "3", "dollar": "4", "percent": "5",
                 "asciicircum": "6", "ampersand": "7", "asterisk": "8", "parenleft": "9", "parenright": "0"}
# X11's default pc layout puts Meta_L on the shifted level of the Alt key (xkb symbols/pc:
# key <LALT> { [ Alt_L, Meta_L ] }), so Alt pressed while Shift is held arrives as Meta_L: it
# is the Alt key, and no alt+shift chord could be captured on Linux without it. On macOS Meta
# is Command, which the mapper has no name for. AltGr (ISO_Level3_Shift) is not Alt on any
# system, so it stays unsupported on purpose.
META = {"Meta_L", "Meta_R"}


def keysym_to_name(keysym, keycode=None, system=None):
    """A tkinter keysym (and keycode) -> the mapper's key name, or None when the mapper has no
    name for it. `system` is platform.system() unless a test says otherwise. Validity is still
    the mapper's call: every result passes validate_key_spec."""
    system = platform.system() if system is None else system
    if keysym in KEYSYM:
        return KEYSYM[keysym]
    if keysym in META:
        return None if system == "Darwin" else "alt"
    if len(keysym) == 1 and keysym.isascii() and keysym.isalnum():
        return keysym.lower()
    if keysym[:1] == "F" and keysym[1:].isdigit() and 1 <= int(keysym[1:]) <= 12:
        return keysym.lower()
    if keysym[:3] == "KP_" and len(keysym) == 4 and keysym[3].isdigit():
        return keysym[3]
    if system == "Windows" and keycode is not None:
        if keycode in WIN_VK:
            return WIN_VK[keycode]
        if 0x30 <= keycode <= 0x39:
            return chr(keycode)
        if 0x41 <= keycode <= 0x5A:
            return chr(keycode + 32)
    elif system != "Darwin" and keycode in X11_KEYCODE:      # X11: Linux and the BSDs
        return X11_KEYCODE[keycode]
    return SHIFTED_DIGIT.get(keysym)


def compose_chord(mods, key=None):
    """{'shift', 'ctrl'}, 'tab' -> 'ctrl+shift+tab'. Modifiers come out in a fixed order; a
    chord of modifiers alone is legal (it is what a Hold slot usually wants)."""
    parts = [m for m in MOD_ORDER if m in mods]
    if key and key not in MODIFIERS:
        parts.append(key)
    return "+".join(parts)


def append_chord(spec, chord):
    """A second capture extends the spec into a sequence: 'ctrl+k' + 'ctrl+left'."""
    spec = (spec or "").strip()
    return f"{spec} {chord}" if spec else chord


class ChordCapture:
    """Builds one chord from press/release events. A non-modifier key completes the chord at
    once; modifiers alone complete it when the last one is released."""

    def __init__(self):
        self.held, self.seen = set(), set()

    def press(self, name):
        if name in MODIFIERS:
            self.held.add(name)
            self.seen.add(name)
            return None
        return compose_chord(self.seen | self.held, name)

    def release(self, name):
        if name in MODIFIERS and name in self.held:
            self.held.discard(name)
            if not self.held and self.seen:
                return compose_chord(self.seen)
        return None


# ------------------------------------------------------------------ the model: a map dict

def fresh_map():
    return ds4_dock.normalise_mapping(ds4_dock.default_mapping())


def validate(m):
    """(normalised map, None) or (None, error text with the path of the bad entry)."""
    try:
        return ds4_dock.normalise_mapping(m), None
    except ValueError as ex:
        return None, str(ex)


def save_map(m, path):
    """Write a map the way the mapper's --dump-map lays it out. Raises ValueError if invalid."""
    text = ds4_dock.format_mapping(ds4_dock.normalise_mapping(m))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def button_slots(m, name):
    """The slot dict for a button, created empty if the button is unbound (null)."""
    if m["buttons"].get(name) is None:
        m["buttons"][name] = {"press": None, "tap": None, "hold": None, "fn": None}
    return m["buttons"][name]


def pair_mode(slots, default="press"):
    """Which pair a button is in: 'taphold' if tap or hold is bound, 'press' if press is. An
    empty pair is either, so `default` decides - the panel passes the radio choice the user
    made last, which is how "Tap + Hold" stays selected while its two slots are still empty."""
    if slots and (slots.get("tap") or slots.get("hold")):
        return "taphold"
    if slots and slots.get("press"):
        return "press"
    return default


def set_pair_mode(m, name, mode):
    """'press' or 'taphold' - the other pair is cleared, because a button has one or the other."""
    slots = button_slots(m, name)
    if mode == "press":
        slots["tap"] = slots["hold"] = None
    else:
        slots["press"] = None


def fn_button(m):
    return m["fn"]["button"] if m.get("fn") else None


def set_fn_button(m, name):
    """Make `name` the Fn button (None = no layer). Its own bindings go, because the loader
    refuses bindings on the Fn button; fn.tap is kept."""
    tap = m["fn"]["tap"] if m.get("fn") else None
    if name is None:
        m["fn"] = None
    else:
        m["fn"] = {"button": name, "tap": tap}
        m["buttons"][name] = None


def bound_count(m, mode):
    """How many of the mode's inputs have at least one binding (for the status line)."""
    live = render_map.ELEMENTS if mode == "full" else render_map.BARE_ELEMENTS
    n = 0
    for el in live:
        b = render_map.ELEMENT_BUTTON.get(el, el)
        if m["buttons"].get(b) or fn_button(m) == b:
            n += 1
        elif el == "LS" and (any(m["left_stick"]["flick"].values()) or any(m["left_stick"]["fn"].values())):
            n += 1
        elif el == "RS" and (m["right_stick"]["mode"] == "cursor" or any(m["right_stick"]["keys"].values())):
            n += 1
        elif el == "Pad" and (m["touchpad"]["one_finger"] or m["touchpad"]["two_finger"]):
            n += 1
    return n, len(live)


# ------------------------------------------------------------------ live indicator

class PadWatcher(threading.Thread):
    """Reads input reports from a plugged-in DualShock 4 and posts the set of pressed elements
    to a queue. Read-only: nothing is ever written to the pad. Silently absent without hidapi
    or a pad, or when the pad cannot be opened."""
    daemon = True

    def __init__(self, q):
        super().__init__(name="pad-watcher")
        self.q, self.stop = q, False

    def run(self):
        try:
            import hid
        except ImportError:
            return
        if not hasattr(hid, "device"):
            return
        dev = None
        try:
            for pid, label in ds4_dock.PIDS.items():
                for info in hid.enumerate(ds4_dock.VID, pid):
                    try:
                        d = hid.device()
                        d.open_path(info["path"])
                        d.set_nonblocking(0)
                        dev, name = d, label
                        break
                    except OSError:
                        continue
                if dev:
                    break
            if dev is None:
                return
            self.q.put(("open", name))
            mode, last = {"bt": None}, None
            while not self.stop:
                st = ds4_dock.read_state(dev, mode)
                if st is None:
                    continue
                lit = set()
                for b in st["buttons"]:
                    if b not in ds4_dock.RESERVED_BUTTONS:          # L2/R2 read pressed for ever
                        lit.add(render_map.BUTTON_ELEMENT.get(b, b))
                if abs(st["lx"] - 128) > 48 or abs(st["ly"] - 128) > 48:
                    lit.add("LS")
                if abs(st["rx"] - 128) > 48 or abs(st["ry"] - 128) > 48:
                    lit.add("RS")
                if any(t[0] for t in st["touch"]):
                    lit.add("Pad")
                if lit != last:
                    self.q.put(("lit", lit))
                    last = lit
        except Exception:        # noqa: BLE001 - a dropped pad just ends the feature
            pass
        finally:
            if dev is not None:
                try:
                    dev.close()
                except Exception:   # noqa: BLE001
                    pass
            self.q.put(("closed", None))


# ------------------------------------------------------------------ the window

CANVAS_BG = "#f6f8fa"
ERR_BG = "#ffd9d9"
KIND_LABEL = {"key": "Key", "mouse": "Mouse", "action": "Action", None: "Nothing"}
LABEL_KIND = {v: k for k, v in KIND_LABEL.items()}
DIR_WORD = {"N": "up", "S": "down", "W": "left", "E": "right"}
ENTRY_ELEMENT = {"dpad": "dpad_N", "face": "Triangle"}       # a group callout selects its first member


def _blend(hexcol, bg, a):
    r1, g1, b1 = int(hexcol[1:3], 16), int(hexcol[3:5], 16), int(hexcol[5:7], 16)
    r2, g2, b2 = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    return "#%02x%02x%02x" % (round(r1 * a + r2 * (1 - a)), round(g1 * a + g2 * (1 - a)), round(b1 * a + b2 * (1 - a)))


def _opacity(extra, which):
    m = re.search(which + r'-opacity="([\d.]+)"', extra or "")
    return float(m.group(1)) if m else 1.0


def tk_styles(bg=CANVAS_BG):
    """render_map's SVG styles as opaque tkinter colours over the canvas background, so the
    canvas and the SVG look the same."""
    shapes, texts = {}, {}
    for cls, (fill, stroke, width, dash, extra) in render_map.STYLE.items():
        shapes[cls] = {
            "fill": "" if fill == "none" else _blend(fill, bg, _opacity(extra, "fill")),
            "outline": "" if stroke == "none" else _blend(stroke, bg, _opacity(extra, "stroke")),
            "width": width, "dash": tuple(int(x) for x in dash.split()) if dash else None,
        }
    for cls, (fill, extra) in render_map.TEXT.items():
        texts[cls] = _blend(fill, bg, _opacity(extra, "fill"))
    return shapes, texts


class BindingRow:
    """One slot in the panel: [label] [kind] [value]. `get()` returns the slot's binding
    (a dict or None) and `put(binding)` stores it; the editor is told after every change."""

    def __init__(self, editor, parent, row, label, kinds, get, put, actions=None, note=None):
        self.ed, self.kinds, self.get, self.put = editor, tuple(kinds), get, put
        self.label = label
        self.actions = tuple(actions or ds4_dock.ACTION_NAMES)
        self.capturing = False
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=3)
        b = get()
        kind = next(iter(b)) if b else None
        self.kind_var = tk.StringVar(value=KIND_LABEL[kind])
        self.kind_cb = None
        # A key-only slot is its entry, and × clears it. Every other slot gets the kind list with
        # Nothing - a one-kind slot like the touchpad taps too, or a null one could never be
        # bound and a bound one never cleared.
        if self.kinds != ("key",):
            self.kind_cb = ttk.Combobox(parent, textvariable=self.kind_var, width=7, state="readonly",
                                        values=[KIND_LABEL[k] for k in self.kinds] + ["Nothing"])
            self.kind_cb.grid(row=row, column=1, sticky="nw", padx=(0, 6), pady=3)
            self.kind_cb.bind("<<ComboboxSelected>>", self._kind_changed)
        self.box = ttk.Frame(parent)
        self.box.grid(row=row, column=2, sticky="ew", pady=3)
        parent.columnconfigure(2, weight=1)
        self.key_var = tk.StringVar(value=b["key"] if b and "key" in b else "")
        self.key_var.trace_add("write", lambda *_: self._key_changed())
        self.choice = tk.StringVar(value=(b.get("mouse") or b.get("action") or "") if b else "")
        self.entry = self.cap_btn = None
        self._build(kind)
        if note:
            ttk.Label(parent, text=note, style="Note.TLabel", wraplength=editor.wrap).grid(
                row=row + 1, column=0, columnspan=3, sticky="w", pady=(0, 4))

    def _build(self, kind):
        for w in self.box.winfo_children():
            w.destroy()
        self.entry = self.cap_btn = None
        if kind == "key" or (kind is None and self.kinds == ("key",)):
            self.entry = tk.Entry(self.box, textvariable=self.key_var, width=16)
            self.entry.pack(side="left", fill="x", expand=True)
            self.cap_btn = ttk.Button(self.box, text="Capture", width=7, command=self.toggle_capture)
            self.cap_btn.pack(side="left", padx=(6, 0))
            ttk.Button(self.box, text="×", width=2, command=lambda: self.key_var.set("")).pack(side="left", padx=(3, 0))
            self._colour()
        elif kind == "mouse":
            cb = ttk.Combobox(self.box, textvariable=self.choice, width=8, state="readonly", values=list(ds4_dock.MOUSE_BUTTONS))
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e: self._choice_changed("mouse"))
        elif kind == "action":
            cb = ttk.Combobox(self.box, textvariable=self.choice, width=14, state="readonly", values=list(self.actions))
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e: self._choice_changed("action"))
            self.action_note = ttk.Label(self.box, text="", style="Note.TLabel", wraplength=self.ed.wrap // 2)
            self.action_note.pack(side="left", padx=(8, 0))
            self._describe()
        else:
            hint = "choose " + " / ".join(KIND_LABEL[k] for k in self.kinds) + " to bind it"
            ttk.Label(self.box, text=hint, style="Note.TLabel").pack(side="left")

    def _describe(self):
        if getattr(self, "action_note", None) and self.action_note.winfo_exists():
            self.action_note.configure(text=ds4_dock.ACTION_NAMES.get(self.choice.get(), ""))

    def _kind_changed(self, _event=None):
        kind = LABEL_KIND[self.kind_var.get()]
        if kind == "key":
            self.put({"key": self.key_var.get().strip()} if self.key_var.get().strip() else None)
        elif kind == "mouse":
            if self.choice.get() not in ds4_dock.MOUSE_BUTTONS:
                self.choice.set("left")
            self.put({"mouse": self.choice.get()})
        elif kind == "action":
            if self.choice.get() not in self.actions:
                self.choice.set(self.actions[0])
            self.put({"action": self.choice.get()})
        else:
            self.put(None)
        self._build(kind)
        self.ed.changed()

    def _choice_changed(self, kind):
        self.put({kind: self.choice.get()})
        self._describe()
        self.ed.changed()

    def _key_changed(self):
        if self.entry is None or not self.entry.winfo_exists():
            return
        text = self.key_var.get().strip()
        self.put({"key": text} if text else None)
        self._colour()
        self.ed.changed()

    def _colour(self):
        if self.entry is None:
            return
        text = self.key_var.get().strip()
        ok = True
        if text:
            try:
                ds4_dock.validate_key_spec(text)
            except ValueError:
                ok = False
        self.entry.configure(bg="white" if ok else ERR_BG)

    def toggle_capture(self):
        if self.capturing:
            self.ed.end_capture()
        else:
            self.ed.begin_capture(self)

    def set_capturing(self, on):
        self.capturing = on
        if self.cap_btn is not None and self.cap_btn.winfo_exists():
            self.cap_btn.configure(text="Cancel" if on else "Capture")

    def captured(self, chord):
        self.key_var.set(append_chord(self.key_var.get(), chord))


class Editor:
    def __init__(self, root, path, mode="bare", select=None):
        self.root, self.path, self.mode = root, None, mode
        self.map = fresh_map()
        self.dirty, self.error = False, None
        self.selected, self.hover, self.lit = None, None, set()
        self.zoom, self.capture, self.capture_row = 1.0, None, None
        self.rows = []
        self.pair_choice = {}       # button -> the Press / Tap + Hold radio as the user last set it
        self._redraw_job = None
        self.shape_style, self.text_style = tk_styles()
        self.font_family = {"Windows": "Segoe UI", "Darwin": "Helvetica Neue"}.get(platform.system(), "Helvetica")
        self._fonts = {}
        try:                                   # Tk's scaling is px per point; 96 dpi = 1.333
            self.scale = max(0.5, float(root.tk.call("tk", "scaling")) / (96 / 72))
        except Exception:   # noqa: BLE001
            self.scale = 1.0
        self.wrap = int(300 * self.scale)      # wraplength is in pixels and does not follow the DPI
        self._build_ui()
        if path:
            self.load(path, quiet=True)
        self.q = queue.SimpleQueue()
        self.pad_name = None
        self.watcher = PadWatcher(self.q)
        self.watcher.start()
        self.root.after(60, self._poll_pad)
        if select:
            self.select(render_map.BUTTON_ELEMENT.get(select, select))
        self.changed(mark=False)

    # ---------- construction
    def _build_ui(self):
        root = self.root
        style = ttk.Style()
        base = tkfont.nametofont("TkDefaultFont")
        self.font_h1 = base.copy()
        self.font_h1.configure(size=base.cget("size") + 4, weight="bold")
        self.font_h2 = base.copy()
        self.font_h2.configure(size=base.cget("size") + 1, weight="bold")
        style.configure("Note.TLabel", foreground="#6e7781")
        style.configure("Err.TLabel", foreground="#b42318")
        style.configure("H1.TLabel", font=self.font_h1)
        style.configure("H2.TLabel", font=self.font_h2)

        top = ttk.Frame(root, padding=(8, 6))
        top.pack(side="top", fill="x")
        for text, cmd in (("Open…", self.open), ("Save", self.save), ("Save as…", self.save_as),
                          ("Reset to defaults", self.reset)):
            b = ttk.Button(top, text=text, command=cmd)
            b.pack(side="left", padx=(0, 4))
            if text == "Save":
                self.save_btn = b
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self.export_btn = ttk.Button(top, text="Export SVG…", command=self.export_svg)
        self.export_btn.pack(side="left", padx=(0, 4))
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self.mode_var = tk.StringVar(value=self.mode)
        for text, val in (("Bare board — five buttons", "bare"), ("Full controller", "full")):
            ttk.Radiobutton(top, text=text, value=val, variable=self.mode_var, command=self.set_mode).pack(side="left", padx=(0, 10))
        self.pad_label = ttk.Label(top, text="", style="Note.TLabel")
        self.pad_label.pack(side="right")

        self.status = ttk.Label(root, text="", anchor="w", padding=(8, 4))
        self.status.pack(side="bottom", fill="x")

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True)
        cframe = ttk.Frame(paned)
        self.canvas = tk.Canvas(cframe, bg=CANVAS_BG, highlightthickness=0)
        vs = ttk.Scrollbar(cframe, orient="vertical", command=self.canvas.yview)
        hs = ttk.Scrollbar(cframe, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        cframe.rowconfigure(0, weight=1)
        cframe.columnconfigure(0, weight=1)
        paned.add(cframe, weight=1)
        outer = ttk.Frame(paned, padding=(10, 8))
        paned.add(outer, weight=0)
        self.panel = outer
        self.canvas.bind("<Configure>", lambda e: self.redraw_later())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(None))
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Control-MouseWheel>", self._on_wheel)
        self.canvas.bind("<Control-Button-4>", lambda e: self.set_zoom(self.zoom * 1.1))
        self.canvas.bind("<Control-Button-5>", lambda e: self.set_zoom(self.zoom / 1.1))
        root.bind_all("<Control-s>", lambda e: self._hotkey(e, self.save))
        root.bind_all("<Control-S>", lambda e: self._hotkey(e, self.save))
        root.bind_all("<Control-equal>", lambda e: self._hotkey(e, lambda: self.set_zoom(self.zoom * 1.1)))
        root.bind_all("<Control-plus>", lambda e: self._hotkey(e, lambda: self.set_zoom(self.zoom * 1.1)))
        root.bind_all("<Control-minus>", lambda e: self._hotkey(e, lambda: self.set_zoom(self.zoom / 1.1)))
        root.bind_all("<Control-0>", lambda e: self._hotkey(e, lambda: self.set_zoom(1.0)))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_panel()

    # ---------- file actions
    def title(self):
        name = os.path.basename(self.path) if self.path else "untitled"
        self.root.title(f"{name}{'*' if self.dirty else ''} — DS4 dock mapping editor")

    def load(self, path, quiet=False):
        try:
            m = ds4_dock.load_mapping(path)
        except (OSError, ValueError) as ex:
            if quiet:
                self.set_status(f"could not open {path}: {ex}", error=True)
                return False
            messagebox.showerror("Open", f"{path}\n\n{ex}", parent=self.root)
            return False
        self.map, self.path, self.dirty = m, path, False
        self.selected, self.pair_choice = None, {}
        self.show_panel()
        self.changed(mark=False)
        return True

    def open(self):
        if not self._discard_ok():
            return
        path = filedialog.askopenfilename(parent=self.root, title="Open control map",
                                          initialdir=os.path.dirname(self.path) if self.path else REPO,
                                          filetypes=[("control map", "*.json"), ("all files", "*")])
        if path:
            self.load(path)

    def save(self):
        if self.capture:
            self.end_capture()
        if self.error:
            messagebox.showerror("Save", f"The map is not valid yet:\n\n{self.error}", parent=self.root)
            return False
        if not self.path:
            return self.save_as()
        try:
            save_map(self.map, self.path)
        except (OSError, ValueError) as ex:
            messagebox.showerror("Save", f"{self.path}\n\n{ex}", parent=self.root)
            return False
        self.dirty = False
        self.changed(mark=False)
        self.set_status(f"saved {self.path} - a running mapper re-reads it within a second")
        return True

    def save_as(self):
        if self.error:
            messagebox.showerror("Save", f"The map is not valid yet:\n\n{self.error}", parent=self.root)
            return False
        path = filedialog.asksaveasfilename(parent=self.root, title="Save control map as", defaultextension=".json",
                                            initialdir=os.path.dirname(self.path) if self.path else REPO,
                                            initialfile=os.path.basename(self.path) if self.path else "mapping.json",
                                            filetypes=[("control map", "*.json"), ("all files", "*")])
        if not path:
            return False
        self.path = path
        return self.save()

    def reset(self):
        if self.dirty and not messagebox.askyesno("Reset", "Throw away the changes and go back to the built-in map?", parent=self.root):
            return
        self.map, self.pair_choice = fresh_map(), {}
        self.dirty = True
        self.show_panel()
        self.changed()
        self.set_status("the built-in map - Save writes it to the file")

    def export_svg(self):
        if self.error:
            messagebox.showerror("Export", f"The map is not valid yet:\n\n{self.error}", parent=self.root)
            return
        images = os.path.join(REPO, "docs", "images")
        path = filedialog.asksaveasfilename(parent=self.root, title="Export the map as SVG", defaultextension=".svg",
                                            initialdir=images if os.path.isdir(images) else REPO,
                                            initialfile="map.svg" if self.mode == "bare" else "map_full.svg",
                                            filetypes=[("SVG", "*.svg")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(render_map.render_svg(self.map, self.mode))
        except (OSError, ValueError) as ex:
            messagebox.showerror("Export", f"{path}\n\n{ex}", parent=self.root)
            return
        self.set_status(f"wrote {path} ({self.mode})")

    def _discard_ok(self):
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("Unsaved changes", "Save the changes first?", parent=self.root)
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def on_close(self):
        if self._discard_ok():
            self.watcher.stop = True
            self.root.destroy()

    def _hotkey(self, event, action):
        """A global shortcut - unless a chord is being captured, in which case it is the chord."""
        if self.capture:
            return self._cap_press(event)
        action()
        return "break"

    # ---------- state
    def set_status(self, text, error=False):
        self.status.configure(text=text, style="Err.TLabel" if error else "TLabel")

    def changed(self, mark=True):
        """After any edit: validate with the mapper's rules, gate Save/Export, redraw."""
        if mark:
            self.dirty = True
        _, self.error = validate(self.map)
        state = ["!disabled"] if not self.error else ["disabled"]
        self.save_btn.state(state)
        self.export_btn.state(state)
        self.title()
        if self.error:
            self.set_status("not valid: " + self.error, error=True)
        else:
            n, total = bound_count(self.map, self.mode)
            where = os.path.basename(self.path) if self.path else "unsaved"
            fnb = fn_button(self.map)
            self.set_status(f"map OK  ·  {n} of {total} inputs bound  ·  Fn = {fnb or 'none'}  ·  {where}")
        self.redraw_later()

    def set_mode(self):
        self.mode = self.mode_var.get()
        if self.selected and self.mode == "bare" and self.selected not in render_map.BARE_ELEMENTS:
            self.selected = None
            self.show_panel()
        self.changed(mark=False)

    def select(self, name):
        if self.capture:
            self.end_capture()
        if name is not None and name not in render_map.ELEMENTS:
            self.set_status(f"no input called {name!r} (one of {', '.join(render_map.ELEMENTS)})", error=True)
            return
        if name is not None and self.mode == "bare" and name not in render_map.BARE_ELEMENTS:
            self.mode_var.set("full")               # a ghost can only be edited in full mode
            self.mode = "full"
        self.selected = name
        self.show_panel()
        self.redraw_later()

    def set_zoom(self, z):
        self.zoom = max(0.5, min(3.0, z))
        self.redraw_later()
        return "break"

    # ---------- canvas
    def _font(self, px, weight):
        key = (px, weight)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=self.font_family, size=-px, weight=weight)
        return self._fonts[key]

    def state_flags(self):
        st = {}
        for name in render_map.ELEMENTS:
            flags = set()
            if name == self.selected:
                flags.add("sel")
            if name == self.hover:
                flags.add("hover")
            if name in self.lit:
                flags.add("lit")
            if flags:
                st[name] = flags
        return st

    def redraw_later(self):
        if self._redraw_job is None:
            self._redraw_job = self.root.after(25, self.redraw)

    def redraw(self):
        self._redraw_job = None
        c = self.canvas
        cw, ch = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        scene = render_map.build_scene(self.map, self.mode, self.state_flags(), legend=False)
        fit = min((cw - 16) / scene["w"], (ch - 16) / scene["h"])
        s = max(0.2, fit * self.zoom)
        W, H = scene["w"] * s, scene["h"] * s
        ox, oy = max(8, (cw - W) / 2), max(8, (ch - H) / 2)
        c.delete("all")
        for p in scene["prims"]:
            el = p.get("el")
            tags = ("el:" + el,) if el and not p.get("ghost") and self._selectable(el) else ()
            if p["kind"] == "text":
                self._draw_text(p, s, ox, oy, tags)
                continue
            st = self.shape_style[p["cls"]]
            width = max(1.0, st["width"] * s) if st["outline"] else 0
            if p["kind"] == "oval":
                c.create_oval(ox + (p["cx"] - p["rx"]) * s, oy + (p["cy"] - p["ry"]) * s,
                              ox + (p["cx"] + p["rx"]) * s, oy + (p["cy"] + p["ry"]) * s,
                              fill=st["fill"], outline=st["outline"], width=width,
                              dash=st["dash"] or "", tags=tags)
                continue
            pts = [v for x, y in p["pts"] for v in (ox + x * s, oy + y * s)]
            if p["kind"] == "poly":
                c.create_polygon(*pts, fill=st["fill"], outline=st["outline"], width=width,
                                 dash=st["dash"] or "", joinstyle="round", tags=tags)
            else:
                c.create_line(*pts, fill=st["outline"] or st["fill"], width=width or 1,
                              dash=st["dash"] or "", capstyle="round", joinstyle="round", tags=tags)
        c.configure(scrollregion=(0, 0, max(cw, W + 16), max(ch, H + 16)))

    def _draw_text(self, p, s, ox, oy, tags):
        px = max(6, int(round(p["size"] * s)))
        font = self._font(px, p["weight"])
        if p.get("angle"):                       # a turned label (the extender stubs): one run, centred
            self.canvas.create_text(ox + p["x"] * s, oy + p["y"] * s, text="".join(t for t, _ in p["segs"]),
                                    anchor="center", font=font, angle=p["angle"],
                                    fill=self.text_style.get(p["segs"][0][1], self.text_style["row"]), tags=tags)
            return
        widths = [font.measure(t) for t, _ in p["segs"]]
        total = sum(widths)
        x = ox + p["x"] * s
        if p["anchor"] == "end":
            x -= total
        elif p["anchor"] == "middle":
            x -= total / 2
        y = oy + p["y"] * s
        for (text, cls), w in zip(p["segs"], widths):
            self.canvas.create_text(x, y, text=text, anchor="w", font=font,
                                    fill=self.text_style.get(cls, self.text_style["row"]), tags=tags)
            x += w

    def _selectable(self, el):
        el = ENTRY_ELEMENT.get(el, el)
        return el in render_map.ELEMENTS and (self.mode == "full" or el in render_map.BARE_ELEMENTS)

    def _element_at(self, _event):
        for item in self.canvas.find_withtag("current"):
            for tag in self.canvas.gettags(item):
                if tag.startswith("el:"):
                    return ENTRY_ELEMENT.get(tag[3:], tag[3:])
        return None

    def _on_motion(self, event):
        self._set_hover(self._element_at(event))

    def _set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.canvas.configure(cursor="hand2" if name else "")
            self.redraw_later()

    def _on_click(self, event):
        self.canvas.focus_set()
        name = self._element_at(event)
        if name != self.selected:
            self.select(name)

    def _on_wheel(self, event):
        self.set_zoom(self.zoom * (1.1 if event.delta > 0 else 1 / 1.1))
        return "break"

    # ---------- live pad
    def _poll_pad(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "open":
                    self.pad_name = val
                    self.pad_label.configure(text=f"pad: {val} - press an input to find it")
                elif kind == "lit":
                    live = render_map.ELEMENTS if self.mode == "full" else render_map.BARE_ELEMENTS
                    self.lit = {e for e in val if e in live}
                    self.redraw_later()
                elif kind == "closed":
                    self.pad_name, self.lit = None, set()
                    self.pad_label.configure(text="")
                    self.redraw_later()
        except queue.Empty:
            pass
        self.root.after(60, self._poll_pad)

    # ---------- capture
    def begin_capture(self, row):
        if self.capture_row is not None:
            self.capture_row.set_capturing(False)
        self.capture, self.capture_row = ChordCapture(), row
        row.set_capturing(True)
        self.root.bind_all("<KeyPress>", self._cap_press)
        self.root.bind_all("<KeyRelease>", self._cap_release)
        self.root.focus_set()
        self.set_status("capturing: press a key or a chord (modifiers alone count too); Cancel to stop")

    def end_capture(self):
        self.root.unbind_all("<KeyPress>")
        self.root.unbind_all("<KeyRelease>")
        if self.capture_row is not None:
            self.capture_row.set_capturing(False)
        self.capture, self.capture_row = None, None

    def _cap_press(self, event):
        name = keysym_to_name(event.keysym, event.keycode)
        if name is None:
            self.set_status(f"capturing: '{event.keysym}' is not a key the mapper can send - try another", error=True)
            return "break"
        chord = self.capture.press(name)
        if chord:
            self._cap_done(chord)
        else:
            held = "+".join(m for m in MOD_ORDER if m in self.capture.held)
            self.set_status(f"capturing: {held}+... (release to keep just the modifiers)")
        return "break"

    def _cap_release(self, event):
        name = keysym_to_name(event.keysym, event.keycode)
        chord = self.capture.release(name) if name else None
        if chord:
            self._cap_done(chord)
        return "break"

    def _cap_done(self, chord):
        row = self.capture_row
        self.end_capture()
        row.captured(chord)
        self.set_status(f"captured {chord}")

    # ---------- the panel
    def _clear_panel(self):
        if self.capture:
            self.end_capture()
        for w in self.panel.winfo_children():
            w.destroy()
        self.rows = []

    def _slots(self, button):
        return button_slots(self.map, button)

    def show_panel(self):
        self._clear_panel()
        p = self.panel
        name = self.selected
        if name is None:
            self._panel_map(p)
            return
        button = render_map.ELEMENT_BUTTON.get(name, name)
        title = render_map.ELEMENT_TITLE.get(name, name)
        ttk.Label(p, text=title, style="H1.TLabel").pack(anchor="w")
        note = {"Pad": "The touchpad surface and its click.", "LS": "The left stick and its click, L3.",
                "RS": "The right stick and its click, R3."}.get(name)
        if button in render_map.KEYBOARD_EDGE:
            note = render_map.KEYBOARD_EDGE_NOTE
        if button in ds4_dock.RESERVED_BUTTONS:
            note = ds4_dock.RESERVED_BUTTONS[button] + ". " + (note or "")
        elif button == fn_button(self.map):
            note = (note + " " if note else "") + "Held = the Fn layer."
        if note:
            ttk.Label(p, text=note, style="Note.TLabel", wraplength=self.wrap).pack(anchor="w", pady=(0, 6))
        if name == "LS":
            self._stick_section(p, "LS")
            self._button_section(p, "L3", "Click (L3)")
        elif name == "RS":
            self._stick_section(p, "RS")
            self._button_section(p, "R3", "Click (R3)")
        elif name == "Pad":
            self._button_section(p, "Pad", "Click")
            self._pad_section(p)
        else:
            self._button_section(p, button, None)

    def _panel_map(self, p):
        ttk.Label(p, text="Control map", style="H1.TLabel").pack(anchor="w")
        ttk.Label(p, text="Click an input on the picture to edit it. The picture is the dock's face plate "
                          "seen from above, keyboard edge at the top; the labels beside the inputs are "
                          "the map, exactly as tools/render_map.py draws it for the README.",
                  style="Note.TLabel", wraplength=self.wrap).pack(anchor="w", pady=(0, 8))
        f = ttk.Frame(p)
        f.pack(fill="x")
        ttk.Label(f, text="Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        name_var = tk.StringVar(value=self.map.get("name", ""))
        e = tk.Entry(f, textvariable=name_var, width=34)
        e.grid(row=0, column=1, sticky="ew", pady=3)
        f.columnconfigure(1, weight=1)

        def name_changed(*_):
            self.map["name"] = name_var.get()
            self.changed()
        name_var.trace_add("write", name_changed)
        ttk.Label(f, text="Notes").grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=3)
        notes = tk.Text(f, width=34, height=4, wrap="word")
        notes.insert("1.0", self.map.get("notes", ""))
        notes.grid(row=1, column=1, sticky="ew", pady=3)

        def notes_changed(_e=None):
            text = notes.get("1.0", "end-1c")
            if text != self.map.get("notes"):
                self.map["notes"] = text
                self.changed()
        notes.bind("<KeyRelease>", notes_changed)
        fnb = fn_button(self.map)
        ttk.Label(p, text=f"Fn layer: {'held ' + fnb if fnb else 'none'}. Tick “Hold = Fn layer” on any "
                          "button to move it; the button's own bindings make way.",
                  style="Note.TLabel", wraplength=self.wrap).pack(anchor="w", pady=(10, 0))
        ttk.Label(p, text="Bindings: a Key (a name, a chord with +, or chords separated by spaces), "
                          "a Mouse button, an Action, or Nothing. Keys the mapper knows: "
                          + ", ".join(ds4_dock.KEY_NAMES) + ", a-z, 0-9, f1-f12.",
                  style="Note.TLabel", wraplength=self.wrap).pack(anchor="w", pady=(10, 0))

    def _button_section(self, p, button, heading):
        if heading:
            ttk.Label(p, text=heading, style="H2.TLabel").pack(anchor="w", pady=(10, 2))
        f = ttk.Frame(p)
        f.pack(fill="x")
        if button in ds4_dock.RESERVED_BUTTONS:
            ttk.Label(f, text="Nothing can be bound here.", style="Note.TLabel").grid(row=0, column=0, sticky="w")
            return
        is_fn = fn_button(self.map) == button
        fn_var = tk.BooleanVar(value=is_fn)

        def fn_toggled():
            set_fn_button(self.map, button if fn_var.get() else None)
            self.changed()
            self.show_panel()
        ttk.Checkbutton(f, text="Hold = Fn layer (opens layer 2 for every other input)", variable=fn_var,
                        command=fn_toggled).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        if is_fn:
            self.rows.append(BindingRow(self, f, 1, "Tap", ds4_dock.SLOT_KINDS["fn_tap"],
                                        lambda: self.map["fn"]["tap"],
                                        lambda b: self.map["fn"].__setitem__("tap", b),
                                        note="A short press fires Tap; a long one opens the layer and fires nothing."))
            return
        slots = self._slots(button)
        pair = tk.StringVar(value=pair_mode(slots, self.pair_choice.get(button, "press")))

        def pair_changed():
            self.pair_choice[button] = pair.get()      # remembered: the pair is empty right after a switch
            set_pair_mode(self.map, button, pair.get())
            self.changed()
            self.show_panel()
        rf = ttk.Frame(f)
        rf.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Radiobutton(rf, text="Press", value="press", variable=pair, command=pair_changed).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(rf, text="Tap + Hold", value="taphold", variable=pair, command=pair_changed).pack(side="left")
        row = 2
        if pair.get() == "press":
            self.rows.append(BindingRow(self, f, row, "Press", ds4_dock.SLOT_KINDS["press"],
                                        lambda: self._slots(button)["press"],
                                        lambda b: self._slots(button).__setitem__("press", b),
                                        note="Held while the button is down: a key or mouse button is held, an action fires once."))
            row += 2
        else:
            self.rows.append(BindingRow(self, f, row, "Tap", ds4_dock.SLOT_KINDS["tap"],
                                        lambda: self._slots(button)["tap"],
                                        lambda b: self._slots(button).__setitem__("tap", b)))
            self.rows.append(BindingRow(self, f, row + 1, "Hold", ds4_dock.SLOT_KINDS["hold"],
                                        lambda: self._slots(button)["hold"],
                                        lambda b: self._slots(button).__setitem__("hold", b),
                                        note="Tap fires on release before hold_s (tune.json); Hold engages at hold_s "
                                             "and stays down - usually a modifier, so the stick can select or jump."))
            row += 3
        fnb = fn_button(self.map)
        self.rows.append(BindingRow(self, f, row, "Fn + it", ds4_dock.SLOT_KINDS["fn"],
                                    lambda: self._slots(button)["fn"],
                                    lambda b: self._slots(button).__setitem__("fn", b),
                                    note=(f"While {fnb} is held. Fires on press, no tap/hold wait." if fnb
                                          else "No Fn button is set, so this slot can never fire.")))

    def _stick_section(self, p, which):
        f = ttk.Frame(p)
        f.pack(fill="x")
        row = 0
        if which == "RS":
            rs = self.map["right_stick"]
            mode = tk.StringVar(value=rs["mode"])

            def mode_changed():
                rs["mode"] = mode.get()
                self.changed()
                self.show_panel()
            mf = ttk.Frame(f)
            mf.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
            ttk.Radiobutton(mf, text="Keys per direction", value="keys", variable=mode, command=mode_changed).pack(side="left", padx=(0, 10))
            ttk.Radiobutton(mf, text="Cursor", value="cursor", variable=mode, command=mode_changed).pack(side="left")
            row += 1
            if rs["mode"] == "cursor":
                ttk.Label(f, text="The stick moves the cursor (the old coarse pointer); the tables below are ignored.",
                          style="Note.TLabel", wraplength=self.wrap).grid(row=row, column=0, columnspan=3, sticky="w")
                return
            ttk.Label(f, text="Repeats faster the further it is pushed. Fn + a direction fires once per push.",
                      style="Note.TLabel", wraplength=self.wrap).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
            row += 1
            tables = (("Alone", rs["keys"], ds4_dock.SLOT_KINDS["tap"], None),
                      ("Fn + it", rs["fn"], ds4_dock.SLOT_KINDS["tap"], None))
            key_spec = True
        else:
            ls = self.map["left_stick"]
            ttk.Label(f, text="A flick fires its chord once; the stick must return to centre before the next.",
                      style="Note.TLabel", wraplength=self.wrap).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
            row += 1
            tables = (("Flick", ls["flick"], ds4_dock.SLOT_KINDS["tap"], None),
                      ("Fn + flick", ls["fn"], ds4_dock.SLOT_KINDS["left_stick_fn"], ("cursor_centre",)))
            key_spec = None     # flick = key specs, fn = bindings
        for ti, (heading, table, kinds, actions) in enumerate(tables):
            ttk.Label(f, text=heading, style="H2.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 2))
            row += 1
            specs = key_spec if key_spec is not None else (ti == 0)
            for d in ds4_dock.DIRECTIONS:
                label = f"{render_map.ARROW[d]}  {DIR_WORD[d]}"
                if specs:
                    self.rows.append(BindingRow(self, f, row, label, kinds,
                                                (lambda t=table, d=d: {"key": t[d]} if t[d] else None),
                                                (lambda b, t=table, d=d: t.__setitem__(d, b["key"] if b else None))))
                else:
                    self.rows.append(BindingRow(self, f, row, label, kinds,
                                                (lambda t=table, d=d: t[d]),
                                                (lambda b, t=table, d=d: t.__setitem__(d, b)), actions=actions))
                row += 1

    def _pad_section(self, p):
        ttk.Label(p, text="Gestures", style="H2.TLabel").pack(anchor="w", pady=(10, 2))
        f = ttk.Frame(p)
        f.pack(fill="x")
        tp = self.map["touchpad"]
        one, two = tk.BooleanVar(value=tp["one_finger"] == "cursor"), tk.BooleanVar(value=tp["two_finger"] == "scroll")

        def moves():
            tp["one_finger"] = "cursor" if one.get() else None
            tp["two_finger"] = "scroll" if two.get() else None
            self.changed()
        ttk.Checkbutton(f, text="One finger moves the cursor", variable=one, command=moves).grid(row=0, column=0, columnspan=3, sticky="w")
        self.rows.append(BindingRow(self, f, 1, "One-finger tap", ds4_dock.SLOT_KINDS["touchpad_tap"],
                                    lambda: tp["one_finger_tap"], lambda b: tp.__setitem__("one_finger_tap", b)))
        ttk.Checkbutton(f, text="Two fingers scroll", variable=two, command=moves).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.rows.append(BindingRow(self, f, 4, "Two-finger tap", ds4_dock.SLOT_KINDS["touchpad_tap"],
                                    lambda: tp["two_finger_tap"], lambda b: tp.__setitem__("two_finger_tap", b),
                                    note="Taps are contacts shorter than tap_max_s that moved less than tap_max_move (tune.json)."))


def run_gui(args):
    global tk, ttk, tkfont, filedialog, messagebox
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter import font as tkfont
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)     # crisp on HiDPI with Tk 8.6; Tk 9 already is
        except Exception:   # noqa: BLE001
            pass
    root = tk.Tk()
    root.withdraw()
    try:
        scale = float(root.tk.call("tk", "scaling")) / (96 / 72)
    except Exception:   # noqa: BLE001
        scale = 1.0
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(int(sw * 0.82), int(1400 * scale)), min(int(sh * 0.84), int(860 * scale))
    root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
    root.minsize(int(900 * scale), int(560 * scale))
    path = args.mapping
    if path is None:
        default = os.path.join(REPO, "mapping.json")
        path = default if os.path.exists(default) else None
    editor = Editor(root, path, mode=args.mode, select=args.select)
    root.deiconify()
    if path is None:
        editor.set_status("no mapping.json found next to ds4_dock.py - editing the built-in map; Save as... writes a file")
    root.mainloop()


# ------------------------------------------------------------------ self-test (no window)

def selftest():
    import json
    import xml.etree.ElementTree as ET

    # keysyms -> the mapper's names
    assert keysym_to_name("Control_L") == "ctrl" and keysym_to_name("Win_L") == "super"
    assert keysym_to_name("Super_R") == "super" and keysym_to_name("Alt_R") == "alt"
    assert keysym_to_name("Return") == "enter" and keysym_to_name("KP_Enter") == "enter"
    assert keysym_to_name("Escape") == "esc" and keysym_to_name("Prior") == "pageup"
    assert keysym_to_name("Left") == "left" and keysym_to_name("KP_Left") == "left"
    assert keysym_to_name("F5") == "f5" and keysym_to_name("F13") is None
    assert keysym_to_name("a") == "a" and keysym_to_name("A") == "a" and keysym_to_name("7") == "7"
    assert keysym_to_name("KP_7") == "7"
    assert keysym_to_name("exclam", 0x31, system="Windows") == "1"     # Shift+1 on Windows: the VK code
    assert keysym_to_name("exclam", 10, system="Linux") == "1"         # Shift+1 on X11: the evdev keycode
    assert keysym_to_name("exclam", system="Linux") == "1"             # and with no keycode at all, the keysym
    assert keysym_to_name("exclam", 18, system="Darwin") == "1"        # macOS: keycodes unknown, the keysym
    assert keysym_to_name("ampersand", 15, system="Linux") == "6"      # German Shift+6: the keycode decides
    assert keysym_to_name("quotedbl", 11, system="Linux") == "2"       # German Shift+2
    assert keysym_to_name("hebrew_shin", 38, system="Linux") == "a"    # a non-Latin layout: the key's letter
    assert keysym_to_name("hebrew_shin", 0x41, system="Windows") == "a"
    assert keysym_to_name("??", 0xB3, system="Windows") == "media_play_pause"
    assert keysym_to_name("??", 0xB3, system="Linux") is None          # nothing invents a name on X11
    assert keysym_to_name("Meta_L", system="Linux") == "alt"           # X11: Alt pressed with Shift held
    assert keysym_to_name("Meta_R", system="Windows") == "alt"
    assert keysym_to_name("Meta_L", system="Darwin") is None           # Command is not Alt
    assert keysym_to_name("ISO_Level3_Shift") is None                  # AltGr is not Alt
    assert keysym_to_name("Caps_Lock") is None and keysym_to_name("eacute") is None
    for keysym in KEYSYM:
        ds4_dock.validate_key_spec(keysym_to_name(keysym))              # every name is one the mapper knows
    for name in list(X11_KEYCODE.values()) + list(SHIFTED_DIGIT.values()):
        ds4_dock.validate_key_spec(name)
    print("keysyms              ok")

    # chords
    c = ChordCapture()
    assert c.press("shift") is None and c.press("ctrl") is None
    assert c.press("tab") == "ctrl+shift+tab"
    c = ChordCapture()
    assert c.press("shift") is None and c.release("shift") == "shift"  # a modifier alone (a Hold slot)
    c = ChordCapture()
    c.press("ctrl")
    c.press("shift")
    assert c.release("ctrl") is None and c.release("shift") == "ctrl+shift"
    assert ChordCapture().press("f5") == "f5"
    assert ChordCapture().release("tab") is None
    assert compose_chord({"super", "shift"}, "s") == "shift+super+s"
    assert append_chord("ctrl+k", "ctrl+left") == "ctrl+k ctrl+left"
    assert append_chord("", "a") == "a" and append_chord(None, "a") == "a"
    for spec in ("ctrl+shift+tab", "shift", "ctrl+k ctrl+left", "shift+super+s"):
        assert ds4_dock.validate_key_spec(spec) == spec
    print("chord capture        ok")

    # model edits, validated by the mapper's own rules
    m = fresh_map()
    assert m == ds4_dock.normalise_mapping(ds4_dock.default_mapping())
    button_slots(m, "Share")["press"] = {"key": "ctrl+bogus"}
    _, err = validate(m)
    assert err and "buttons.Share.press.key" in err and "bogus" in err, err
    set_pair_mode(m, "Share", "press")
    assert m["buttons"]["Share"]["tap"] is None and m["buttons"]["Share"]["hold"] is None
    _, err = validate(m)
    assert err and "not both" not in err                     # only the bad key is left to complain about
    button_slots(m, "Share")["press"] = {"key": "ctrl+c"}
    assert validate(m)[1] is None
    set_pair_mode(m, "Share", "taphold")
    assert m["buttons"]["Share"]["press"] is None
    button_slots(m, "Share")["tap"] = {"key": "ctrl+c"}
    _, err = validate(m)
    assert err and "hold" in err                             # tap without hold is refused
    button_slots(m, "Share")["hold"] = {"key": "shift"}
    assert validate(m)[1] is None
    assert pair_mode(m["buttons"]["Share"]) == "taphold" and pair_mode(m["buttons"]["R3"]) == "press"
    assert pair_mode(None) == "press"
    # the Press / Tap + Hold radio: switching a Press button to Tap + Hold empties the pair, and
    # the rebuilt panel must then follow the user's choice, not fall back to Press
    m2 = fresh_map()
    set_pair_mode(m2, "R3", "taphold")
    assert m2["buttons"]["R3"] == {"press": None, "tap": None, "hold": None, "fn": {"key": "super+h"}}
    assert pair_mode(m2["buttons"]["R3"], "taphold") == "taphold"      # what the panel derives
    assert pair_mode(m2["buttons"]["R3"]) == "press"                   # no choice: an empty pair is Press
    assert pair_mode(None, "taphold") == "taphold"
    assert pair_mode(fresh_map()["buttons"]["Share"], "press") == "taphold"    # bindings beat the choice
    assert pair_mode(fresh_map()["buttons"]["R3"], "taphold") == "press"
    assert validate(m2)[1] is None                                     # an empty pair is just unbound
    m2["buttons"]["R3"]["tap"], m2["buttons"]["R3"]["hold"] = {"key": "ctrl+c"}, {"key": "shift"}
    assert validate(m2)[1] is None
    # a touchpad tap takes a mouse button or nothing; the panel must offer both
    assert ds4_dock.SLOT_KINDS["touchpad_tap"] == ("mouse",)
    m2["touchpad"]["one_finger_tap"] = None
    assert validate(m2)[1] is None
    set_fn_button(m, "R3")
    assert fn_button(m) == "R3" and m["buttons"]["R3"] is None and m["fn"]["tap"] == {"key": "esc"}
    assert validate(m)[1] is None
    button_slots(m, "L3")["press"] = {"key": "enter"}        # the old Fn button can be bound again
    assert validate(m)[1] is None
    set_fn_button(m, None)
    assert m["fn"] is None and validate(m)[1] is None
    button_slots(m, "L2")["press"] = {"key": "a"}
    _, err = validate(m)
    assert err and "trigger" in err, err
    m["buttons"]["L2"] = None
    m["right_stick"]["mode"] = "cursor"
    m["left_stick"]["fn"]["W"] = {"action": "cursor_centre"}
    m["touchpad"]["one_finger"] = None
    assert validate(m)[1] is None
    assert bound_count(fresh_map(), "bare") == (5, 5)
    assert bound_count(fresh_map(), "full") == (15, 18)      # L2, R2, PS unbound
    empty = ds4_dock.normalise_mapping({})
    assert bound_count(empty, "bare") == (0, 5)
    print("model edits          ok")

    # round trip: edit -> save in the mapper's layout -> load_mapping -> the same map
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "edited.json")
        save_map(m, path)
        back = ds4_dock.load_mapping(path)
        assert back == ds4_dock.normalise_mapping(m)
        assert back["right_stick"]["mode"] == "cursor" and back["fn"] is None
        assert back["buttons"]["Share"] == {"press": None, "tap": {"key": "ctrl+c"}, "hold": {"key": "shift"}, "fn": {"key": "super+shift+s"}}
        save_map(fresh_map(), path)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert text == ds4_dock.format_mapping(fresh_map()) and "\r" not in text
        assert ds4_dock.load_mapping(path) == fresh_map()
        assert json.loads(text)["schema"] == ds4_dock.MAP_SCHEMA
        try:
            save_map({"schema": 1, "buttons": {"L2": {"press": {"key": "a"}}}}, path)
        except ValueError as ex:
            assert "trigger" in str(ex)
        else:
            raise AssertionError("an invalid map was saved")
        shipped = os.path.join(REPO, "mapping.json")
        if os.path.exists(shipped):
            assert ds4_dock.load_mapping(shipped) == ds4_dock.normalise_mapping(ds4_dock.load_mapping(shipped))
    print("save / load          ok")

    # the drawing covers the mapper: every button has exactly one element with one main shape,
    # and nothing is drawn that the mapper has no name for - a new button cannot be undrawable
    drawn = {render_map.ELEMENT_BUTTON.get(e, e) for e in render_map.ELEMENTS}
    assert drawn == set(ds4_dock.BUTTONS), drawn ^ set(ds4_dock.BUTTONS)
    assert len(render_map.ELEMENTS) == len(set(render_map.ELEMENTS)) == len(ds4_dock.BUTTONS)
    for name in render_map.ELEMENTS:
        assert sum(1 for p in render_map._ELEMENTS[name]["shapes"] if p.get("main")) == 1, name
    assert set(render_map.KEYBOARD_EDGE) <= set(render_map.ELEMENTS)
    assert set(render_map.BARE_ELEMENTS) <= set(render_map.ELEMENTS)
    # the drawing: well-formed SVG, every input present, the bindings legible
    for mode in render_map.MODES:
        svg = render_map.render_svg(fresh_map(), mode)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" and root.get("viewBox")
        texts = " ".join("".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text"))
        for needle in ("Touchpad", "Left stick", "Right stick", "Share", "Options", "Ctrl+C", "Ctrl+V",
                       "Suspend injection", "Centre cursor", "hold = Fn layer", "Win+H", "Ctrl+K Ctrl+Left",
                       "keyboard edge", "user's edge", "extender 60 mm", "extenders 115 + 115 mm"):
            assert needle in texts, (mode, needle)
        if mode == "full":
            for needle in ("D-pad", "Face buttons", "L1", "R2", "reserved", "PS", "unbound", "Play/Pause",
                           render_map.KEYBOARD_EDGE_ROW):
                assert needle in texts, needle
        else:
            assert "not on this board" in texts and "D-pad" not in texts
            assert "unreachable" not in texts
        scene = render_map.build_scene(fresh_map(), mode)
        els = {p.get("el") for p in scene["prims"]}
        assert set(render_map.ELEMENTS) <= els
        assert scene["w"] > 0 and scene["h"] > 0
        for p in scene["prims"]:                 # every class the drawing uses has a style in both backends
            if p["kind"] == "text":
                assert all(c in render_map.TEXT for _, c in p["segs"]), p
            else:
                assert p["cls"] in render_map.STYLE, p
        # the touchpad's leader comes in over the keyboard edge, a stick's straight in from the side
        lead = {p["el"]: p["pts"] for p in scene["prims"] if p["kind"] == "line" and p["cls"] == "leader"}
        plate_top = render_map.mm_to_px(0, render_map.PLATE_Y1)[1]
        assert lead["Pad"][1][1] == lead["Pad"][2][1] < plate_top and lead["Pad"][2][0] == lead["Pad"][3][0]
        assert lead["LS"][2][1] == lead["LS"][3][1] == render_map.mm_to_px(*render_map.STICKS["LS"])[1]
        assert "<script" not in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")
    # odd maps draw too: nothing bound, no Fn layer, cursor mode, a mid-edit invalid spec
    render_map.build_scene(ds4_dock.normalise_mapping({}), "full")
    nofn = fresh_map()
    set_fn_button(nofn, None)
    render_map.render_svg(nofn, "bare")
    cur = fresh_map()
    cur["right_stick"]["mode"] = "cursor"
    assert "moves the cursor" in render_map.render_svg(cur, "bare")
    bad = fresh_map()
    bad["buttons"]["Share"]["tap"] = {"key": "ctrl+"}
    render_map.build_scene(bad, "bare")          # the canvas must still draw while a spec is being typed
    assert render_map.pretty_key("ctrl+k ctrl+left") == "Ctrl+K Ctrl+Left"
    assert render_map.pretty_key("super+shift+s") == "Win+Shift+S" and render_map.pretty_key("f5") == "F5"
    assert render_map.pretty_binding({"mouse": "middle"}) == "Middle click"
    assert render_map.pretty_binding({"action": "suspend"}) == "Suspend injection"
    assert render_map.pretty_binding(None) is None
    # selection / hover / lit flags change only the classes they should
    sel = render_map.build_scene(fresh_map(), "bare", {"Share": {"sel", "lit"}})
    assert any(p["cls"] == "sel-outline" and p.get("el") == "Share" for p in sel["prims"])
    assert any(p["cls"] == "input-lit" and p.get("el") == "Share" for p in sel["prims"])
    ghost = render_map.build_scene(fresh_map(), "bare", {"Cross": {"sel"}})
    assert not any(p["cls"] == "sel-outline" for p in ghost["prims"])      # a ghost cannot be selected
    assert any(p["cls"] == "tab-ghost" and p.get("el") == "L1" for p in ghost["prims"])   # bare: the tabs are ghosts
    tab = render_map.build_scene(fresh_map(), "full", {"L1": {"sel", "hover"}})         # full: selectable
    assert any(p["cls"] == "sel-outline" and p.get("el") == "L1" for p in tab["prims"])
    assert any(p["cls"] == "input-hover" and p.get("el") == "L1" for p in tab["prims"])
    assert render_map.KEYBOARD_EDGE_NOTE.startswith("This edge faces the keyboard")
    shapes, texts = tk_styles()
    assert shapes["input"]["fill"].startswith("#") and shapes["input-ghost"]["dash"] == (4, 3)
    assert shapes["tab"]["dash"] == (5, 3) and shapes["ext"]["outline"].startswith("#") and "label" in texts
    print("render_map           ok   bare and full SVG well-formed")

    assert "tkinter" not in sys.modules, "the selftest must not touch tkinter"
    print("editor selftest passed")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mapping", nargs="?", help="control map to edit (default: mapping.json next to ds4_dock.py)")
    ap.add_argument("--mode", choices=render_map.MODES, default="bare",
                    help="start in bare (five buttons, default) or full mode")
    ap.add_argument("--select", metavar="INPUT", help="start with this input selected, e.g. Share, RS, dpad_N")
    ap.add_argument("--selftest", action="store_true", help="run the logic tests without a window and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    run_gui(args)


if __name__ == "__main__":
    main()
