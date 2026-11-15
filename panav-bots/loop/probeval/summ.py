"""Summarise PROBEVAL: MATCH WINS first, then chips. usage: summ.py [out.md]"""
import json, math, sys
from pathlib import Path
R = Path("panav-bots/loop/results/probeval")
TRAP = {"new_trapper", "trapper"}
def load(p):
    return json.loads(p.read_text()) if p.exists() else None
def res(pr):  # per-seed: match result (1/.5/0), chips/hand
    return {r["seed"]: (1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0, r["chips"] / max(1, r["hands"])) for r in pr["pairs"]}, sum(r["ff_a"] for r in pr["pairs"])
def sd(x):
    n = len(x); m = sum(x) / n
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else float("nan")
def stage(prefix, lines):
    bots = sorted({p.stem.split("_", 2)[2] for p in R.glob(f"{prefix}_base_*.json")})
    rows = []; perseed = {}; perseedc = {}; ff = 0
    for b in bots:
        a = load(R / f"{prefix}_base_{b}.json"); c = load(R / f"{prefix}_probe_{b}.json")
        if not a or not c: continue
        ra, fa = res(a); rc, fc = res(c); ff += fa + fc
        seeds = sorted(set(ra) & set(rc)); n = len(seeds)
        dw = [rc[s][0] - ra[s][0] for s in seeds]; dc = [rc[s][1] - ra[s][1] for s in seeds]
        wb = sum(ra[s][0] for s in seeds); wc = sum(rc[s][0] for s in seeds)
        rows.append((b, n, wb, wc, 100 * sum(dw) / n, 100 * sd(dw) / math.sqrt(n), sum(dc) / n, sd(dc) / math.sqrt(n)))
        for s, x, y in zip(seeds, dw, dc):
            perseed.setdefault(s, {})[b] = x; perseedc.setdefault(s, {})[b] = y
    def pool(excl, d):
        v = [sum(x for b, x in dd.items() if b not in excl) / max(1, len([1 for b in dd if b not in excl])) for dd in d.values()]
        return sum(v) / len(v), sd(v) / math.sqrt(len(v)), len(v)
    lines.append(f"| bot | pairs | base W/N (%) | probe W/N (%) | dwin pp ± SE | dchips/hand ± SE | flag |\n|---|---|---|---|---|---|---|")
    for b, n, wb, wc, dw, sw, dc, scc in rows:
        flag = "DOWN>2SE" if dw < -2 * sw else ("up>2SE" if dw > 2 * sw else "")
        if b in TRAP: flag += " (trapper-type)"
        lines.append(f"| {b} | {n} | {wb:g}/{n} ({100*wb/n:.0f}%) | {wc:g}/{n} ({100*wc/n:.0f}%) | {dw:+.1f} ± {sw:.1f} | {dc:+.2f} ± {scc:.2f} | {flag} |")
    if rows:
        tb = sum(r[2] for r in rows); tc = sum(r[3] for r in rows); tn = sum(r[1] for r in rows)
        lines.append(f"\nPOOLED MATCH WINS {len(rows)} bots: base {tb:g}/{tn} ({100*tb/tn:.1f}%) -> probe {tc:g}/{tn} ({100*tc/tn:.1f}%)")
        for name, ex in (("all (rule 1)", set()), ("excl trapper-type", TRAP), ("excl trapper-type & s1_ranges", TRAP | {"s1_ranges"})):
            w = pool(ex, perseed); c = pool(ex, perseedc)
            lines.append(f"- {name}: dwin {100*w[0]:+.2f} ± {100*w[1]:.2f} pp (SE over {w[2]} seeds); dchips/hand {c[0]:+.3f} ± {c[1]:.3f}")
        lines.append(f"- forfeits (A side) {ff}")
    return rows
out = []
out.append("## Stage 1 (200h legs, seeds 30000-30039)"); stage("s1", out)
out.append("\n## Stage 2 (500h legs, seeds 30100-30123)"); stage("s2", out)
h = load(R / "h2h_200.json")
if h:
    r = [1.0 if p["chips"] > 0 else 0.5 if p["chips"] == 0 else 0.0 for p in h["pairs"]]
    ch = [p["chips"] / max(1, p["hands"]) for p in h["pairs"]]
    out.append(f"\n## Head-to-head probe vs base (200h, 30200-30239)\nprobe MATCH WINS {sum(r):g}/{len(r)} ({100*sum(r)/len(r):.0f}%); chips/hand {sum(ch)/len(ch):+.2f} ± {sd(ch)/math.sqrt(len(ch)):.2f}; forfeits {sum(p['ff_a'] for p in h['pairs'])}/{sum(p['ff_b'] for p in h['pairs'])}")
txt = "\n".join(out); print(txt)
if len(sys.argv) > 1: Path(sys.argv[1]).write_text(txt + "\n")
