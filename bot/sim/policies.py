"""Generic decision policies for special (non-betting) steps, built on the rollout layer.

Every policy takes the Reconstruction of the current position, the legal set, a numpy
Generator, a time budget and a parameter dict, and returns an Action.

  discard / draw / swap / choose / hook   PIMC over the legal choices (capped)
  bounty (chosen rank)                    PIMC with full rollouts (the bounty pays at the end)
  auction bid                             prize value V = E[chips | we win it] - E[chips |
                                          they win it], by simulation; bid = fraction x V,
                                          shaded by auction type
  market quote                            fair value of the quantity over the worlds
  expose                                  show the lowest-ranked card(s)
  peek                                    yes if free, or if the cost is below
                                          info_bonus x pot (rollouts can't value information)
"""
from __future__ import annotations

from typing import Any

import numpy as np

from bot.actions import Action, LegalActions
from bot.game.payoffs import market_value
from bot.sim.replay import Reconstruction
from bot.sim.rollout import pimc

DEFAULTS: dict[str, Any] = {
    "max_candidates": 16,
    "bid_fraction": 0.9,
    "bid_shade": {"second_price": 1.0, "first_price": 0.55, "all_pay": 0.35},
    "quote_skew": 0.0,
    "info_bonus": 0.03,
    "pimc_worlds": 400,
}


def _parse_idx(choice: str) -> list[int]:
    return [] if choice in ("none", "") else [int(x) for x in choice.split("+")]


def _candidates(legal: LegalActions, rng, cap: int) -> list[Action]:
    opts = list(legal.special.choices)
    if len(opts) > cap:
        keep = [o for o in opts if o == "none"]
        rest = [o for o in opts if o != "none"]
        pick = rng.choice(len(rest), size=cap - len(keep), replace=False)
        opts = keep + [rest[i] for i in sorted(pick)]
    return [Action.special(o) for o in opts]


def step_of(rec: Reconstruction):
    st = rec.state
    return st.rules.program[st.pc]


def decide_special(rec: Reconstruction, legal: LegalActions, rng: np.random.Generator,
                   budget_s: float, params: dict | None = None,
                   stats: dict | None = None) -> Action:
    """stats (optional dict) receives "rollouts" and "worlds" for benchmarking."""
    p = dict(DEFAULTS)
    p.update(params or {})
    p["_stats"] = stats if stats is not None else {}
    step = step_of(rec)
    kind = step.type_name
    sp = legal.special
    if kind == "auction" and sp.is_range:
        return auction_bid(rec, legal, rng, budget_s, step, p)
    if kind == "market" and sp.is_range:
        return market_quote(rec, legal, rng, budget_s, step, p)
    if kind == "expose":
        return expose_lowest(rec, legal)
    if kind == "peek":
        cost = getattr(step, "cost", 0)
        ok = "yes" in sp.choices and (cost == 0 or cost <= p["info_bonus"] * rec.state.pot)
        return Action.special("yes" if ok else "no")
    if sp.is_range:
        return Action.special(sp.default())
    if len(sp.choices) == 1:
        return Action.special(sp.choices[0])
    res = pimc(rec, _candidates(legal, rng, int(p["max_candidates"])), rng, budget_s,
               max_worlds=int(p["pimc_worlds"]), inference=p.get("_inference"))
    p["_stats"].update(rollouts=res.rollouts, worlds=res.worlds)
    return res.best


def expose_lowest(rec: Reconstruction, legal: LegalActions) -> Action:
    st, me = rec.state, rec.me
    hole = [rec.mapping.get(t, t) for t in st.hole[me]]

    def strength(choice: str) -> int:
        return sum(hole[i] // 4 for i in _parse_idx(choice) if hole[i] >= 0)
    return Action.special(min(legal.special.choices, key=strength))


def auction_bid(rec, legal, rng, budget_s, step, p) -> Action:
    me = rec.me
    sp = legal.special

    def award_to(winner):
        def apply(w, _a):
            step.award(w, winner)
            w.step_state.order = []        # no more bids in this world
        return apply

    worlds = int(p["pimc_worlds"])
    inf = p.get("_inference")
    win = pimc(rec, [Action.special("win")], rng, budget_s / 2, max_worlds=worlds,
               apply_fn=award_to(me), inference=inf)
    lose = pimc(rec, [Action.special("lose")], rng, budget_s / 2, max_worlds=worlds,
                apply_fn=award_to(1 - me), inference=inf)
    value = win.values["win"] - lose.values["lose"]
    p["_stats"].update(rollouts=win.rollouts + lose.rollouts, worlds=win.worlds + lose.worlds)
    shade = p["bid_shade"].get(step.kind, 0.5)
    bid = int(round(max(0.0, value) * p["bid_fraction"] * shade))
    return Action.special(str(min(max(bid, sp.lo), sp.hi)))


def market_quote(rec, legal, rng, budget_s, step, p) -> Action:
    """Fair value of the market quantity: complete the board in many worlds."""
    import time
    t0 = time.perf_counter()
    sp = legal.special
    st = rec.state
    need = max(0, st.rules.board_cards - len(st.board) - (len(st.boards[0]) if st.boards else 0))
    vals = []
    cap = min(4000, 10 * int(p["pimc_worlds"]))
    while len(vals) < cap and (len(vals) < min(50, cap) or time.perf_counter() - t0 < budget_s):
        w = rec.world(rng)
        board = list(w.board) + (w.boards[0] if w.boards else [])
        vals.append(market_value(step.quantity, board + w.deck[:need]))
    fair = float(np.mean(vals)) + p["quote_skew"]
    return Action.special(str(min(max(int(round(fair)), sp.lo), sp.hi)))
