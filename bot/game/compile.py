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
from bot.game.steps import (Betting, Choose, DealBoard, DealHole, Discard, Draw, Expose, Peek,
                            PostBlinds, ShowdownStep, Swap)
from bot.game.steps.side import Auction, Bounty, Market
from variant.spec import STEP_PARAMS
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
    if round_index == 0:
        default_first = "BB" if b.straddle else b.preflop_first   # straddler acts last
    else:
        default_first = b.postflop_first
    first = s.get("first") or default_first
    label = s.get("round") or street_label(round_index)
    fixed = b.fixed_bets[round_index] if b.structure == "FL" else None
    return Betting(first, b.max_raises, b.big_blind, label, structure=b.structure,
                   fixed_bet=fixed, bet_sizes=b.bet_sizes, bet_multiple=b.bet_multiple,
                   check_raise=b.check_raise)


def compile_spec(spec) -> Rules:
    """VariantSpec -> Rules. Raises SpecError if invalid, NotSupported if a plugin is missing."""
    spec.check()
    b, m = spec.betting, spec.match
    deck = build_deck(spec)
    evaluator = build_evaluator(spec, deck)

    prog: list[Step] = []
    streets: list[int] = [0]
    hole = 0
    rounds = 0
    for s in spec.full_program():
        t = s["type"]
        if t == "post_blinds":
            prog.append(PostBlinds(b.small_blind, b.big_blind, b.ante, b.straddle))
        elif t == "deal_hole":
            prog.append(DealHole(s["n"], s["face_up"]))
            hole += s["n"]
        elif t == "deal_board":
            prog.append(DealBoard(s["n"], s["burn"], s["burn_revealed"], s["boards"] or 1))
            streets.append(s["n"])
        elif t == "betting":
            prog.append(_betting_step(spec, s, rounds))
            rounds += 1
        elif t == "showdown":
            prog.append(ShowdownStep(s.get("runs", 1)))
        elif t == "discard":
            prog.append(Discard(s["n"], s["destination"], s["optional"], order=s["order"],
                                visibility=s["visibility"]))
        elif t == "draw":
            prog.append(Draw(s["max"], s["min"], order=s["order"], cost=s["cost"],
                             visibility=s["visibility"]))
        elif t == "swap":
            if s["n"] != 1:
                raise NotSupported("swapping more than one card", 99)
            prog.append(Swap(s["with"], s["mode"], s["probability"], order=s["order"],
                             cost=s["cost"]))
        elif t == "choose":
            prog.append(Choose(s["offer"], s["keep"], order=s["order"], visibility=s["visibility"]))
        elif t == "peek":
            prog.append(Peek(s["target"], order=s["order"], cost=s["cost"]))
        elif t == "expose":
            prog.append(Expose(s["n"], s["chosen"], order=s["order"]))
        elif t == "bounty":
            prog.append(_bounty(s, spec))
        elif t == "auction":
            prog.append(Auction(s["kind"], s["prize"], s["payment"], s["tie"], s["max_bid"]))
        elif t == "market":
            prog.append(Market(s["quantity"], s["size"], s["settle_scale"],
                               sum(x["n"] for x in spec.full_program() if x["type"] == "deal_board")))
        else:
            raise NotSupported(f"step {t}", 99)
    if "post_blinds" not in spec.step_types() and b.ante:
        prog.insert(0, PostBlinds(0, 0, b.ante, 0))          # antes-only variants
    modifiers = []
    for pay in spec.payoffs:
        if pay["type"] == "bounty":                          # bounty as a payoff = a step
            prog.insert(1, _bounty({**STEP_PARAMS["bounty"], **pay}, spec))
        else:
            modifiers.append(dict(pay))
    schedule = tuple(sorted(tuple(row) for row in m.blind_schedule))
    return Rules(tuple(prog), evaluator, spec.players, hole, b.small_blind, b.big_blind,
                 m.starting_stack, m.reset_stacks, m.hands, m.time_bank_s, deck.cards,
                 tuple(streets), spec.name, m.bust_ends_match, spec, b.ante, b.straddle,
                 schedule, tuple(modifiers))


def _bounty(s: dict, spec) -> Step:
    return Bounty(s["mode"], s.get("rank"), s["bonus"], s["multiplier"], spec.deck.ranks)
