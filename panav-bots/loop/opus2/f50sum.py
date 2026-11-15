import json, math
from pathlib import Path
R = Path("panav-bots/loop/results/opus2/final50")
def sc(x): return 1.0 if x > 0 else 0.5 if x == 0 else 0.0
for o in ("lakshya1", "new_eqrandom", "new_trapper", "trapper"):
    P = [p for f in sorted(R.glob(f"C_{o}_*.json")) for p in json.load(open(f))["pairs"]]
    if not P: continue
    n = len(P); w = sum(sc(p["chips"]) for p in P); ch = [p["chips"] / 1000 for p in P]
    m = sum(ch) / n; se = math.sqrt(sum((x - m) ** 2 for x in ch) / (n - 1) / n) if n > 1 else 0
    print(f"{o}: MATCH WINS {w:g}/{n} ({100*w/n:.0f}%) chips/hand {m:+.2f} ± {se:.2f} forfeits {sum(p['ff_a'] for p in P)} "
          f"worst reply {max(p['worst_a'] for p in P):.2f}s min bank left {min(p['bank_left_a'] for p in P):.0f}s")
