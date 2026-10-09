# Pause-map background capture: screenshot the open pause map and keep the map area,
# with the transform from screen pixels to world X/Z.
import subprocess, threading, os, time
from PIL import Image, ImageDraw

SCREEN_W, SCREEN_H = 5120, 1440
UI_SCALE = SCREEN_H / 1080.0                     # 1920x1080 UI canvas, scaled by height
UI_X0 = (SCREEN_W - 1920 * UI_SCALE) / 2         # canvas is centred horizontally
VIEW = (115.2, 216.0, 1804.8, 1000.0)            # map viewport on the canvas (icon clamp bounds)
HERE = os.path.dirname(os.path.abspath(__file__))

def canvas_to_screen(cx, cy):
    return UI_X0 + cx * UI_SCALE, cy * UI_SCALE

def grab():
    out = os.path.join(HERE, "mapbg_raw.png")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "ddagrab=output_idx=0:framerate=30", "-vf", "hwdownload,format=bgra",
                    "-frames:v", "1", out], creationflags=0x08000000, timeout=10)
    return Image.open(out).convert("RGB")

class MapBackground:
    """Latest captured pause map: image + world transform (world = origin + px / ppu)."""
    def __init__(self):
        self.img = None
        self.busy = False

    def capture_async(self, player_world, player_canvas, scale):
        if self.busy:
            return
        self.busy = True
        def work():
            try:
                full = grab()
                x0, y0 = canvas_to_screen(VIEW[0], VIEW[1])
                x1, y1 = canvas_to_screen(VIEW[2], VIEW[3])
                crop = full.crop((int(x0), int(y0), int(x1), int(y1)))
                ppu = scale * UI_SCALE                  # screen px per world unit
                # cover the (stale) baked-in player icon
                px, py = canvas_to_screen(*player_canvas)
                d = ImageDraw.Draw(crop)
                d.ellipse((px - x0 - 22, py - y0 - 22, px - x0 + 22, py - y0 + 22), fill=(18, 16, 48))
                # world coordinate of the crop's top-left pixel
                ox = player_world[0] - (px - x0) / ppu
                oz = player_world[1] - (py - y0) / ppu
                self.img, self.origin, self.ppu = crop, (ox, oz), ppu
                crop.save(os.path.join(HERE, "mapbg_latest.png"))
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()

    def view(self, player_world, radius_world, size):
        """Square crop around the player, resized to size x size (None if no capture)."""
        if self.img is None:
            return None
        cx = (player_world[0] - self.origin[0]) * self.ppu
        cy = (player_world[1] - self.origin[1]) * self.ppu
        r = radius_world * self.ppu
        return self.img.crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r))).resize((size, size), Image.BILINEAR)
