"""DB part 1: the discard-rule fit (lab/opps/discard_rules.py)."""
from pathlib import Path

import numpy as np
import pytest

from bot.cards import parse_cards as P
from bot.sim.discard import opponent_keeps
from lab.opps import discard_rules as D
from lab.opps import record

EV = D.evaluator()
REC = Path(__file__).resolve().parents[1] / "logs/records/s0_9000"


def test_baseline_matches_batch_opponent_keeps():
    rng = np.random.default_rng(7)
    deck = np.arange(52)
    for _ in range(150):
        cards = rng.choice(deck, 6, replace=False)
        h3, flop = [int(c) for c in cards[:3]], [int(c) for c in cards[3:]]
        kept = opponent_keeps(EV, np.array([h3]), np.array(flop))[0]
        drop = D.accepted_drops("opponent_keeps", EV, h3, flop)
        assert len(drop) == 1
        assert sorted(c for i, c in enumerate(h3) if i != drop[0]) == sorted(int(c) for c in kept)


def test_rules_on_a_hand():
    h3, flop = P("As,Kd,7h"), P("Ac,8d,2s")           # pair of aces on the board side
    assert D.accepted_drops("drop_lowest", EV, h3, flop) == [2]
    assert D.accepted_drops("keep_pair", EV, h3, flop) == [2]        # keep As (pair) + higher of the rest
    h3, flop = P("9s,8s,2d"), P("Ts,5s,Kd")           # nut-ish flush draw with 9s 8s
    assert D.accepted_drops("keep_flush_draw", EV, h3, flop) == [2]
    h3, flop = P("9c,8d,As"), P("7h,6s,Kd")           # open-ended with 9 8
    assert D.accepted_drops("keep_straight_draw", EV, h3, flop) == [2]
    assert D.accepted_drops("random", EV, h3, flop) == [0, 1, 2]


def test_ties_give_a_set():
    h3, flop = P("5s,5d,9h"), P("Kc,Qd,2s")
    assert D.accepted_drops("drop_lowest", EV, h3, flop) == [0, 1]


def test_holm_and_chi2():
    out = D.holm({"a": 0.001, "b": 0.02, "c": 0.5, "d": None})
    assert out["a"][2] and not out["b"][2] and not out["c"][2] and out["d"][0] is None
    assert D.chi2_p({"low": [10, 100], "mid": [10, 100], "high": [10, 100]}) == pytest.approx(1.0)
    assert D.chi2_p({"low": [60, 100], "mid": [30, 100], "high": [10, 100]}) < 1e-6
    assert D.chi2_p({"low": [0, 50], "mid": [0, 50], "high": [0, 50]}) is None


def test_turn_fold_counts_by_class():
    def hand(cls_card, kind):
        return {"rv": [["m", [cls_card]], ["o", [30]]],
                "h": [[2, "m", "R", 4, None], [2, "o", kind, None, None]]}
    d = {"pairs": [{"seed": 0, "matches": [{"hands": [hand(0, "F"), hand(20, "C"), hand(48, "F")]}]}]}
    c = D.turn_fold_counts(d)
    assert c == {"low": [1, 1], "mid": [0, 1], "high": [1, 1]}


@pytest.mark.skipif(not (REC / "starter.json.gz").exists(), reason="S0 recordings not present")
def test_starter_is_a_drop_lowest_bot():
    r = D.fit_rules(record.load(REC / "starter.json.gz"), EV)
    assert r["n"] > 5000
    assert r["drop_lowest"]["hit"] == 1.0
    assert r["disagree"] > 0.15
