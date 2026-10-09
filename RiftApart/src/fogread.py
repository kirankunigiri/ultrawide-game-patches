# Read the game's fog-of-war (explored cells) exactly as the pause map does
# (GUI2::PauseMenuElementMapPage::InitMapTextures):
#   G = FogOfWarSystem hash map (exe+0x580fc08): +0 keys*, +8 records*, +0x14 capacity,
#       +0x20 record stride. Key = map id (u64), record found at records + slot*stride.
#   record: +0x78 width, +0x7c height, +0x80 self-relative (or absolute) pointer to bits.
#   visited(row, col) = bit (row*width + col) of the bit buffer.
import struct, numpy as np
from mem import read, EXE

G_RVA = 0x580fc08

def table():
    g = read(EXE.lpBaseOfDll + G_RVA, 0x28)
    keys, recs = struct.unpack_from("<QQ", g, 0)
    cap = struct.unpack_from("<I", g, 0x14)[0]
    stride = struct.unpack_from("<I", g, 0x20)[0]
    kb = read(keys, cap * 8)
    out = []
    for slot in range(cap):
        k = struct.unpack_from("<Q", kb, slot * 8)[0]
        if k:
            out.append((k, recs + slot * stride))
    return out

def grid(rec):
    r = read(rec, 0x90)
    w, h = struct.unpack_from("<II", r, 0x78)
    p = struct.unpack_from("<q", r, 0x80)[0]
    buf = rec + 0x80 + p if p < 0 else p          # self-relative when negative (as 0x1415b19d0)
    n = (w * h + 7) // 8
    bits = np.unpackbits(np.frombuffer(read(buf, n), np.uint8), bitorder="little")[: w * h]
    return bits.reshape(h, w)

if __name__ == "__main__":
    from PIL import Image
    for k, rec in table():
        try:
            g = grid(rec)
            print(f"map {k:#x}: record {rec:#x}  grid {g.shape[1]}x{g.shape[0]}  visited {int(g.sum())} cells")
            Image.fromarray((g * 255).astype(np.uint8)).save(f"fog_{k:x}.png")
        except Exception as e:
            print(f"map {k:#x}: record {rec:#x}  unreadable ({e})")
