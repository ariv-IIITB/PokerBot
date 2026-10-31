"""The CFR blueprint at run time (docs/cfr/ABSTRACTION_V1.md sections 2, 3, 5, 7).

`Blueprint` holds the trained table (uint8 probabilities per row) and its metadata (parameters,
history strings, bucket cuts). `abstract_view` replays the hand's real betting on real chips with
the contract's menu formulas, turning every action into an abstract label (an off-menu raise is
translated pseudo-harmonically between its two neighbouring menu sizes). `bucket` computes our
bucket on the current street. Nothing here reads files: the table comes from the embedded
artifact (bot.artifacts) or is handed in by the lab.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from bot import abstraction as A
from bot.artifacts import decode_npy
from bot.state import ME, HandState

LABELS = ("F", "C", "H", "P", "R", "A")
BET_FRACTIONS = (("H", 0.5), ("P", 1.0))
OPEN_MULT, RERAISE_MULT = 2.5, 3.0
BETTING = frozenset("FKCR")
VERSION = "v1"


@dataclass(frozen=True)
class Params:
    stack: int
    sb: int
    bb: int
    max_raises: int
    blind_counts_as_raise: bool
    sized_raise_cap: int


class Blueprint:
    """The table and what is needed to key it."""

    def __init__(self, meta: dict, probs: np.ndarray) -> None:
        if meta.get("version") != VERSION:
            raise ValueError(f"blueprint version {meta.get('version')!r}, runtime {VERSION}")
        self.meta = meta
        self.params = Params(**meta["params"])
        self.probs = np.asarray(probs, dtype=np.uint8)
        self.n_buckets = [int(x) for x in meta["n_buckets"]]
        self.offset = [int(x) for x in meta["offset"]]
        self.ids = [{h: i for i, h in enumerate(hs)} for hs in meta["histories"]]
        self.cuts = meta["thresholds"]
        if self.probs.shape[0] != int(meta["rows"]):
            raise ValueError("blueprint table does not match its metadata")

    @classmethod
    def from_artifact(cls, art: dict) -> "Blueprint":
        """{"meta": {...}, "files": {"probs": base64 .npy}} (tools/embed_data.py)."""
        return cls(art["meta"], decode_npy(art["files"]["probs"]))

    @classmethod
    def from_npz(cls, data) -> "Blueprint":
        """A loaded lab export (np.load of lab/cfr/fast/train.py's blueprint_v1.npz)."""
        return cls(json.loads(str(data["meta"])), data["probs"])

    def lookup(self, street: int, history: str, bucket: int, n_actions: int) -> Optional[np.ndarray]:
        """The action probabilities (uint8, n_actions) or None (unknown history, untrained row)."""
        hid = self.ids[street].get(history)
        if hid is None or not 0 <= bucket < self.n_buckets[street]:
            return None
        row = self.probs[self.offset[street] + hid * self.n_buckets[street] + bucket, :n_actions]
        return row if int(row.sum()) > 0 else None


# --------------------------------------------------------------------------- the real betting

@dataclass
class Street:
    """Betting state of the current street on real chips; seats 0 = button, 1 = big blind."""
    street: int
    bets: list
    stacks: list
    raises: int
    last_raise: int

    def to_call(self, seat: int) -> int:
        return max(self.bets) - self.bets[seat]

    def pot(self, par: Params) -> int:
        return 2 * par.stack - sum(self.stacks)


def menu(st: Street, seat: int, par: Params) -> list[tuple[str, str, Optional[int]]]:
    """(label, kind, raise-to) for the abstract actions at this real state (contract section 2;
    the same formulas as lab/cfr/fast/tree.actions)."""
    q = 1 - seat
    to_call = st.to_call(seat)
    out: list[tuple[str, str, Optional[int]]] = []
    if to_call > 0:
        out.append(("F", "F", None))
    out.append(("C", "C" if to_call > 0 else "K", None))
    if not (st.stacks[seat] > to_call and st.stacks[q] > 0 and st.raises < par.max_raises):
        return out
    high = max(st.bets)
    rmax = st.bets[seat] + st.stacks[seat]
    rmin = min(high + max(st.last_raise, par.bb), rmax)
    if st.raises >= par.sized_raise_cap:
        wanted: list = []
    elif high == 0:
        pot = st.pot(par)
        wanted = [(lab, st.bets[seat] + to_call + f * (pot + to_call)) for lab, f in BET_FRACTIONS]
    else:
        mult = RERAISE_MULT if st.street == 0 and high > par.bb else OPEN_MULT
        wanted = [("R", mult * high)]
    seen: set = set()
    for lab, x in wanted:
        amt = min(max(int(round(x)), rmin), rmax)
        if amt == rmax or amt in seen:
            continue
        seen.add(amt)
        out.append((lab, "R", amt))
    out.append(("A", "R", rmax))
    return out


def _translate(amount: int, st: Street, seat: int, acts: list, par: Params, u: float) -> Optional[str]:
    """Label for an observed raise-to `amount`: exact menu amount, else pseudo-harmonic between
    the neighbouring menu raises as pot fractions (Ganzfried & Sandholm). None if the menu has no
    raise of that kind (a sized raise past the abstraction's cap)."""
    raises = [(lab, amt) for lab, kind, amt in acts if kind == "R"]
    for lab, amt in raises:
        if amt == amount:
            return lab
    sized = [(lab, amt) for lab, amt in raises if lab != "A"]
    rmax = raises[-1][1] if raises else None
    if not sized:
        return "A" if rmax is not None and amount >= rmax else None
    to_call = st.to_call(seat)
    denom = max(1, st.pot(par) + to_call)

    def frac(amt: int) -> float:
        return (amt - st.bets[seat] - to_call) / denom

    sizes = [(lab, frac(amt)) for lab, amt in raises]
    x = frac(amount)
    if x <= sizes[0][1]:
        return sizes[0][0]
    for (la, a), (lb, b) in zip(sizes, sizes[1:]):
        if a <= x <= b:
            p_a = (b - x) * (1 + a) / ((b - a) * (1 + x)) if b > a else 1.0
            return la if u < p_a else lb
    return sizes[-1][0]


@dataclass
class View:
    """The abstract picture of a decision."""
    history: str
    street: Street
    seat: int
    translated: int = 0                 # actions mapped to a label by translation
    trail: list = field(default_factory=list)


def abstract_view(h: HandState, par: Params, rng=None) -> Optional[View]:
    """Replay the hand's betting; None if it leaves the abstract tree (a miss)."""
    me = h.seat
    st = Street(0, [par.sb, par.bb], [par.stack - par.sb, par.stack - par.bb],
                1 if par.blind_counts_as_raise else 0, par.bb)
    hist, translated = "", 0
    for r in h.history:
        kind = r.action.kind
        if kind not in BETTING:
            continue
        if r.street != st.street:                    # the previous street closed
            hist += "/"
            st = Street(r.street, [0, 0], list(st.stacks), 0, par.bb)
        seat = me if r.actor == ME else 1 - me
        acts = menu(st, seat, par)
        if kind == "F":
            label = "F"
        elif kind in ("K", "C"):
            label = "C"
        else:
            u = rng.random() if rng is not None else 0.5
            label = _translate(int(r.action.amount), st, seat, acts, par, u)
            if label is None:
                return None
            exact = any(amt == r.action.amount for _l, k, amt in acts if k == "R")
            translated += int(not exact)
        if label not in {lab for lab, _k, _a in acts}:
            return None
        hist += label
        # apply the real action to the real chips
        if kind == "C":
            pay = min(st.to_call(seat), st.stacks[seat])
            st.bets[seat] += pay
            st.stacks[seat] -= pay
        elif kind == "R":
            amt = int(r.action.amount)
            high = max(st.bets)
            st.stacks[seat] -= amt - st.bets[seat]
            st.bets[seat] = amt
            if amt - high >= st.last_raise:
                st.last_raise = amt - high
            st.raises += 1
        elif kind == "F":
            return None
    if h.street != st.street:                        # first decision of a new street
        hist += "/"
        st = Street(h.street, [0, 0], list(st.stacks), 0, par.bb)
    return View(hist, st, me, translated)


# --------------------------------------------------------------------------- buckets

def bucket(h: HandState, street: int, bp: Blueprint, evaluator, classes) -> Optional[int]:
    """Our bucket on `street` (contract section 5), or None if the cards don't fit."""
    hole, board = list(h.hole), list(h.board)
    if street == 0:
        return int(classes.class_of(hole)) if len(hole) == 3 else None
    c = bp.cuts
    if street == 1 and len(hole) == 3 and len(board) == 3:
        _k, x, y = A.flop_features(evaluator, hole, board)
        return A.grid_bucket(x, y, c["flop"]["x"], c["flop"]["y"])
    dead = sorted(h.dead_cards)
    if len(hole) != 2 or len(dead) != 2:
        return None
    if street == 2 and len(board) == 4:
        x, y = A.turn_features(evaluator, hole, board, dead)
        return A.grid_bucket(x, y, c["turn"]["x"], c["turn"]["y"])
    if street == 3 and len(board) == 5:
        hs, blk = A.river_features(evaluator, hole, board, dead)
        return A.river_bucket(hs, blk, c["river"])
    return None
