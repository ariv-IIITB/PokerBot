"""OPUS1: tables per the pre-registered rule (reports/opus1_prereg.md). MATCH WINS first.
  .venv/bin/python panav-bots/loop/opus1/agg.py > panav-bots/loop/results/opus1/val_tables.md
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from summ import load, win, cph, mse, one   # noqa: E402

R = Path("panav-bots/loop/results/opus1/val")
S1 = ["new_trapper", "new_eqrandom", "lakshya1", "trapper", "conv_opp3", "eqtag", "potctl", "polar", "new_geometric", "new_exploiter",
      "new_lag", "new_minraise", "new_rules", "conv_opp4", "s2_rollout", "s5_preflop", "s7_solver", "s10_regret", "light3b", "tilt"]
OTHER = [b for b in S1 if b not in ("new_trapper", "new_eqrandom")]


def row(tag):
    v = R / f"v2_{tag}.json"
    if not v.exists():
        return None
    fk, fn = (int(x) for x in (R / f"v2_{tag}.fired").read_text().split())
    C, _ = load(v)
    a = R / f"A_{tag}.json"
    if fk == 0:
        B = C                                   # identical code path: delta 0 by construction (pre-registered cost rule)
    elif a.exists():
        B, _ = load(a)
    else:
        return dict(pending=True, fk=fk, fn=fn)
    ks = sorted(set(C) & set(B))
    dw = [100 * (win(C[k]) - win(B[k])) for k in ks]
    dc = [cph(C[k]) - cph(B[k]) for k in ks]
    return dict(n=len(ks), wc=sum(win(C[k]) for k in ks), wa=sum(win(B[k]) for k in ks),
                cc=mse([cph(C[k]) for k in ks]), ca=mse([cph(B[k]) for k in ks]), dw=dw, dc=dc, fk=fk, fn=fn,
                same=fk == 0, ff=sum(C[k].get("ff_a", 0) for k in ks))


def fmt(name, r):
    if r is None:
        return f"| {name} | not run yet |"
    if r.get("pending"):
        return f"| {name} | exit fired {r['fk']}/{r['fn']} legs; A run pending |"
    n = r["n"]
    w = mse(r["dw"]) if not r["same"] else (0.0, 0.0)
    c = mse(r["dc"]) if not r["same"] else (0.0, 0.0)
    flag = "" if r["same"] else (" **DOWN>2SE**" if w[0] < -2 * w[1] else "")
    note = "identical (never fired)" if r["same"] else f"{r['fk']}/{r['fn']}"
    return (f"| {name} | {r['wa']:g}/{n} ({100*r['wa']/n:.0f}%) | {r['wc']:g}/{n} ({100*r['wc']/n:.0f}%) | {w[0]:+.1f} ± {w[1]:.1f}{flag} | "
            f"{r['ca'][0]:+.2f} | {r['cc'][0]:+.2f} | {c[0]:+.3f} ± {c[1]:.3f} | {note} | {r['ff']} |")


HDR = "| bot | A wins | v2 wins | dwin pp ± SE | A ch/h | v2 ch/h | dchips ± SE | exit legs | ff |\n|---|---|---|---|---|---|---|---|---|"


def pooled(names, pre):
    rs = [row(f"{pre}_{b}") for b in names]
    rs = [r for r in rs if r and not r.get("pending")]
    if not rs:
        return "no data"
    # pooled: per-seed mean over bots of the per-bot delta (seeds are shared across bots), SE over seeds
    n = min(r["n"] for r in rs)
    dws = [sum(r["dw"][i] for r in rs) / len(rs) for i in range(n)]
    dcs = [sum(r["dc"][i] for r in rs) / len(rs) for i in range(n)]
    wa = sum(r["wa"] for r in rs); wc = sum(r["wc"] for r in rs); N = sum(r["n"] for r in rs)
    w, c = mse(dws), mse(dcs)
    return (f"{len(rs)} bots, {N} matches: A {wa:g}/{N} ({100*wa/N:.1f}%) -> v2 {wc:g}/{N} ({100*wc/N:.1f}%); "
            f"dwin {w[0]:+.2f} ± {w[1]:.2f} pp; dchips {c[0]:+.3f} ± {c[1]:.3f}")


if __name__ == "__main__":
    print("## Stage 1 (200-hand legs, 40 pairs, seeds 50000-50039)\n" + HDR)
    for b in S1:
        print(fmt(b, row(f"S1_{b}")))
    print("\nPooled other 18 bots (b): " + pooled(OTHER, "S1"))
    print("Pooled all 20 bots: " + pooled(S1, "S1"))
    print("\n## Stage 2 (500-hand legs, 24 pairs, seeds 51000-51023)\n" + HDR)
    for b in ("lakshya1", "new_eqrandom"):
        print(fmt(b, row(f"S2_{b}")))
    h = R / "h2h_v2_A.json"
    if h.exists():
        s = one(h)
        p = 0.5; se = 100 * math.sqrt(p * (1 - p) / s["n"])
        print(f"\n## Head-to-head v2 vs A (200h, seeds 52000-52039)\nv2 {s['w']:g}/{s['n']} ({s['pct']:.1f}%), {s['cph']:+.3f} ± {s['se']:.3f} ch/h, "
              f"forfeits {s['ff'][0]}/{s['ff'][1]}; 2-SE floor {50 - 2 * se:.1f}%")
