# AGENTS.md - working on ultrawide-game-patches

Guide for anyone (people or AI coding agents) adding or changing a fix in this repo.
Read it before touching a game folder. The README is the user-facing overview; this file
is the rulebook.

## What this repo is

Fixes that make games render correctly at ultrawide resolutions (21:9, 32:9): full-width
image, correct field of view, correctly sized and placed UI. The owner plays at
5120x1440 (32:9), which is the default target and the one every fix is tested at.

## Rules

### 1. Silent by default (logging)
A fix must not write anything at runtime unless the user turns on its debug switch.

- **Default off.** No log lines, log files, console output, breadcrumbs or diagnostic
  probes in the shipped build unless debug logging is enabled. That includes error
  messages: an exception that repeats every frame must not flood a log.
- **One switch per fix**, in whatever the fix uses for settings: a config-file key
  (`Debug = true` in Fatal Claw's `config.lua`, the reference implementation), a loader
  preference (e.g. a `DebugLogging` entry in `MelonPreferences.cfg`) or a command-line
  flag. Name it in the game's `INSTALL.txt` (CONFIGURATION and TROUBLESHOOTING) and
  `notes.md`.
- **Gate at the source.** Route every message through one helper that returns
  immediately when debug is off, and skip diagnostic-only work (probes, object scans made
  just to print them) entirely.
- **Development diagnostics** are fine while iterating, but before committing they must be
  removed or sit behind the debug switch.
- **One-shot patchers** (like Bastion's) may print progress to the console while they run,
  but must not write log files. Nothing may be injected into a game that logs.
- Third-party loaders (UE4SS, MelonLoader) keep their own logs. That's outside our
  control; say so in the notes.
- **Existing fixes:** Gecko Gods predates this rule and still logs (init, scene, FOV
  messages and a per-scene probe in MelonLoader's log). Don't change it on the side;
  bring it in line only as its own task, when the owner can retest it in-game. Bastion
  already complies (its patcher only prints progress to the console).

### 2. Configurable resolution
Default to 5120x1440 (32:9), but take the user's resolution or aspect ratio as a setting
(config file, preference or patcher argument) so 21:9 works too. Derive every number from
the aspect ratio (FOV, overlay sizes); never hard-code 32:9-only constants. Document example
values for 21:9 and 32:9, and say plainly which aspect ratios were actually tested in-game.

### 3. Per-game folder layout
```
<Game>/
  dist/      Drop-in files for the game folder + INSTALL.txt
  src/       Source needed to produce the fix (patcher / mod project). Left out when the
             fix is a script with no build step; dist/ is then the source.
  notes.md   Technical write-up
```
- Folder names have no spaces (`GeckoGods`, `FatalClaw`).
- `INSTALL.txt` is plain text: steps to install (including where to get the exact tested
  version of any loader such as UE4SS or MelonLoader), configuration, uninstall,
  troubleshooting.
- `notes.md` follows the existing ones: the game, the problem, the fix (every change and
  why), lessons, configuration, install pointers, what's not covered, and a reusable
  discovery method.
- Add the game to the README: a row in the Game List table and a
  "### <Game> - what's fixed" section with bullets, in the same style as the others.

### 4. What may be committed
- Never commit game binaries, game assets or backups of them (`.gitignore` blocks `*.exe`,
  `*.dll`, `*.orig-backup` and similar). Ship patchers that the user runs on their own copy.
- Our own built mods may ship in `dist/` (add a `.gitignore` exception for the file).
- Don't commit third-party loaders (UE4SS, MelonLoader); link to their releases instead.

### 5. Writing style
- Use a normal hyphen "-" in docs, never an em dash.
- Be specific about versions and builds that were tested (engine version, loader build,
  game build date).

### 6. Commits
- Don't add AI co-author or attribution trailers (`Co-Authored-By: ...`, "Generated
  with ...") to commits, including amends and force-pushes.
- The owner pushes straight to `main`; only commit or push when asked.

## Testing with the owner (live games)
- Back up the game's save files before installing anything.
- After each fix, relaunch the game yourself (check it isn't already running first). The
  owner closes it before reporting results, so never kill an instance they may be playing.
- Prefer evidence over guesses: when a visual bug is hard to describe, add a per-call trace
  behind the debug switch rather than periodic sampling, and test bookkeeping logic
  offline against recorded values before shipping it.
