"""Compiled rules: the hand program (a tuple of steps) plus the numbers every step needs.

`rules_from_config(GameConfig)` turns the classic config into a program. Standard Hold'em:

    post_blinds, deal_hole(2), betting(SB first),
    deal_board(3), betting(BB first), deal_board(1), betting, deal_board(1), betting,
    showdown

Special-step hooks are inserted on their street, before or after its betting round.
Rules are built once per match and never re-interpreted inside hot loops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from bot.cards import FULL_DECK
from bot.game.steps import Betting, DealBoard, DealHole, HookStep, PostBlinds, ShowdownStep
from bot.game.steps.base import Step

STREET_NAMES = ("preflop", "flop", "turn", "river")


@dataclass(frozen=True)
class Rules:
    program: tuple[Step, ...]
    evaluator: Any = field(compare=False, repr=False)
    n_players: int = 2
    hole_cards: int = 2
    small_blind: int = 1
    big_blind: int = 2
    starting_stack: int = 400
    reset_stacks_each_hand: bool = True
    hands_per_match: int = 400
    time_bank_s: float = 60.0
    deck: tuple[int, ...] = FULL_DECK
    streets: tuple[int, ...] = (0, 3, 1, 1)   # board cards dealt per street (0 = preflop)
    name: str = "holdem"
    bust_ends_match: bool = True
    spec: Any = field(default=None, compare=False, repr=False)

    @property
    def board_cards(self) -> int:
        """Board cards dealt by the end of the hand (per board)."""
        return sum(self.streets)

    def describe(self) -> str:
        """The hand program in plain English, one step per line."""
        return "\n".join(f"{i + 1:>2}. {s.describe()}" for i, s in enumerate(self.program))


def street_label(i: int) -> str:
    return STREET_NAMES[i] if i < len(STREET_NAMES) else f"street {i}"


def rules_from_config(cfg, evaluator: Optional[Any] = None) -> Rules:
    """Compile a variant.rules.GameConfig into Rules."""
    if evaluator is None:
        from variant.evaluator_hook import make_evaluator
        evaluator = make_evaluator(cfg)
    prog: list[Step] = [PostBlinds(cfg.small_blind, cfg.big_blind), DealHole(cfg.hole_cards)]
    for street, n_new in enumerate(cfg.streets):
        if street > 0:
            prog.append(DealBoard(n_new))
        hooks = [h for h in cfg.special_steps if h.street == street]
        prog += [HookStep(h) for h in hooks if h.timing == "before_betting"]
        first = cfg.preflop_first_actor if street == 0 else cfg.postflop_first_actor
        prog.append(Betting(first, cfg.max_raises_per_street, cfg.big_blind, street_label(street)))
        prog += [HookStep(h) for h in hooks if h.timing == "after_betting"]
    prog.append(ShowdownStep())
    return Rules(tuple(prog), evaluator, 2, cfg.hole_cards, cfg.small_blind, cfg.big_blind,
                 cfg.starting_stack, cfg.reset_stacks_each_hand, cfg.hands_per_match,
                 cfg.time_bank_s, FULL_DECK, tuple(cfg.streets), "config")


def to_rules(variant: Any, evaluator: Optional[Any] = None) -> Rules:
    """Rules from a Rules, a variant.spec.VariantSpec or a legacy GameConfig."""
    if isinstance(variant, Rules):
        return variant
    if hasattr(variant, "full_program"):            # VariantSpec
        from bot.game.compile import compile_spec
        return compile_spec(variant)
    return rules_from_config(variant, evaluator)


ACTIVE_SPEC = "active.json"


def active_rules() -> Rules:
    """The variant the bot plays: $POKERBOT_VARIANT or variant/active.json if present and
    valid, otherwise the built-in GameConfig. Never raises."""
    import os
    from pathlib import Path
    candidates = [os.environ.get("POKERBOT_VARIANT"),
                  str(Path(__file__).resolve().parents[2] / "variant" / ACTIVE_SPEC)]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                from variant.spec import VariantSpec
                return to_rules(VariantSpec.load(path))
            except Exception as e:  # bad spec: fall back, but say so
                from bot.log import warn
                warn(f"could not use variant spec {path}: {e!r}")
    from variant.rules import DEFAULT_CONFIG
    return rules_from_config(DEFAULT_CONFIG)
