# Bastion Ultrawide - Install

The entire fix is a binary patch to `Bastion.exe` (including borderless windowed mode - no
launcher `.bat` or Steam launch options needed anymore). You apply it by running the patcher
in [`../src`](../src) against your `Bastion.exe`.

## Step 1 - Patch the exe

Needs the [.NET 8 SDK](https://dotnet.microsoft.com). Open PowerShell in the repo's
`Bastion/src` folder and run:

```powershell
dotnet run -- --exe "<path to your Bastion.exe>" --width 5120 --height 1440
```

Examples:

```powershell
# Steam:
dotnet run -- --exe "C:\Program Files (x86)\Steam\steamapps\common\Bastion\Bastion.exe" --width 5120 --height 1440
# Other install:
dotnet run -- --exe "C:\Games\Bastion\Bastion.exe" --width 3440 --height 1440
```

- Change `--width` / `--height` for a different ultrawide resolution.
- Safe to re-run: it restores from a stock backup each time before patching.
- A stock backup (`Bastion.exe.orig-backup`) is created next to your exe on first run.
- Add `--keep-fullscreen` if you do NOT want borderless windowed baked in.

## Step 2 - Play

1. Launch the game normally (from Steam, or by running `Bastion.exe`). It starts in
   borderless windowed mode automatically.
2. In-game: **Options > Video** > set resolution to 5120x1440 (it replaces the old
   1920x1200 entry).

Result: full-width gameplay, correctly-sized HUD/menus/subtitles centered in a 16:9 band,
full-width parallax backdrop, borderless windowed.

## Notes

- Steam copies: saves work normally via Steam Cloud (the patch does NOT touch the save
  path). Don't run Steam's "Verify integrity of game files" or it will revert the patched
  exe (just re-run the patcher if that happens).
- If anything looks wrong, restore `Bastion.exe.orig-backup` over `Bastion.exe` and re-run
  the patcher. See [../notes.md](../notes.md) for full details.
