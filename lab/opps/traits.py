"""The opponent profile table from recorded matches (lab only; records: lab.opps.record).

Every column is a rate hits / n over the opponent's opportunities, measured from our side:

  vpip            calls or raises preflop, per hand where it had a preflop decision
  pfr             raises preflop, same denominator
  fold_flop/turn/river   folds, per decision facing our bet or raise on that street
  bet_river       bets the river when not facing a bet (a lead, or after our check). The book
                  labels this column "bets river when checked to"; its numbers use this definition
  bet_river_after_check   the same, only after we checked to it (in position)
  weak_river_bet  per river bet or raise shown down: the shown hand is weak, meaning its
                  strength against a random hand on that board is below 0.5 (dead cards:
                  its hole cards, the board and both discards)
  wtsd            reaches showdown, per hand that saw a flop
  discard_lowest  per showdown: its discard was its lowest card (ties count as lowest)

These match the book's profile table (docs/book/pokerbot_book.html section 2.8); the fixture
test tests/test_opp_traits.py holds them to it.

    .venv/bin/python -m lab.opps.traits logs/records/*.json.gz
    .venv/bin/python -m lab.opps.traits logs/records/*.json.gz --fixtures tests/fixtures/opp_records
        (also writes the first 2 pairs of each file there: the X0 test fixtures)
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from bot.cards import rank_of
from lab.opps import record
from lab.stats import mean_se

COLUMNS = ("vpip", "pfr", "fold_flop", "fold_turn", "fold_river", "bet_river",
           "weak_river_bet", "wtsd", "discard_lowest", "bet_river_after_check")
FOLD_COLUMN = {1: "fold_flop", 2: "fold_turn", 3: "fold_river"}
SHORT = {"fold_flop": "f_flop", "fold_turn": "f_turn", "fold_river": "f_river",
         "bet_river": "bet_rv", "weak_river_bet": "weak_rv", "discard_lowest": "disc_low",
         "bet_river_after_check": "bet_rv_ck"}
BETTING = frozenset("FKCR")       # S (a discard or other special choice) is not a bet


@dataclass(frozen=True)
class Rate:
    hits: int = 0
    n: int = 0

    @property
    def value(self) -> Optional[float]:
        return self.hits / self.n if self.n else None

    def add(self, hit: bool) -> "Rate":
        return Rate(self.hits + int(hit), self.n + 1)


@dataclass(frozen=True)
class OppDecision:
    """One betting decision of the opponent, with the context the traits need."""
    street: int          # 0 preflop .. 3 river
    kind: str            # F K C R
    facing: bool         # facing our bet or raise on this street (postflop; preflop: False)
    checked_to: bool     # postflop: we checked earlier on this street and it is not facing


def opp_decisions(rec: dict) -> list[OppDecision]:
    """The opponent's betting decisions in one recorded hand, oldest first."""
    out: list[OppDecision] = []
    street, facing, we_checked = -1, False, False
    for st, who, kind, _amount, _choice in rec["h"]:
        if kind not in BETTING:
            continue
        if st != street:
            street, facing, we_checked = st, False, False
        if who == "m":
            if kind == "R":
                facing = True
            elif kind == "K":
                we_checked = True
            continue
        post = st > 0
        out.append(OppDecision(st, kind, post and facing, post and we_checked and not facing))
        if kind == "R":
            facing = False
    return out


@lru_cache(maxsize=None)
def _strength(hole: tuple[int, ...], board: tuple[int, ...], dead: tuple[int, ...]) -> float:
    """Showdown share of `hole` against every 2-card hand from the unseen cards."""
    from bot.equity import equity_exact
    return equity_exact(hole, board, dead=dead, opp_cards=2, runout=0).equity


def is_weak(rec: dict) -> bool:
    dead = tuple(sorted(c for _who, cards in rec["rv"] for c in cards))
    return _strength(tuple(rec["opp"]), tuple(rec["board"]), dead) < 0.5


