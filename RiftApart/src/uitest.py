# End-to-end overlay test: screenshot the minimap, open/close the pause map (Tab) so icons
# get captured, screenshot again, and toggle the fullscreen map with the ` key.
import subprocess, sys, time, json
from PIL import Image
import drive

drive.SC.update({"tab": 0x0F, "grave": 0x29})

def shot(name, box=None):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "ddagrab=output_idx=0:framerate=30", "-vf", "hwdownload,format=bgra", "-frames:v", "1", name])
    if box:
        Image.open(name).crop(box).save(name)

MINI = (5120 - 460, 0, 5120, 460)
drive.focus(); time.sleep(1.5)
shot("ui_mini_before.png", MINI)
drive.hold("tab", 0.1); time.sleep(2.0)            # open the pause map: overlay captures icons
drive.hold("tab", 0.1); time.sleep(1.5)            # close it again
shot("ui_mini_after.png", MINI)
print("icons remembered:", len(json.load(open("minimap_icons.json"))))
if "full" in sys.argv:
    drive.hold("grave", 0.1); time.sleep(1.2)
    shot("ui_full.png"); Image.open("ui_full.png").resize((1600, 450)).save("ui_full_small.png")
    drive.hold("grave", 0.1); time.sleep(0.5)       # back to the minimap
