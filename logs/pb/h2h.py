"""PB step 3: a tier4p point head-to-head vs Tier 3, both endgame locks off (lab.eval cannot
turn the opponent's lock off). Output: one lab.eval-style summary line.

    .venv/bin/python logs/pb/h2h.py 'tier4p:{...}' FIRST_SEED PAIRS OUT
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lab.eval import parse_brain  # noqa: E402
from lab.harness import load_variant, run_duplicate  # noqa: E402
from lab.players import PlayerSpec  # noqa: E402

if __name__ == "__main__":
    brain, seed, pairs, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    a = parse_brain(brain, "off")
    b = PlayerSpec.brain("tier3", {"lock_enabled": False}, label="tier3-nolock")
    rep = run_duplicate(a, b, load_variant("discard_holdem"), seeds=range(seed, seed + pairs),
                        hands=400, processes=3)
    print(rep.summary(), flush=True)
    Path(out).write_text(rep.summary() + "\n")
