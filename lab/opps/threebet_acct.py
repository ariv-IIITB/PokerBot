"""Chip accounting for pots where the opponent 3-bets preflop and we see a flop (O3 task 6).

    .venv/bin/python -m lab.opps.threebet_acct BRAIN OPPONENT PAIRS [--first-seed N]

A 3-bet pot here = the opponent raises preflop after we raised, and the hand reaches the flop. Those hands
get the ending label "3bp:<ending>" in the usual lab.eval accounting (we_fold / opp_fold / showdown_*, by
street); every other hand keeps its normal label. Runs in one process (the relabelling is a monkeypatch of
`track.ending_of`), locks off. Lab-only.
"""
from __future__ import annotations

import argparse

from bot.actions import RAISE
from lab.opps import track

_orig = track.ending_of


def _opp_three_bet(h) -> bool:
    mine = False
    for r in h.history:
        if r.street != 0 or r.action.kind != RAISE:
            continue
        if r.actor == "me":
            mine = True
        elif mine:
            return True
    return False


def ending_3bp(h):
    end, street = _orig(h)
    if len(h.board) >= 3 and _opp_three_bet(h):
        return "3bp:" + end, street
    return end, street


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("brain")
    ap.add_argument("opponent")
    ap.add_argument("pairs", type=int)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--variant", default="discard_holdem")
    args = ap.parse_args(argv)
    track.ending_of = ending_3bp
    from lab.eval import main as eval_main
    return eval_main([args.brain, "--pool", args.opponent, "--pairs", str(args.pairs), "--first-seed",
                      str(args.first_seed), "--locks", "off", "--report", "accounting", "--processes", "1",
                      "--variant", args.variant])


if __name__ == "__main__":
    raise SystemExit(main())
