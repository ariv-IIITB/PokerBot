"""Per-opponent effect table: cand - base per switch (paired by seed). usage: effects.py [out.json]"""
import json, sys, math
from pathlib import Path
R = Path("panav-bots/loop/results/meta1")
SW = ["probe", "foldall", "valuebet", "potfold"]

def load(p):
    d = json.load(open(p)); return {r["seed"]: r for r in d["pairs"]}

def win(r): return 1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0
def ch(r): return r["chips"] / max(1, r["hands"])

def se(x):
    n = len(x); m = sum(x) / n
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1) / n) if n > 1 else float("nan")

def table():
    out = {}
    for bp in sorted(R.glob("base_*.json")):
        bot = bp.stem[5:]; b = load(bp)
        row = {"base": {"chips": sum(map(ch, b.values())) / len(b), "win": sum(map(win, b.values())) / len(b), "n": len(b)}}
        for s in SW:
            cp = R / f"{s}_{bot}.json"
            if not cp.exists(): continue
            c = load(cp); seeds = sorted(set(b) & set(c))
            dw = [win(c[k]) - win(b[k]) for k in seeds]; dc = [ch(c[k]) - ch(b[k]) for k in seeds]
            row[s] = {"dwin": sum(dw) / len(dw), "dwin_se": se(dw), "dchips": sum(dc) / len(dc), "dchips_se": se(dc), "n": len(seeds),
                      "dw_list": dw, "dc_list": dc, "seeds": seeds, "cand_win": sum(win(c[k]) for k in seeds) / len(seeds)}
        out[bot] = row
    return out

if __name__ == "__main__":
    t = table()
    if len(sys.argv) > 1: json.dump(t, open(sys.argv[1], "w"))
    print(f"{'bot':14s} base(w%,ch) | " + " | ".join(f"{s:>22s}" for s in SW))
    for bot, r in t.items():
        cells = []
        for s in SW:
            x = r.get(s)
            cells.append(f"{100*x['dwin']:+5.1f}±{100*x['dwin_se']:4.1f}pp {x['dchips']:+.2f}±{x['dchips_se']:.2f}" if x else " " * 22)
        print(f"{bot:14s} {100*r['base']['win']:4.0f}% {r['base']['chips']:+.2f} | " + " | ".join(cells))
    for s in SW:
        xs = [r[s] for r in t.values() if s in r]
        if xs: print(s, "mean over", len(xs), "bots: dwin %+.2fpp dchips %+.3f" % (100*sum(x['dwin'] for x in xs)/len(xs), sum(x['dchips'] for x in xs)/len(xs)))
