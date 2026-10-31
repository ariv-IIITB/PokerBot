"""The v1 abstract betting tree of docs/cfr/ABSTRACTION_V1.md, in plain Python (lab only).

This is the reference for the contract: the Numba game core (C1) and the runtime key builder
(C5) must give the same labels, chip amounts and history strings. It also enumerates every
decision node, which gives the history ids of the strategy table (C3) and the size numbers in
the document.

Numbers come from the variant spec (stack, blinds, raise cap), so a rule change is a config change.

    .venv/bin/python -m lab.cfr.fast.tree --count [--variant discard_holdem]
    .venv/bin/python -m lab.cfr.fast.tree --line "R R C | C H C | C P R A C"
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from typing import Iterator, Optional

STREETS = ("preflop", "flop", "turn", "river")
LABELS = ("F", "C", "H", "P", "R", "A")       # the order actions are listed in, always
BET_FRACTIONS = (("H", 0.5), ("P", 1.0))       # unopened postflop street: bet x pot
OPEN_MULT = 2.5                                # facing only the big blind, or any postflop bet
RERAISE_MULT = 3.0                             # preflop, facing a raise above the big blind


@dataclass(frozen=True)
class Params:
    stack: int = 200
    sb: int = 1
    bb: int = 2
    max_raises: int = 4
    blind_counts_as_raise: bool = True
    sized_raise_cap: int = 3      # abstraction only: from this many bets/raises on a street on,
                                  # only all-in is offered as a raise (v1: 3; the engine allows 4)

    @classmethod
    def from_variant(cls, name_or_path: str = "discard_holdem") -> "Params":
        from lab.harness import load_variant
        spec = load_variant(name_or_path)
        b = spec.betting
        return cls(spec.match.starting_stack, b.small_blind, b.big_blind, b.max_raises,
                   b.blind_counts_as_raise)


@dataclass(frozen=True)
class Node:
    """A betting state. Seat 0 = button (posts the small blind, acts first preflop)."""
    street: int
    bets: tuple[int, int]        # chips in on this street, per seat
    stacks: tuple[int, int]      # chips behind, per seat
    raises: int                  # bets/raises this street (the BB counts preflop)
    last_raise: int              # size of the last full raise this street
    actor: int
    needs: frozenset             # seats that still have to act this street
    history: str = ""
    folded: Optional[int] = None
    done: bool = False           # betting is over (fold, or no more decisions this hand)

    @property
    def pot(self) -> int:
        """Every chip committed this hand (all streets, this street's bets included)."""
        return 2 * self._start_stack - sum(self.stacks)

    _start_stack: int = 200

    def to_call(self, p: int) -> int:
        return max(self.bets) - self.bets[p]


def root(par: Params) -> Node:
    bets = (par.sb, par.bb)
    stacks = (par.stack - par.sb, par.stack - par.bb)
    return Node(0, bets, stacks, 1 if par.blind_counts_as_raise else 0, par.bb, 0,
                frozenset({0, 1}), _start_stack=par.stack)


def _raise_bounds(n: Node, par: Params) -> Optional[tuple[int, int]]:
    """(min, max) raise-to amounts, as bot/game/steps/betting.py computes them (None: no raise)."""
    p, q = n.actor, 1 - n.actor
    to_call = n.to_call(p)
    if not (n.stacks[p] > to_call and n.stacks[q] > 0 and n.raises < par.max_raises):
        return None
    high = max(n.bets)
    rmax = n.bets[p] + n.stacks[p]
    rmin = min(high + max(n.last_raise, par.bb), rmax)
    return rmin, rmax


def actions(n: Node, par: Params) -> list[tuple[str, str, Optional[int]]]:
    """(label, kind, raise-to amount) for every abstract action at a decision node.

    kind: F fold, K check, C call, R raise-to. Sizes are clamped to the legal range; a size
    equal to all-in is labelled A; equal amounts keep the first label in LABELS order."""
    p = n.actor
    to_call = n.to_call(p)
    out: list[tuple[str, str, Optional[int]]] = []
    if to_call > 0:
        out.append(("F", "F", None))
    out.append(("C", "C" if to_call > 0 else "K", None))
    bounds = _raise_bounds(n, par)
    if bounds is None:
        return out
    rmin, rmax = bounds
    high = max(n.bets)
    wanted: list[tuple[str, float]] = []
    if high == 0:                                   # unopened postflop street: bet x pot
        wanted = [(lab, n.bets[p] + to_call + f * (n.pot + to_call)) for lab, f in BET_FRACTIONS]
    else:                                           # facing a bet (preflop: the BB counts)
        mult = RERAISE_MULT if n.street == 0 and high > par.bb else OPEN_MULT
        wanted = [("R", mult * high)]
    if n.raises >= par.sized_raise_cap:
        wanted = []
    seen: set[int] = set()
    for lab, x in wanted:
        amt = min(max(int(round(x)), rmin), rmax)   # Python round: half to even
        if amt == rmax or amt in seen:
            continue
        seen.add(amt)
        out.append((lab, "R", amt))
    out.append(("A", "R", rmax))
    return out


def _next_street(n: Node, par: Params) -> Node:
    """Close the street: the next street's opening node, or done."""
    hist = n.history + "/"
    live = {p for p in (0, 1) if n.stacks[p] > 0}
    if n.street == 3 or len(live) < 2:
        return replace(n, history=hist, done=True, needs=frozenset())
    return replace(n, street=n.street + 1, bets=(0, 0), raises=0, last_raise=par.bb,
                   actor=1, needs=frozenset(live), history=hist)


def child(n: Node, label: str, par: Params) -> Node:
    """The node after the actor takes abstract action `label`."""
    acts = {lab: (kind, amt) for lab, kind, amt in actions(n, par)}
    if label not in acts:
        raise ValueError(f"{label!r} is not legal at {n.history!r} (legal: {''.join(acts)})")
    kind, amt = acts[label]
    p, q = n.actor, 1 - n.actor
    hist = n.history + label
    if kind == "F":
        return replace(n, history=hist, folded=p, done=True, needs=frozenset())
    bets, stacks = list(n.bets), list(n.stacks)
    needs = set(n.needs)
    raises, last = n.raises, n.last_raise
    if kind == "C":
        pay = min(n.to_call(p), stacks[p])
        bets[p] += pay
        stacks[p] -= pay
        needs.discard(p)
    elif kind == "K":
        needs.discard(p)
    else:
        high = max(bets)
        stacks[p] -= amt - bets[p]
        bets[p] = amt
        if amt - high >= last:
            last = amt - high
        raises += 1
        needs = {q} if stacks[q] > 0 else set()
    m = replace(n, bets=(bets[0], bets[1]), stacks=(stacks[0], stacks[1]), raises=raises,
                last_raise=last, actor=q, needs=frozenset(needs), history=hist)
    if not needs:
        return _next_street(m, par)
    if q not in needs:                 # only p still needs to act (cannot happen heads-up)
        m = replace(m, actor=p)
    return m


def decision_nodes(par: Params) -> Iterator[Node]:
    """Every decision node, depth first, children in LABELS order."""
    stack = [root(par)]
    while stack:
        n = stack.pop()
        if n.done:
            continue
        yield n
        kids = [child(n, lab, par) for lab, _k, _a in actions(n, par)]
        stack.extend(reversed(kids))


def history_ids(par: Params) -> list[dict[str, int]]:
    """Per street: history string -> id (0.. in enumeration order). The table layout of C3."""
    ids: list[dict[str, int]] = [{} for _ in STREETS]
    for n in decision_nodes(par):
        ids[n.street].setdefault(n.history, len(ids[n.street]))
    return ids


DECISION, FOLD, SHOWDOWN = 0, 1, 2


def flatten(par: Params) -> dict:
    """The whole abstract tree as flat NumPy arrays (the trainer walks these; no betting logic).

    Per node n (0 = root): kind (DECISION / FOLD / SHOWDOWN), street, actor, hist (history id within
    its street, decision nodes only, as history_ids), n_act, first (index of its first edge),
    contrib[n, seat] (chips each seat has put in), folder (seat that folded, else -1).
    Per edge e: child[e] (node index), label[e] (index into LABELS). Children are in LABELS order.
    """
    from collections import deque

    import numpy as np

    ids = history_ids(par)
    nodes: list[Node] = []
    edges_child: list[int] = []
    edges_label: list[int] = []
    first: list[int] = []
    n_act: list[int] = []
    queue = deque([root(par)])
    while queue:                                   # breadth first: parents before children
        n = queue.popleft()
        nodes.append(n)
        if n.done:
            first.append(-1)
            n_act.append(0)
            continue
        acts = actions(n, par)
        first.append(len(edges_child))
        n_act.append(len(acts))
        for lab, _k, _a in acts:
            edges_label.append(LABELS.index(lab))
            edges_child.append(-1)                 # filled below
            queue.append(child(n, lab, par))
    # children were appended to the queue in order, so node indices follow edge order
    nxt = 1
    for e in range(len(edges_child)):
        edges_child[e] = nxt
        nxt += 1
    kind = [FOLD if n.folded is not None else SHOWDOWN if n.done else DECISION for n in nodes]
    start = par.stack
    return {
        "kind": np.array(kind, dtype=np.int8),
        "street": np.array([n.street for n in nodes], dtype=np.int8),
        "actor": np.array([n.actor for n in nodes], dtype=np.int8),
        "hist": np.array([ids[n.street][n.history] if not n.done else -1 for n in nodes], dtype=np.int32),
        "n_act": np.array(n_act, dtype=np.int8),
        "first": np.array(first, dtype=np.int32),
        "contrib": np.array([[start - n.stacks[0], start - n.stacks[1]] for n in nodes], dtype=np.int32),
        "folder": np.array([-1 if n.folded is None else n.folded for n in nodes], dtype=np.int8),
        "child": np.array(edges_child, dtype=np.int32),
        "label": np.array(edges_label, dtype=np.int8),
        "histories": [sorted(d, key=d.get) for d in ids],
    }


def infoset_key(street: int, bucket: int, history: str) -> str:
    """Same format as bot.abstraction.infoset_key."""
    return f"{street}|{bucket}|{history}"


def walk_line(line: str, par: Params) -> list[tuple[Node, list, str]]:
    """Follow a line of labels ("|" between streets is optional decoration)."""
    n, out = root(par), []
    for label in line.replace("|", " ").split():
        out.append((n, actions(n, par), label))
        n = child(n, label, par)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="discard_holdem")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--buckets", default="1755,100,100,50")
    ap.add_argument("--line", default=None)
    ap.add_argument("--sized-raise-cap", type=int, default=None)
    args = ap.parse_args(argv)
    par = Params.from_variant(args.variant)
    if args.sized_raise_cap is not None:
        par = replace(par, sized_raise_cap=args.sized_raise_cap)
    if args.count:
        buckets = [int(x) for x in args.buckets.split(",")]
        nodes = list(decision_nodes(par))
        per = [[n for n in nodes if n.street == s] for s in range(4)]
        acts = [sum(len(actions(n, par)) for n in ns) for ns in per]
        rows = [len(ns) * b for ns, b in zip(per, buckets)]
        cells = [a * b for a, b in zip(acts, buckets)]
        print(f"params {par}")
        for s, name in enumerate(STREETS):
            print(f"{name:8} histories {len(per[s]):6}  actions {acts[s]:7}  "
                  f"infosets {rows[s]:9,}  table cells {cells[s]:10,}")
        print(f"total    histories {len(nodes):6}  infosets {sum(rows):,}  "
              f"table cells {sum(cells):,} (uint8: {sum(cells) / 1e6:.2f} MB raw)")
    if args.line:
        for n, acts, label in walk_line(args.line, par):
            menu = " ".join(f"{lab}{'' if amt is None else '→' + str(amt)}" for lab, _k, amt in acts)
            print(f"{STREETS[n.street]:8} seat {n.actor} pot {n.pot:3} bets {n.bets} "
                  f"history {n.history!r:24} menu [{menu}] -> {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
