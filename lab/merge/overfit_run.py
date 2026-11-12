"""Overfitting check: final vs v3 against held-out bots + a polarised probe, paired seeds.

Writes one JSON line per two-leg match: {bot, opp, seed, chips, hands, forfeits, errors}.
Run from the repo root with PYTHONPATH=. (uses lab.harness.play_pair)."""
import json
import sys
from multiprocessing import Pool

from lab.harness import load_variant, play_pair
from lab.players import PlayerSpec

BOTS = ["d_xfinal", "d_xv3"]
OPPS = ["d_v16", "d_xprobe_polar", "d_v6", "d_conv_opp4", "d_new_geometric", "d_new_eqrandom"]
FIRST_SEED = 130000


def one(args):
    a, b, seed = args
    try:
        p = play_pair(PlayerSpec.brain(a), PlayerSpec.brain(b), load_variant("discard_holdem"), seed, 200,
                      time_bank_s=30.0)
        return {"bot": a, "opp": b, "seed": seed, "chips": list(p.a_chips), "hands": p.hands,
                "forfeits": list(p.forfeits), "errors": list(p.errors)}
    except Exception as e:  # keep the run going; record the failure
        return {"bot": a, "opp": b, "seed": seed, "error": repr(e)}


def main():
    pairs, out = int(sys.argv[1]), sys.argv[2]
    done = set()
    try:
        for line in open(out):
            r = json.loads(line)
            if "error" not in r:
                done.add((r["bot"], r["opp"], r["seed"]))
    except FileNotFoundError:
        pass
    tasks = [(bot, opp, FIRST_SEED + i) for opp in OPPS for i in range(pairs) for bot in BOTS
             if (bot, opp, FIRST_SEED + i) not in done]
    with Pool(4) as pool, open(out, "a") as f:
        for r in pool.imap_unordered(one, tasks):
            f.write(json.dumps(r) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
