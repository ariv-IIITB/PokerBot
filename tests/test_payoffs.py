"""Phase 15: payoff and side-mechanic plugins, with hand-computed expected payouts.
Chip conservation always counts the house: sum(deltas) + house == 0."""
import sys

import pytest

from bot.actions import Action, LegalActions, SpecialOption, clamp, is_legal
from bot.cards import parse_cards as P
from bot.game.compile import compile_spec
from bot.game.payoffs import market_value
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from bot.protocol import BoardUpdate, Info, encode_message, parse_legal, parse_line
from lab.engine import play_match
from lab.players import PlayerSpec, SubprocessPlayer
from variant.spec import VariantSpec, default_program, load_catalog


def deck_with(*texts):
    head = [c for t in texts for c in P(t)]
    return head + [c for c in range(52) if c not in head]


def spec_with(extra_steps=None, showdown=None, **kw) -> VariantSpec:
    prog = default_program()
    for at, step in reversed(extra_steps or []):
        prog.insert(at, step)
    if showdown:
        prog[-1] = showdown
    return VariantSpec.from_dict({"program": prog, **kw})


def run(spec, deck, script):
    """Play with `script` = list of actions for successive decisions; default check/call."""
    rules = compile_spec(spec)
    st = GameState(rules, deck, [rules.starting_stack] * 2, audit=True)
    import numpy as np
    rng = np.random.default_rng(0)
    script = list(script)
    while True:
        p = advance(st, rng)
        if p is None:
            break
        legal = legal_actions(st, p)
        a = script.pop(0) if script else (Action.check() if legal.check else Action.call())
        act(st, p, a)
    assert sum(st.deltas) + st.house == 0
    return st


# SB: AA, BB: KK, board blank -> SB wins at showdown
AA_KK = deck_with("Ah,Ad", "Kh,Kd", "2c,7s,9d", "Jc", "3h")


# --------------------------------------------------------------------------- bounty

def test_fixed_bounty_bonus() -> None:
    spec = spec_with([(2, {"type": "bounty", "mode": "fixed", "rank": "A", "bonus": 10})])
    st = run(spec, AA_KK, [])
    # Limp/check down: pot 4 -> SB +2, plus bounty 10 from BB.
    assert st.deltas == [12, -12]
    assert any(e.kind == "bounty" for e in st.events)


def test_bounty_needs_the_rank_and_an_outright_win() -> None:
    spec = spec_with([(2, {"type": "bounty", "mode": "fixed", "rank": "K", "bonus": 10})])
    st = run(spec, AA_KK, [])
    assert st.deltas == [2, -2]                    # BB holds the K but lost: no bounty


def test_bounty_multiplier() -> None:
    spec = spec_with([(2, {"type": "bounty", "mode": "fixed", "rank": "A", "multiplier": 3.0})])
    st = run(spec, AA_KK, [Action.raise_to(10), Action.call()])
    # Pot: 10 each -> +10; multiplier 3 -> extra (3-1) x 10 = 20.
    assert st.deltas == [30, -30]


def test_chosen_bounty_hidden_until_showdown() -> None:
    spec = spec_with([(2, {"type": "bounty", "mode": "chosen", "bonus": 5})])
    st = run(spec, AA_KK, [Action.special("A"), Action.special("Q")])
    assert st.deltas == [7, -7]
    choices = [e for e in st.events if e.kind == "special"]
    assert all(e.data["action"].choice in ("hidden", "A", "Q") for e in choices)
    assert [e.data["action"].choice for e in choices if e.visible == 1 and e.player == 0] == ["hidden"]


# --------------------------------------------------------------------------- auction

def auction_spec(**kw):
    step = {"type": "auction", "kind": "second_price", "prize": "card", "payment": "pot",
            "tie": "BB"}
    step.update(kw)
    return spec_with([(4, step)])                   # after the flop is dealt


