# Which fog grid belongs to the Sargasso map texture, and in which orientation?
# Score = fraction of explored cells that land on island (land) pixels of the texture.
import numpy as np
from PIL import Image
from fogread import table, grid

tex = np.array(Image.open("maps/sargasso_map_UV_6-17-2021.png").convert("RGB"))
land = tex[:, :, 1] > 8                                   # island fill has green, water has none
ops = {"as-is": lambda g: g, "transpose": lambda g: g.T, "flip-v": lambda g: g[::-1],
       "flip-h": lambda g: g[:, ::-1], "rot180": lambda g: g[::-1, ::-1],
       "transpose+flip-v": lambda g: g.T[::-1], "transpose+flip-h": lambda g: g.T[:, ::-1]}
best = []
for k, rec in table():
    g = grid(rec)
    if g.sum() == 0:
        continue
    for name, f in ops.items():
        gg = f(g)
        m = np.array(Image.fromarray((gg * 255).astype(np.uint8)).resize(land.shape[::-1], Image.NEAREST)) > 0
        score = (m & land).sum() / max(1, m.sum())
        best.append((score, f"{k:#x}", name, gg.shape))
best.sort(reverse=True)
for s in best[:10]:
    print(f"  on-land {s[0]:.3f}  map {s[1]}  {s[2]}  grid {s[3]}")
print(f"(texture land fraction overall: {land.mean():.3f})")
