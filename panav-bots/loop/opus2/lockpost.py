"""Post-hoc lock replay on recorded per-hand deltas (exact for the win indicator: before the lock the
lock build plays the same code as A; once net > 2 x hands_left it cannot lose).
  .venv/bin/python panav-bots/loop/opus2/lockpost.py RESULT.json [...] [--k 2] [--order split|adjacent|asis]"""
import json, sys, math

def lock_outcome(deltas, total, k=2):
    net = 0
    for i, d in enumerate(deltas):
        left = total - i                     # hands not finished at the start of hand i+1
        if net > k * left:
            return True, i + 1, net
        net += d
    return False, None, net

def score(x):
    return 1.0 if x > 0 else 0.5 if x == 0 else 0.0

def analyse(pairs, total, k=2, bleed=1.5):
    rows = []
    for p in pairs:
        if p.get("ff_a") or p.get("ff_b") or p["hands"] < total:
            fired, at, net = False, None, p["chips"]
        else:
            fired, at, net = lock_outcome(p["deltas"], total, k)
        sa = score(p["chips"])
        if fired:
            sc = 1.0
            cc = net - bleed * (total - at + 1)       # chips: locked net minus the expected check/fold bleed
        else:
            sc, cc = sa, p["chips"]
        rows.append(dict(seed=p["seed"], fired=fired, at=at, sa=sa, sc=sc, ca=p["chips"], cc=cc))
    return rows

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for f in args:
        d = json.load(open(f)); rows = analyse(d["pairs"], d["hands"])
        n = len(rows); wa = sum(r["sa"] for r in rows); wc = sum(r["sc"] for r in rows)
        fired = [r for r in rows if r["fired"]]
        print(f"{f.split('/')[-1]}: n {n} A wins {wa:g} -> lock {wc:g} ; fired {len(fired)} at {[r['at'] for r in fired]} "
              f"flipped {sum(1 for r in fired if r['sa'] < 1)} ; dchips/hand {sum(r['cc']-r['ca'] for r in rows)/n/d['hands']:+.3f}")
