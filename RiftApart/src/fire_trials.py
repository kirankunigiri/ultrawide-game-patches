# Summarize state_probe_log.json: per LMB hold, how long until firing is steady.
import json
import sys
BTN = sys.argv[1] if len(sys.argv) > 1 else "lmb"
log = [r for r in json.load(open("state_probe_log.json")) if len(r) >= 7]
start = next((r[0] for r in log if BTN in r[4]), None)
end = next((r[0] for r in log if start and r[0] > start and BTN not in r[4]), None)
seg = [r for r in log if start and start <= r[0] < (end or 1e9)]
pre = [r[2] for r in log if start and r[0] < start and r[2] is not None][-1:]
lastrun = max((r[0] for r in seg if "HeroStateRun," in r[1] + "," and "Strafe" not in r[1]), default=None)
print(f"pre-toggle {pre} lock {round(lastrun - start, 3) if lastrun else 0}s of hold {round((end or seg[-1][0]) - start, 2)}s")
