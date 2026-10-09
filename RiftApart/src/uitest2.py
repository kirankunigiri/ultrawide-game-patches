# Overlay end-to-end test v2: fullscreen on/off, then pause map (Tab to open, Esc to close).
import subprocess, time, json
from PIL import Image
import drive

drive.SC.update({"tab": 0x0F, "grave": 0x29, "esc": 0x01})
MINI = (5120 - 520, 0, 5120, 520)

def shot(name, box=None, small=None):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "ddagrab=output_idx=0:framerate=30", "-vf", "hwdownload,format=bgra", "-frames:v", "1", name])
    im = Image.open(name)
    if box: im = im.crop(box)
    if small: im = im.resize(small)
    im.save(name)

drive.focus(); time.sleep(1.0)
drive.hold("grave", 0.1); time.sleep(1.2); shot("t_full.png", small=(1600, 450))
drive.hold("grave", 0.1); time.sleep(1.0); shot("t_mini.png", box=MINI)
drive.hold("tab", 0.1); time.sleep(2.0)                  # open pause map -> icon capture
drive.hold("esc", 0.1); time.sleep(1.5)                  # close it
drive.focus(); time.sleep(0.8)
shot("t_mini_icons.png", box=MINI)
print("icons remembered:", len(json.load(open("minimap_icons.json"))))
a, b = Image.open("t_mini.png"), Image.open("t_mini_icons.png")
s = Image.new("RGB", (1050, 520)); s.paste(a, (0, 0)); s.paste(b, (530, 0)); s.save("t_compare.png")

