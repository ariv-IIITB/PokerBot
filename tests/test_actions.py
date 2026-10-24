import numpy as np
import pytest

from bot.actions import Action, LegalActions, SpecialOption, clamp, is_legal, safe_action

FACING_BET = LegalActions(fold=True, call=True, raise_min=8, raise_max=400)
FREE = LegalActions(check=True, raise_min=2, raise_max=398)
DISCARD = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))


def test_legal_actions_pass_through() -> None:
    for a in [Action.fold(), Action.call(), Action.raise_to(8), Action.raise_to(400)]:
        assert clamp(a, FACING_BET) == a


def test_raise_above_stack_clamped_to_max() -> None:
    assert clamp(Action.raise_to(10_000), FACING_BET) == Action.raise_to(400)


def test_raise_below_min_clamped_to_min() -> None:
    assert clamp(Action.raise_to(3), FACING_BET) == Action.raise_to(8)


def test_all_in_for_less_than_min_raise() -> None:
    # Engine offers only the all-in amount (stack < full min-raise): min == max.
    legal = LegalActions(fold=True, call=True, raise_min=150, raise_max=150)
    assert clamp(Action.raise_to(300), legal) == Action.raise_to(150)
    assert clamp(Action.raise_to(10), legal) == Action.raise_to(150)


def test_inverted_range_means_no_raise() -> None:
    legal = LegalActions(fold=True, call=True, raise_min=200, raise_max=150)
    assert not legal.can_raise
    assert clamp(Action.raise_to(200), legal) == Action.call()


def test_weird_amounts() -> None:
    assert clamp(Action(kind="R", amount=np.int64(50)), FACING_BET) == Action.raise_to(50)
    assert clamp(Action(kind="R", amount=12.6), FACING_BET) == Action.raise_to(13)  # type: ignore[arg-type]
    assert clamp(Action(kind="R", amount=float("nan")), FACING_BET) == Action.raise_to(8)  # type: ignore[arg-type]
    assert clamp(Action(kind="R", amount=None), FACING_BET) == Action.raise_to(8)


def test_raise_when_not_allowed_becomes_call_or_check() -> None:
    assert clamp(Action.raise_to(50), LegalActions(fold=True, call=True)) == Action.call()
    assert clamp(Action.raise_to(50), LegalActions(check=True)) == Action.check()


def test_check_when_facing_bet_folds() -> None:
    assert clamp(Action.check(), FACING_BET) == Action.fold()


def test_fold_when_free_checks() -> None:
    assert clamp(Action.fold(), FREE) == Action.check()


def test_call_when_free_checks() -> None:
    assert clamp(Action.call(), FREE) == Action.check()


def test_nothing_legal_but_fold() -> None:
    only_fold = LegalActions(fold=True)
    for a in [Action.check(), Action.call(), Action.raise_to(10), Action.special("0"), None]:
        assert clamp(a, only_fold) == Action.fold()


def test_nothing_legal_at_all_returns_fold() -> None:
    assert clamp(Action.call(), LegalActions()) == Action.fold()
    assert safe_action(LegalActions()) == Action.fold()


def test_special() -> None:
    assert clamp(Action.special("2"), DISCARD) == Action.special("2")
    assert clamp(Action.special("9"), DISCARD) == Action.special("0")
    assert clamp(Action.fold(), DISCARD) == Action.special("0")
    assert clamp(Action.special("1"), FACING_BET) == Action.fold()


@pytest.mark.parametrize("junk", [None, 42, "F", Action(kind="Z")])
def test_garbage_brain_output(junk) -> None:
    assert clamp(junk, FACING_BET) == Action.fold()
    assert clamp(junk, FREE) == Action.check()


def test_clamp_output_always_legal() -> None:
    rng = np.random.default_rng(0)
    legals = [FACING_BET, FREE, DISCARD, LegalActions(fold=True),
              LegalActions(call=True), LegalActions(fold=True, call=True, raise_min=5, raise_max=5)]
    kinds = ["F", "K", "C", "R", "S", "?"]
    for _ in range(2000):
        legal = legals[rng.integers(len(legals))]
        a = Action(kinds[rng.integers(len(kinds))], amount=int(rng.integers(-50, 1000)),
                   choice=str(rng.integers(0, 5)))
        assert is_legal(clamp(a, legal), legal)
