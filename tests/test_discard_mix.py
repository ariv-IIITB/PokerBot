"""DC: the 2-rule opponent discard model (bot/sim/discard.py, Inference discard_mix)."""
import numpy as np

from bot.sim import discard as S
from bot.sim.inference import Inference
from lab.opps import discard_rules as D

EV = D.evaluator()


def _deals(n, seed):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        c = rng.choice(52, 6, replace=False)
        yield np.array(c[:3], dtype=np.intp), np.array(c[3:], dtype=np.intp)


def test_vectorized_rules_match_the_lab_rules():
    for h3, flop in _deals(300, 3):
        assert S._opp_drop(EV, h3[None], flop)[0] == D.accepted_drops("opponent_keeps", EV, list(h3), list(flop))[0]
        acc = D.accepted_drops("keep_straight_draw", EV, list(h3), list(flop))
        assert set(np.flatnonzero(S._draw_keeps(h3[None], flop)[0])) == set(acc)


def test_probs_and_keeps():
    h3 = np.array([d[0] for d in _deals(200, 5)])
    flop = next(_deals(1, 6))[1]
    p = S.opp_drop_probs(EV, h3, flop, 0.3, 0.2)
    assert np.allclose(p.sum(axis=1), 1) and (p > 0).all()
    rng = np.random.default_rng(0)
    assert (S.mixed_keeps(EV, h3, flop, 0.0, rng) == S.opponent_keeps(EV, h3, flop)).all()
    kept = S.mixed_keeps(EV, h3, flop, 1.0, rng)
    assert all(set(k) <= set(h) and len(set(k)) == 2 for k, h in zip(kept, h3))


def test_inference_discard_ll_mixture_uniform_at_zero_beta():
    class R:  # the bits _discard_ll reads
        pass
    rec = R(); rec.state = R(); rec.state.rules = R(); rec.state.rules.evaluator = EV
    h3, flop = next(_deals(1, 9))
    d = R(); d.options = ("0", "1", "2"); d.action = R(); d.action.choice = "1"
    rng = np.random.default_rng(0)
    for beta, want in ((0.0, np.log(1 / 3)), ):
        inf = Inference({"enabled": True, "beta": beta, "discard_mix": 0.2, "discard_eps": 0.2})
        assert np.isclose(inf._discard_ll(rec, d, h3[None], list(flop), rng)[0], want)
    inf = Inference({"enabled": True, "beta": 6.0, "discard_mix": 0.2, "discard_eps": 0.2})
    lls = []
    for c in "012":
        d.action.choice = c
        lls.append(np.exp(inf._discard_ll(rec, d, h3[None], list(flop), rng)[0]))
    assert np.isclose(sum(lls), 1)
