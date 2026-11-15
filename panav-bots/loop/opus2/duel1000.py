"""OPUS2: realistic Stage-2 match = ONE process per bot for the whole match (protocol.pdf: init total_hands is
the match length, 400 / ~1000; duplicates are inside the match, the bot is not told which deals pair up).

  PYTHONPATH=. .venv/bin/python panav-bots/loop/opus2/duel1000.py A.py B.py --seeds 24 --first-seed 60000 \
      --hands 1000 --order split --processes 4 --out OUT.json
--order split: deals 0..N/2-1, then the same deals again with seats swapped (deal d = h mod N/2).
--order adjacent: hand 2k and 2k+1 share deal k (the alternating button swaps the seats).
A match = one duplicate pair; A wins if its total chips > 0 (draw 0.5). Bank = 0.15 s/hand (150 s / 1000 hands).
Per-hand deltas are stored so that endgame rules can be replayed post hoc.
"""
from __future__ import annotations
import argparse, json, math, multiprocessing as mp, sys, time
from pathlib import Path
from bot.game.rules_spec import to_rules
from bot.game.runner import LazyRng
from bot.protocol import MatchEnd, MatchInfo
from lab.engine import Forfeit, Hand, MatchResult, Seat, _safe_notify, deck_for, SB, BB
from lab.harness import load_variant
from lab.players import SubprocessPlayer


def make(path):
    p = Path(path).resolve()
    return SubprocessPlayer([sys.executable, str(p)], cwd=str(p.parent), name=p.stem, protocol="pokerbots")


def play(players, seed, hands, order, bank, clock_scale=1.0):
    rules = to_rules(load_variant("discard_holdem"))
    seats = [Seat(p, bank, clock_scale, 5.0) for p in players]
    info = MatchInfo(hands, bank, rules.small_blind, rules.big_blind, rules.starting_stack)
    start = rules.starting_stack
    res = MatchResult([0, 0], 0, [0, 0]); res.forfeit = None; res.forfeit_reason = None
    half = hands // 2
    try:
        for i in (0, 1):
            _safe_notify(seats, i, info)
        for h in range(hands):
            if order == "split":
                deal = h % half if h < 2 * half else h
                sbp = (h % 2) ^ (1 if half <= h < 2 * half else 0)
            else:
                deal = h // 2
                sbp = h % 2
            by_role = [seats[sbp], seats[1 - sbp]]
            hand = Hand(rules, by_role, [start, start], deck_for(seed, deal, rules.deck), h, "fold",
                        rng=LazyRng([seed, deal, 1]))
            try:
                r = hand.play()
            except Forfeit as f:
                res.forfeit = sbp if f.role == SB else 1 - sbp
                res.forfeit_reason = f.reason
                break
            d0 = r.deltas[SB] if sbp == 0 else r.deltas[BB]
            res.chips[0] += d0; res.chips[1] -= d0
            res.hand_deltas.append(d0)
            res.hands_played += 1
        for i in (0, 1):
            _safe_notify(seats, i, MatchEnd())
    finally:
        for s in seats:
            try:
                s.player.close()
            except Exception:
                pass
    return res, [s.bank for s in seats], [s.worst_decision_s for s in seats]


def one(args):
    a, b, seed, hands, order, bank, swap = args
    t = time.time()
    ps = [make(a), make(b)]
    if swap:                      # A sits in slot 1 (it gets the other first-hand seat)
        ps = ps[::-1]
    r, banks, worst = play(ps, seed, hands, order, bank)
    ia = 1 if swap else 0
    deltas = r.hand_deltas if ia == 0 else [-x for x in r.hand_deltas]
    ff = r.forfeit
    return dict(seed=seed, chips=sum(deltas), hands=r.hands_played, deltas=deltas,
                ff_a=int(ff == ia), ff_b=int(ff is not None and ff != ia), reason=r.forfeit_reason,
                bank_left_a=banks[ia], worst_a=worst[ia], secs=round(time.time() - t, 1))


def summarize(rs, label=""):
    n = len(rs)
    per = [r["chips"] / max(1, r["hands"]) for r in rs]
    m = sum(per) / n
    se = math.sqrt(sum((x - m) ** 2 for x in per) / (n - 1) / n) if n > 1 else float("nan")
    w = sum(1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0 for r in rs)
    return (f"{label} MATCH WINS {w:g}/{n} ({100*w/n:.1f}%) chips/hand {m:+.3f} ± {se:.3f} forfeits A/B "
            f"{sum(r['ff_a'] for r in rs)}/{sum(r['ff_b'] for r in rs)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--first-seed", type=int, default=60000)
    ap.add_argument("--hands", type=int, default=1000)
    ap.add_argument("--order", default="split", choices=["split", "adjacent"])
    ap.add_argument("--processes", type=int, default=4)
    ap.add_argument("--bank", type=float, default=None)
    ap.add_argument("--out")
    a = ap.parse_args()
    bank = a.bank if a.bank is not None else 0.15 * a.hands
    tasks = [(a.a, a.b, s, a.hands, a.order, bank, s % 2 == 1) for s in range(a.first_seed, a.first_seed + a.seeds)]
    with mp.get_context("spawn").Pool(min(a.processes, len(tasks))) as pool:
        rs = pool.map(one, tasks, chunksize=1)
    print(summarize(rs, f"{Path(a.a).stem} vs {Path(a.b).parent.name if Path(a.b).name == 'bot.py' else Path(a.b).stem}:"),
          f"| min bank left A {min(r['bank_left_a'] for r in rs):.1f}s worst reply {max(r['worst_a'] for r in rs):.2f}s", flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(dict(a=a.a, b=a.b, hands=a.hands, order=a.order, pairs=rs)))


if __name__ == "__main__":
    main()
