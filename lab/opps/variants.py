"""Tier 2 config variants vs one opponent (both locks off). Usage: python3 -m lab.opps.variants OPP SEEDS [variant ...]"""
import json, sys
from lab.harness import run_duplicate, load_variant
from lab.players import PlayerSpec

VARIANTS = {
    "base": {},
    "no_inference": {"inference": False},
    "no_pressure": {"bet_pressure": 0.0},
    "looser_call": {"call_margin": -0.04, "bet_pressure": 0.0},
    "raise_pre": {"raise_equity": [0.55, 0.68, 0.70, 0.74]},
    "combo": {"bet_pressure": 0.0, "call_margin": -0.04, "raise_equity": [0.55, 0.68, 0.70, 0.74]},
}
if __name__ == "__main__":
    opp, n = sys.argv[1], int(sys.argv[2])
    names = sys.argv[3:] or list(VARIANTS)
    v = load_variant("lab/opps/holdem_100bb.json")
    cfg_b = {"fold_out": False} if opp == "opp3" else None
    for name in names:
        cfg = dict(VARIANTS[name], lock_enabled=False)
        r = run_duplicate(PlayerSpec.brain("tier2", cfg, label=f"tier2[{name}]"),
                          PlayerSpec.brain(opp, cfg_b, label=opp), v, seeds=range(n), hands=400)
        print(r.summary(), flush=True)
