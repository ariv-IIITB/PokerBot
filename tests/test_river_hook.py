"""Tier 4 R1: the river solver inside Tier 3 (flag t3_river_solver) and its fallbacks."""
import math

import pytest

import bot.brains.tier3 as tier3_mod
from bot.brains.tier3 import Tier3Brain
from bot.timing import TimeManager, TimingConfig
from lab.engine import play_match
from lab.players import PlayerSpec
from variant.spec import load_catalog

DH = load_catalog()["discard_holdem"]
CAPPED = {"max_samples": 120, "rollout_worlds": 120, "pimc_worlds": 30, "range_samples": 80,
          "discard_mode": "lowest", "lock_enabled": False}


def play(cfg: dict, opp: str = "calling_station", seed: int = 7, hands: int = 40):
    a = PlayerSpec.brain("tier3", dict(CAPPED, **cfg)).build()
    m = play_match([a, PlayerSpec.brain(opp).build()], DH, seed=seed, hands=hands, time_bank_s=1e6)
    return m, a.bot.brain


def test_the_solver_is_off_by_default() -> None:
    assert Tier3Brain.defaults()["t3_river_solver"] is False
    m, brain = play({}, hands=25)
    assert brain.stats["river_solves"] == 0 and brain.stats["river_fallbacks"] == 0
    assert m.errors == [0, 0] and m.forfeit is None


def test_the_flag_solves_river_decisions_legally() -> None:
    m, brain = play({"t3_river_solver": True, "river_budget_s": 0.02})
    st = brain.stats
    assert m.errors == [0, 0] and m.forfeit is None
    assert st["river_solves"] > 0 and st["river_errors"] == 0 and st["t3_errors"] == 0
    assert st["river_iters"] / st["river_solves"] >= 20            # the min the hook demands, on average and up
    assert len(brain.river_iters_log) == st["river_solves"]


def test_an_exception_in_the_solver_falls_back_to_tier3s_river(monkeypatch) -> None:
    def boom(*a, **kw):
        raise RuntimeError("solver bug")
    monkeypatch.setattr(tier3_mod, "solve_river", boom)
    m, brain = play({"t3_river_solver": True}, hands=25)
    st = brain.stats
    assert m.errors == [0, 0] and m.forfeit is None
    assert st["river_errors"] > 0 and st["river_solves"] == 0 and st["river_fallbacks"] == st["river_errors"]
    assert st["t3_errors"] == 0                  # Tier 3's own river decided: Tier 2 was not needed for it


def test_too_few_iterations_fall_back() -> None:
    m, brain = play({"t3_river_solver": True, "river_min_iters": 10**9}, hands=25)
    st = brain.stats
    assert m.errors == [0, 0] and st["river_few_iters"] > 0 and st["river_few_iters"] == st["river_fallbacks"]


def test_no_time_for_a_single_pass_falls_back() -> None:
    m, brain = play({"t3_river_solver": True, "river_budget_s": 1e-7}, hands=25)
    st = brain.stats
    assert m.errors == [0, 0] and st["river_no_pass"] > 0 and st["river_solves"] == 0


def test_a_missing_piece_falls_back(monkeypatch) -> None:
    def none_rec(self):                          # a hand that cannot be reconstructed
        return None
    from bot.situation import Situation
    monkeypatch.setattr(Situation, "rec", property(none_rec))
    m, brain = play({"t3_river_solver": True}, hands=25)
    assert m.errors == [0, 0] and brain.stats["river_solves"] == 0


# ---- the time box against the hard deadline (bot/timing.py)

@pytest.mark.parametrize("bank,hands", [(60.0, 400), (150.0, 1000)])
def test_the_river_box_always_sits_inside_the_hard_deadline(bank, hands) -> None:
    tm = TimeManager(bank, hands)
    cfg = tm.cfg
    assert cfg.river_budget_s == 0.020 and cfg.river_box_mult == 4.0
    worst_ratio = 0.0
    for left in (bank, 0.9 * bank, 0.5 * bank, 0.2 * bank, 0.1 * bank, 0.06 * bank):
        tm.observe_timeleft(left)
        if tm.emergency():
            continue                                        # Tier 0 plays: no solver
        for remaining in (hands, hands // 2, 20, 1):
            b = tm.budget(remaining)
            box = tm.river_box(b)
            assert box <= cfg.river_budget_s + 1e-12 and box <= cfg.river_box_mult * b + 1e-12
            hard = tm.hard_limit(b)
            # the box leaves room for the rest of the decision (equity, own-range percentile, tree set-up)
            assert hard >= 2.0 * box or box == 0.0, (left, remaining, b, box, hard)
            worst_ratio = max(worst_ratio, box / hard if hard else 0.0)
    assert worst_ratio < 0.5 and not math.isnan(worst_ratio)


def test_the_brain_uses_the_same_box_numbers() -> None:
    d = Tier3Brain.defaults()
    assert d["river_budget_s"] == TimingConfig().river_budget_s
    assert d["river_box_mult"] == TimingConfig().river_box_mult
