"""Example variant specs for fuzzing and tests (lab only)."""
from __future__ import annotations

from variant.spec import BettingSpec, EvalSpec, MatchSpec, VariantSpec, default_program


def _discard3() -> VariantSpec:
    """3 hole cards; after the flop is dealt (before its betting) BB then SB discard one
    card face up onto the board."""
    prog = default_program(3)
    prog.insert(4, {"type": "discard", "n": 1, "order": "BB_first", "visibility": "public",
                    "destination": "board"})
    return VariantSpec(name="discard3", program=prog)


EXAMPLES: dict[str, VariantSpec] = {
    "holdem": VariantSpec(name="holdem"),
    "discard3": _discard3(),
    "omaha": VariantSpec(name="omaha", hole_cards=4, evaluation=EvalSpec(hole_exact=2)),
    "short_stacks": VariantSpec(name="short_stacks", match=MatchSpec(starting_stack=25)),
    "raise_cap": VariantSpec(name="raise_cap", betting=BettingSpec(max_raises=2)),
    "persistent": VariantSpec(name="persistent",
                              match=MatchSpec(reset_stacks=False, starting_stack=200)),
    "big_blinds": VariantSpec(name="big_blinds", betting=BettingSpec(small_blind=5, big_blind=10),
                              match=MatchSpec(starting_stack=300)),
    "extra_street": VariantSpec(name="extra_street", streets=[0, 3, 1, 1, 0]),
}
