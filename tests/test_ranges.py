"""Phase G: preflop model (frequencies of the four spots) and the own-range percentile."""
import numpy as np
import pytest

from bot.actions import Action
from bot.cards import parse_cards as P
from bot.game.rules_spec import active_rules
from bot.sim.tables import load_tables
from bot.state import ME, OPP, ActionRecord, HandState
from bot.strategy.preflop import (PreflopModel, Spot, blend_above, blocker_value, keep_playability,
                                  playability, preflop_spot)
from bot.strategy.ranges import OwnRange

RULES = active_rules()
TABLES = load_tables(RULES)
pytestmark = pytest.mark.skipif(TABLES is None or TABLES.classes.size != 3,
                                reason="needs the embedded 3-card tables")


@pytest.fixture(scope="module")
def model() -> PreflopModel:
    return PreflopModel(TABLES)


def share(model: PreflopModel, arr: np.ndarray) -> np.ndarray:
    return (arr * model.counts[:, None]).sum(0) / model.total


def test_blend_is_linear_over_the_band() -> None:
    x = np.array([0.0, 0.48, 0.50, 0.52, 1.0])
    assert blend_above(x, 0.5, 0.04).tolist() == pytest.approx([0, 0.0, 0.5, 1.0, 1.0])
    assert blend_above(x, 0.5, 0.0).tolist() == [0, 0, 1, 1, 1]


def test_playability_ranks_connected_suited_hands_over_junk() -> None:
    assert keep_playability(*P("9h,8h")) > keep_playability(*P("9h,3c"))
    assert keep_playability(*P("Ah,5h")) > keep_playability(*P("Ah,5c"))
    assert playability(P("9h,8h,7h")) > playability(P("9h,8h,2c"))      # three working together
    assert playability(P("Kh,Kd,2c")) >= 0.8
    assert blocker_value(P("Ah,5h,2c")) == 1.0 and blocker_value(P("Ah,5c,2d")) == 0.85
    assert blocker_value(P("Kh,5c,2d")) == 0.4 and blocker_value(P("Qh,5c,2d")) == 0.0


def test_percentiles_are_ordered_and_count_weighted(model: PreflopModel) -> None:
    aces = model.class_of(P("Ah,Ad,Ac"))
    trash = model.class_of(P("2h,4d,9c"))
    assert model.c_pct[aces] > 0.97 and model.c_pct[trash] < 0.05
    assert model.s_pct[aces] > model.s_pct[trash]
    mean = float((model.c_pct * model.counts).sum() / model.total)
    assert mean == pytest.approx(0.5, abs=0.01)                         # a percentile is uniform


def test_spot_tables_hit_their_frequencies(model: PreflopModel) -> None:
    fold, limp, raise_ = share(model, model.btn_open(0.05, 0.25, 0.04, 0.25, 0.04))
    assert (fold, limp, raise_) == pytest.approx((0.05, 0.25, 0.70), abs=0.02)
    assert share(model, model.bb_vs_limp(0.40, 0.04))[2] == pytest.approx(0.40, abs=0.01)
    f, c, r = share(model, model.bb_vs_open(0.70, 0.08, 0.16, 0.04))
    assert (1 - f) == pytest.approx(0.70, abs=0.03) and r == pytest.approx(0.16, abs=0.01)
    f, c, r = share(model, model.btn_vs_3bet(0.60, 0.03, 0.08, 0.04))
    assert (1 - f) == pytest.approx(0.60, abs=0.03) and r == pytest.approx(0.08, abs=0.01)
    for arr in (model.btn_open(0.05, 0.25, 0.04, 0.25, 0.04), model.bb_vs_open(0.7, 0.08, 0.16, 0.04)):
        assert np.allclose(arr.sum(axis=1), 1.0) and arr.min() >= 0


