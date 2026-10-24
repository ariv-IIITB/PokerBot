"""Phase 13: card-manipulation steps (discard, draw, swap, choose, peek, expose).

Covers every option combination with random play (audit on): card conservation after
every step, no information leaks, private choices hidden, simultaneous choices blind,
costs, delayed reveals, and the protocol path through a real subprocess bot.
"""
import itertools
import random
import sys

import pytest

from bot.actions import Action
from bot.cards import parse_cards as P
from bot.game.compile import compile_spec
from bot.game.observation import hidden_from, observe
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from bot.protocol import Info, OppAction, encode_message, parse_line
from lab.engine import deck_for, play_match
from lab.players import PlayerSpec, SubprocessPlayer
from variant.spec import VariantSpec


def holdem_with(step: dict, street: int = 1, **spec) -> VariantSpec:
    """Hold'em with `step` inserted before the betting round of `street`."""
    prog = [{"type": "post_blinds"}, {"type": "deal_hole", "n": spec.pop("hole", 3)}]
    for i, n in enumerate([0, 3, 1, 1]):
        if i:
            prog.append({"type": "deal_board", "n": n})
        if i == street:
            prog.append(step)
        prog.append({"type": "betting"})
    prog.append({"type": "showdown"})
    return VariantSpec.from_dict({"program": prog, **spec})


ORDERS = ["BB_first", "SB_first", "simultaneous"]
STEP_VARIANTS = (
    [{"type": "discard", "n": n, "order": o, "visibility": v, "destination": d, "optional": opt}
     for n, o, v, d, opt in itertools.product([1, 2], ORDERS, ["public", "private", "later"],
                                              ["board", "muck", "opponent"], [False, True])]
    + [{"type": "draw", "max": m, "min": lo, "cost": c, "visibility": v, "order": o}
       for m, lo, c, v, o in itertools.product([1, 3], [0, 1], [0, 3], ["public", "private"], ORDERS)
       if lo <= m]
    + [{"type": "swap", "with": w, "mode": md, "probability": pr, "order": o, "cost": c}
       for w, md, pr, o, c in itertools.product(["opponent", "board", "deck"],
                                                ["optional", "forced", "random"], [1.0, 0.5],
                                                ORDERS, [0, 2])]
    + [{"type": "choose", "offer": of, "keep": k, "order": o}
       for of, k, o in [(3, 1, "BB_first"), (4, 2, "simultaneous"), (2, 2, "SB_first")]]
    + [{"type": "peek", "target": t, "cost": c, "order": o}
       for t, c, o in itertools.product(["board", "opponent"], [0, 5], ORDERS)]
    + [{"type": "expose", "n": n, "chosen": ch, "order": o}
       for n, ch, o in itertools.product([1, 2], [True, False], ORDERS)]
)


def random_policy(rng: random.Random):
    def policy(st, p, legal):
        if legal.can_special:
            return Action.special(rng.choice(legal.special.choices))
        opts = [a for a, ok in [(Action.fold(), legal.fold), (Action.check(), legal.check),
                                (Action.call(), legal.call)] if ok]
        if legal.can_raise and rng.random() < 0.3:
            opts.append(Action.raise_to(rng.randint(legal.raise_min, legal.raise_max)))
        return rng.choice(opts)
    return policy


def all_cards(st) -> list[int]:
    offers = [c for cs in st.extra.get("offers", {}).values() for c in cs]
    return sorted(st.deck + st.board + st.muck + offers + [c for h in st.hole for c in h])


def play_audited(spec: VariantSpec, seed: int) -> GameState:
    rules = compile_spec(spec)
    st = GameState(rules, deck_for(seed, 0, rules.deck), [rules.starting_stack] * 2,
                   audit=True)
    rng = random.Random(seed)
    policy = random_policy(rng)
    start = sorted(rules.deck)
    import numpy as np
    srng = np.random.default_rng(seed)
    while True:
        p = advance(st, srng)
        assert all_cards(st) == start, "cards duplicated or lost"
        for q in range(2):
            if not st.done:
                assert not (observe(st, q).seen_cards & hidden_from(st, q)), ("leak", q)
        if p is None:
            break
        act(st, p, policy(st, p, legal_actions(st, p)))
        assert all_cards(st) == start, "cards duplicated or lost"
    assert sum(st.deltas) == 0 and st.done
    return st


