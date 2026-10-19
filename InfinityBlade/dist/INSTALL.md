# Infinity Blade II & III (Android port) - full screen on foldables and tablets

Builds of the open-source Infinity Blade II and III Android port
([jelqedagain/ib-2-3-android](https://github.com/jelqedagain/ib-2-3-android), MIT) with one fix: on
screens squarer than 3:2 (foldable inner screens, tablets, 4:3) the game fills the screen instead of
showing a 3:2 or 16:9 picture with black bars above and below. Everything else is the port as released
(IB2 1.9.6 / IB3 1.9.5 sources). See [../notes.md](../notes.md) for how it works.

You still need your own `.ipa` of each game, as with the official port (IB2 1.3.5, e.g. the Community
Patch v2.5; IB3 1.4.4 or the Community Patch v2.5).

## Quick install

1. Download the APKs from the
   [infinityblade-v1.0 release](https://github.com/kirankunigiri/ultrawide-game-patches/releases/tag/infinityblade-v1.0):
   [ib2-android-1.9.6-squarer.apk](https://github.com/kirankunigiri/ultrawide-game-patches/releases/download/infinityblade-v1.0/ib2-android-1.9.6-squarer.apk),
   [ib3-android-1.9.6-squarer.apk](https://github.com/kirankunigiri/ultrawide-game-patches/releases/download/infinityblade-v1.0/ib3-android-1.9.6-squarer.apk).
2. **Already have the official port installed?** It is signed with the port developer's key and these
   APKs with another, so Android will not install one over the other: the official app has to be
   uninstalled first, and uninstalling deletes the game and your saves. So first, in the official app:
   **Saves > Back up saves**, and keep the .zip (e.g. in Downloads). Then uninstall the official app.
3. Install the APK (allow installs from your browser or file manager; on a Play Protect warning choose
   "Install anyway").
4. Open it, tap **Choose .ipa file** and pick your `.ipa` (under a minute).
5. If you backed up saves: **Saves > Restore saves** and pick the .zip.
6. IB2 only: keep **Settings > Screen** on **Full screen** (the default). 16:9 brings the bars back.

## Configuration

Nothing to set: the app reads the screen's shape when the game starts. Screens squarer than 3:2 get
the fix; 3:2 to 16:9 and longer screens behave exactly like the official port.

- On a foldable, start the game on the screen you will play on. The shape is read once per launch:
  after unfolding or folding, close the app from Recents and start it again.
- Tested: OPPO Find N6 inner screen, 2480x2248 (about 1.1:1). Other squarer shapes (4:3, 16:10
  tablets) take the same path but were not tested.

## What changes on screen

- **IB2:** the 3D view and the HUD fill the screen. The view keeps the width it has at 3:2 and shows
  more above and below. Menus' swirl backdrops are scaled to cover the taller view.
- **IB3:** the 3D view fills the screen the same way (gameplay and in-engine cutscenes). The HUD keeps
  IB3's own iPad layout, a 3:2 area across the middle of the screen (health bars and buttons sit a
  little in from the top and bottom edges). The iPad mask bars and the exploring vignette, which only
  covered that area, are removed.
- Pre-rendered videos (the IB2 and IB3 intros) are 16:9 and keep their bars. IB2's in-engine
  cutscenes use 16:9 cinematic cameras and keep their bars too.

## Uninstall

Back up saves (**Saves > Back up saves**), uninstall the app, install the official APK from the
[port's releases](https://github.com/jelqedagain/ib-2-3-android/releases) and restore the saves.

## Manual build

`../src/build.sh` clones the port at the tested commit, applies `squarer-screens.patch` and builds both
APKs into `src/out/` (macOS or Linux, Android SDK + NDK 27.0.12077973; see the script's header). A
build from your machine is signed with your own key, so it does not install over the Releases APKs
either: same backup / uninstall / restore as above.

## Troubleshooting

- **Still black bars above and below in IB2:** check **Settings > Screen** is **Full screen**, then
  restart the app.
- **Still black bars in a fight or while exploring (IB3), or a 3:2 picture:** your `.ipa`'s script is
  not the one the fix expects (only the Community Patch .ipas above were tested), and the game falls
  back to its own layout. Nothing breaks; the bars just stay.
- **The fix writes no log of its own and has no debug switch.** The port itself always keeps a log
  (`ib3rt.log`, shared through **Help > Report a problem**); with the fix active, IB2's contains
  `widescreen: HUD laid out for the full 457x414 screen` on a 2480x2248 screen.
