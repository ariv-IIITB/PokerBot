"""wins.py DIR BASE CAND: match wins (a match = one duplicate pair; chips>0 win, ==0 draw .5) W/N per bot, base vs cand."""
import json, glob, os, sys
d, tb, tc = sys.argv[1:4]
def w(f):
    p = json.load(open(f))["pairs"]; return sum(1.0 if x["chips"] > 0 else 0.5 if x["chips"] == 0 else 0 for x in p), len(p)
tw = [0, 0, 0]
for f in sorted(glob.glob(f"{d}/{tb}/*.json")):
    g = f.replace(f"/{tb}/", f"/{tc}/")
    if not os.path.exists(g): continue
    (a, n), (b, _) = w(f), w(g); tw[0] += a; tw[1] += b; tw[2] += n
    print(f"{os.path.basename(f)[:-5]:14s} base {a:5.1f}/{n} {100*a/n:4.0f}%   cand {b:5.1f}/{n} {100*b/n:4.0f}%")
print(f"POOLED base {tw[0]:.1f}/{tw[2]} {100*tw[0]/tw[2]:.1f}%  cand {tw[1]:.1f}/{tw[2]} {100*tw[1]/tw[2]:.1f}%  diff {100*(tw[1]-tw[0])/tw[2]:+.1f} pp")