@pytest.mark.parametrize("i", range(len(STEP_VARIANTS)))
def test_every_option_combination(i: int) -> None:
    step = STEP_VARIANTS[i]
    spec = holdem_with(dict(step), street=1, hole=3 if step["type"] != "choose" else 2)
    assert spec.validate() == [], spec.validate()
    for seed in range(12):
        play_audited(spec, seed)


# --------------------------------------------------------------------------- semantics

def drive(spec: VariantSpec, script: list, deck=None):
    """Play a hand where decisions come from `script` ([(player, Action)...] consumed in
    order); unscripted decisions check/call/first option."""
    rules = compile_spec(spec)
    st = GameState(rules, deck or deck_for(1, 0, rules.deck), [rules.starting_stack] * 2,
                   audit=True)
    import numpy as np
    rng = np.random.default_rng(0)
    seen = []
    while True:
        p = advance(st, rng)
        if p is None:
            return st, seen
        legal = legal_actions(st, p)
        seen.append((p, legal))
        if script and script[0][0] == p and (legal.can_special == (script[0][1].kind == "S")):
            a = script.pop(0)[1]
        elif legal.can_special:
            a = Action.special(legal.special.choices[0])
        else:
            a = Action.check() if legal.check else Action.call()
        act(st, p, a)


def deck_with(*texts):
    head = [c for t in texts for c in P(t)]
    return head + [c for c in range(52) if c not in head]


def test_public_discard_to_board_bb_first() -> None:
    spec = holdem_with({"type": "discard", "n": 1, "order": "BB_first"}, street=1)
    deck = deck_with("Ah,Kh,Qh", "2c,3c,4c", "9d,8d,7d")
    st, seen = drive(spec, [(1, Action.special("2")), (0, Action.special("0"))], deck)
    assert [p for p, legal in seen if legal.can_special] == [1, 0]
    assert seen[[i for i, (p, l) in enumerate(seen) if l.can_special][0]][1].special.choices == ("0", "1", "2")
    assert P("4c")[0] in st.board and P("Ah")[0] in st.board
    v0 = observe(st, 0)
    assert (1, Action.special("2")) in v0.actions        # public: SB saw BB's exact choice


def test_private_discard_hides_choice_and_cards() -> None:
    spec = holdem_with({"type": "discard", "n": 1, "visibility": "private", "destination": "muck"})
    st, _ = drive(spec, [(1, Action.special("1"))])
    v0 = observe(st, 0)
    assert (1, Action.special("hidden")) in v0.actions
    assert not any(e.kind == "reveal" for e in st.events)


def test_later_visibility_reveals_at_showdown_only() -> None:
    spec = holdem_with({"type": "discard", "n": 1, "visibility": "later", "destination": "muck"})
    st, _ = drive(spec, [])
    reveals = [e for e in st.events if e.kind == "reveal"]
    assert st.showdown and len(reveals) == 2
    assert all(st.events.index(e) > max(i for i, x in enumerate(st.events) if x.kind == "board")
               for e in reveals)


def test_discard_to_opponent() -> None:
    spec = holdem_with({"type": "discard", "n": 1, "destination": "opponent", "order": "SB_first"})
    st, _ = drive(spec, [(0, Action.special("0"))])
    assert len(st.hole[0]) == 3 and len(st.hole[1]) == 3   # each gave one, got one


def test_simultaneous_second_player_is_blind() -> None:
    spec = holdem_with({"type": "discard", "n": 1, "order": "simultaneous"})
    rules = compile_spec(spec)
    st = GameState(rules, deck_for(2, 0), [400, 400], audit=True)
    p = advance(st)
    while not legal_actions(st, p).can_special:
        act(st, p, Action.call() if legal_actions(st, p).call else Action.check())
        p = advance(st)
    assert p == 0
    act(st, 0, Action.special("1"))
    p = advance(st)
    assert p == 1
    assert not any(e.kind == "special" for e in st.events)   # nothing revealed yet
    act(st, 1, Action.special("0"))
    advance(st)
    assert sum(e.kind == "special" for e in st.events) == 4   # 2 choices x 2 viewers


