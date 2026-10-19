# Lists the UnrealScript functions that use a float constant (EX_FloatConst 0x1e), e.g. aspect-ratio
# limits:   python3 find_floats.py SwordGame.xxx 1.5 1.7 1.8
# and, with --dump <Class.Function>, hex-dumps one function's serialized data with the object
# references it contains resolved, to read its bytecode by hand.
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upk import Pkg  # noqa: E402

pkg = Pkg(sys.argv[1])
if len(sys.argv) > 3 and sys.argv[2] == "--dump":
    for i, e in enumerate(pkg.exports):
        if pkg.path(i + 1) == sys.argv[3] and pkg.objname(e["cls"]) == "Function":
            b = pkg.d[e["off"]:e["off"] + e["size"]]
            print(f"{sys.argv[3]} at 0x{e['off']:x}, {e['size']} bytes")
            for o in range(0, len(b), 16):
                print(f"{o:04x} " + " ".join(f"{x:02x}" for x in b[o:o + 16]))
            for o in range(1, len(b) - 4):
                v = struct.unpack_from("<i", b, o)[0]
                if b[o - 1] in (0x00, 0x01, 0x1c, 0x20, 0x2d, 0x35, 0x48) and v and (0 < v <= len(pkg.exports) or 0 < -v <= len(pkg.imports)):
                    print(f"  @{o:04x} token {b[o - 1]:02x} -> {pkg.path(v)}")
    sys.exit()
for value in map(float, sys.argv[2:]):
    for m in re.finditer(re.escape(b"\x1e" + struct.pack("<f", value)), pkg.d):
        i = pkg.owner_of(m.start())
        print(f"{value:g}  0x{m.start():x}  {pkg.path(i + 1) if i is not None else '?'}")
