"""OPUS1: split a bot's paired v2-A delta by whether the exit fired in that pair (either leg).
  .venv/bin/python panav-bots/loop/opus1/fired_split.py TAG   (e.g. S1_new_lag)"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from summ import load, win, cph, mse
R = Path("panav-bots/loop/results/opus1/val"); tag = sys.argv[1]
C, _ = load(R / f"v2_{tag}.json"); B, _ = load(R / f"A_{tag}.json")
fired = {}
for f in (R / f"err_v2_{tag}").glob("*.err"):
    s = int(f.stem.split("_")[0][4:])
    m = re.findall(r"'probeexit': \{[^}]*'events': \[([^\]]*)\]", f.read_text(errors="replace"))
    fired[s] = fired.get(s, False) or bool(m and "'no'" in m[-1])
for lab, sel in (("fired", True), ("not fired", False)):
    ks = [k for k in C if k in B and fired.get(k, False) == sel]
    if len(ks) < 2: print(lab, len(ks)); continue
    dw = mse([100 * (win(C[k]) - win(B[k])) for k in ks]); dc = mse([cph(C[k]) - cph(B[k]) for k in ks])
    print(f"{tag} {lab:9s} pairs {len(ks):2d}: v2 {sum(win(C[k]) for k in ks):g} A {sum(win(B[k]) for k in ks):g}  dwin {dw[0]:+.1f}±{dw[1]:.1f}  dchips {dc[0]:+.3f}±{dc[1]:.3f}")
