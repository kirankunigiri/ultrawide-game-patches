# Render memory around a candidate as an image (bits or bytes) at several row widths.
import sys, numpy as np
from PIL import Image
from mem import read

addr = int(sys.argv[1], 16); mode = sys.argv[2]; name = sys.argv[3]
widths = [int(w) for w in sys.argv[4].split(",")]
span = 0x10000
b = read(addr - span // 2, span) or read(addr, span // 2)
a = np.frombuffer(b, np.uint8)
if mode == "bits":
    a = np.unpackbits(a, bitorder="little") * 255
tiles = []
for w in widths:
    h = min(len(a) // w, 400)
    img = Image.fromarray(a[: w * h].reshape(h, w).astype(np.uint8)).resize((min(w, 400) * 1, h), Image.NEAREST)
    tiles.append(img)
W = sum(t.size[0] + 10 for t in tiles); H = max(t.size[1] for t in tiles)
sheet = Image.new("L", (W, H), 60); x = 0
for t in tiles:
    sheet.paste(t, (x, 0)); x += t.size[0] + 10
sheet.save(name)
print("saved", name, "widths", widths)
