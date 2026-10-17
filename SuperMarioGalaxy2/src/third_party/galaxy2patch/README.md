# Galaxy-2-Patch (Classic Controller part)

`cc_SB4E01.json` is the Classic Controller patch data for Super Mario Galaxy 2 (USA, SB4E01)
from [Wii-Patches/Galaxy-2-Patch](https://github.com/Wii-Patches/Galaxy-2-Patch) by quatric,
MIT License (see `LICENSE`).

- Source file: `tools/prebuilt/cc_SB4E01.json`
- Commit: `a02ef5dc58a9b765de471fbedbf5c90bf5c3fb9c` (2026-10-16, "Fix the title-screen crash and
  build GameCube support for every region"; newer than the v1.2 release, which has the title-screen
  crash)
- SHA-256: `60aca03bdc45a59126d69caa3f67bca3140be919658087f82af24c001471afc1`

`../../make_preset.py` turns its operations into Dolphin `[OnFrame]` patches. The file is copied
unchanged; to update it, replace it and the hash in `make_preset.py`.
