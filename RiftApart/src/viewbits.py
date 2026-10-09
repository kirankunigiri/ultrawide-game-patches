# Render a memory range as a bit image at several row widths (in bits), plus what changed
# between snapshot B and now (changed bits highlighted red).
import sys, json, numpy as np
from PIL import Image
from mem import read

start = int(sys.argv[1], 16); length = int(sys.argv[2], 16); out = sys.argv[3]
widths = [int(w) for w in sys.argv[4].split(",")]
now = np.frombuffer(read(start, length), np.uint8)
old = None
idx = json.load(open("snapB.json"))
with open("snapB.bin", "rb") as f:
    for base, size, off in idx:
        if base <= start and start + length <= base + size:
            f.seek(off + start - base); old = np.frombuffer(f.read(length), np.uint8)
bn = np.unpackbits(now, bitorder="little")
bo = np.unpackbits(old, bitorder="little") if old is not None else bn
tiles = []
for w in widths:
    h = len(bn) // w
    rgb = np.zeros((h, w, 3), np.uint8)
    on = bn[: w * h].reshape(h, w).astype(bool)
    new = on & ~bo[: w * h].reshape(h, w).astype(bool)
    rgb[on] = (230, 230, 230); rgb[new] = (255, 40, 40)
    im = Image.fromarray(rgb)
    s = max(1, 360 // max(w, h))
    tiles.append(im.resize((w * s, h * s), Image.NEAREST))
W = sum(t.size[0] + 12 for t in tiles); H = max(t.size[1] for t in tiles)
sheet = Image.new("RGB", (W, H), (40, 40, 70)); x = 0
for t in tiles:
    sheet.paste(t, (x, 0)); x += t.size[0] + 12
sheet.save(out); print("saved", out)