def _opp_discard(rec: dict) -> Optional[int]:
    cards = [cards for who, cards in rec["rv"] if who == "o"]
    return cards[0][0] if cards and len(cards[0]) == 1 else None


def add_hand(rec: dict, p: dict[str, Rate]) -> None:
    """Add one recorded hand to the running rates `p` (column -> Rate)."""
    ds = opp_decisions(rec)
    pre = [d for d in ds if d.street == 0]
    if pre:
        p["vpip"] = p["vpip"].add(any(d.kind in "CR" for d in pre))
        p["pfr"] = p["pfr"].add(any(d.kind == "R" for d in pre))
    for d in ds:
        if d.street in FOLD_COLUMN and d.facing:
            col = FOLD_COLUMN[d.street]
            p[col] = p[col].add(d.kind == "F")
        if d.street == 3 and not d.facing:
            p["bet_river"] = p["bet_river"].add(d.kind == "R")
            if d.checked_to:
                p["bet_river_after_check"] = p["bet_river_after_check"].add(d.kind == "R")
    shown = len(rec["opp"]) == 2 and len(rec["board"]) == 5
    if len(rec["board"]) >= 3:
        p["wtsd"] = p["wtsd"].add(shown)
    if not shown:
        return
    if any(d.street == 3 and d.kind == "R" for d in ds):
        p["weak_river_bet"] = p["weak_river_bet"].add(is_weak(rec))
    disc = _opp_discard(rec)
    if disc is not None:
        p["discard_lowest"] = p["discard_lowest"].add(
            rank_of(disc) <= min(rank_of(x) for x in rec["opp"]))


def profile(hands: Iterable[dict]) -> dict[str, Rate]:
    p = {col: Rate() for col in COLUMNS}
    for rec in hands:
        add_hand(rec, p)
    return p


def match_summary(data: dict) -> dict:
    """Our chips/hand ± SE over duplicate pairs and our mean match score."""
    per_pair, scores = [], []
    for pair in data["pairs"]:
        hands = sum(len(m["hands"]) for m in pair["matches"])
        per_pair.append(sum(m["chips"] for m in pair["matches"]) / max(1, hands))
        scores += [m["score"] for m in pair["matches"]]
    cph, se = mean_se(per_pair)
    return {"chips_per_hand": cph, "se": se, "wins": sum(scores) / max(1, len(scores)),
            "matches": len(scores)}


# --------------------------------------------------------------------------- output

def _cell(rate: Rate) -> str:
    return "  —  " if rate.n == 0 else f"{rate.value:4.0%} "


def format_table(rows: list[tuple[str, dict, dict]]) -> str:
    """rows: (opponent, match_summary, profile)."""
    head = (f"{'opponent':18}{'chips/hand':>15}{'wins':>6} "
            + " ".join(f"{SHORT.get(c, c[:8]):>8}" for c in COLUMNS))
    lines = [head]
    for name, s, p in rows:
        lines.append(f"{name:18}{s['chips_per_hand']:+8.2f} ± {s['se']:4.2f}{s['wins']:6.0%} "
                     + " ".join(f"{_cell(p[c]):>8}" for c in COLUMNS))
    lines.append("(n per column) " + "; ".join(
        f"{name}: " + ",".join(str(p[c].n) for c in COLUMNS) for name, _s, p in rows))
    return "\n".join(lines)


def write_fixture(data: dict, out_dir: Path, pairs: int = 2) -> Path:
    """The first `pairs` duplicate pairs of a recording, as a test fixture."""
    small = dict(data, pairs=data["pairs"][:pairs])
    path = out_dir / f"{data['opponent']}.json.gz"
    record.save(path, small)
    return path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fixtures", default=None, help="also write test fixtures (2 pairs each) here")
    args = ap.parse_args(argv)
    rows = []
    for f in args.files:
        data = record.load(Path(f))
        rows.append((data["opponent"], match_summary(data), profile(record.iter_hands(data))))
        if args.fixtures:
            write_fixture(data, Path(args.fixtures))
    print(format_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
