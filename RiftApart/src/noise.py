# Pages that change at all versus a snapshot (taken while the player stands still) = noise.
import json, sys, numpy as np
from mem import read

NAME = sys.argv[1]
idx = json.load(open(NAME + ".json"))
noisy = []
with open(NAME + ".bin", "rb") as f:
    for base, size, off in idx:
        new = read(base, size)
        if not new or len(new) != size or size % 4096:
            continue
        f.seek(off)
        old = np.frombuffer(f.read(size), np.uint8).reshape(-1, 4096)
        nw = np.frombuffer(new, np.uint8).reshape(-1, 4096)
        noisy += [base + int(p) * 4096 for p in np.nonzero((old != nw).any(1))[0]]
json.dump(noisy, open("fog_noise.json", "w"))
print(len(noisy), "noisy pages")
