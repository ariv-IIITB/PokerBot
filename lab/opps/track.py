"""Per-decision and per-hand bookkeeping for in-process brains, merged over many matches.

A Tracker wraps the brains of one match (lab.harness.play_pair(..., track=True) does this) and
records, for each player:

  profile   (street, facing) -> action kind counts       "what does it do when checked to?"
  spots     spot label -> action kind counts             the labels TARGETS in lab/eval.py uses
  acct      (how the hand ended, street) -> [hands, chips]    "where do the chips go?"

Everything is plain dicts of ints so results cross process boundaries. `merge` adds them up and
`format_profile` / `format_accounting` print the blocks lab.eval and the lab.opps CLIs show.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from bot.actions import FOLD, SPECIAL
from bot.protocol import HandEnd

STREET = {0: "pre", 3: "flop", 4: "turn", 5: "river"}
STREET_BY_INDEX = ("pre", "flop", "turn", "river")


def spot_of(state, legal) -> Optional[str]:
    """The strategic spot of a betting decision (None if it is not one we label)."""
    h = state.hand
    if h is None or legal.can_special:
        return None
    street = STREET.get(len(h.board))
    bb = state.match.bb
    if street is None:
        return None
    if street == "pre":
        if h.tocall > 0 and (h.opp_bet or 0) > bb:
            return "pre/vs_raise"
        if h.tocall > 0 and h.seat == 0:
            return "pre/open"
        return "pre/bb_vs_limp" if h.tocall == 0 else None
    if h.tocall > 0:
        return f"{street}/vs_bet"
    if street == "flop":
        raised_pre = any(r.actor == "me" and r.action.kind == "R" and r.street == 0
                         for r in h.history)
        return "flop/cbet" if raised_pre else "flop/checked_to"
    return f"{street}/bet"


def ending_of(h) -> tuple[str, str]:
    """(how the hand ended for us, street): we_fold / opp_fold / showdown_win / showdown_loss /
    showdown_chop / other."""
    delta = h.delta or 0
    if h.opp_cards:
        return ("showdown_win" if delta > 0 else "showdown_loss" if delta < 0
                else "showdown_chop"), "river"
    last = h.history[-1] if h.history else None      # a fold is always the last action
    if last is not None and last.action.kind == FOLD:
        return ("we_fold" if last.actor == "me" else "opp_fold"), STREET_BY_INDEX[min(last.street, 3)]
    return "other", STREET.get(len(h.board), "?")


def _empty() -> dict:
    return {"profile": defaultdict(lambda: defaultdict(int)),
            "spots": defaultdict(lambda: defaultdict(int)),
            "acct": defaultdict(lambda: [0, 0])}


class Tracker:
    """Wraps brains; `data` holds {"A": ..., "B": ...} (plain dicts after to_plain())."""

    def __init__(self) -> None:
        self.data = {"A": _empty(), "B": _empty()}

    def wrap(self, player, label: str):
        """Hook one in-process player (no-op for subprocess players)."""
        bot = getattr(player, "bot", None)
        if bot is None:
            return player
        brain, d = bot.brain, self.data[label]
        decide, observe = brain.decide, brain.observe

        def tracked_decide(state, legal, budget):
            a = decide(state, legal, budget)
            h = state.hand
            if a.kind != SPECIAL and h is not None:
                street = STREET.get(len(h.board), "?")
                facing = "vs_bet" if h.tocall > 0 else "checked_to"
                if street == "pre":
                    facing = ("vs_raise" if h.tocall > 1 and (h.opp_bet or 0) > 2 else
                              "open" if h.seat == 0 and (h.my_bet or 0) == 1 else "other")
                d["profile"][(street, facing)][a.kind] += 1
                spot = spot_of(state, legal)
                if spot:
                    d["spots"][spot][a.kind] += 1
            return a

        def tracked_observe(state, msg):
            observe(state, msg)
            if isinstance(msg, HandEnd) and state.hand is not None:
                cell = d["acct"][ending_of(state.hand)]
                cell[0] += 1
                cell[1] += msg.delta

        brain.decide, brain.observe = tracked_decide, tracked_observe
        return player

    def hook(self, a_player, b_player) -> None:
        self.wrap(a_player, "A")
        self.wrap(b_player, "B")

    def to_plain(self) -> dict:
        return {who: {"profile": {k: dict(v) for k, v in d["profile"].items()},
                      "spots": {k: dict(v) for k, v in d["spots"].items()},
                      "acct": {k: list(v) for k, v in d["acct"].items()}}
                for who, d in self.data.items()}


def merge(parts: list[dict]) -> dict:
    """Add up Tracker.to_plain() results (e.g. one per duplicate pair)."""
    out = {who: _empty() for who in ("A", "B")}
    for part in parts:
        for who, d in part.items():
            for k, counts in d["profile"].items():
                for kind, n in counts.items():
                    out[who]["profile"][k][kind] += n
            for k, counts in d["spots"].items():
                for kind, n in counts.items():
                    out[who]["spots"][k][kind] += n
            for k, (n, chips) in d["acct"].items():
                out[who]["acct"][k][0] += n
                out[who]["acct"][k][1] += chips
    return out


def _pct(counts: dict, kinds) -> str:
    total = sum(counts.values())
    return " ".join(f"{k}={counts.get(k, 0) / total:.0%}" for k in kinds)


def format_profile(merged: dict, names: dict[str, str]) -> str:
    lines = []
    for who in ("A", "B"):
        lines.append(f"--- profile: {names[who]}")
        for (street, facing), counts in sorted(merged[who]["profile"].items()):
            lines.append(f"  {street:5} {facing:10} n={sum(counts.values()):5} "
                         + _pct(counts, sorted(counts)))
    return "\n".join(lines)


def format_accounting(merged: dict, names: dict[str, str], hands: int) -> str:
    lines = []
    for who in ("A", "B"):
        acct = merged[who]["acct"]
        total = sum(c for _, c in acct.values())
        lines.append(f"--- accounting: {names[who]} ({total:+d} chips over {hands} hands, "
                     f"{total / max(1, hands):+.2f}/hand)")
        for (end, street), (n, chips) in sorted(acct.items()):
            lines.append(f"  {end:14} {street:6} hands={n:6} chips={chips:+8d} "
                         f"({chips / max(1, hands):+.3f}/hand)")
    return "\n".join(lines)
