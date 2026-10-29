"""Phase 14: betting-structure plugins, with hand-computed expected results."""
import pytest

from bot.actions import Action, LegalActions, clamp, is_legal, pot_fraction_raise
from bot.lock import lock_margin
from bot.game.compile import compile_spec
from bot.game.payoffs import side_pots
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from bot.protocol import (ActRequest, HandStart, MatchInfo, encode_message, format_legal,
                          parse_legal, parse_line)
from bot.state import GameState as BotState
from lab.engine import deck_for, play_match
from lab.players import PlayerSpec
from variant.spec import VariantSpec


def state(betting=None, match=None, hand_id=0, **kw) -> GameState:
    spec = VariantSpec.from_dict({"betting": betting or {}, "match": match or {}, **kw})
    rules = compile_spec(spec)
    return GameState(rules, deck_for(0, hand_id, rules.deck),
                     [rules.starting_stack] * 2, hand_id=hand_id, audit=True)


def step(st, action=None):
    """Advance; apply `action` for the player to act; return (player, legal) of the next."""
    p = advance(st)
    if action is not None:
        act(st, p, action)
        p = advance(st)
    return p, (legal_actions(st, p) if p is not None else None)


# --------------------------------------------------------------------------- pot limit

def test_pot_limit_max_raise_math() -> None:
    st = state({"structure": "PL"})
    p, legal = step(st)
    # SB: pot 3, to call 1 -> max raise to = 2 + (3 + 1) = 6
    assert p == 0 and (legal.raise_min, legal.raise_max) == (4, 6)
    p, legal = step(st, Action.raise_to(6))
    # BB: pot 8, to call 4 -> 6 + (8 + 4) = 18
    assert p == 1 and (legal.raise_min, legal.raise_max) == (10, 18)
    p, legal = step(st, Action.call())
    # Flop: pot 12, nothing to call -> max bet 12
    assert p == 1 and (legal.raise_min, legal.raise_max) == (2, 12)


# --------------------------------------------------------------------------- fixed limit

def test_fixed_limit_sizes_and_cap() -> None:
    st = state({"structure": "FL", "fixed_bets": [2, 2, 4, 4]})
    p, legal = step(st)
    assert (legal.raise_min, legal.raise_max) == (4, 4)          # 2 + small bet 2
    raises = 0
    while legal is not None and legal.can_raise and st.street == 0:
        p, legal = step(st, Action.raise_to(legal.raise_min))
        raises += 1
    assert raises == 4 and not legal.can_raise                   # 4-bet cap
    while st.street < 2:                                         # call down to the turn
        p, legal = step(st, Action.call() if legal.call else Action.check())
    assert (legal.raise_min, legal.raise_max) == (4, 4)          # big bet on the turn


# --------------------------------------------------------------------------- antes / straddle

def test_antes_are_dead_money() -> None:
    st = state({"ante": 1})
    p, legal = step(st)
    assert st.pot == 1 + 1 + 1 + 2 and st.to_call(0) == 1 and st.bet == [1, 2]
    assert (legal.raise_min, legal.raise_max) == (4, 399)       # 1 bet + 398 behind


def test_straddle_order_and_min_raise() -> None:
    st = state({"straddle": 4})
    p, legal = step(st)
    assert p == 1                                                # BB acts first facing it
    assert st.bet == [4, 2] and st.to_call(1) == 2
    assert legal.raise_min == 8                                  # twice the straddle
    p, legal = step(st, Action.call())
    assert p == 0 and legal.check and legal.can_raise            # straddler's option


# --------------------------------------------------------------------------- restrictions

def test_bet_sizes_restricted_to_pot_fractions() -> None:
    st = state({"bet_sizes": [0.5, 1.0]})
    p, legal = step(st)
    # SB: high 2, pot after call 4 -> 2 + 2 = 4, 2 + 4 = 6, plus all-in 400
    assert legal.raise_sizes == (4, 6, 400)
    assert is_legal(Action.raise_to(6), legal) and not is_legal(Action.raise_to(5), legal)
    assert clamp(Action.raise_to(5), legal) == Action.raise_to(4)     # nearest (tie: smaller)
    assert clamp(Action.raise_to(300), legal) == Action.raise_to(400)


def test_bet_multiple() -> None:
    st = state({"bet_multiple": 5}, match={"starting_stack": 403})
    p, legal = step(st)
    assert legal.raise_min == 5 and legal.raise_step == 5 and legal.raise_max == 403
    assert is_legal(Action.raise_to(10), legal) and not is_legal(Action.raise_to(12), legal)
    assert is_legal(Action.raise_to(403), legal)                 # all-in always allowed
    assert clamp(Action.raise_to(12), legal) == Action.raise_to(10)
    assert pot_fraction_raise(1.0, 3, 1, 1, legal).amount % 5 == 0


