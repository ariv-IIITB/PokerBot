"""Paired arms test: every bot plays every opponent on the same seeds (two-leg matches), resumable.

    PYTHONPATH=. python arms_run.py OUT.jsonl --bots d_xfinal,d_xfin_rnr --opps d_v16,tier3x --pairs 40 \
        --hands 500 --bank 75 --seed 140000
One JSON line per match: {bot, opp, seed, chips, hands, forfeits, errors}; already-played matches are skipped."""
import argparse
import json
from multiprocessing import Pool

from lab.harness import load_variant, play_pair
from lab.players import PlayerSpec


def one(args):
    a, b, seed, hands, bank = args
    try:
        p = play_pair(PlayerSpec.brain(a), PlayerSpec.brain(b), load_variant("discard_holdem"), seed, hands,
                      time_bank_s=bank)
        return {"bot": a, "opp": b, "seed": seed, "chips": list(p.a_chips), "hands": p.hands,
                "forfeits": list(p.forfeits), "errors": list(p.errors)}
    except Exception as e:
        return {"bot": a, "opp": b, "seed": seed, "error": repr(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bots", required=True)
    ap.add_argument("--opps", required=True)
    ap.add_argument("--pairs", type=int, default=40)
    ap.add_argument("--hands", type=int, default=500)
    ap.add_argument("--bank", type=float, default=75.0)
    ap.add_argument("--seed", type=int, default=140000)
    ap.add_argument("--processes", type=int, default=4)
    a = ap.parse_args()
    done = set()
    try:
        for line in open(a.out):
            r = json.loads(line)
            if "error" not in r:
                done.add((r["bot"], r["opp"], r["seed"]))
    except FileNotFoundError:
        pass
    bots, opps = a.bots.split(","), a.opps.split(",")
    tasks = [(b, o, a.seed + i, a.hands, a.bank) for i in range(a.pairs) for o in opps for b in bots
             if (b, o, a.seed + i) not in done]
    with Pool(a.processes) as pool, open(a.out, "a") as f:
        for r in pool.imap_unordered(one, tasks):
            f.write(json.dumps(r) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
