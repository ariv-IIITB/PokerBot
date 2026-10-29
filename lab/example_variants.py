"""Example variant specs for fuzzing and tests (lab only)."""
from __future__ import annotations

from variant.spec import BettingSpec, EvalSpec, MatchSpec, VariantSpec

# 3 hole cards; after the flop is dealt, BB then SB discard one hole card face up onto the board.
DISCARD3_PROGRAM = [
    {"type": "post_blinds"}, {"type": "deal_hole", "n": 3},
    {"type": "betting", "round": "preflop"},
    {"type": "deal_board", "n": 3},
    {"type": "discard", "n": 1, "order": "BB_first", "visibility": "public", "destination": "board"},
    {"type": "betting", "round": "flop"},
    {"type": "deal_board", "n": 1}, {"type": "betting", "round": "turn"},
    {"type": "deal_board", "n": 1}, {"type": "betting", "round": "river"},
    {"type": "showdown"},
]

EXAMPLES: dict[str, VariantSpec] = {
    "holdem": VariantSpec(name="holdem"),
    "discard3": VariantSpec(name="discard3", hole_cards=3, program=DISCARD3_PROGRAM),
    "omaha": VariantSpec(name="omaha", hole_cards=4, evaluation=EvalSpec(hole_exact=2)),
    "short_stacks": VariantSpec(name="short_stacks", match=MatchSpec(starting_stack=25)),
    "raise_cap": VariantSpec(name="raise_cap", betting=BettingSpec(max_raises=2)),
    "persistent": VariantSpec(name="persistent",
                              match=MatchSpec(reset_stacks=False, starting_stack=200)),
    "big_blinds": VariantSpec(name="big_blinds", betting=BettingSpec(small_blind=5, big_blind=10),
                              match=MatchSpec(starting_stack=300)),
    "extra_street": VariantSpec(name="extra_street", streets=[0, 3, 1, 1, 0]),
}
