# Load a UI map model from the archives and fit texture UV <-> vertex X/Z (linear).
import io, sys, numpy as np
from extract_tex import toc, find
import dat1lib, dat1lib.types.sections.model.geo as geo

path = sys.argv[1] if len(sys.argv) > 1 else "models/ui/Map_sargasso/Map_sargasso.model"
e = find(path)[0]
model = dat1lib.read(io.BytesIO(toc().extract_asset(e)))
vs = model.dat1.get_section(geo.VertexesSection.TAG).vertexes
P = np.array([(v.x, v.y, v.z) for v in vs], float)
UV = np.array([(v.u, v.v) for v in vs], float) / 16384.0
print(f"{len(vs)} vertices")
for i, n in enumerate("xyz"):
    print(f"  {n}: {P[:, i].min():10.3f} .. {P[:, i].max():10.3f}")
print(f"  u: {UV[:, 0].min():.4f} .. {UV[:, 0].max():.4f}   v: {UV[:, 1].min():.4f} .. {UV[:, 1].max():.4f}")
# fit u = a*X + b*Z + c and v = d*X + e*Z + f
A = np.c_[P[:, 0], P[:, 2], np.ones(len(P))]
for name, col in (("u", 0), ("v", 1)):
    coef, res, *_ = np.linalg.lstsq(A, UV[:, col], rcond=None)
    err = np.abs(A @ coef - UV[:, col]).max()
    print(f"  {name} = {coef[0]:+.6e}*X {coef[1]:+.6e}*Z {coef[2]:+.6f}   max err {err:.2e}")
np.savez("mapmodel_sargasso.npz", P=P, UV=UV)
