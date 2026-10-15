#!/usr/bin/env python3
"""Apply the Eden (Android) settings used with the Smash Ultimate Vert+ camera, over adb.

What it sets (see ../notes.md "Input latency" for why):

  global  config/config.ini
    use_vsync=1                          Mailbox (Eden's default FIFO queues frames)
    async_presentation=false
    use_asynchronous_shaders=true        less shader-compile stutter
    use_asynchronous_gpu_emulation=...   --async-gpu on|off (default: off, lowest latency)
  Smash only  config/custom/01006A800016E000.ini
    aspect_ratio=4                       Stretch to window (required by the camera patch)

Every file is backed up next to the original (*.bak-<timestamp>) before it is changed,
and Eden is force-stopped first so it can't overwrite the change on exit.

Usage:
  python3 eden_settings.py --dry-run
  python3 eden_settings.py [--serial 192.168.1.166:5555] [--async-gpu on|off]
  python3 eden_settings.py --oppo-refresh-high     # also set ColorOS screen refresh to "High"
"""
import argparse
import re
import subprocess
import sys
import tempfile
import time

PKG = "dev.eden.eden_emulator"
ROOT = f"/sdcard/Android/data/{PKG}/files/config"
GLOBAL_INI = f"{ROOT}/config.ini"
SMASH_INI = f"{ROOT}/custom/01006A800016E000.ini"


def adb(args, serial, check=True, capture=True):
    cmd = ["adb"] + (["-s", serial] if serial else []) + args
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        sys.exit(f"adb failed: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout


def set_key(text, key, value, per_game=False):
    """Set a Qt-ini key the way Eden writes it (key\\default / key\\use_global + key)."""
    changed = []
    flag = "use_global" if per_game else "default"
    pat_flag = re.compile(rf"(?m)^{re.escape(key)}\\{flag}=\w+$")
    pat_val = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    current = pat_val.search(text)
    in_use = not per_game or not re.search(rf"(?m)^{re.escape(key)}\\use_global=true$", text)
    if current and current.group(0) == f"{key}={value}" and in_use:
        return text, changed  # already set; leave Eden's own default flags alone
    if current:
        text = pat_flag.sub(f"{key}\\\\{flag}=false", text)
        if per_game and not re.search(rf"(?m)^{re.escape(key)}\\default=", text):
            text = pat_val.sub(f"{key}\\\\default=false\n{key}={value}", text, count=1)
        else:
            text = re.sub(rf"(?m)^{re.escape(key)}\\default=\w+$", f"{key}\\\\default=false", text)
            text = pat_val.sub(f"{key}={value}", text)
        changed.append(key)
    elif pat_flag.search(text):  # per-game file with only use_global=true present
        text = pat_flag.sub(f"{key}\\\\{flag}=false\n{key}\\\\default=false\n{key}={value}", text)
        changed.append(key)
    else:
        raise KeyError(f"{key} not found - open the game's settings in Eden once, then retry")
    return text, changed


def edit_remote(path, edits, serial, dry_run, per_game=False):
    with tempfile.TemporaryDirectory() as tmp:
        local = f"{tmp}/f.ini"
        adb(["pull", path, local], serial)
        text = open(local, encoding="utf-8").read()
        new = text
        for k, v in edits.items():
            new, _ = set_key(new, k, v, per_game)
        diff = [l for l in new.splitlines() if l not in text.splitlines()]
        print(f"{path}:")
        for l in diff or ["(already set)"]:
            print(f"  {l}")
        if dry_run or new == text:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        adb(["shell", f"cp '{path}' '{path}.bak-{stamp}'"], serial)
        open(local, "w", encoding="utf-8", newline="\n").write(new)
        adb(["push", local, path], serial)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", help="adb device serial (default: the only connected device)")
    ap.add_argument("--async-gpu", choices=["on", "off"], default="off")
    ap.add_argument("--oppo-refresh-high", action="store_true",
                    help="ColorOS only: Settings > Display > Screen refresh rate = High")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.dry_run:
        adb(["shell", "am", "force-stop", PKG], a.serial)
    edit_remote(GLOBAL_INI, {
        "use_vsync": "1",
        "async_presentation": "false",
        "use_asynchronous_shaders": "true",
        "use_asynchronous_gpu_emulation": "true" if a.async_gpu == "on" else "false",
    }, a.serial, a.dry_run)
    edit_remote(SMASH_INI, {"aspect_ratio": "4"}, a.serial, a.dry_run, per_game=True)

    if a.oppo_refresh_high:
        # Observed on ColorOS 16 (OPPO Find N6): 0 = Auto select, 3 = High.
        print("ColorOS: secure oplus_customize_screen_refresh_rate = 3 (High)")
        if not a.dry_run:
            adb(["shell", "settings", "put", "secure", "oplus_customize_screen_refresh_rate", "3"], a.serial)
    print("dry run - nothing changed" if a.dry_run else "done - launch Smash from Eden")


if __name__ == "__main__":
    main()
