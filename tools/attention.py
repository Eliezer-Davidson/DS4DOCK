#!/usr/bin/env python3
"""Set the attention state the mapper's light bar shows: `attention.py waiting` or `attention.py idle`.

Writes the one word to attention_state.txt next to ds4_dock.py, which the mapper polls every
0.25 s: `waiting` turns the light bar orange, `idle` hands it back to the normal policy. Anything
that can run a command can drive it - the documented example is Claude Code's hooks (Notification
and Stop write `waiting`, UserPromptSubmit writes `idle`; see the README). On Windows call it with
pythonw.exe so no console window flashes. Exits 2 on a bad argument and never raises.
"""
import os
import sys

WORDS = ("waiting", "idle")


def main(argv):
    word = argv[1].strip().lower() if len(argv) > 1 else ""
    if word not in WORDS:
        sys.stderr.write("usage: attention.py waiting|idle\n")
        return 2
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "attention_state.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(word + "\n")
    except OSError as ex:
        sys.stderr.write(f"attention.py: could not write {path}: {ex}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
