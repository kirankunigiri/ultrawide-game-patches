import json
r1 = {d["addr"]: d for d in json.load(open("fog_round1.json"))}
r2 = {d["addr"]: d for d in json.load(open("fog_round2.json"))}
noise = set(json.load(open("fog_noise.json")))
both = [a for a in r2 if a in r1 and a not in noise]
print("in both rounds, not noisy:", len(both))
for a in sorted(both, key=lambda a: -r2[a]["changed"])[:30]:
    d1, d2 = r1[a], r2[a]
    print(f"  {a:#x}: round1 +{d1['changed']} round2 +{d2['changed']}  "
          f"nonzero {d2['nz_before']}->{d2['nz_after']}  vals {d2['new_values']}")
json.dump(both, open("fog_both.json", "w"))
