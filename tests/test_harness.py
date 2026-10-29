import pytest

from lab.harness import play_pair, run_duplicate
from lab.players import PlayerSpec
from lab.stats import mean_se, win_rate, z_score
from variant.spec import VariantSpec

T0 = PlayerSpec.brain("tier0")


def test_mirror_match_is_exactly_zero() -> None:
    # Identical deterministic bots: duplicate pairs cancel exactly.
    rep = run_duplicate(T0, T0, seeds=range(3), hands=40, processes=1)
    assert rep.chips_per_hand == (0.0, 0.0)
    assert rep.total_hands == 3 * 80


def test_pair_bookkeeping() -> None:
    p = play_pair(T0, T0, VariantSpec(), seed=1, hands=10)
    assert p.hands == 20 and p.errors == (0, 0) and p.forfeits == (0, 0)


def test_parallel_matches_inline() -> None:
    a = PlayerSpec.brain("tier0")
    inline = run_duplicate(a, T0, seeds=range(4), hands=20, processes=1)
    parallel = run_duplicate(a, T0, seeds=range(4), hands=20, processes=2)
    assert [p.a_chips for p in inline.pairs] == [p.a_chips for p in parallel.pairs]
    assert "chips/hand" in parallel.summary()


def test_stats() -> None:
    m, se = mean_se([1, 2, 3, 4])
    assert m == 2.5 and se == pytest.approx(0.6455, abs=1e-3)
    assert mean_se([]) == (0.0, 0.0) and mean_se([5]) == (5.0, 0.0)
    assert win_rate([1, 0, 0.5, 1])[0] == 0.625
    assert z_score(1.0, 0.5) == 2.0


def test_spec_without_hands_uses_the_spec_hand_count() -> None:
    # A VariantSpec has no hands_per_match; the harness must read it via the compiled rules.
    from dataclasses import replace
    from lab.harness import load_variant
    spec = load_variant("discard_holdem")
    spec = replace(spec, match=replace(spec.match, hands=6))
    rep = run_duplicate(T0, T0, spec, seeds=range(1), processes=1)
    assert rep.hands_per_match == 6 and rep.total_hands == 12


def test_subprocess_player_learns_the_match_variant() -> None:
    # play_match calls set_rules on every player; a subprocess gets the spec at launch
    # (before, `lab.harness --subprocess --variant X` silently played the embedded variant).
    import sys

    from lab.engine import to_rules
    from lab.players import SubprocessPlayer
    from variant.spec import load_catalog
    echo = "import os, json; print(json.loads(os.environ['POKERBOT_VARIANT_JSON'])['name'], flush=True)"
    p = SubprocessPlayer([sys.executable, "-c", echo])
    assert p.proc is None                                   # not started until the match begins
    p.set_rules(to_rules(load_catalog()["holdem_nl"]))
    try:
        assert p._read_line(10.0) == "holdem_nl"
    finally:
        p.close()
