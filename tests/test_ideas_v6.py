"""Self-check (x_selfdef) and check-raise (x_cr): the strength functions, and both off by default."""
from bot.brains.exploit import EXPLOIT_DEFAULTS, checkraise_lambda, foldable_lambda
from bot.brains.tier3x import Tier3XBrain

P = dict(EXPLOIT_DEFAULTS)


def test_off_by_default() -> None:
    d = Tier3XBrain.defaults()
    assert d["x_selfdef"] is False and d["x_cr"] is False


def test_foldable_zero_without_data_or_aggression() -> None:
    assert foldable_lambda(P, 0, 0, 0.9) == 0.0          # prior fold rate 0.35 < ref 0.45
    assert foldable_lambda(P, 40, 30, 0.40) == 0.0       # folds a lot, but the opponent rarely bets


def test_foldable_grows_with_our_fold_rate_and_their_bets() -> None:
    lo = foldable_lambda(P, 40, 24, 0.75)
    hi = foldable_lambda(P, 40, 32, 0.80)
    assert 0.0 < lo < hi <= 1.0
    assert foldable_lambda(P, 200, 180, 0.95) == 1.0


def test_checkraise_needs_samples_and_a_folder() -> None:
    assert checkraise_lambda(P, 0.9, 0.9, 2) == 0.0      # too few of our bets answered
    assert checkraise_lambda(P, 0.9, 0.30, 50) == 0.0    # does not fold to our bets
    assert checkraise_lambda(P, 0.40, 0.9, 50) == 0.0    # does not bet often
    assert 0.0 < checkraise_lambda(P, 0.70, 0.50, 20) < 1.0
    assert checkraise_lambda(P, 0.95, 0.80, 50) == 1.0


def test_brain_plays_with_both_on() -> None:
    from lab.harness import load_variant, run_duplicate
    cfg = load_variant("discard_holdem")
    on = 'tier3x:{"x_selfdef": true, "x_cr": true}'
    from lab.eval import parse_brain
    rep = run_duplicate(parse_brain(on, "off"), parse_brain("maniac", "off"), cfg, seeds=[7], hands=40, processes=1)
    assert rep is not None
