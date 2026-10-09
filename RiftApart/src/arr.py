# Read the live pause-map icon array (records 0xE8 apart; layout from the UI bindings).
import sys, struct, json
from mem import read

REC = 0xE8

def icons(base, n=64):
    out = []
    for i in range(n):
        r = read(base + i * REC, REC)
        if not r:
            break
        img = r[4:0x84].split(b"\0")[0].decode("latin-1")
        if not img:
            continue
        x, y = struct.unpack_from("<2f", r, 0xDC)
        out.append(dict(i=i, type=struct.unpack_from("<i", r, 0)[0], img=img.split("/")[-1].split(".")[0],
                        vis=r[0x84], done=r[0x85], x=round(x, 2), y=round(y, 2),
                        arrow=r[0xC6], arrowRot=round(struct.unpack_from("<f", r, 0xC8)[0], 1),
                        rot=round(struct.unpack_from("<f", r, 0xCC)[0], 1), id=struct.unpack_from("<I", r, 0xD8)[0]))
    return out

if __name__ == "__main__":
    base = int(sys.argv[1], 16)
    data = icons(base)
    for d in data:
        print(d)
    if len(sys.argv) > 2:
        json.dump(data, open(sys.argv[2], "w"), indent=1)
