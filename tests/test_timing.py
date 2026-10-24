import time

import pytest

from bot.timing import (DeadlineExceeded, TimeManager, TimingConfig, deadline_supported,
                        hard_deadline)


def test_budget_formula() -> None:
    tm = TimeManager(60.0, 400, TimingConfig(decisions_per_hand=3, safety_factor=2,
                                             reserve_frac=0.1, max_budget_s=10))
    # (60 - 6) / (400 * 3) / 2 = 22.5 ms
    assert tm.budget(400) == pytest.approx(0.0225)
    # Fewer hands left -> bigger budget per decision.
    assert tm.budget(100) == pytest.approx(0.09)


def test_budget_reads_match_info_not_hardcoded() -> None:
    tm = TimeManager()
    tm.configure(bank_s=100.0, hands=1000)
    cfg = tm.cfg
    expected = (100 - cfg.reserve_frac * 100) / (1000 * cfg.decisions_per_hand) / cfg.safety_factor
    assert tm.budget(1000) == pytest.approx(expected)


def test_engine_timeleft_is_authoritative() -> None:
    tm = TimeManager(60.0, 400)
    tm.add_used(5.0)
    assert tm.bank_left == pytest.approx(55.0)
    tm.observe_timeleft(30.0)
    assert tm.bank_left == pytest.approx(30.0)
    tm.add_used(1.0)  # our time since the last report still counts
    assert tm.bank_left == pytest.approx(29.0)


def test_budget_capped_and_zero_when_out() -> None:
    tm = TimeManager(60.0, 400)
    assert tm.budget(1) == tm.cfg.max_budget_s
    tm.observe_timeleft(0.0)
    assert tm.budget(10) == 0.0


def test_emergency_mode() -> None:
    tm = TimeManager(60.0, 400)  # threshold = max(1.0, 0.05 * 60) = 3 s
    tm.observe_timeleft(10.0)
    assert not tm.emergency()
    tm.observe_timeleft(2.9)
    assert tm.emergency()


def test_hard_limit_bounds() -> None:
    tm = TimeManager(60.0, 400)
    assert tm.hard_limit(0.001) == tm.cfg.hard_min_s
    assert tm.hard_limit(0.1) == pytest.approx(0.4)
    tm.observe_timeleft(0.4)
    assert tm.hard_limit(0.1) == pytest.approx(0.1)  # never > 25% of what's left


@pytest.mark.skipif(not deadline_supported(), reason="needs SIGALRM")
def test_hard_deadline_interrupts() -> None:
    t0 = time.perf_counter()
    with pytest.raises(DeadlineExceeded):
        with hard_deadline(0.02):
            time.sleep(2)
    assert time.perf_counter() - t0 < 0.5


@pytest.mark.skipif(not deadline_supported(), reason="needs SIGALRM")
def test_hard_deadline_not_swallowed_by_except_exception() -> None:
    def sloppy_brain() -> None:
        try:
            time.sleep(2)
        except Exception:
            pass

    with pytest.raises(DeadlineExceeded):
        with hard_deadline(0.02):
            sloppy_brain()


def test_hard_deadline_disarms() -> None:
    with hard_deadline(0.01):
        pass
    time.sleep(0.03)  # an alarm here would raise; it must not