def test_draw_replaces_cards_and_shows_count() -> None:
    spec = holdem_with({"type": "draw", "max": 2, "visibility": "private"}, hole=3)
    st, _ = drive(spec, [(1, Action.special("0+2"))])
    v0 = observe(st, 0)
    assert (1, Action.special("2")) in v0.actions            # opponent sees "drew 2"
    assert len(st.muck) == 2 and len(st.hole[1]) == 3


def test_draw_cost_paid_to_pot() -> None:
    spec = holdem_with({"type": "draw", "max": 1, "cost": 3})
    st, _ = drive(spec, [(1, Action.special("0")), (0, Action.special("none"))])
    assert st.total[1] - st.total[0] == 3          # BB paid 3 to draw; SB drew nothing
    assert sum(st.deltas) == 0


def test_unaffordable_cost_only_free_option() -> None:
    spec = holdem_with({"type": "peek", "cost": 500})
    st, seen = drive(spec, [])
    peeks = [legal for p, legal in seen if legal.can_special]
    assert peeks and all(l.special.choices == ("no",) for l in peeks)


def test_peek_board_shows_next_card() -> None:
    spec = holdem_with({"type": "peek", "target": "board", "order": "BB_first"}, street=1)
    st, _ = drive(spec, [(1, Action.special("yes"))])
    peek = [e for e in st.events if e.kind == "peek"]
    assert len(peek) == 1 and peek[0].visible == 1
    turn = st.board[3]
    assert peek[0].data["cards"] == (turn,)                   # it really was the next card


def test_swap_with_board_and_deck() -> None:
    spec = holdem_with({"type": "swap", "with": "board", "mode": "forced", "order": "BB_first"})
    deck = deck_with("Ah,Kh,Qh", "2c,3c,4c", "9d,8d,7d")
    st, _ = drive(spec, [(1, Action.special("h0b1"))], deck)
    assert P("2c")[0] in st.board and P("8d")[0] in st.hole[1]
    spec = holdem_with({"type": "swap", "with": "deck", "mode": "optional"})
    st, _ = drive(spec, [(1, Action.special("2"))])
    assert len(st.muck) == 1


def test_choose_offers_privately() -> None:
    spec = VariantSpec.from_dict({"program": [
        {"type": "post_blinds"}, {"type": "choose", "offer": 4, "keep": 2},
        {"type": "betting"}, {"type": "deal_board", "n": 5}, {"type": "betting"},
        {"type": "showdown"}]})
    st, seen = drive(spec, [(1, Action.special("1+3"))])
    offers = [e for e in st.events if e.kind == "offer"]
    assert [e.visible for e in offers] == [0, 1]
    assert st.hole[1] == [offers[1].data["cards"][1], offers[1].data["cards"][3]]
    assert len(st.muck) == 4


def test_expose_random_and_face_up_deal() -> None:
    spec = holdem_with({"type": "expose", "n": 1, "chosen": False})
    st, seen = drive(spec, [])
    assert not any(l.can_special for _, l in seen)            # no decision when random
    assert sum(e.kind == "expose" for e in st.events) == 2
    face_up = VariantSpec.from_dict({"program": [
        {"type": "post_blinds"}, {"type": "deal_hole", "n": 2, "face_up": 1},
        {"type": "betting"}, {"type": "deal_board", "n": 5}, {"type": "showdown"}]})
    st, _ = drive(face_up, [])
    ups = [e for e in st.events if e.kind == "expose"]
    assert [e.data["cards"][0] for e in ups] == [st.hole[0][0], st.hole[1][0]]


# --------------------------------------------------------------------------- protocol

def test_info_message_round_trip() -> None:
    for m in [Info("expose", "opp", P("Ah")), Info("offer", "me", P("2c,3d,4h")),
              Info("burn", "none", P("9s"))]:
        assert parse_line(encode_message(m)) == m
    assert parse_line("OPP type=S choice=0+2") == OppAction(Action.special("0+2"))


@pytest.mark.parametrize("name", ["mit2026_discard", "draw1", "choose_two", "exposed_hole",
                                  "peek_board", "swap_opponent", "pineapple"])
def test_real_subprocess_bot_plays_card_steps(name: str) -> None:
    from variant.spec import load_catalog
    spec = load_catalog()[name]
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", "tier2"])
    m = play_match([bot, PlayerSpec.brain("random_legal").build()], spec, seed=3, hands=15,
                   audit=True)
    assert m.forfeit is None and m.errors[0] == 0, m.forfeit_reason