def test_light_threebets_use_blockers_not_the_worst_hands(model: PreflopModel) -> None:
    arr = model.bb_vs_open(0.70, 0.08, 0.16, 0.04)
    value = model.c_pct >= 0.92
    bluffs = (arr[:, 2] > 0.5) & ~value
    assert bluffs.sum() > 0 and model.bluff[bluffs].mean() > model.bluff[~bluffs].mean()
    assert model.class_of(P("2h,4d,9c")) not in np.nonzero(bluffs)[0]    # the worst hand never bluffs


def test_the_very_best_hands_sometimes_limp_as_traps(model: PreflopModel) -> None:
    arr = model.btn_open(0.05, 0.25, 0.04, 0.25, 0.04)
    top = arr[model.class_of(P("Ah,Ad,Ac"))]
    assert 0.1 < top[1] < 0.5 and top[2] > 0.5


# --------------------------------------------------------------------------- spots

def hand(seat: int, recs) -> HandState:
    h = HandState(1, seat, 200, 200)
    h.history = [ActionRecord(0, a, act) for a, act in recs]
    h.opp_bet = None
    return h


def test_spot_detection() -> None:
    assert preflop_spot(hand(0, []), 2) == Spot("btn_open")
    assert preflop_spot(hand(1, [(OPP, Action.call())]), 2) == Spot("bb_vs_limp")
    s = preflop_spot(hand(1, [(OPP, Action.raise_to(5))]), 2)
    assert s.name == "bb_vs_open" and s.raise_to_bb == 2.5
    s = preflop_spot(hand(0, [(ME, Action.raise_to(5)), (OPP, Action.raise_to(18))]), 2)
    assert s.name == "btn_vs_3bet" and s.raise_to_bb == 9.0 and s.ratio == pytest.approx(3.6)
    s = preflop_spot(hand(0, [(ME, Action.call()), (OPP, Action.raise_to(8))]), 2)
    assert s.name == "bb_vs_open" and s.raise_to_bb == 4.0
    assert preflop_spot(hand(1, [(OPP, Action.raise_to(5)), (ME, Action.raise_to(18)),
                                 (OPP, Action.raise_to(40))]), 2) is None      # facing a 4-bet: Tier 2
    flop = hand(0, [])
    flop.street = 1
    assert preflop_spot(flop, 2) is None


# --------------------------------------------------------------------------- own range

def test_percentile_orders_hands_on_a_board(model: PreflopModel) -> None:
    ev = RULES.evaluator
    rng_ = OwnRange(ev, TABLES, RULES.deck)
    board = P("Ad,7c,2h")
    rng = np.random.default_rng(1)
    top = rng_.percentile(P("Ah,Ac,7d"), board, [], None, rng)
    mid = rng_.percentile(P("Ah,Kc,5d"), board, [], None, np.random.default_rng(1))
    low = rng_.percentile(P("9h,8c,3d"), board, [], None, np.random.default_rng(1))
    assert top > 0.9 and low < 0.35 and top > mid > low


def test_percentile_respects_class_weights(model: PreflopModel) -> None:
    """Against a range of only strong hands the same hand ranks lower than against everything."""
    ev = RULES.evaluator
    rng_ = OwnRange(ev, TABLES, RULES.deck)
    board = P("Ad,7c,2h")
    hand_ = P("Kh,Qc,5d")                                # king high on an ace-high board
    wide = rng_.percentile(hand_, board, [], None, np.random.default_rng(2), n=1500)
    tight = rng_.percentile(hand_, board, [], (model.c_pct >= 0.9).astype(float), np.random.default_rng(2), n=1500)
    assert tight < wide


def test_percentile_turn_and_empty_range(model: PreflopModel) -> None:
    ev = RULES.evaluator
    rng_ = OwnRange(ev, TABLES, RULES.deck)
    p = rng_.percentile(P("Ah,Kc"), P("Ad,7c,2h,9s"), P("3d,4d"), None, np.random.default_rng(3))
    assert 0.0 <= p <= 1.0
    assert rng_.percentile(P("Ah,Kc"), P("Ad,7c,2h"), [], np.zeros(model.n), np.random.default_rng(3)) is None
    assert rng_.percentile(P("Ah,Kc"), [], [], None, np.random.default_rng(3)) is None
