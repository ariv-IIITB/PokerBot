"""Tier 2 (current defaults) vs Tier 2 with a config override, duplicate deals, locks off.
usage: python -m tools.e_eval.head2head PAIRS 'json override of the opponent' [variant]"""
import json, sys
from lab.harness import run_duplicate, load_variant
from lab.players import PlayerSpec

if __name__ == "__main__":
    pairs, cfg = int(sys.argv[1]), json.loads(sys.argv[2])
    v = load_variant(sys.argv[3] if len(sys.argv) > 3 else "discard_holdem")
    a = PlayerSpec.brain("tier2", {"lock_enabled": False}, label="tier2-now")
    b = PlayerSpec.brain("tier2", dict(cfg, lock_enabled=False), label="tier2-ref")
    print(run_duplicate(a, b, v, seeds=range(pairs), hands=400).summary(), flush=True)
