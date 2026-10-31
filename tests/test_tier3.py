"""Tier 3 ("Ivey" style, Phase G): registration, the Tier 2 equivalence switch, legality, and the
guards against wide, big-betting opponents (eq_floor, mdf_eq_slack, bluff_tilt_scale)."""
from __future__ import annotations

import pytest

from bot.brains.tier2 import Tier2Brain
from bot.brains.tier3 import DEFAULTS, Tier3Brain, mixed
from bot.main import BRAINS, DEFAULT_BRAIN
from lab.engine import play_match
from lab.players import PlayerSpec
from variant.spec import load_catalog

DH = load_catalog()["discard_holdem"]
# Sample caps far below what the clock allows: the equity samples are then fixed by the seed, not
# by wall-clock time, so two runs (or two brains that play alike) give equal chips. The fast
# discard sizes its sample chunks by the measured sampling rate (clock-dependent under load), so
# these matches use the deterministic "lowest" discard.
CAPPED = {"max_samples": 120, "rollout_worlds": 120, "pimc_worlds": 30, "range_samples": 80,
          "discard_mode": "lowest", "lock_enabled": False}
BIG_BANK = 1e6


def capped_match(a: str, a_cfg: dict, b: str, seed: int, hands: int, b_cfg=None):
    pa = PlayerSpec.brain(a, a_cfg).build()
    pb = PlayerSpec.brain(b, b_cfg).build()
    m = play_match([pa, pb], DH, seed=seed, hands=hands, time_bank_s=BIG_BANK)
    return m, pa.bot.brain


def test_tier3_is_registered_and_is_the_default_since_g8() -> None:
    assert BRAINS["tier3"] == "bot.brains.tier3:Tier3Brain"
    assert BRAINS["tier2"] == "bot.brains.tier2:Tier2Brain"     # kept: the fallback if Tier 3 is reverted
    assert DEFAULT_BRAIN == "tier3"


def test_tier3_starts_from_the_shipped_tier2_parameters() -> None:
    t2, t3 = Tier2Brain().p, Tier3Brain().p
    assert {k: (v, t3[k]) for k, v in t2.items() if t3.get(k) != v} == {}


def test_tier3_follows_a_change_to_the_shipped_tier2_json(monkeypatch) -> None:
    from bot import embedded
    params = {k: dict(v) for k, v in embedded.PARAMS.items()}
    params.setdefault("tier2", {})["call_margin"] = 0.123
    monkeypatch.setattr(embedded, "PARAMS", params)
    assert Tier2Brain().p["call_margin"] == 0.123
    assert Tier3Brain().p["call_margin"] == 0.123


def test_every_new_flag_is_on_by_default() -> None:
    assert DEFAULTS["t3"] and DEFAULTS["eq_floor"] and DEFAULTS["bluff_tilt_scale"]
    assert DEFAULTS["mdf_eq_slack"] is not None
    assert DEFAULTS["value_floor"] and DEFAULTS["value_floor_gate"] and DEFAULTS["value_floor_size"] == "t2"


def test_the_value_floor_is_gated_on_players_who_do_not_fold() -> None:
    b = Tier3Brain()
    p = dict(b.p)
    spots = b.opponent.spots.spots
    assert b.value_floor_weight(p) == 0.0                       # below the sample gate
    for k in ("fold_turn", "fold_river"):
        spots[k].n, spots[k].hits = 60, 30                      # folds half the time: a normal player
    assert b.value_floor_weight(p) == 0.0
    for k in ("fold_turn", "fold_river"):
        spots[k].n, spots[k].hits = 60, 1                       # (almost) never folds: a calling station
    assert b.value_floor_weight(p) == pytest.approx(1.0)
    assert b.value_floor_weight({**p, "t3_adapt": False}) == 0.0
    assert b.value_floor_weight({**p, "value_floor_gate": False}) == 1.0
    assert DEFAULTS["hide_discard"] is False          # G7: no gain in its A/B (docs/reports/TIER3.md)
    assert DEFAULTS["pf_size_pressure"] is False      # no gain vs its target (random_legal)


def test_t3_off_hands_every_decision_to_tier2(monkeypatch) -> None:
    """With "t3": false every decision is Tier2Brain.play with Tier 2's parameters (the test above)
    and none of Tier 3's own code runs. (Equal chips cannot be asserted: the discard and rollout
    samplers size their batches by the clock, so two runs differ under load.)"""
    calls = {"t2": 0}
    t2_play = Tier2Brain.play

    def counted(self, *a, **kw):
        calls["t2"] += 1
        return t2_play(self, *a, **kw)

    def forbidden(self, *a, **kw):
        raise AssertionError("Tier 3 code ran with t3 off")

    monkeypatch.setattr(Tier2Brain, "play", counted)
    for name in ("_bets", "_hidden_discard", "_preflop", "_postflop"):
        monkeypatch.setattr(Tier3Brain, name, forbidden)
    m, brain = capped_match("tier3", {**CAPPED, "t3": False, "hide_discard": True}, "maniac", 3, 60)
    assert m.errors == [0, 0]
    assert brain.stats == {"t3_decisions": 0, "t3_fallbacks": 0, "t3_errors": 0}
    assert calls["t2"] > 100


