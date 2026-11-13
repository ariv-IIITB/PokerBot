import json, sys
from pathlib import Path
sys.path.insert(0, "panav-bots/loop/meta1")
import traits as T
R = Path("panav-bots/loop/results/meta1")
out = {}
for d in sorted((R / "logs").iterdir()):
    out[d.name] = {}
    for N in (60, 100):
        ls = T.legs(str(d), N)
        r, n = T.pooled(ls)
        # per-leg rates for a few features, to measure within-bot noise
        per = {k: [c[k][0] / c[k][1] for c in ls if c[k][1] > 0] for k in T.KEYS}
        out[d.name][N] = {"rate": r, "n": n, "legsd": {k: (__import__("statistics").pstdev(v) if len(v) > 1 else None) for k, v in per.items()}}
    print(d.name, flush=True)
json.dump(out, open(R / "traits.json", "w"))
