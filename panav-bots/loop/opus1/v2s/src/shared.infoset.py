"""Infoset layout: dense tables, prefix formulas and offsets (BUILDMAP §5.3).

Probability of (table, prefix, node, slot) = T[prefix, node.offset + slot_position].
Concatenated order (trainer arrays, checkpoints, exported blob): PRE, FLOP, DISC, TURN, RIVER.

One Layout per card abstraction (shared/abstraction.py). The module-level names (N_B3, PREFIXES,
flop_prefix, ...) are a1's, the frozen layout of runs A and B; layout(A) gives any abstraction's.
The prefix methods also take numpy arrays (range tracking), without the range checks.
"""
import numbers

from . import abstraction as AB
from .betting import POST_SLOTS, PRE_SLOTS

N_PRE = 1755
N_PC = 6
N_AGG = 3
N_SEAT = 2
N_DCLS = 4
N_KEEP = 3
TABLES = ("PRE", "FLOP", "DISC", "TURN", "RIVER")


def _check(name, v, n):
    if not (isinstance(v, numbers.Integral) and not isinstance(v, bool) and 0 <= v < n):
        raise ValueError(f"{name}={v!r} outside [0, {n})")


def _scalar(*xs):
    return all(isinstance(x, numbers.Integral) and not isinstance(x, bool) for x in xs)


class Layout:
    def __init__(self, abstraction):
        A = abstraction
        self.A = A
        self.TABLES = TABLES
        self.N_B3, self.N_BT, self.N_BR = A.n_b3, A.n_bt, A.n_br
        self.N_TAGG = A.turn_agg
        self.PREFIXES = {
            "PRE": N_PRE,
            "FLOP": A.n_b3 * N_PC * N_AGG,
            "DISC": A.n_b3 * N_PC * N_AGG * N_SEAT,
            "TURN": A.n_bt * N_DCLS * N_DCLS * N_PC * A.turn_agg,
            "RIVER": A.n_br * N_DCLS * N_PC,
        }
        self.SLOTS = {"PRE": PRE_SLOTS, "FLOP": POST_SLOTS, "DISC": N_KEEP, "TURN": POST_SLOTS, "RIVER": POST_SLOTS}
        self.SIZES = {t: self.PREFIXES[t] * self.SLOTS[t] for t in TABLES}
        self.OFFSETS = {}
        off = 0
        for t in TABLES:
            self.OFFSETS[t] = off
            off += self.SIZES[t]
        self.TOTAL = off

    # prefixes: scalars are range-checked; numpy arrays (range tracking) are not
    def pre_prefix(self, hand):
        _check("hand", hand, N_PRE)
        return hand

    def flop_prefix(self, b3, pc, pagg):
        if _scalar(b3, pc, pagg):
            _check("b3", b3, self.N_B3); _check("pc", pc, N_PC); _check("pagg", pagg, N_AGG)
        return (b3 * 6 + pc) * 3 + pagg

    def disc_prefix(self, b3, pc, fagg, seat):
        if _scalar(b3, pc, fagg, seat):
            _check("b3", b3, self.N_B3); _check("pc", pc, N_PC); _check("fagg", fagg, N_AGG)
            _check("seat", seat, N_SEAT)
        return ((b3 * 6 + pc) * 3 + fagg) * 2 + seat

    def turn_prefix(self, bt, od, md, pc, fagg=0):
        """a1 (turn_agg 1) ignores fagg: its key has no flop aggressor."""
        if _scalar(bt, od, md, pc, fagg):
            _check("bt", bt, self.N_BT); _check("od", od, N_DCLS); _check("md", md, N_DCLS)
            _check("pc", pc, N_PC); _check("fagg", fagg, N_AGG)
        k = ((bt * 4 + od) * 4 + md) * 6 + pc
        return k if self.N_TAGG == 1 else k * self.N_TAGG + fagg

    def river_prefix(self, br, od, pc):
        if _scalar(br, od, pc):
            _check("br", br, self.N_BR); _check("od", od, N_DCLS); _check("pc", pc, N_PC)
        return (br * 4 + od) * 6 + pc

    def index(self, table, prefix, node_offset, slot_pos):
        """Position in the concatenated array of (table, prefix, node.offset + slot_pos).
        For DISC, node_offset is 0 and slot_pos is the keep slot."""
        _check("prefix", prefix, self.PREFIXES[table])
        _check("column", node_offset + slot_pos, self.SLOTS[table])
        return self.OFFSETS[table] + prefix * self.SLOTS[table] + node_offset + slot_pos

    def row_range(self, table, prefix):
        """[start, stop) of one prefix's row in the concatenated array."""
        start = self.index(table, prefix, 0, 0)
        return start, start + self.SLOTS[table]


_LAYOUTS = {}


def layout(abstraction=None):
    """The Layout of an abstraction (an Abstraction, its name, or None for a1)."""
    A = abstraction if isinstance(abstraction, AB.Abstraction) else AB.get(abstraction)
    if A.name not in _LAYOUTS:
        _LAYOUTS[A.name] = Layout(A)
    return _LAYOUTS[A.name]


# ---------------------------------------------------------------- a1, the frozen layout (module level)

LAYOUT_A1 = layout(AB.A1)
N_B3, N_BT, N_BR = LAYOUT_A1.N_B3, LAYOUT_A1.N_BT, LAYOUT_A1.N_BR
PREFIXES, SLOTS, SIZES, OFFSETS, TOTAL = (LAYOUT_A1.PREFIXES, LAYOUT_A1.SLOTS, LAYOUT_A1.SIZES, LAYOUT_A1.OFFSETS,
                                          LAYOUT_A1.TOTAL)
assert TOTAL == 2_787_570


def pre_prefix(hand):
    return LAYOUT_A1.pre_prefix(hand)


def flop_prefix(b3, pc, pagg):
    return LAYOUT_A1.flop_prefix(b3, pc, pagg)


def disc_prefix(b3, pc, fagg, seat):
    return LAYOUT_A1.disc_prefix(b3, pc, fagg, seat)


def turn_prefix(bt, od, md, pc):
    return LAYOUT_A1.turn_prefix(bt, od, md, pc)


def river_prefix(br, od, pc):
    return LAYOUT_A1.river_prefix(br, od, pc)


def index(table, prefix, node_offset, slot_pos):
    return LAYOUT_A1.index(table, prefix, node_offset, slot_pos)


def row_range(table, prefix):
    return LAYOUT_A1.row_range(table, prefix)
