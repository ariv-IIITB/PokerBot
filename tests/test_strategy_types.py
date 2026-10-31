"""X2: the opponent type posterior (bot/strategy/types.py) and its embedded library.

The library (data/discard_holdem/types.json, lab/opps/types.py) was built from recorded pairs 2-11;
the committed fixtures (pairs 0-1) are held-out seeds here. Styles outside the library (random_legal,
all_in) must end "unknown", not confidently matched to a real bot.
"""
from pathlib import Path

import numpy as np
import pytest

from bot.opponent import Opponent
from bot.protocol import HandEnd, OppAction
from bot.state import OPP, GameState, HandState
from bot.strategy import types as TY
from bot.strategy.traits import classify
from lab.harness import load_variant
from lab.opps import record

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "opp_records"
FAMILY = {"d_new_exploiter": "overfolder", "d_conv_opp3": "overfolder", "d_new_rules": "overfolder",
          "d_new_minraise": "valueonly", "tight": "nit", "starter": "station",
          "calling_station": "station", "d_new_trapper": "trapper", "d_new_lag": "aggressor",
          "maniac": "aggressor", "random_legal": "unknown", "all_in": "unknown"}


@pytest.fixture(scope="module")
def rules():
    from bot.game.rules_spec import to_rules
    return to_rules(load_variant("discard_holdem"))


@pytest.fixture(scope="module")
def library(rules) -> dict:
    from bot.artifacts import embedded
    art = embedded("types", rules)
    assert art is not None, "types artifact missing: run lab.opps.types, then tools.embed_data"
    return art["meta"]


def test_the_library_is_embedded_and_well_formed(library) -> None:
    assert "unknown" in library["types"] and len(library["types"]) >= 6
    for name, t in library["types"].items():
        p = np.array(t["probs"])
        assert p.shape == (TY.N_CTX, len(TY.ACTS)) and np.allclose(p.sum(axis=1), 1.0, atol=1e-3)
        assert set(t["slow"]) >= {"river_bluff", "river_bet"}
    members = {b for t in library["types"].values() for b in t["members"]}
    assert not members & {"d_conv_opp4", "d_new_eqrandom", "d_new_geometric"}   # never held-out bots


def _families_along(match_hands: list, library: dict, at=(100, 400)) -> dict:
    tp = TY.TypePosterior(library)
    out = {}
    for i, hand in enumerate(match_hands, 1):
        hs = record.to_hand_state(hand)
        for j in range(len(hs.history)):
            ev = classify(hs.history[: j + 1])
            if ev is not None:
                tp.observe(ev)
        if i in at:
            out[i] = tp.families()
    out["tp"] = tp
    return out


@pytest.mark.parametrize("name", sorted(FAMILY))
def test_held_out_seeds_are_identified_by_family(library, name: str) -> None:
    data = record.load(FIXTURES / f"{name}.json.gz")
    want = FAMILY[name]
    ok100 = ok400 = 0
    for pair in data["pairs"]:
        for m in pair["matches"]:
            snaps = _families_along(m["hands"], library)
            ok100 += snaps[100].get(want, 0.0) >= 0.5
            ok400 += snaps[400].get(want, 0.0) >= 0.7
    assert ok400 == 4, f"{name}: right family at hand 400 in {ok400}/4 matches"
    assert ok100 >= 3, f"{name}: right family at hand 100 in {ok100}/4 matches"


def test_implied_river_bluffing(library) -> None:
    def implied(name):
        m = record.load(FIXTURES / f"{name}.json.gz")["pairs"][0]["matches"][0]
        return _families_along(m["hands"], library)["tp"].implied("river_bluff")
    assert implied("d_new_exploiter") < 0.1 and implied("d_new_rules") < 0.1
    assert implied("maniac") > 0.4
    assert 0.1 < implied("random_legal") < 0.4               # unknown: the population average


def test_misfit_is_small_for_library_bots_and_large_for_others(library) -> None:
    for name, lo, hi in (("d_new_exploiter", -1, 0.03), ("tight", -1, 0.03), ("random_legal", 0.06, 9)):
        m = record.load(FIXTURES / f"{name}.json.gz")["pairs"][1]["matches"][1]
        tp = _families_along(m["hands"], library)["tp"]
        assert lo < tp.misfit() < hi, (name, tp.misfit())


def test_opponent_builds_and_feeds_the_posterior(rules) -> None:
    opp = Opponent()
    state = GameState()
    hands = record.load(FIXTURES / "starter.json.gz")["pairs"][0]["matches"][0]["hands"][:120]
    for hand in hands:
        full = record.to_hand_state(hand)
        h = HandState(hand_id=full.hand_id, seat=full.seat, start_stack=200, opp_start_stack=200)
        state.hand = h
        for r in full.history:
            h.history.append(r)
            if r.actor == OPP:
                opp.observe(state, OppAction(r.action), rng=None, rules=rules)
        opp.observe(state, HandEnd(full.delta or 0), rng=None, rules=rules)
    assert opp.types is not None and opp.types.n > 100
    assert opp.types.families()["station"] > 0.9


def test_a_broken_library_never_reaches_the_bot(rules, monkeypatch) -> None:
    def boom(_rules):
        raise RuntimeError("boom")
    monkeypatch.setattr(TY.TypePosterior, "from_rules", staticmethod(boom))
    opp = Opponent()
    state = GameState()
    state.hand = HandState(hand_id=1, seat=0, start_stack=200, opp_start_stack=200)
    opp.observe(state, HandEnd(0), rng=None, rules=rules)        # must not raise
    assert opp.types is None
