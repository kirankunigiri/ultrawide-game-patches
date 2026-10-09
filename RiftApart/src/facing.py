# For each copy of the player position, test whether the 48 bytes before it are a rotation
# (3 orthonormal float4 rows) - i.e. the position is the translation row of a 4x4 transform.
import numpy as np, struct, json
from mem import read
from pos import reread

a = np.load("player_cands.npy")
v = reread(a)
P = np.median(v[np.isfinite(v).all(1)], 0)
near = a[np.abs(v - P).max(1) < 0.5]
hits = []
for addr in near:
    b = read(int(addr) - 48, 64)
    if not b:
        continue
    m = np.array(struct.unpack("<16f", b)).reshape(4, 4)
    R = m[:3, :3]
    if not np.isfinite(R).all():
        continue
    if np.allclose(R @ R.T, np.eye(3), atol=1e-3) and abs(np.linalg.det(R) - 1) < 1e-2:
        hits.append((int(addr), R))
print(f"{len(near)} position copies, {len(hits)} with a rotation matrix in front")
for addr, R in hits[:12]:
    # yaw of each basis row projected on the ground (X/Z), in degrees
    yaws = [np.degrees(np.arctan2(r[2], r[0])) for r in R]
    print(f"{addr:#x}  rows:", " | ".join(f"({r[0]:+.2f},{r[1]:+.2f},{r[2]:+.2f})" for r in R),
          " yaw(row0,row2) = %.1f, %.1f" % (yaws[0], yaws[2]))
json.dump([h[0] for h in hits], open("facing_cands.json", "w"))
