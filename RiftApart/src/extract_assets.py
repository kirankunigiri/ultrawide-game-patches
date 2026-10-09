# One-time setup: extract the minimap's artwork from your own game install into maps/
# and icons/ (game assets are not shipped in the repo). Needs the ALERT checkout in
# src/ALERT and, for full-resolution planet maps, ALERT's libdeflate.dll in src/
# (see dist/INSTALL.md). Without the DLL, GDeflate-compressed maps fall back to 512 px.
#   python extract_assets.py [game folder]
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                       # ALERT loads libdeflate.dll from the working directory
import extract_tex

ICONS = ["collectiblebolt", "collectiblelorb", "collectiblespybot", "mapiconbeetle", "mapiconflyer",
         "mapicongoldbolt", "mapiconloreshrine", "mapiconobjective", "mapiconobjectiveoptional",
         "mapiconphasequartz", "mapiconplayer", "mapiconpocketdim", "mapiconraritanium",
         "mapiconrynopart", "mapiconship", "mapiconteleport", "mapiconvanity", "mapiconvendor",
         "mapiconzurpstone"]
ICON_PATH = "ui/loaded/authored/_art/textures/{}.texture"
MAP_PATH = "materialgraph/ui/Material_Textures/{}.texture"


def main():
    if len(sys.argv) > 1:
        extract_tex.GAME = sys.argv[1]
    if not os.path.exists(os.path.join(extract_tex.GAME, "toc")):
        sys.exit(f"Game not found at {extract_tex.GAME} (pass the folder that contains 'toc').")
    if not os.path.exists("libdeflate.dll"):
        print("note: libdeflate.dll not in src/ - planet maps other than Sargasso will be 512 px")
    os.makedirs("maps", exist_ok=True)
    os.makedirs("icons", exist_ok=True)
    failed = 0
    for entry in json.load(open("maps.json")).values():
        name = os.path.splitext(os.path.basename(entry["texture"]))[0]
        print(extract_tex.extract(MAP_PATH.format(name), os.path.join("maps", name + ".png")))
        failed += not os.path.exists(os.path.join("maps", name + ".png"))
    for name in ICONS:
        print(extract_tex.extract(ICON_PATH.format(name), os.path.join("icons", name + ".png")))
        failed += not os.path.exists(os.path.join("icons", name + ".png"))
    print("done" if not failed else f"{failed} asset(s) missing - see messages above")


if __name__ == "__main__":
    main()
