"""call1: paired comparison of cand vs base runs written by call1_duel/file_duel (--out json), seed-matched.

  .venv/bin/python panav-bots/loop/tools/call1_compare.py LABEL=base.json,cand.json [LABEL=...] [--max-seed N]
Per bot: delta (cand - base) chips/hand +- SE over seed pairs, base/cand chips/hand, match wins (a pair = one match, won if total
chips > 0; ties count half) and the z of the delta. Pooled: mean of the per-bot deltas, SE = sqrt(sum SE^2)/k.
"""
import json, math, sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
mx = None
if "--max-seed" in sys.argv:
    mx = int(sys.argv[sys.argv.index("--max-seed") + 1]); args = [a for a in args if a != str(mx)]
rows = []
for a in args:
    label, files = a.split("=", 1); fb, fc = files.split(",")
    B = {p["seed"]: p for p in json.load(open(fb))["pairs"]}; C = {p["seed"]: p for p in json.load(open(fc))["pairs"]}
    seeds = sorted(set(B) & set(C))
    if mx is not None:
        seeds = [s for s in seeds if s < mx]
    d = [C[s]["chips"] / C[s]["hands"] - B[s]["chips"] / B[s]["hands"] for s in seeds]
    n = len(d); m = sum(d) / n; se = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1) / n) if n > 1 else float("nan")
    wb = sum(1.0 if B[s]["chips"] > 0 else 0.5 if B[s]["chips"] == 0 else 0.0 for s in seeds)
    wc = sum(1.0 if C[s]["chips"] > 0 else 0.5 if C[s]["chips"] == 0 else 0.0 for s in seeds)
    mb = sum(B[s]["chips"] / B[s]["hands"] for s in seeds) / n; mc = sum(C[s]["chips"] / C[s]["hands"] for s in seeds) / n
    ff = sum(C[s]["ff_a"] for s in seeds)
    rows.append((label, n, m, se, mb, mc, wb, wc, ff))
    print(f"{label:16s} n={n:3d} delta {m:+.3f} ± {se:.3f} (z {m / se if se else float('nan'):+.1f}) | base {mb:+.2f} cand {mc:+.2f} | wins base {wb:.1f} cand {wc:.1f} | cand forfeits {ff}")
k = len(rows)
pm = sum(r[2] for r in rows) / k; pse = math.sqrt(sum(r[3] ** 2 for r in rows)) / k
print(f"POOLED over {k} bots: delta {pm:+.3f} ± {pse:.3f} (z {pm / pse:+.1f}); wins base {sum(r[6] for r in rows):.1f} cand {sum(r[7] for r in rows):.1f} of {sum(r[1] for r in rows)}; "
      f"worst bot z {min(r[2] / r[3] for r in rows):+.1f}")
