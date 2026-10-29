"""Tests for the worked-example plugin `redraw_board` (copy this file for new plugins)."""
import sys

import numpy as np
import pytest

from bot.actions import Action
from bot.cards import parse_cards as P
from bot.game.compile import compile_spec
from bot.game.observation import hidden_from, observe
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from bot.protocols import ADAPTERS, get_adapter
from bot.protocol import ActRequest, OppAction
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from lab.engine import deck_for, play_match
from lab.players import PlayerSpec, SubprocessPlayer
from variant.spec import load_catalog

SPEC = load_catalog()["redraw_board"]


def deck_with(*texts):
    head = [c for t in texts for c in P(t)]
    return head + [c for c in range(52) if c not in head]


def play(script, deck=None, audit=True):
    rules = compile_spec(SPEC)
    st = GameState(rules, deck or deck_for(1, 0), [400, 400], audit=audit)
    script, seen = list(script), []
    while True:
        p = advance(st)
        if p is None:
            return st, seen
        legal = legal_actions(st, p)
        seen.append((p, legal))
        if legal.can_special:
            a = script.pop(0) if script else Action.special("none")
        else:
            a = Action.check() if legal.check else Action.call()
        act(st, p, a)


# 1. legality: who is asked, with which options, and the cost rule
def test_options_and_order() -> None:
    st, seen = play([])
    specials = [(p, l.special.choices) for p, l in seen if l.can_special]
    assert specials == [(1, ("none", "b0", "b1", "b2", "b3")), (0, ("none", "b0", "b1", "b2", "b3"))]


# 2. effects + conservation
def test_redraw_replaces_card_and_charges_cost() -> None:
    deck = deck_with("Ah,Kd", "2c,3d", "9s,8s,7s", "Qh", "Jc", "4d")
    st, _ = play([Action.special("b3"), Action.special("none")], deck)
    assert P("Qh")[0] in st.muck and P("Jc")[0] in st.board      # turn card replaced
    assert st.total[1] - st.total[0] == 3                          # BB paid the cost
    cards = st.deck + st.board + st.muck + st.hole[0] + st.hole[1]
    assert sorted(cards) == list(range(52))


# 3. no information leaks (state audit on) + the old card is public
def test_no_leaks_random_play() -> None:
    rng = np.random.default_rng(0)
    rules = compile_spec(SPEC)
    for seed in range(40):
        st = GameState(rules, deck_for(seed, 0), [400, 400], audit=True)
        while True:
            p = advance(st)
            for q in (0, 1):
                if not st.done:
                    assert not (observe(st, q).seen_cards & hidden_from(st, q))
            if p is None:
                break
            legal = legal_actions(st, p)
            if legal.can_special:
                a = Action.special(legal.special.choices[int(rng.integers(len(legal.special.choices)))])
            else:
                a = Action.check() if legal.check else Action.call()
            act(st, p, a)
        assert sum(st.deltas) == 0


# 4. protocol: the step's tokens survive every adapter
@pytest.mark.parametrize("name", sorted(n for n in ADAPTERS if n != "pokerbots"))
def test_tokens_round_trip(name) -> None:
    st, seen = play([])
    legal = [l for _, l in seen if l.can_special][0]
    e, b = get_adapter(name), get_adapter(name)
    req = ActRequest(10, 0, 395, 395, legal, 30.0, 0, 0)
    assert b.parse_line(e.encode_message(req)) == req
    for c in legal.special.choices:
        assert e.parse_action(b.encode_action(Action.special(c))) == Action.special(c)
        assert b.parse_line(e.encode_message(OppAction(Action.special(c)))) == OppAction(Action.special(c))


# 5. default policy: the generic layer replaces a card that hurts us
def test_default_policy_redraws_a_dangerous_card() -> None:
    from bot.state import GameState as BotState
    from bot.protocol import BoardUpdate, HandStart, HoleCards
    rules = compile_spec(SPEC)
    st = BotState()
    st.apply(HandStart(0, 1, 400, 400))                      # BB: we redraw first
    st.apply(HoleCards(P("Kc,Kd")))
    st.apply(OppAction(Action.raise_to(40)))
    st.record_my_action(Action.call())
    st.apply(BoardUpdate(1, P("2c,7h,9s")))
    st.record_my_action(Action.check())
    st.apply(OppAction(Action.check()))
    st.apply(BoardUpdate(2, P("2c,7h,9s,Ah")))               # an ace hit: bad for our kings
    rec = reconstruct(rules, st.hand, np.random.default_rng(0))
    legal = legal_actions(rec.state, rec.me)
    # bounded by worlds, not the wall clock, so CPU load cannot change the sample count
    picks = [decide_special(rec, legal, np.random.default_rng(s), 5.0, {"pimc_worlds": 200}).choice
             for s in range(3)]
    assert picks.count("b3") >= 2, picks


# 6. a full match with real bots, in-process and over the wire
def test_matches() -> None:
    m = play_match([PlayerSpec.brain("tier2", {"rollout_worlds": 24, "pimc_worlds": 4}).build(),
                    PlayerSpec.brain("random_legal").build()], SPEC, seed=4, hands=30, audit=True)
    assert m.errors == [0, 0] and m.forfeit is None
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", "tier2"])
    m = play_match([bot, PlayerSpec.brain("maniac").build()], SPEC, seed=5, hands=10, audit=True)
    assert m.errors == [0, 0] and m.forfeit is None
