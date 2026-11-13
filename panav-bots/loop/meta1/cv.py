"""Oracle ceiling (split-half corrected) and leave-one-bot-out gating rules.  usage: cv.py [N=100] [metric=dwin|dchips]"""
import json, sys, math, itertools, random
sys.path.insert(0, "panav-bots/loop/meta1")
from effects import table, SW
N = sys.argv[1] if len(sys.argv) > 1 else "100"
METRIC = sys.argv[2] if len(sys.argv) > 2 else "dwin"
EXCL = {"s1_ranges"}                       # degenerate folding bot: we win 24/24, no room to measure
FEATS = ["fb_all", "fb_flop", "fb_turn", "fb_river", "fold_all", "fold_flop", "fold_turn", "fold_river", "raise_fb", "big_share",
         "pre_open", "pre_fold_open", "pre_fold_vs_raise", "pre_3bet", "xr", "sd_value", "sd_big_value"]
tr = json.load(open("panav-bots/loop/results/meta1/traits.json"))
T = table()
SCALE = 100 if METRIC == "dwin" else 1     # report win points in pp

def eff(bot, s):
    x = T[bot][s]; return SCALE * x[METRIC], SCALE * x[METRIC + "_se"]

def oracle(s, bots):
    full = []; split = []; rows = []
    for b in bots:
        x = T[b][s]; l = x["dw_list"] if METRIC == "dwin" else x["dc_list"]
        e = SCALE * sum(l) / len(l)
        full.append(max(e, 0.0))
        A = l[0::2]; B = l[1::2]; mA = sum(A) / len(A); mB = sum(B) / len(B)
        split.append(SCALE * ((mB if mA > 0 else 0.0) + (mA if mB > 0 else 0.0)) / 2)
    n = len(bots)
    return sum(full) / n, sum(split) / n, sum(SCALE * sum((T[b][s]["dw_list"] if METRIC == "dwin" else T[b][s]["dc_list"])) / len(T[b][s]["dw_list"]) for b in bots) / n

def conds(train, s, feats):
    """all single monotone conditions (feature, sign, threshold) with their train gain"""
    out = []
    for f in feats:
        vals = [(tr[b][N]["rate"][f], eff(b, s)[0]) for b in train if tr[b][N]["rate"][f] == tr[b][N]["rate"][f]]
        if len(vals) < 8: continue
        xs = sorted(set(v for v, _ in vals))
        for sign in (1, -1):
            for i in range(len(xs) - 1):
                th = (xs[i] + xs[i + 1]) / 2
                g = sum(e for v, e in vals if sign * v >= sign * th)
                out.append((g, f, sign, th))
    return sorted(out, reverse=True)

def on(b, c):
    _, f, sign, th = c
    v = tr[b][N]["rate"][f]
    return v == v and sign * v >= sign * th

def lobo(s, bots, two=False):
    gains = []; picks = []
    for h in bots:
        train = [b for b in bots if b != h]
        cs = conds(train, s, FEATS)
        best = None
        if cs and cs[0][0] > 0:
            best = ("1", cs[0])
            if two:
                top = cs[:12]; bg = cs[0][0]; bp = None
                for c1, c2 in itertools.combinations(top, 2):
                    g = sum(eff(b, s)[0] for b in train if on(b, c1) and on(b, c2))
                    if g > bg: bg, bp = g, (c1, c2)
                if bp: best = ("2", bp)
        if best is None: gains.append(0.0); picks.append(None); continue
        if best[0] == "1": o = on(h, best[1])
        else: o = on(h, best[1][0]) and on(h, best[1][1])
        gains.append(eff(h, s)[0] if o else 0.0); picks.append((best[1][1:] if best[0] == "1" else [c[1:] for c in best[1]]))
    return gains, picks

def main():
    print(f"metric={METRIC} (pp for dwin, chips/hand for dchips) trait window N={N}")
    for s in SW:
        bots = [b for b in T if s in T[b] and b not in EXCL and b in tr]
        if len(bots) < 12: print(s, "only", len(bots), "bots done"); continue
        n = len(bots)
        alw = [eff(b, s)[0] for b in bots]
        sd = lambda g: math.sqrt(sum((x - sum(g) / n) ** 2 for x in g) / (n - 1) / n)
        orc_full, orc_split, always_on = oracle(s, bots)
        g1, p1 = lobo(s, bots); g2, p2 = lobo(s, bots, two=True)
        print(f"\n{s}: {n} bots | always-on {always_on:+.2f} ± {sd(alw):.2f} | oracle(hindsight) {orc_full:+.2f} | oracle(split-half, noise-corrected) {orc_split:+.2f}")
        print(f"   LOBO 1-feature {sum(g1)/n:+.2f} ± {sd(g1):.2f}   LOBO 2-feature {sum(g2)/n:+.2f} ± {sd(g2):.2f}   (always-off = 0)")
        from collections import Counter
        print("   LOBO picks:", Counter(str((p[0], p[1])) if p else "off" for p in p1).most_common(3))

if __name__ == "__main__": main()
