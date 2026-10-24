"""Compile a VariantSpec into Rules (a hand program of step plugins + numbers).

Done once at startup; nothing is re-interpreted in hot loops. Features whose plugin
hasn't been built yet raise NotSupported(feature, phase), which the catalog tests turn
into xfail markers.
"""
from __future__ import annotations

from typing import Optional

from bot.cards import RANKS, face_of, is_joker, parse_card
from bot.evaluator import HandEvaluator, order_from_names
from bot.game.deck import Deck
from bot.game.scoring import SCORES, CustomEvaluator, Scorer
from bot.game.rules_spec import Rules, street_label
from bot.game.steps import Betting, DealBoard, DealHole, PostBlinds, ShowdownStep
from bot.game.steps.base import Step


class NotSupported(Exception):
    def __init__(self, feature: str, phase: int) -> None:
        super().__init__(f"{feature} (planned for phase {phase})")
        self.feature, self.phase = feature, phase


def build_deck(spec) -> Deck:
    """Deck plugin: the spec's deck with its lookup arrays."""
    try:
        return Deck.from_spec(spec.deck)
    except ValueError as e:
        raise NotSupported(f"deck: {e}", 99) from None


def wild_ids(spec, deck: Deck) -> list[int]:
    """Card ids that are wild under evaluation.wild."""
    w = spec.evaluation.wild or {}
    ids = set()
    if w.get("jokers"):
        ids |= {c for c in deck.cards if is_joker(c)}
    if w.get("rank"):
        r = RANKS.index(w["rank"])
        ids |= {c for c in deck.cards if not is_joker(c) and face_of(c) // 4 == r}
    for text in w.get("cards", ()):
        face = face_of(parse_card(text))
        ids |= {c for c in deck.cards if face_of(c) == face}
    return sorted(ids)


def build_evaluator(spec, deck: Optional[Deck] = None) -> Scorer:
    """Evaluator plugin: a Scorer for the spec's evaluation section."""
    ev = spec.evaluation
    deck = deck or build_deck(spec)
    if ev.kind == "score":
        return Scorer(high=CustomEvaluator(SCORES[ev.score], deck))
    k = min(ev.hand_size, 5)
    common = dict(hole_exact=ev.hole_exact, hole_min=ev.hole_min, hole_max=ev.hole_max,
                  deck=deck, wild_ids=wild_ids(spec, deck), select_size=ev.hand_size)
    order = order_from_names(ev.category_order)
    qualifier = None
    if ev.low_qualifier is not None:
        qualifier = {1: "A", 10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}.get(
            ev.low_qualifier, str(ev.low_qualifier))
    if ev.kind == "high":
        return Scorer(high=HandEvaluator(k, mode="high", order=order, **common))
    if ev.kind == "low_27":
        return Scorer(low=HandEvaluator(k, mode="low_27", **common))
    if ev.kind == "low_a5":
        return Scorer(low=HandEvaluator(k, mode="low_a5", qualifier=qualifier, **common))
    if ev.kind == "hilo":
        return Scorer(high=HandEvaluator(k, mode="high", order=order, **common),
                      low=HandEvaluator(k, mode="low_a5", qualifier=qualifier, **common))
    raise NotSupported(f"evaluation kind {ev.kind}", 99)


def _betting_step(spec, s: dict, round_index: int) -> Step:
    b = spec.betting
    if b.structure != "NL":
        raise NotSupported(f"{b.structure} betting", 14)
    if b.bet_sizes or b.bet_multiple or not b.check_raise:
        raise NotSupported("restricted bet sizes / no check-raise", 14)
    first = s.get("first") or (b.preflop_first if round_index == 0 else b.postflop_first)
    label = s.get("round") or street_label(round_index)
    return Betting(first, b.max_raises, b.big_blind, label)


def compile_spec(spec) -> Rules:
    """VariantSpec -> Rules. Raises SpecError if invalid, NotSupported if a plugin is missing."""
    spec.check()
    b, m = spec.betting, spec.match
    if b.ante or b.straddle:
        raise NotSupported("antes / straddle", 14)
    if m.blind_schedule or not m.bust_ends_match:
        raise NotSupported("blind schedule / bust rules", 14)
    if spec.payoffs:
        raise NotSupported("payoff modifiers (bounty / multiplier / rake)", 15)
    deck = build_deck(spec)
    evaluator = build_evaluator(spec, deck)

    prog: list[Step] = []
    streets: list[int] = [0]
    hole = 0
    rounds = 0
    for s in spec.full_program():
        t = s["type"]
        if t == "post_blinds":
            prog.append(PostBlinds(b.small_blind, b.big_blind))
        elif t == "deal_hole":
            if s["face_up"]:
                raise NotSupported("face-up hole cards", 13)
            prog.append(DealHole(s["n"]))
            hole += s["n"]
        elif t == "deal_board":
            if s["boards"] not in (None, 1):
                raise NotSupported("multiple boards", 15)
            prog.append(DealBoard(s["n"], s["burn"], s["burn_revealed"]))
            streets.append(s["n"])
        elif t == "betting":
            prog.append(_betting_step(spec, s, rounds))
            rounds += 1
        elif t == "showdown":
            if s.get("runs", 1) != 1:
                raise NotSupported("run it multiple times", 15)
            prog.append(ShowdownStep())
        elif t in ("discard", "draw", "swap", "choose", "peek", "expose"):
            raise NotSupported(f"{t} step", 13)
        elif t in ("auction", "market", "bounty"):
            raise NotSupported(f"{t} step", 15)
        else:
            raise NotSupported(f"step {t}", 99)
    return Rules(tuple(prog), evaluator, spec.players, hole, b.small_blind, b.big_blind,
                 m.starting_stack, m.reset_stacks, m.hands, m.time_bank_s, deck.cards,
                 tuple(streets), spec.name, m.bust_ends_match, spec)
