# Runs the minimap/sprint helper alongside Rift Apart: waits for RiftApart.exe, starts
# src/minimap.py once the game has been up a few seconds, restarts it if it dies while
# the game is running, and stops it when the game exits. Started at logon by the
# shortcut that Install-Autostart.ps1 puts in the Startup folder.
# Extra arguments (e.g. --debug) are passed on to minimap.py; with --debug its output
# goes to research/minimap.stdout.log / .stderr.log, otherwise nothing is written.
import os, subprocess, sys, time
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
GAME = "riftapart.exe"
PYTHONW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
ARGS = sys.argv[1:]
DEBUG = "--debug" in ARGS
STARTUP_DELAY = 10      # let the game finish loading its executable/modules first
RESTART_DELAY = 5       # between restarts if the helper keeps exiting


def find_game():
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == GAME:
            return p
    return None


def existing_helpers():
    """minimap.py processes started some other way (e.g. by hand); never start a second."""
    out = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower().startswith("python") and \
                    any(a.endswith("minimap.py") for a in (p.info["cmdline"] or [])):
                out.append(p)
        except (psutil.Error, TypeError):
            pass
    return out


def start_helper():
    out = err = subprocess.DEVNULL
    if DEBUG:
        research = os.path.join(HERE, "research")
        os.makedirs(research, exist_ok=True)
        out = open(os.path.join(research, "minimap.stdout.log"), "w")
        err = open(os.path.join(research, "minimap.stderr.log"), "w")
    return subprocess.Popen([PYTHONW, "-u", "minimap.py", *ARGS], cwd=SRC, stdout=out, stderr=err,
                            creationflags=subprocess.CREATE_NO_WINDOW)


def stop(proc):
    try:
        proc.terminate()
        proc.wait(5)
    except (psutil.Error, subprocess.TimeoutExpired, OSError):
        pass


def note(message):
    """--debug only: why the launcher had to recover."""
    if DEBUG:
        with open(os.path.join(HERE, "research", "autostart.log"), "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")


def main():
    while True:
        try:
            run()
        except Exception as exc:          # never let the launcher itself die
            import traceback
            note("launcher error: " + "".join(traceback.format_exception(exc)))
            time.sleep(5)


def run():
    helper = None
    game_pid = None
    while True:
        game = find_game()
        if game is None:
            if helper is not None:
                stop(helper)
                helper = None
            game_pid = None
            time.sleep(3)
            continue
        if game.pid != game_pid:                    # game (re)launched
            if helper is not None:
                stop(helper)
                helper = None
            game_pid = game.pid
            time.sleep(STARTUP_DELAY)
            continue
        if helper is None or helper.poll() is not None:
            if helper is not None:
                time.sleep(RESTART_DELAY)           # it exited (crash/hang); try again
            if not existing_helpers():
                helper = start_helper()
            else:
                helper = None                       # someone else's copy is running
        time.sleep(2)


if __name__ == "__main__":
    main()
