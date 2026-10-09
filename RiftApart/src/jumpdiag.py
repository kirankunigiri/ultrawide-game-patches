# Find the cause of position jumps: sample every chain's value at 20 Hz during balanced moves
# and print per-chain values around any jump of the consensus.
import math, threading, time, struct, numpy as np
import drive, heroread
from mem import read

chains = heroread.POS_CHAINS + [(r, o) for r, o, _, _ in heroread.ROOT_CHAINS]
def all_vals():
    out = []
    for rva, offs in chains:
        e = heroread._endpoint(rva, offs)
        b = read(e, 12) if e else None
        out.append(struct.unpack("<3f", b) if b else (np.nan,) * 3)
    return np.array(out)[:, [0, 2]]

frames, stop = [], threading.Event()
def sampler():
    while not stop.is_set():
        frames.append((heroread.hero_xz(), all_vals())); time.sleep(0.05)
drive.focus(); time.sleep(0.6)
th = threading.Thread(target=sampler, daemon=True); th.start()
for k in ["w", "s", "d", "a", "s", "w", "a", "d"]:
    drive.focus(); drive.hold(k, 1.0); time.sleep(0.4)
stop.set(); th.join()
for i in range(1, len(frames)):
    a, b = frames[i - 1][0], frames[i][0]
    if a and b and math.dist(a, b) > 1.5:
        print(f"jump {math.dist(a, b):.2f} at frame {i}: {a} -> {b}")
        for j, (rva, offs) in enumerate(chains):
            v0, v1 = frames[i - 1][1][j], frames[i][1][j]
            print(f"   exe+{rva:#x} {offs}: ({v0[0]:.1f},{v0[1]:.1f}) -> ({v1[0]:.1f},{v1[1]:.1f})")
        break
else:
    print("no jumps >1.5 in", len(frames), "frames")

