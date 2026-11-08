"""Tier 4 R: our own range for the river solver (bot/strategy/own_range.py)."""
import numpy as np

from bot.actions import Action
from bot.cards import parse_cards as P
from bot.game.compile import compile_spec
from bot.protocol import BoardUpdate, HandStart, HoleCards, OppAction
from bot.sim.replay import reconstruct
from bot.state import GameState as BotState
from bot.strategy.own_range import own_range_weights
from variant.spec import load_catalog

STRONG, WEAK = P("Kd,Qc"), P("5c,4s")                 # on Ks Kh 7d 2c: trips vs nothing


def _turn_spot(line: str):
    """Hold'em, we are the small blind with 2h 3d. line: "bet" = raise preflop, flop; "check" = never bet."""
    rules = compile_spec(load_catalog()["holdem_nl"])
    st = BotState()
    st.apply(HandStart(0, 0, 400, 400))
    st.apply(HoleCards(P("2h,3d")))
    st.record_my_action(Action.raise_to(6) if line == "bet" else Action.call())
    st.apply(OppAction(Action.call() if line == "bet" else Action.check()))
    st.apply(BoardUpdate(1, P("Ks,Kh,7d")))
    st.apply(OppAction(Action.check()))                      # the big blind acts first after the flop
    if line == "bet":
        st.record_my_action(Action.raise_to(10))
        st.apply(OppAction(Action.call()))
    else:
        st.record_my_action(Action.check())
    st.apply(BoardUpdate(1, P("Ks,Kh,7d,2c")))
    return reconstruct(rules, st.hand, np.random.default_rng(0))


def test_a_line_of_bets_shifts_weight_toward_stronger_combos() -> None:
    combos = np.array([STRONG, WEAK])
    bet = own_range_weights(_turn_spot("bet"), combos, np.random.default_rng(1))
    chk = own_range_weights(_turn_spot("check"), combos, np.random.default_rng(1))
    assert abs(bet.sum() - 1.0) < 1e-9 and abs(chk.sum() - 1.0) < 1e-9
    assert bet[0] > bet[1]                                   # raising twice: trips beat nothing
    assert bet[0] / bet[1] > chk[0] / chk[1]                 # ... and more so than after checking it down


def test_combos_with_seen_cards_get_no_weight_and_ours_stays_possible() -> None:
    rec = _turn_spot("bet")
    combos = np.array([P("Kd,Qc"), P("Ks,Qc"), P("2h,3d"), P("2c,9h")])   # board card, our hand, board card
    w = own_range_weights(rec, combos, np.random.default_rng(2))
    assert w[1] == 0.0 and w[3] == 0.0 and w[0] > 0 and w[2] > 0


def test_uniform_when_nothing_in_our_line_is_informative() -> None:
    rec = _turn_spot("bet")
    rec.my_decisions = []                                    # no recorded decision of ours
    w = own_range_weights(rec, np.array([STRONG, WEAK]), np.random.default_rng(3))
    assert np.allclose(w, 0.5)


def test_the_public_discard_is_excluded_and_scored_with_the_hand() -> None:
    """Discard Hold'em, in a real match: the public discards are in no candidate hand, the weights are a
    distribution, and our own hand always keeps weight."""
    from lab.river_bench import record_spots
    spots = record_spots(12, opponents=("d_conv_opp3",), hands=60, first_seed=51000)
    checked = 0
    for c in spots:
        rec = c.rec
        discard = [t for t in rec.mapping if t not in rec.state.hole[rec.me] and t not in rec.state.board
                   and t in {x for h in rec.state.hole for x in h} | set(rec.state.muck)]
        pool = np.array(sorted(set(rec.pool) | set(c.hole)), dtype=np.int64)
        i, j = np.triu_indices(len(pool), 1)
        combos = np.stack([pool[i], pool[j]], axis=1)
        gone = {rec.mapping[t] for t in discard}
        assert gone and not np.isin(combos, list(gone)).any()      # the public discard is not in the pool at all
        bad = np.array([[min(gone), int(pool[0])]])                # ... and a combo holding it gets no weight
        w = own_range_weights(rec, np.vstack([combos, bad]), np.random.default_rng(4))
        assert w[-1] == 0.0
        w = own_range_weights(rec, combos, np.random.default_rng(4))
        assert abs(w.sum() - 1.0) < 1e-9 and (w >= 0).all()
        mine = int(np.nonzero((combos[:, 0] == min(c.hole)) & (combos[:, 1] == max(c.hole)))[0][0])
        assert w[mine] > 0                                          # our own hand is always possible
        checked += 1
    assert checked == len(spots) == 12
