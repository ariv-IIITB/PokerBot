"""Card abstractions (BUILDMAP §5.1, §5.3; docs/retrain_plan.md).

a1 is the frozen abstraction of runs A and B and of every bot up to v2 (data/spec.txt, data/thresholds.json,
tables/). a2 is the finer one (data/a2/, tables/a2/): more flop and turn bins, and the flop aggressor in
the turn key. Everything else is shared: cards, hand values, features (S1, S2, V), betting templates,
pot classes, discard classes, preflop classes, the river bucket.

    class2 = s1bin * flop_v + vbin                  (flop pair class)
    b3     = class2(keep slot 0) * gap + gapbin     (flop 3-card bucket)
    bt     = s1bin * turn_v + vbin                  (turn bucket)
    br     = river bin                              (river bucket)
    TURN prefix = (((bt * 4 + od) * 4 + md) * 6 + pc) * turn_agg + (fagg if turn_agg == 3 else 0)

With turn_agg = 1 the TURN prefix is a1's formula. class2 and bt are at most 254 (the C++ bucket tables
are uint8, with 255 marking a pair that hits the board).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Abstraction:
    name: str
    flop_s1: int        # S1 bins of a flop pair (quantiles of S1)
    flop_v: int         # V bins inside each flop S1 bin (quantiles of V among that bin's samples)
    gap: int            # bins of the S1 gap between keep slots 0 and 1
    turn_s1: int        # S1 bins of a turn pair
    turn_v: int         # V bins inside each turn S1 bin
    river: int          # river bins (quantiles of E)
    turn_agg: int       # 1: no flop aggressor in the turn key (a1); 3: fagg in the turn key

    def __post_init__(self):
        if self.turn_agg not in (1, 3):
            raise ValueError("turn_agg must be 1 or 3")
        if self.n_class2 > 254 or self.n_bt > 254:
            raise ValueError("class2 and the turn bucket must fit uint8 tables (at most 254)")

    @property
    def n_class2(self):
        return self.flop_s1 * self.flop_v

    @property
    def n_b3(self):
        return self.n_class2 * self.gap

    @property
    def n_bt(self):
        return self.turn_s1 * self.turn_v

    @property
    def n_br(self):
        return self.river

    @property
    def data_dir(self):
        """Relative to the repository root: spec.txt, thresholds.json, golden/."""
        return "data" if self.name == "a1" else f"data/{self.name}"

    @property
    def tables_dir(self):
        """Relative to the repository root: the C++ bucket tables."""
        return "tables" if self.name == "a1" else f"tables/{self.name}"

    def threshold_shapes(self):
        return {"flop_s1": (self.flop_s1 - 1,), "flop_v": (self.flop_s1, self.flop_v - 1), "gap": (self.gap - 1,),
                "turn_s1": (self.turn_s1 - 1,), "turn_v": (self.turn_s1, self.turn_v - 1), "river": (self.river - 1,)}


A1 = Abstraction("a1", flop_s1=16, flop_v=5, gap=5, turn_s1=40, turn_v=5, river=100, turn_agg=1)
A2 = Abstraction("a2", flop_s1=32, flop_v=7, gap=5, turn_s1=42, turn_v=6, river=100, turn_agg=3)
ABSTRACTIONS = {a.name: a for a in (A1, A2)}


def get(name):
    """The abstraction called `name` (None or "" -> a1, for blobs and thresholds written before a2)."""
    a = ABSTRACTIONS.get(name or "a1")
    if a is None:
        raise ValueError(f"unknown abstraction {name!r}")
    return a
