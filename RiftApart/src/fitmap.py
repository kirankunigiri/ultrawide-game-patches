# Fit the extracted map texture onto a pause-map screenshot (scale + offset, no rotation),
# then express it as world bounds using the screenshot's known screen->world transform.
import json, sys, numpy as np, cv2

TEX = sys.argv[1] if len(sys.argv) > 1 else "maps/sargasso_map_UV_6-17-2021.png"
SHOT = "cap_test.png"
# screenshot transform (pause map open at capture time): player world (431.59, 291.01) at
# canvas (1038.15, 876.70); canvas -> screen: x*1.3333+1280, y*1.3333; 1.5655 canvas px / unit
PW = (431.59, 291.01); PC = (1038.15, 876.70); UI = 1440 / 1080; X0 = 1280; S = 1.5655 * UI
def screen_to_world(sx, sy):
    cx, cy = (sx - X0) / UI, sy / UI
    return PW[0] + (cx - PC[0]) / 1.5655, PW[1] + (cy - PC[1]) / 1.5655

def outline(img_bgr):
    # island boundaries as edges of the (smoothed) brightness - independent of map tint
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 2.5)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    m = cv2.magnitude(gx, gy)
    m = np.minimum(m / (np.percentile(m, 99) + 1e-6), 1.0) * 255
    return cv2.GaussianBlur(m, (0, 0), 2)

shot = cv2.imread(SHOT)
crop = (1900, 300, 3400, 1330)                                # clear map area (no UI panels/windows)
tmpl = outline(shot[crop[1]:crop[3], crop[0]:crop[2]])
tex = cv2.imread(TEX)
texo = outline(tex)

rng = np.random.default_rng(0)
tmpl = tmpl / 255.0 + rng.normal(0, 1e-3, tmpl.shape).astype(np.float32)   # no zero-variance patches
texo = texo / 255.0 + rng.normal(0, 1e-3, texo.shape).astype(np.float32)
best = (-1, None, None)
for s in np.arange(1.0, 1.31, 0.01):     # visual estimate ~1.14 screen px per texture px
    big = cv2.resize(texo, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    if big.shape[0] < tmpl.shape[0] or big.shape[1] < tmpl.shape[1]:
        continue
    r = cv2.matchTemplate(big, tmpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    if mx > best[0]:
        best = (mx, s, loc)
# refine scale
mx, s0, _ = best
for s in np.arange(s0 - 0.05, s0 + 0.05, 0.005):
    big = cv2.resize(texo, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
    r = cv2.matchTemplate(big, tmpl, cv2.TM_CCOEFF_NORMED)
    _, m2, _, loc = cv2.minMaxLoc(r)
    if m2 > best[0]:
        best = (m2, s, loc)
score, s, (lx, ly) = best
# texture pixel (u, v) appears at screen (crop.x0 + u*s - lx, crop.y0 + v*s - ly)
def tex_to_screen(u, v):
    return crop[0] + u * s - lx, crop[1] + v * s - ly
h, w = tex.shape[:2]
x_min, z_min = screen_to_world(*tex_to_screen(0, 0))
x_max, z_max = screen_to_world(*tex_to_screen(w, h))
print(f"match score {score:.3f}, scale {s:.3f} screen px per texture px")
print(f"texture world bounds: X {x_min:.2f} .. {x_max:.2f}   Z {z_min:.2f} .. {z_max:.2f}")
print(f"world units per texture px: {(x_max - x_min) / w:.4f}")
json.dump(dict(texture=TEX, x_min=x_min, x_max=x_max, z_min=z_min, z_max=z_max, score=score),
          open("map_bounds_sargasso.json", "w"), indent=1)
# overlay check image
big = cv2.resize(tex, None, fx=s, fy=s)
ov = shot.copy()
x0, y0 = int(crop[0] - lx), int(crop[1] - ly)
H, W = ov.shape[:2]
xs, ys = max(0, x0), max(0, y0)
xe, ye = min(W, x0 + big.shape[1]), min(H, y0 + big.shape[0])
mask = outline(big[ys - y0: ye - y0, xs - x0: xe - x0]) > 40
ov[ys:ye, xs:xe][mask] = (0, 0, 255)
cv2.imwrite("fit_check.png", cv2.resize(ov[:, 1280:3840], (1280, 720)))
