# Validate root-transform chains while driving the hero, and learn which matrix row (and sign)
# is "forward" by comparing with the direction of travel.
import json, math, struct, time, numpy as np
import drive
from chaincheck import q, lo, hero
from mem import read
from pos import reread

chains = [(int(c["static"][4:], 16), (c["off"],)) for c in json.load(open("rootchains1.json"))]
chains += [(int(c["static"][4:], 16), (c["off2"], c["off1"])) for c in json.load(open("rootchains2.json"))]

def endpoint(ch):
    rva, offs = ch
    p = q(lo + rva)
    for o in offs[:-1]:
        p = q(p + o) if p else None
    return p + offs[-1] if p else None

def matrix(ch):
    e = endpoint(ch)
    b = read(e - 48, 64) if e else None
    return np.array(struct.unpack("<16f", b)).reshape(4, 4) if b else None

def truth():
    v = reread(hero); return np.median(v[np.isfinite(v).all(1)], 0)

def main():
  alive = list(chains)
  score = {}
  prev = start = truth()
  for k in ["w", "s", "d", "a", "s", "w", "a", "d"]:      # balanced pairs: ends where it started
      if np.hypot(*(truth() - start)[[0, 2]]) > 12:
          print("  safety stop: drifted more than 12 units from the start"); break
      drive.focus(); drive.hold(k, 1.0); time.sleep(0.5)
      t = truth()
      mv = math.atan2(t[2] - prev[2], t[0] - prev[0]); prev = t
      keep = []
      for ch in alive:
          m = matrix(ch)
          if m is None or not np.isfinite(m).all() or m[1, 1] < 0.999 or np.abs(m[3, [0, 2]] - t[[0, 2]]).max() > 0.5:
              continue
          keep.append(ch)
          for row in (0, 2):
              for sgn in (1, -1):
                  yaw = math.atan2(sgn * m[row, 2], sgn * m[row, 0])
                  s = score.setdefault((ch, row, sgn), [0.0, 0]); s[0] += math.cos(yaw - mv); s[1] += 1
      alive = keep
      print(f"after '{k}': {len(alive)} root chains still correct")
  end = truth()
  print(f"  drift from start: {np.hypot(*(end - start)[[0, 2]]):.1f} units")
  ranked = sorted(((s[0] / s[1], key) for key, s in score.items() if key[0] in alive), reverse=True)
  for sc, (ch, row, sgn) in ranked[:6]:
      print(f"  forward match {sc:+.2f}: exe+{ch[0]:#x} {ch[1]}  row {row} sign {sgn:+d}")
  json.dump([dict(static=f"exe+{ch[0]:#x}", offsets=list(ch[1]), row=row, sign=sgn, score=sc)
             for sc, (ch, row, sgn) in ranked if sc > 0.7], open("facing_chains.json", "w"), indent=1)


if __name__ == "__main__":
    main()


