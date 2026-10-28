"""Match runner: plays duplicate-deal heads-up matches between two bots.

Examples (run from the project root):
  python -m sim.match --a brain --b tag --hands 400 --matches 10
  python -m sim.match --a brain --b station --matches 20 --procs 4
  python -m sim.match --a brain --b mypkg.mymod:MyBot --seed 7

Bot spec: a name from the registry (random call fold shove maniac tag nit lag station),
'brain' / 'brain:fast' (our bot), or 'module.path:ClassName'.
Duplicate modes: --dup bot  (each bot plays the same cards from both seats; default)
                 --dup seat (same cards stay with the seat; bots swap seats)
"""
import argparse
import importlib
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pb.brain import Brain  # noqa: E402
from sim.baselines import REGISTRY  # noqa: E402
from sim.engine import Engine, Seat  # noqa: E402


def load_bot(spec, seed=1):
    if spec == "brain":
        return Brain(seed=seed)
    if spec == "brain:fast":
        return Brain(seed=seed, max_samples=300)
    if spec == "brain:nofold":
        return Brain(seed=seed, fold_out=False)
    if spec in REGISTRY:
        return REGISTRY[spec](seed=seed)
    if ":" in spec:
        mod, cls = spec.split(":")
        return getattr(importlib.import_module(mod), cls)()
    raise SystemExit("unknown bot spec: %s" % spec)


def play_match(args):
    spec_a, spec_b, hands, seed, bank, dup = args
    a, b = load_bot(spec_a, seed * 2 + 1), load_bot(spec_b, seed * 2 + 2)
    bank_total = bank * hands / 400.0
    for bot in (a, b):
        bot.new_match(hands, bank)
    sa, sb = Seat(a, bank_total), Seat(b, bank_total)
    eng = Engine()
    rng = np.random.default_rng(seed)
    bk = {"a": 0, "b": 0}
    pairs = []
    hand_no = 0
    forfeit = None
    for _ in range(hands // 2):
        deck = rng.permutation(52)
        hole_a, hole_b, board = deck[0:2], deck[2:4], deck[4:9]
        pair = 0
        for run in (0, 1):
            if run == 0:
                seats, holes, a_seat = [sa, sb], [hole_a, hole_b], 0
            else:
                seats = [sb, sa]
                holes = [hole_b, hole_a] if dup == "bot" else [hole_a, hole_b]
                a_seat = 1
            bankrolls = [bk["a"], bk["b"]] if run == 0 else [bk["b"], bk["a"]]
            d = eng.play_hand(seats, 0, holes, board, hand_no, hands - hand_no, bankrolls)
            da = d[a_seat]
            bk["a"] += da
            bk["b"] -= da
            pair += da
            hand_no += 1
        pairs.append(pair)
        if sa.timed_out or sb.timed_out:
            forfeit = "a" if sa.timed_out else "b"
            break
    chips = bk["a"]
    if forfeit == "a":
        chips = -abs(chips) - 1
    elif forfeit == "b":
        chips = abs(chips) + 1
    return {
        "chips": chips, "pairs": pairs, "hands": hand_no,
        "forfeit": forfeit,
        "time_a": sa.used, "time_b": sb.used,
        "max_a": sa.max_decision, "max_b": sb.max_decision,
        "crash_a": sa.crashes + getattr(a, "crashes", 0), "crash_b": sb.crashes + getattr(b, "crashes", 0),
        "illegal_a": sa.illegal, "illegal_b": sb.illegal,
    }


def summarize(spec_a, spec_b, results, hands):
    n = len(results)
    wins = sum(r["chips"] > 0 for r in results)
    losses = sum(r["chips"] < 0 for r in results)
    ties = n - wins - losses
    allpairs = np.array([p for r in results for p in r["pairs"]], dtype=float)
    mean_pair = allpairs.mean() if len(allpairs) else 0.0
    se = allpairs.std(ddof=1) / math.sqrt(len(allpairs)) if len(allpairs) > 1 else float("nan")
    per100 = mean_pair / 2 * 100
    ci = 1.96 * se / 2 * 100
    tot_hands = sum(r["hands"] for r in results)
    print("\n=== %s  vs  %s | %d matches x %d hands ===" % (spec_a, spec_b, n, hands))
    print("match record (A): %d W - %d L - %d T   (win rate %.0f%%)" % (wins, losses, ties, 100.0 * wins / max(n, 1)))
    print("A chips/100 hands: %+.1f  (95%% CI +-%.1f)   mean chips/match: %+.1f" %
          (per100, ci, float(np.mean([r["chips"] for r in results]))))
    print("A time: %.2fs/match (%.1f ms/hand), slowest decision %.0f ms | B time: %.2fs/match" % (
        np.mean([r["time_a"] for r in results]),
        1000 * sum(r["time_a"] for r in results) / max(tot_hands, 1),
        1000 * max(r["max_a"] for r in results), np.mean([r["time_b"] for r in results])))
    print("faults A: crashes %d, illegal %d, forfeits %d | B: crashes %d, illegal %d, forfeits %d" % (
        sum(r["crash_a"] for r in results), sum(r["illegal_a"] for r in results),
        sum(r["forfeit"] == "a" for r in results),
        sum(r["crash_b"] for r in results), sum(r["illegal_b"] for r in results),
        sum(r["forfeit"] == "b" for r in results)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default="brain")
    ap.add_argument("--b", default="tag")
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--matches", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bank", type=float, default=60.0, help="time bank seconds per 400 hands")
    ap.add_argument("--dup", choices=("bot", "seat"), default="bot")
    ap.add_argument("--procs", type=int, default=1)
    a = ap.parse_args()
    if a.hands % 2:
        a.hands += 1
    jobs = [(a.a, a.b, a.hands, a.seed * 1000 + i, a.bank, a.dup) for i in range(a.matches)]
    t = time.time()
    if a.procs > 1:
        with Pool(a.procs) as p:
            results = p.map(play_match, jobs)
    else:
        results = []
        for j in jobs:
            results.append(play_match(j))
            r = results[-1]
            print("  match seed %d: A %+d chips%s" % (j[3], r["chips"], "  (FORFEIT %s)" % r["forfeit"] if r["forfeit"] else ""),
                  flush=True)
    summarize(a.a, a.b, results, a.hands)
    print("wall time %.1fs" % (time.time() - t))


if __name__ == "__main__":
    main()
