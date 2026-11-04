"""RD: the river exploit pieces in Tier 3: shifts on the solver's strategy, size-aware range narrowing, the fitted own range."""
import numpy as np

import bot.brains.tier3 as t3
from bot.brains.tier3 import Tier3Brain
from bot.state import OPP
from bot.strategy.own_range import OWN_BET

FACING = [("F", 0), ("C", 10), ("R", 40)]
UNFACED = [("K", 0), ("R", 10), ("R", 99)]


def test_shifts_do_nothing_without_evidence():
    b = Tier3Brain()
    p = b.p
    for labels in (FACING, UNFACED):
        probs = np.array([0.2, 0.5, 0.3])
        assert np.allclose(b._river_shift(probs, labels, 0.3, p), probs)


def test_shifts_move_the_right_way(monkeypatch):
    b = Tier3Brain()
    monkeypatch.setattr(t3, "overfolder_lambda", lambda tr, ramp: 1.0)
    monkeypatch.setattr(t3, "valueonly_lambda", lambda ty, q: 1.0)
    bluff = b._river_shift(np.array([0.9, 0.05, 0.05]), UNFACED, 0.1, b.p)
    assert bluff[1] + bluff[2] > 0.1 and abs(bluff.sum() - 1) < 1e-9          # a weak hand bets more
    assert np.allclose(b._river_shift(np.array([0.9, 0.05, 0.05]), UNFACED, 0.9, b.p), [0.9, 0.05, 0.05])   # a strong hand: untouched
    fold = b._river_shift(np.array([0.1, 0.8, 0.1]), FACING, 0.5, b.p)
    assert fold[0] > 0.1 and fold[1] < 0.8 and abs(fold.sum() - 1) < 1e-9     # a bluff-catcher folds more


class _H:
    tocall, pot, hand_id = 50, 150, 1
    history: list = []


def test_narrowing_follows_bet_size_and_is_inert_without_a_bet():
    from types import SimpleNamespace as NS
    b = Tier3Brain()
    rank = np.arange(200)
    w = np.ones(200)
    h = _H()
    assert np.allclose(b._narrow_range(w, rank, h, b.p), w)                  # no opponent bet in the history: unchanged
    h.history = [NS(street=3, actor=OPP, action=NS(kind="R"))]
    st = b.opponent.spots
    for _ in range(60):                                                      # a value-heavy bettor seen at showdown
        st.spots["bluff_index"].add(False)
        st.spots["river_bet"].add(True)
    small = b._narrow_range(w, rank, h, b.p)
    h.tocall, h.hand_id = 400, 2                                              # a much bigger bet: a rarer, stronger slice
    big = b._narrow_range(w, rank, h, b.p)
    top = rank >= 150
    assert big[top].sum() > small[top].sum() > w[top].sum() / w.sum()        # mass moves to the top, more for the bigger bet
    assert abs(big.sum() - 1) < 1e-9 and (big > 0).all()


def test_own_bet_table_is_a_proper_model():
    for (nb, facing), tab in OWN_BET.items():
        assert nb in (0, 3, 4, 5) and ("F" in tab or "C" in tab) == facing and all(len(v) == 2 for v in tab.values())