def test_a_deadline_while_building_the_preflop_model_does_not_disable_tier3(monkeypatch) -> None:
    """The first decision builds the preflop model and the own-range helper. If the hard deadline
    fires in between, the next decision must build both again: before the fix, the model was kept,
    the helper stayed None, and every postflop decision of the match fell back to Tier 2."""
    import bot.brains.tier3 as t3
    from bot.timing import DeadlineExceeded

    real, fired = t3.OwnRange, []

    def interrupted_once(*a, **kw):
        if not fired:
            fired.append(True)
            raise DeadlineExceeded()          # the alarm lands while this is being built
        return real(*a, **kw)

    monkeypatch.setattr(t3, "OwnRange", interrupted_once)
    m, brain = capped_match("tier3", CAPPED, "calling_station", 2, 60)
    assert fired and m.errors == [0, 0] and m.forfeit is None
    assert brain.stats["t3_errors"] == 0
    assert brain.stats["t3_decisions"] > 0


@pytest.mark.parametrize("opp", ["maniac", "all_in", "random_legal", "calling_station", "tight"])
def test_tier3_plays_legally_and_never_raises(opp: str) -> None:
    """No errors, no forfeits, and the style code never threw (a throw would hand the decision to
    Tier 2; t3_fallbacks also counts the spots Tier 3 leaves to Tier 2 on purpose)."""
    m, brain = capped_match("tier3", CAPPED, opp, 5, 80)
    assert m.errors == [0, 0] and m.forfeit is None
    assert brain.stats["t3_decisions"] > 0
    assert brain.stats["t3_errors"] == 0


def priced_folds(cfg: dict, opp: str, seed: int, hands: int) -> tuple[int, int]:
    """(folds Tier 2's pot-odds rule would have called, all folds facing a bet before the river)."""
    pa, pb = PlayerSpec.brain("tier3", cfg).build(), PlayerSpec.brain(opp).build()
    brain = pa.bot.brain
    counts = [0, 0]
    decide = brain.decide

    def counted(state, legal, budget):
        a = decide(state, legal, budget)
        h = state.hand
        if (a.kind == "F" and h is not None and h.street <= 2 and h.tocall > 0
                and not legal.can_special):
            counts[1] += 1
            eq = brain.situation(state).equity(budget)        # the cached equity of this decision
            counts[0] += Tier3Brain.t2_calls(h, eq, brain.adjusted(h.street))
        return a

    brain.decide = counted
    play_match([pa, pb], DH, seed=seed, hands=hands, time_bank_s=BIG_BANK)
    return counts[0], counts[1]


@pytest.mark.parametrize("opp", ["all_in", "maniac"])
def test_the_equity_floor_never_folds_a_priced_call(opp: str) -> None:
    """The MDF slice and the preflop tables fold hands that have the price against wide bettors
    (defence is clipped to 20 % vs big raises); with eq_floor Tier 3 calls what Tier 2 would."""
    off_bad, off_n = priced_folds({**CAPPED, "eq_floor": False}, opp, 7, 100)
    on_bad, on_n = priced_folds(CAPPED, opp, 7, 100)
    assert off_n > 10 and on_n > 10
    assert off_bad > 0
    assert on_bad == 0


def test_bluff_mass_shrinks_to_value_against_a_player_who_never_folds() -> None:
    b = Tier3Brain()
    p = dict(b.p)
    spot = b.opponent.spots.spots["fold_to_3bet"]
    assert b._bluff_mass(0.16, 0.08, 0.06, p) == pytest.approx(0.16)       # below the gate: base
    spot.n, spot.hits = 60, 0                                              # never folds to a 3-bet
    assert b._bluff_mass(0.16, 0.08, 0.06, p) == pytest.approx(0.08)       # bluffs gone
    assert b._bluff_mass(0.16, 0.08, 0.06, {**p, "bluff_tilt_scale": False}) == pytest.approx(0.10)
    spot.n, spot.hits = 60, 60                                             # always folds
    assert b._bluff_mass(0.16, 0.08, 0.06, p) == pytest.approx(0.22)


class _H:
    def __init__(self, pot: int, tocall: int) -> None:
        self.pot, self.tocall = pot, tocall


def test_tier2_call_rule_matches_tier1_choose() -> None:
    p = {"call_margin": 0.02, "bet_pressure": 0.10}
    # pot 20 (their bet of 10 included), 10 to call: odds 1/3, + 0.02 + 0.10 * 0.5 = 0.4033
    assert not Tier3Brain.t2_calls(_H(20, 10), 0.40, p)
    assert Tier3Brain.t2_calls(_H(20, 10), 0.41, p)
    assert not Tier3Brain.t2_calls(_H(20, 0), 0.99, p)


def test_mixed_draws_follow_the_probabilities() -> None:
    assert mixed([0.2, 0.3, 0.5], 0.0) == 0
    assert mixed([0.2, 0.3, 0.5], 0.25) == 1
    assert mixed([0.2, 0.3, 0.5], 0.99) == 2
    assert mixed([0.0, 0.0, 0.0], 0.5) == 2