def bids(sb, bb):
    # preflop: SB calls, BB checks; then the two sealed bids (SB first, BB second)
    return [Action.call(), Action.check(), Action.special(str(sb)), Action.special(str(bb))]


def test_second_price_auction_card_prize() -> None:
    st = run(auction_spec(), AA_KK, bids(10, 4))
    assert len(st.hole[0]) == 3 and len(st.hole[1]) == 2     # SB won the extra card
    assert st.total == [2 + 4, 2]                             # paid the loser's bid (4)


def test_first_price_and_all_pay() -> None:
    st = run(auction_spec(kind="first_price"), AA_KK, bids(10, 4))
    assert st.total == [12, 2]
    st = run(auction_spec(kind="all_pay"), AA_KK, bids(10, 4))
    assert st.total == [12, 6]


def test_auction_payment_destinations() -> None:
    st = run(auction_spec(payment="burn"), AA_KK, bids(10, 4))
    assert st.house == 4 and st.deltas[0] + st.deltas[1] == -4
    st = run(auction_spec(payment="opponent"), AA_KK, bids(10, 4))
    # SB pays BB 4, then wins the 4-chip pot with AA: +2 - 4 = -2
    assert st.deltas == [-2, 2]


def test_auction_tie_rules() -> None:
    st = run(auction_spec(tie="BB"), AA_KK, bids(5, 5))
    assert len(st.hole[1]) == 3
    st = run(auction_spec(tie="none"), AA_KK, bids(5, 5))
    assert len(st.hole[0]) == len(st.hole[1]) == 2 and st.total == [2, 2]


def test_auction_position_prize() -> None:
    st = run(auction_spec(prize="position"), AA_KK, bids(0, 3))   # BB wins position
    acts = [e.player for e in st.events if e.kind == "action"]
    assert acts[2:4] == [0, 1]                    # flop: SB (loser) acts first now


def test_auction_swap_and_peek_prizes() -> None:
    st = run(auction_spec(prize="swap"), AA_KK, bids(6, 1) + [Action.special("0")])
    assert len(st.muck) == 1 and P("Ah")[0] in st.muck
    st = run(auction_spec(prize="peek"), AA_KK, bids(0, 2))
    peek = [e for e in st.events if e.kind == "peek"]
    assert len(peek) == 1 and peek[0].visible == 1 and peek[0].data["cards"] == (st.board[3],)


def test_bid_range_legal_and_clamped() -> None:
    legal = LegalActions(special=SpecialOption("bid", (), 0, 50))
    assert is_legal(Action.special("17"), legal) and not is_legal(Action.special("51"), legal)
    assert not is_legal(Action.special("x"), legal)
    assert clamp(Action.special("99"), legal) == Action.special("50")
    assert clamp(Action.fold(), legal) == Action.special("0")
    assert parse_legal("S:bid:0-50") == legal


# --------------------------------------------------------------------------- boards / runs

def test_two_boards_split() -> None:
    prog = [{"type": "post_blinds"}, {"type": "deal_hole", "n": 2}, {"type": "betting"},
            {"type": "deal_board", "n": 5, "boards": 2}, {"type": "betting"},
            {"type": "showdown"}]
    spec = VariantSpec.from_dict({"program": prog})
    # board 0 gives SB a flush, board 1 gives BB a straight
    deck = deck_with("Ah,2h", "9c,Tc", "3h,4h,8h,Kd,Ks", "Jd,Qs,8s,2d,2s")
    st = run(spec, deck, [])
    assert st.deltas == [0, 0]                  # one board each: 2 + 2 back
    assert len(st.boards) == 2 and sum(e.kind == "board" for e in st.events) == 2