def test_no_check_raise() -> None:
    st = state({"check_raise": False})
    p, legal = step(st, Action.call())          # SB limps
    p, legal = step(st, Action.check())         # BB checks: flop
    assert p == 1 and legal.can_raise
    p, legal = step(st, Action.check())         # BB checks the flop
    p, legal = step(st, Action.raise_to(4))     # SB bets
    assert p == 1 and legal.call and not legal.can_raise   # BB may not check-raise


# --------------------------------------------------------------------------- side pots

def test_side_pots_three_players() -> None:
    # A all-in 50, B 100, C 100 (C folded after putting in 100)
    pots = side_pots([50, 100, 100], live=[0, 1])
    assert pots == [(150, [0, 1]), (100, [1])]
    assert side_pots([30, 50], live=[0, 1]) == [(60, [0, 1]), (20, [1])]


def test_short_all_in_gets_refund_heads_up() -> None:
    st = state(match={"starting_stack": 400})
    st.stack = [30, 400]
    st.start = [30, 400]
    p, legal = step(st, Action.raise_to(30))   # SB all-in
    p, legal = step(st, Action.raise_to(100))  # (BB can only call here)
    assert sum(st.deltas) == 0


# --------------------------------------------------------------------------- protocol / clamp

def test_legal_tokens_round_trip() -> None:
    for legal in [LegalActions(fold=True, call=True, raise_min=4, raise_max=400, raise_step=2),
                  LegalActions(check=True, raise_min=4, raise_max=400, raise_sizes=(4, 6, 400))]:
        text = format_legal(legal)
        assert parse_legal(text) == legal
    assert format_legal(parse_legal("R:6|12|400")) == "R:6|12|400"
    assert parse_legal("F,C,R:8-400/5").raise_step == 5


def test_hand_message_with_blinds_round_trip() -> None:
    m = HandStart(120, 1, 400, 400, 50.0, sb=2, bb=4, ante=1)
    assert parse_line(encode_message(m)) == m


# --------------------------------------------------------------------------- match level

def test_blind_schedule_levels_and_messages() -> None:
    spec = VariantSpec.from_dict({"match": {"blind_schedule": [[3, 2, 4], [6, 5, 10]],
                                            "starting_stack": 1000}})
    rules = compile_spec(spec)
    assert [rules.level_at(h)[:2] for h in (0, 2, 3, 5, 6, 99)] == [
        (1, 2), (1, 2), (2, 4), (2, 4), (5, 10), (5, 10)]
    p = PlayerSpec.brain("calling_station").build()
    seen = []
    p.notify = lambda msg, inner=p.notify: (seen.append(msg), inner(msg))[1]
    play_match([p, PlayerSpec.brain("tier0").build()], spec, seed=0, hands=8, audit=True)
    hands = [m for m in seen if isinstance(m, HandStart)]
    assert [m.bb for m in hands] == [2, 2, 2, 4, 4, 4, 10, 10]


def test_persistent_stacks_rebuy() -> None:
    spec = VariantSpec.from_dict({"match": {"reset_stacks": False, "bust_ends_match": False,
                                            "starting_stack": 20}})
    m = play_match([PlayerSpec.brain("all_in").build(), PlayerSpec.brain("all_in").build()],
                   spec, seed=1, hands=40, audit=True)
    assert m.hands_played == 40                     # nobody's bust ends it
    assert m.chips[0] == -m.chips[1]


def test_lock_margin_follows_schedule_and_antes() -> None:
    spec = VariantSpec.from_dict({"betting": {"ante": 1},
                                  "match": {"hands": 6, "blind_schedule": [[4, 5, 10]]}})
    rules = compile_spec(spec)
    st = BotState()
    st.apply(MatchInfo(hands=6, sb=1, bb=2))
    st.hands_played, st.bankroll = 2, 100
    st.apply(HandStart(2, 0, 400, 400, sb=1, bb=2, ante=1))
    st.apply(ActRequest(5, 1, 398, 397, LegalActions(fold=True, call=True)))
    # committed 2 (ante 1 + sb 1); future hands 3 (BB: 1+2), 4 (SB: 1+5), 5 (BB: 1+10)
    assert lock_margin(st, True, rules) == 100 - 2 - (3 + 6 + 11)


@pytest.mark.parametrize("name", ["plo", "fl_holdem", "antes_straddle", "escalating_blinds"])
def test_catalog_betting_variants_play(name) -> None:
    from variant.spec import load_catalog
    spec = load_catalog()[name]
    for opp in ["maniac", "random_legal"]:
        m = play_match([PlayerSpec.brain("tier2", {"max_samples": 64, "rollout_worlds": 12, "pimc_worlds": 2}).build(),
                        PlayerSpec.brain(opp).build()], spec, seed=2, hands=150, audit=True)
        assert m.errors == [0, 0] and m.forfeit is None
