"""Phase 17: inference from public information (importance weights on opponent hands)."""
import numpy as np

from bot.actions import Action
from bot.cards import parse_cards as P
from bot.game.compile import compile_spec
from bot.protocol import BoardUpdate, HandStart, HoleCards, OppAction
from bot.sim.inference import Inference
from bot.sim.replay import reconstruct
from bot.state import GameState as BotState
from variant.spec import load_catalog

ON = {"enabled": True, "beta": 6.0, "gamma": 3.0, "ref_hands": 200, "min_ess": 0.0}


def mit_after_opp_discard(opp_discard_choice: str):
    """MIT variant, we are SB: BB discarded publicly first (BB-first order), now our turn.
    The discarded card shows up on the board."""
    rules = compile_spec(load_catalog()["mit2026_discard"])
    st = BotState()
    st.apply(HandStart(0, 0, 400, 400))
    st.apply(HoleCards(P("2c,3d,4h")))
    st.record_my_action(Action.raise_to(20))
    st.apply(OppAction(Action.call()))
    st.apply(BoardUpdate(1, P("9s,8s")))
    st.apply(OppAction(Action.special(opp_discard_choice)))
    st.apply(BoardUpdate(1, P("9s,8s,Ah")))                 # their discard: the ace
    rec = reconstruct(rules, st.hand, np.random.default_rng(0))
    return rules, rec


def test_discard_weights_favour_consistent_hands() -> None:
    rules, rec = mit_after_opp_discard("0")
    d = [x for x in rec.opp_decisions if x.kind == "discard"]
    assert len(d) == 1
    inf = Inference(dict(ON))
    # Their hole when deciding: [ace, x, y]. Which (x, y) did they keep?
    unknown = [t for t in d[0].hole if t not in rec.mapping]
    assert len(unknown) == 2
    kept_kk = P("Kc,Kd")
    kept_72 = P("7c,2s")
    cols = {unknown[0]: np.array([kept_kk[0], kept_72[0]]),
            unknown[1]: np.array([kept_kk[1], kept_72[1]])}
    lw = inf.log_weights(rec, cols, 2, np.random.default_rng(1))
    assert lw is not None and lw[0] > lw[1]          # throwing the ace keeping KK: plausible


def test_bet_weights_favour_strong_hands_after_a_raise() -> None:
    rules = compile_spec(load_catalog()["holdem_nl"])
    st = BotState()
    st.apply(HandStart(0, 1, 400, 400))                      # we are BB
    st.apply(HoleCards(P("2c,3d")))
    st.apply(OppAction(Action.call()))
    st.record_my_action(Action.check())
    st.apply(BoardUpdate(1, P("Ks,Kh,7d")))
    st.record_my_action(Action.check())
    st.apply(OppAction(Action.raise_to(6)))                  # they bet the flop
    rec = reconstruct(rules, st.hand, np.random.default_rng(0))
    unknown = [t for t in rec.state.hole[0] if t not in rec.mapping]
    strong, weak = P("Kd,Qc"), P("5c,4s")
    cols = {unknown[0]: np.array([strong[0], weak[0]]), unknown[1]: np.array([strong[1], weak[1]])}
    lw = Inference(dict(ON)).log_weights(rec, cols, 2, np.random.default_rng(2))
    assert lw[0] > lw[1]


def test_off_switch_and_collapse_fallback() -> None:
    _, rec = mit_after_opp_discard("0")
    cols = rec.assignments(np.random.default_rng(3), 50)
    assert Inference({"enabled": False}).log_weights(rec, cols, 50, np.random.default_rng(3)) is None
    sharp = dict(ON, beta=1e4, min_ess=0.5)                  # absurdly sharp -> collapses
    assert Inference(sharp).weights(rec, cols, 50, np.random.default_rng(3)) is None
    w = Inference(dict(ON)).weights(rec, cols, 50, np.random.default_rng(3))
    assert w is not None and abs(w.mean() - 1.0) < 1e-9


def test_inference_shifts_the_share_estimate() -> None:
    """After the opponent bets a paired board, our expected share with inference is lower."""
    from bot.sim.share import expected_share
    rules = compile_spec(load_catalog()["holdem_nl"])
    st = BotState()
    st.apply(HandStart(0, 1, 400, 400))
    st.apply(HoleCards(P("Qc,Jd")))
    st.apply(OppAction(Action.raise_to(6)))
    st.record_my_action(Action.call())
    st.apply(BoardUpdate(1, P("As,8h,3d")))
    st.record_my_action(Action.check())
    st.apply(OppAction(Action.raise_to(8)))
    rec = reconstruct(rules, st.hand, np.random.default_rng(0))
    off = expected_share(rec, np.random.default_rng(4), 0.05, max_samples=6000)
    on = expected_share(rec, np.random.default_rng(4), 0.05, max_samples=6000,
                        inference=Inference(dict(ON, min_ess=0.02)))
    assert on.share < off.share


def test_tier2_with_inference_plays_legally() -> None:
    from lab.engine import play_match
    from lab.players import PlayerSpec
    for name in ["mit2026_discard", "holdem_nl", "auction_card"]:
        m = play_match([PlayerSpec.brain("tier2", {"inference": True, "rollout_worlds": 24,
                                                   "pimc_worlds": 4}).build(),
                        PlayerSpec.brain("random_legal").build()], load_catalog()[name],
                       seed=2, hands=25, audit=True)
        assert m.errors == [0, 0] and m.forfeit is None


def test_trust_levels() -> None:
    from bot.sim.inference import Trust
    t = Trust()
    assert abs(t.level("bet") - 0.5) < 1e-9                  # starts half-trusting
    t.update({"bet": (-0.1 * 50, 50)})                        # model explains them badly
    assert t.level("bet") == 0.0
    t2 = Trust()
    t2.update({"bet": (0.25 * 40, 40), "discard": (0.0, 10)})
    assert t2.level("bet") == 1.0 and t2.level("discard") < 0.5


def test_opponent_range_weights_over_explicit_hands() -> None:
    # The opponent module answers "how likely is each hand" with the same likelihood the
    # sampled worlds use, so a river solver needs no second copy of it.
    from bot.opponent import Opponent
    rules = compile_spec(load_catalog()["holdem_nl"])
    st = BotState()
    st.apply(HandStart(0, 1, 400, 400))
    st.apply(HoleCards(P("2c,3d")))
    st.apply(OppAction(Action.call()))
    st.record_my_action(Action.check())
    st.apply(BoardUpdate(1, P("Ks,Kh,7d")))
    st.record_my_action(Action.check())
    st.apply(OppAction(Action.raise_to(6)))
    rec = reconstruct(rules, st.hand, np.random.default_rng(0))
    opp = Opponent(dict(ON), use_trust=False)
    combos = np.array([P("Kd,Qc"), P("5c,4s"), P("2c,9h")])  # strong, weak, holds our 2c
    w = opp.range_weights(rec, combos, np.random.default_rng(1))
    assert abs(w.sum() - 1.0) < 1e-9 and w[0] > w[1] and w[2] == 0.0
    flat = Opponent({"enabled": False}).range_weights(rec, combos[:2], np.random.default_rng(1))
    assert np.allclose(flat, [0.5, 0.5])                     # nothing informative: uniform
