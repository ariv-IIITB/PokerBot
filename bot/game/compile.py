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
from bot.game.rules_spec import Rules
from bot.game.steps import STEP_TYPES, CompileContext, PostBlinds, Step, step_class
from variant.spec import STEP_PARAMS


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


def compile_spec(spec) -> Rules:
    """VariantSpec -> Rules. Raises SpecError if invalid, NotSupported if a plugin is missing.
    Each program entry is built by its plugin's from_spec (see bot/game/steps/)."""
    spec.check()
    b, m = spec.betting, spec.match
    deck = build_deck(spec)
    evaluator = build_evaluator(spec, deck)
    program = spec.full_program()
    ctx = CompileContext(spec, 0, sum(x["n"] for x in program if x["type"] == "deal_board"))

    prog: list[Step] = []
    streets: list[int] = [0]
    hole = 0
    for s in program:
        t = s["type"]
        if t not in STEP_TYPES:
            raise NotSupported(f"step {t}", 99)
        prog.append(step_class(t).from_spec(s, ctx))
        if t == "deal_hole":
            hole += s["n"]
        elif t == "deal_board":
            streets.append(s["n"])
        elif t == "betting":
            ctx.round_index += 1
    if "post_blinds" not in spec.step_types() and b.ante:
        prog.insert(0, PostBlinds(0, 0, b.ante, 0))          # antes-only variants
    modifiers = []
    for pay in spec.payoffs:
        if pay["type"] == "bounty":                          # bounty as a payoff = a step
            prog.insert(1, step_class("bounty").from_spec({**STEP_PARAMS["bounty"], **pay}, ctx))
        else:
            modifiers.append(dict(pay))
    schedule = tuple(sorted(tuple(row) for row in m.blind_schedule))
    return Rules(tuple(prog), evaluator, spec.players, hole, b.small_blind, b.big_blind,
                 m.starting_stack, m.reset_stacks, m.hands, m.time_bank_s, deck.cards,
                 tuple(streets), spec.name, m.bust_ends_match, spec, b.ante, b.straddle,
                 schedule, tuple(modifiers))
