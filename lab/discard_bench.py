"""Decision quality of the one-card discard, without any betting: how much of the pot does each
discard rule win at showdown?

    .venv/bin/python -m lab.discard_bench [--deals 3000] [--seed 0] [--budget-ms 6]

For each random deal (our 3 hole cards, a flop, the opponent's 3 hole cards, turn and river)
every mode picks a card to drop on exactly what we may see (our cards, the flop), then the
board is run out and the showdown scored: share = 1 win, 0.5 tie, 0 loss. The same deals and the
same opponent for every mode, so the differences are paired. The opponent keeps its pair by a
rule chosen per column:
  best     the pair making the best five-card hand with the flop (the usual rule)
  lowest   the rules' fallback (drops its lowest card)
  random   a uniformly random card
The modes are the brain's `discard_mode` values. "pimc" runs the generic rollout policy with
rollouts that discard sensibly; "pimc-old" is the Phase D behaviour (rollouts discard at random). Output: mean share per mode and opponent, and the
paired difference to "lowest" with its standard error.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import numpy as np

from bot.actions import LegalActions, SpecialOption
from bot.cards import FULL_DECK
from bot.game.rules_spec import to_rules
from bot.game.steps.cards import fallback_discard
from bot.protocol import ActRequest, BoardUpdate, HandStart, HoleCards, MatchInfo, OppAction
from bot.actions import Action
from bot.sim.discard import opponent_keeps
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.state import GameState
from variant.spec import load_catalog

MODES = ("fast", "pimc", "pimc-old", "highest2", "lowest")
OPPONENTS = ("best", "lowest", "random")
DISCARD = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))


def reconstruction(rules, hole, flop, rng):
    """Our view at the discard: button, limp-check preflop, check-check on the flop."""
    st = GameState()
    st.apply(MatchInfo(hands=400, sb=1, bb=2, stack=200))
    st.apply(HandStart(0, 0, 200, 200))
    st.apply(HoleCards(tuple(hole)))
    st.apply(ActRequest(3, 1, 199, 198, LegalActions(fold=True, call=True, raise_min=4,
                                                      raise_max=200), None, 1, 2))
    st.record_my_action(Action.call())
    st.apply(OppAction(Action.check()))
    st.apply(BoardUpdate(1, tuple(flop)))
    st.apply(OppAction(Action.check()))
    st.apply(ActRequest(4, 0, 198, 198, LegalActions(check=True, raise_min=2, raise_max=198), None, 0, 0))
    st.record_my_action(Action.check())
    st.apply(ActRequest(4, 0, 198, 198, DISCARD, None, 0, 0))
    return reconstruct(rules, st.hand, rng)


def opp_keep(kind: str, ev, opp3, flop, rng) -> list[int]:
    if kind == "best":
        return opponent_keeps(ev, np.array([opp3], dtype=np.intp), np.array(flop, dtype=np.intp))[0].tolist()
    drop = opp3.index(fallback_discard(opp3)) if kind == "lowest" else int(rng.integers(3))
    return [c for i, c in enumerate(opp3) if i != drop]


def run(deals: int, seed: int, budget_s: float, modes=MODES) -> dict:
    rules = to_rules(load_catalog()["discard_holdem"])
    ev = rules.evaluator
    rng = np.random.default_rng(seed)
    shares = {(m, o): np.zeros(deals) for m in modes for o in OPPONENTS}
    spent = {m: 0.0 for m in modes}
    for d in range(deals):
        cards = rng.permutation(FULL_DECK)[:11].tolist()
        mine, flop, opp3, turn, river = cards[:3], cards[3:6], cards[6:9], cards[9], cards[10]
        rec = reconstruction(rules, mine, flop, rng)
        board = flop + [turn, river]
        picks = {}
        for m in modes:
            t0 = time.perf_counter()
            rec.smart_discard = m != "pimc-old"          # pimc-old: the Phase D rollouts (random discards)
            a = decide_special(rec, DISCARD, rng, budget_s,
                               {"discard_mode": "pimc" if m.startswith("pimc") else m, "pimc_worlds": 400})
            spent[m] += time.perf_counter() - t0
            picks[m] = int(a.choice)
        for o in OPPONENTS:
            kept_o = opp_keep(o, ev, opp3, flop, rng)
            for m in modes:
                kept = [c for i, c in enumerate(mine) if i != picks[m]]
                sh = ev.shares_batch(np.array([kept], dtype=np.intp), np.array([kept_o], dtype=np.intp),
                                     [np.array([board], dtype=np.intp)])[0]
                shares[(m, o)][d] = sh
    return {"shares": shares, "ms": {m: 1000 * spent[m] / deals for m in modes}}


def report(res: dict, modes=MODES) -> str:
    lines = [f"{'mode':9}{'ms/call':>8}  " + "".join(f"{'vs ' + o:<26}" for o in OPPONENTS)]
    for m in modes:
        cells = []
        for o in OPPONENTS:
            x, base = res["shares"][(m, o)], res["shares"][("lowest", o)]
            d = x - base
            se = d.std(ddof=1) / len(d) ** 0.5 if len(d) > 1 else 0.0
            cells.append(f"{x.mean():.4f} ({d.mean():+.4f}±{se:.4f})")
        lines.append(f"{m:9}{res['ms'][m]:>8.1f}  " + "".join(f"{c:<26}" for c in cells))
    lines.append("(share of the pot at showdown; in brackets: paired difference to 'lowest' ± SE)")
    if "pimc-old" in modes and "fast" in modes:
        d = [res["shares"][("fast", o)] - res["shares"][("pimc-old", o)] for o in OPPONENTS]
        cells = [f"{x.mean():+.4f}±{x.std(ddof=1) / len(x) ** 0.5:.4f}" for x in d]
        lines.append("fast minus pimc-old, paired: " + ", ".join(f"vs {o} {c}" for o, c in zip(OPPONENTS, cells)))
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="One-card discard decision quality.")
    ap.add_argument("--deals", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget-ms", type=float, default=6.0)
    ap.add_argument("--modes", default=",".join(MODES))
    args = ap.parse_args(argv)
    modes = tuple(m for m in args.modes.split(",") if m)
    if "lowest" not in modes:
        modes += ("lowest",)
    print(report(run(args.deals, args.seed, args.budget_ms / 1000.0, modes), modes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
