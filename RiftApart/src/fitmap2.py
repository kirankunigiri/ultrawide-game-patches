# Align the extracted map texture with a pause-map screenshot via SIFT features + RANSAC
# (similarity transform), then convert the texture's corners to world coordinates.
import json, sys, numpy as np, cv2

TEX = sys.argv[1] if len(sys.argv) > 1 else "maps/sargasso_map_UV_6-17-2021.png"
SHOT = "cap_test.png"
PW = (431.59, 291.01); PC = (1038.15, 876.70); UI = 1440 / 1080; X0 = 1280
def screen_to_world(sx, sy):
    cx, cy = (sx - X0) / UI, sy / UI
    return PW[0] + (cx - PC[0]) / 1.5655, PW[1] + (cy - PC[1]) / 1.5655

def prep(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g)

shot = cv2.imread(SHOT)
crop = (1880, 280, 3400, 1340)
s_img = prep(shot[crop[1]:crop[3], crop[0]:crop[2]])
t_img = prep(cv2.imread(TEX))

sift = cv2.SIFT_create(nfeatures=8000)
kt, dt = sift.detectAndCompute(t_img, None)
ks, ds = sift.detectAndCompute(s_img, None)
m = cv2.BFMatcher().knnMatch(dt, ds, k=2)
good = [a for a, b in m if a.distance < 0.8 * b.distance]
pt = np.float32([kt[g.queryIdx].pt for g in good])
ps = np.float32([ks[g.trainIdx].pt for g in good]) + np.float32([crop[0], crop[1]])
M, inl = cv2.estimateAffinePartial2D(pt, ps, method=cv2.RANSAC, ransacReprojThreshold=4.0, maxIters=20000)
n_in = int(inl.sum()) if inl is not None else 0
print(f"features tex={len(kt)} shot={len(ks)} good={len(good)} inliers={n_in}")
if M is None:
    sys.exit("no fit")
scale = float(np.hypot(M[0, 0], M[1, 0])); rot = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
print(f"screen px per texture px {scale:.4f}, rotation {rot:.3f} deg")
h, w = t_img.shape
def tex_to_world(u, v):
    sx = M[0, 0] * u + M[0, 1] * v + M[0, 2]; sy = M[1, 0] * u + M[1, 1] * v + M[1, 2]
    return screen_to_world(sx, sy)
x0, z0 = tex_to_world(0, 0); x1, z1 = tex_to_world(w, h)
print(f"texture world bounds: X {x0:.2f} .. {x1:.2f}   Z {z0:.2f} .. {z1:.2f}  ({(x1 - x0) / w:.4f} units/px)")
json.dump(dict(texture=TEX, x_min=x0, x_max=x1, z_min=z0, z_max=z1, inliers=n_in, rot=rot),
          open("map_bounds_sargasso.json", "w"), indent=1)
warp = cv2.warpAffine(cv2.imread(TEX), M, (shot.shape[1], shot.shape[0]))
edges = cv2.Canny(cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY), 40, 120) > 0
ov = shot.copy(); ov[edges] = (0, 0, 255)
cv2.imwrite("fit_check.png", cv2.resize(ov[:, 1280:3840], (1280, 720)))
