"""DS4 dock autostart (Windows): start the mapper whenever the pad is plugged in.

Runs hidden at logon from the Startup-folder shortcut "DS4 dock autostart". Every 2 s it checks
for the DualShock 4 on USB. When the pad is present and no mapper is running, it starts
ds4_dock.py with no console window. If the mapper exits (unplug, USB dropout, crash), it is
started again as soon as the pad is back. The mapper itself is unchanged.

  pause:   create a file named autostart.off next to this script (the mapper is stopped too);
           delete it to resume
  stop:    end "pythonw.exe" running ds4_autostart.pyw in Task Manager
  remove:  delete the Startup shortcut (Win+R, shell:startup)
  log:     autostart.log next to this script. The mapper's stderr is appended to it too - a
           startup failure's message, an uncaught error's traceback - while its stdout (the
           dashboard and the control-map / tune-file notices) is discarded
"""
import ctypes
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
MAPPER = os.path.join(HERE, "ds4_dock.py")
LOG = os.path.join(HERE, "autostart.log")
OFF = os.path.join(HERE, "autostart.off")
VID, PIDS = 0x054C, (0x09CC, 0x05C4)
POLL_S = 2.0
QUICK_EXIT_S = 10       # a mapper that dies this fast is not retried for BACKOFF_S
BACKOFF_S = 30
CREATE_NO_WINDOW = 0x08000000


def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 512 * 1024:      # keep the log small
            with open(LOG, "rb") as f:
                tail = f.read()[-128 * 1024:]
            with open(LOG, "wb") as f:
                f.write(tail)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def single_instance():
    """A named mutex, so a second copy of this launcher exits at once."""
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW(None, False, "Local\\ds4_dock_autostart")
    return k32.GetLastError() != 183            # ERROR_ALREADY_EXISTS


def pad_present(hid):
    try:
        return any(hid.enumerate(VID, pid) for pid in PIDS)
    except Exception:                            # noqa: BLE001
        return False


def other_mapper_running():
    """A mapper started by hand (with its console) - don't run a second one on top of it."""
    cmd = ("(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "Where-Object { $_.CommandLine -like '*ds4_dock.py*' }).Count")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                             capture_output=True, text=True, timeout=30,
                             creationflags=CREATE_NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return out not in ("", "0")


def start_mapper():
    err = open(LOG, "a", encoding="utf-8")
    p = subprocess.Popen([PY, MAPPER], cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=err, creationflags=CREATE_NO_WINDOW)
    err.close()
    return p


def main():
    if not single_instance():
        return
    import hid
    log("autostart running")
    child, started, wait_until, was_present = None, 0.0, 0.0, None
    while True:
        now = time.time()
        present = pad_present(hid)
        if present != was_present:
            log("pad plugged in" if present else "pad not connected")
            was_present = present
        if child is not None and child.poll() is not None:
            ran = now - started
            log(f"mapper exited (code {child.returncode}) after {ran:.0f} s")
            child = None
            if ran < QUICK_EXIT_S:
                wait_until = now + BACKOFF_S
                log(f"exited quickly - next try in {BACKOFF_S} s")
        if os.path.exists(OFF):
            if child is not None:
                child.terminate()
                log("autostart.off found - mapper stopped, paused")
                child = None
        elif present and child is None and now >= wait_until:
            if other_mapper_running():
                wait_until = now + 15                # check again later; the hand-started one owns the pad
            else:
                child = start_mapper()
                started = now
                log(f"mapper started (pid {child.pid})")
        time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:                      # noqa: BLE001
        log(f"autostart crashed: {ex!r}")
        raise