def test_run_it_twice_after_all_in() -> None:
    spec = spec_with(showdown={"type": "showdown", "runs": 2})
    st = run(spec, AA_KK, [Action.raise_to(400), Action.call()])
    runs = [e for e in st.events if e.kind == "run"]
    assert len(runs) == 1 and len(runs[0].data["cards"]) == 5      # the second run
    assert st.deltas in ([400, -400], [0, 0], [-400, 400])           # each run is half the pot
    assert len(st.muck) == 5                                          # second run's cards


def test_run_it_twice_only_when_all_in() -> None:
    spec = spec_with(showdown={"type": "showdown", "runs": 2})
    st = run(spec, AA_KK, [])
    assert not any(e.kind == "run" for e in st.events) and st.deltas == [2, -2]


# --------------------------------------------------------------------------- market

def test_market_trade_and_settlement() -> None:
    spec = spec_with([(2, {"type": "market", "quantity": "board_rank_sum"})])
    st = run(spec, AA_KK, [Action.special("30"), Action.special("40")])
    value = market_value("board_rank_sum", st.board)        # 2+7+9+11+3 = 32
    assert value == 32
    # BB bought 1 unit at 35, value 32 -> BB pays SB 3; SB also wins the 4-chip pot.
    assert st.deltas == [2 + 3, -2 - 3]


def test_market_settles_even_after_a_fold() -> None:
    spec = spec_with([(2, {"type": "market", "quantity": "board_hearts"})])
    st = run(spec, AA_KK, [Action.special("0"), Action.special("4"), Action.fold()])
    assert st.folded == 0 and any(e.kind == "reveal" and e.data.get("what") == "market"
                                  for e in st.events)
    hearts = market_value("board_hearts", P("2c,7s,9d,Jc,3h"))
    assert st.deltas[1] == 1 + (hearts - 2)               # BB bought at 2; won SB's blind


# --------------------------------------------------------------------------- modifiers

def test_rake_and_no_flop_no_drop() -> None:
    spec = VariantSpec.from_dict({"payoffs": [{"type": "rake", "percent": 10, "cap": 3}]})
    st = run(spec, AA_KK, [Action.raise_to(20), Action.call()])
    assert st.house == 3 and st.deltas == [17, -20]
    st = run(spec, AA_KK, [Action.fold()])
    assert st.house == 0


def test_pot_multiplier() -> None:
    spec = VariantSpec.from_dict({"payoffs": [{"type": "multiplier", "factor": 2.0}]})
    st = run(spec, AA_KK, [Action.raise_to(10), Action.call()])
    assert st.deltas == [20, -20]


# --------------------------------------------------------------------------- protocol

def test_protocol_round_trips() -> None:
    for m in [Info("bounty", "none", (), 12), Info("auction", "opp", (), 4),
              Info("run", "none", P("2c,3d,4h,5s,6c"), 1), BoardUpdate(1, P("2c,3d,4h"), 1)]:
        assert parse_line(encode_message(m)) == m


@pytest.mark.parametrize("name", ["auction_card", "bounty_rank", "side_market", "three_boards",
                                  "run_it_twice", "boards_discard_pl", "short_bounty_rit"])
def test_real_subprocess_bot_plays_side_mechanics(name: str) -> None:
    spec = load_catalog()[name]
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", "tier2"])
    m = play_match([bot, PlayerSpec.brain("random_legal").build()], spec, seed=4, hands=15,
                   audit=True)
    assert m.forfeit is None and m.errors[0] == 0, m.forfeit_reason


def test_dead_hand_loses_to_any_live_hand() -> None:
    from bot.evaluator import HandEvaluator
    from bot.game.scoring import Scorer
    sc = Scorer(high=HandEvaluator(5, hole_exact=2))
    board = P("2c,7s,9d,Jc,3h")
    # P0 holds a single card: can't use exactly 2 hole cards -> dead; P1 has 7-high junk.
    assert sc.shares([P("Ah"), P("4d,5h")], [board]) == [0.0, 1.0]
    assert sc.shares([P("Ah"), P("Kd")], [board]) == [0.5, 0.5]   # both dead: split
