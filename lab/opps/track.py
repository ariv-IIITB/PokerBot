"""Per-decision and per-hand bookkeeping for in-process brains, merged over many matches.

A Tracker wraps the brains of one match (lab.harness.play_pair(..., track=True) does this) and
records, for each player:

  profile   (street, facing) -> action kind counts       "what does it do when checked to?"
  spots     spot label -> action kind counts             the labels TARGETS in lab/eval.py uses
  acct      (how the hand ended, street) -> [hands, chips]    "where do the chips go?"
  lines     (preflop line, how it ended, street) -> [hands, chips]   e.g. "3bet_opp": they 3-bet, we called
  stats     the brain's own int counters (`brain.stats`, e.g. Tier 3's t3_fallbacks), summed

Everything is plain dicts of ints so results cross process boundaries. `merge` adds them up and
`format_profile` / `format_accounting` / `format_stats` print the blocks lab.eval and the lab.opps CLIs show.
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


def preflop_line(h) -> str:
    """Who made the preflop raises (the BB is not a raise here): limp, open_me/open_opp (one raise),
    3bet_me/3bet_opp (two; `3bet_opp` = we opened, they re-raised), 4bet+ (three or more)."""
    raises = [r.actor for r in h.history if r.street == 0 and r.action.kind == "R"]
    if not raises:
        return "limp"
    if len(raises) >= 3:
        return "4bet+"
    return ("open_" if len(raises) == 1 else "3bet_") + ("me" if raises[-1] == "me" else "opp")


def _empty() -> dict:
    return {"profile": defaultdict(lambda: defaultdict(int)),
            "spots": defaultdict(lambda: defaultdict(int)),
            "acct": defaultdict(lambda: [0, 0]),
            "lines": defaultdict(lambda: [0, 0]),
            "stats": defaultdict(int)}


class Tracker:
    """Wraps brains; `data` holds {"A": ..., "B": ...} (plain dicts after to_plain())."""

    def __init__(self) -> None:
        self.data = {"A": _empty(), "B": _empty()}
        self.brains: dict[str, list] = {"A": [], "B": []}

    def wrap(self, player, label: str):
        """Hook one in-process player (no-op for subprocess players)."""
        bot = getattr(player, "bot", None)
        if bot is None:
            return player
        brain, d = bot.brain, self.data[label]
        self.brains[label].append(brain)
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
                    line = preflop_line(h)
                    if line in ("3bet_opp", "3bet_me", "4bet+") and (street != "pre" or h.tocall > 0):
                        d["spots"][f"{line}:{spot}"][a.kind] += 1    # how we play re-raised pots
            return a

        def tracked_observe(state, msg):
            observe(state, msg)
            if isinstance(msg, HandEnd) and state.hand is not None:
                end = ending_of(state.hand)
                for cell in (d["acct"][end], d["lines"][(preflop_line(state.hand),) + end]):
                    cell[0] += 1
                    cell[1] += msg.delta

        brain.decide, brain.observe = tracked_decide, tracked_observe
        return player

    def hook(self, a_player, b_player) -> None:
        self.wrap(a_player, "A")
        self.wrap(b_player, "B")

    def brain_stats(self, label: str) -> dict:
        """The int counters in `brain.stats`, summed over the brains wrapped as `label`."""
        out: dict = defaultdict(int)
        for brain in self.brains[label]:
            for k, v in (getattr(brain, "stats", None) or {}).items():
                if isinstance(v, int) and not isinstance(v, bool):
                    out[k] += v
        return dict(out)

    def to_plain(self) -> dict:
        return {who: {"profile": {k: dict(v) for k, v in d["profile"].items()},
                      "spots": {k: dict(v) for k, v in d["spots"].items()},
                      "acct": {k: list(v) for k, v in d["acct"].items()},
                      "lines": {k: list(v) for k, v in d["lines"].items()},
                      "stats": self.brain_stats(who)}
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
            for key in ("acct", "lines"):
                for k, (n, chips) in d.get(key, {}).items():
                    out[who][key][k][0] += n
                    out[who][key][k][1] += chips
            for k, n in d.get("stats", {}).items():
                out[who]["stats"][k] += n
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


def _per_pair(parts: list[dict], who: str, pair_hands: float):
    """{bucket: array of chips/hand, one entry per duplicate pair} and the same for all river buckets."""
    import numpy as np
    keys = sorted({k for part in parts for k in part[who]["acct"]})
    per = {k: np.array([part[who]["acct"].get(k, (0, 0))[1] for part in parts], float) / pair_hands for k in keys}
    per[("river", "all")] = sum((v for (e, st), v in per.items() if st == "river"), np.zeros(len(parts)))
    return per


def format_accounting(merged: dict, names: dict[str, str], hands: int,
                      parts: Optional[list[dict]] = None) -> str:
    """With `parts` (one Tracker.to_plain() per duplicate pair) each bucket also gets `+-SE` (the standard
    error of its chips/hand over pairs) and one extra line sums every river bucket (showdown + we_fold
    + opp_fold on the river): the number to read when a change folds or calls more, as the showdown
    buckets alone can be gamed by folding."""
    lines = []
    for who in ("A", "B"):
        acct = merged[who]["acct"]
        total = sum(c for _, c in acct.values())
        lines.append(f"--- accounting: {names[who]} ({total:+d} chips over {hands} hands, "
                     f"{total / max(1, hands):+.2f}/hand)")
        per = _per_pair(parts, who, hands / len(parts)) if parts and len(parts) > 1 else {}
        se = lambda k: (f" +-{per[k].std(ddof=1) / len(per[k]) ** 0.5:.3f}" if k in per else "")
        for (end, street), (n, chips) in sorted(acct.items()):
            lines.append(f"  {end:14} {street:6} hands={n:6} chips={chips:+8d} "
                         f"({chips / max(1, hands):+.3f}{se((end, street))}/hand)")
        if per:
            k = ("river", "all")
            lines.append(f"  {'river-all':14} {'river':6} hands={sum(n for (e, st), (n, _) in acct.items() if st == 'river'):6} "
                         f"chips={sum(c for (e, st), (_, c) in acct.items() if st == 'river'):+8d} "
                         f"({per[k].mean():+.3f}{se(k)}/hand over {len(parts)} pairs)")
    return "\n".join(lines)


def format_lines(merged: dict, names: dict[str, str], hands: int,
                 parts: Optional[list[dict]] = None) -> str:
    """Chips by preflop line (who raised preflop), then by how the hand ended and on which street.
    `+-SE` over duplicate pairs when `parts` is given."""
    import numpy as np
    lines = []
    for who in ("A", "B"):
        lines.append(f"--- preflop lines: {names[who]}")
        cells = merged[who]["lines"]
        ph = hands / max(1, len(parts or [1]))

        def se(match) -> str:
            if not parts or len(parts) < 2:
                return ""
            v = np.array([sum(c for k, (_, c) in part[who].get("lines", {}).items() if match(k))
                          for part in parts], float) / ph
            return f" +-{v.std(ddof=1) / len(v) ** 0.5:.3f}"
        for line in sorted({k[0] for k in cells}):
            sub = {k: v for k, v in cells.items() if k[0] == line}
            n, c = sum(v[0] for v in sub.values()), sum(v[1] for v in sub.values())
            lines.append(f"  {line:9} hands={n:6} chips={c:+8d} ({c / max(1, hands):+.3f}"
                         f"{se(lambda k, l=line: k[0] == l)}/hand, {c / max(1, n):+.2f}/pot)")
            for k, (n, c) in sorted(sub.items()):
                lines.append(f"      {k[1]:14} {k[2]:6} hands={n:6} chips={c:+8d} "
                             f"({c / max(1, hands):+.3f}{se(lambda x, kk=k: x == kk)}/hand, {c / max(1, n):+.2f}/pot)")
        for k, counts in sorted(merged[who]["spots"].items()):
            if ":" in k:
                lines.append(f"  spot {k:24} n={sum(counts.values()):5} " + _pct(counts, sorted(counts)))
    return "\n".join(lines)


def format_stats(merged: dict, names: dict[str, str]) -> str:
    """The brains' own counters (only players whose brain keeps a `stats` dict)."""
    lines = []
    for who in ("A", "B"):
        st = merged[who].get("stats") or {}
        if st:
            lines.append(f"--- brain stats: {names[who]}: "
                         + " ".join(f"{k}={v}" for k, v in sorted(st.items())))
    return "\n".join(lines) if lines else "--- brain stats: none"
