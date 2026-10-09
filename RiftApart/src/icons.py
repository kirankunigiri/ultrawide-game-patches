# Find live MapIconData records (layout decoded from the UI binding registration):
#   +0x00 int  symbolType      +0x04 char[128] image     +0x84 bool visible
#   +0x85 bool complete        +0x86 ?[0x40] transform2D +0xC6 bool arrowVisible
#   +0xC8 float arrowRot       +0xCC float rot           +0xD0 int zIndex
#   +0xD4 bool focused         +0xD5 bool pinned
# Strategy: search writable memory for icon image paths and parse the record around them.
import re, struct, collections, sys, json
from mem import regions, read

PAT = re.compile(rb"(coui://|ui/loaded/)[ -~]{4,120}?(\.svg|\.png|\.texture)\x00")

def parse(rec):
    st = struct.unpack_from("<i", rec, 0)[0]
    img = rec[4:0x84].split(b"\0")[0].decode("latin-1")
    t = rec[0x86:0xC6]
    return dict(symbolType=st, image=img, visible=rec[0x84], complete=rec[0x85],
                tf=[round(x, 2) for x in struct.unpack_from("<16f", t)] if len(t) == 64 else None,
                tf_raw=t.hex(), rot=struct.unpack_from("<f", rec, 0xCC)[0], pinned=rec[0xD5])

def scan():
    found = []
    for base, size in regions():
        b = read(base, size)
        if not b:
            continue
        for m in PAT.finditer(b):
            start = m.start() - 4
            if start < 0 or start + 0xD8 > len(b):
                continue
            rec = b[start:start + 0xD8]
            st = struct.unpack_from("<i", rec, 0)[0]
            if not (0 <= st < 1000) or rec[0x84] > 1 or rec[0x85] > 1:
                continue
            found.append((base + start, parse(rec)))
    return found

if __name__ == "__main__":
    f = scan()
    print(f"{len(f)} candidate MapIconData records")
    byimg = collections.Counter(r["image"] for _, r in f)
    for img, n in byimg.most_common(40):
        print(f"  {n:4d}  {img}")
    json.dump([dict(addr=hex(a), **r) for a, r in f], open("icons_dump.json", "w"), indent=1)
