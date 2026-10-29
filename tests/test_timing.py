import time

import pytest

from bot.timing import (DeadlineExceeded, TimeManager, TimingConfig, deadline_supported,
                        hard_deadline)


def test_budget_formula() -> None:
    tm = TimeManager(60.0, 400, TimingConfig(decisions_per_hand=3, safety_factor=2,
                                             reserve_frac=0.1, max_budget_s=10))
    # (60 - 6) / (400 * 3) / 2 = 22.5 ms
    assert tm.budget(400) == pytest.approx(0.0225)
    # Fewer hands left -> bigger budget per decision, up to catch_up_cap x the opening pace.
    assert tm.budget(100) == pytest.approx(tm.cfg.catch_up_cap * 0.0225)
    free = TimeManager(60.0, 400, TimingConfig(decisions_per_hand=3, safety_factor=2,
                                               reserve_frac=0.1, max_budget_s=10, catch_up_cap=100))
    assert free.budget(100) == pytest.approx(0.09)


def test_savings_are_not_spent_late() -> None:
    """A bank left untouched must not turn into 10x budgets at the end of the match."""
    tm = TimeManager(60.0, 400)
    opening = tm.budget(400)
    tm.observe_timeleft(55.0)                       # almost nothing spent
    assert tm.budget(20) <= tm.cfg.catch_up_cap * opening * 1.0001


def test_default_config_uses_the_measured_decisions_per_hand() -> None:
    tm = TimeManager(60.0, 400)
    assert tm.cfg.decisions_per_hand >= 5.1                    # measured 5.1-5.6 on discard_holdem
    assert tm.budget(400) == pytest.approx(54.0 / (400 * tm.cfg.decisions_per_hand) / tm.cfg.safety_factor)


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
    tm = TimeManager(60.0, 400, TimingConfig(max_budget_s=0.005))
    assert tm.budget(1) == 0.005
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
    assert tm.hard_limit(0.1) == pytest.approx(0.6)
    tm.observe_timeleft(0.4)
    assert tm.hard_limit(0.1) == pytest.approx(0.1)  # never > 25% of what's left


def test_hard_limit_never_exceeds_a_third_of_the_reply_limit() -> None:
    """Protocol 8: any single reply within 5 s. Whatever the budget or the bank, the brain is
    interrupted well before that (the old formula allowed 15 s early in a match)."""
    tm = TimeManager(60.0, 400)
    assert tm.reply_s == 5.0                                   # default when init says nothing
    for budget in (0.0, 0.01, 0.25, 1.0, 10.0, 1000.0):
        assert tm.hard_limit(budget) <= 1.5
    tm.observe_timeleft(60.0)
    assert max(tm.hard_limit(b) for b in (0.25, 5.0)) <= 1.5
    tm.configure(150.0, 1000, per_response_s=1.0)              # a stricter engine
    assert tm.hard_limit(5.0) == pytest.approx(0.3)
    tm.configure(150.0, 1000, per_response_s=20.0)             # a looser one is still capped at 1.5 s
    assert tm.hard_limit(5.0) == pytest.approx(1.5)


def test_bot_passes_the_engines_reply_limit_to_the_timer() -> None:
    import io

    from bot.main import Bot
    from bot.protocols import get_adapter
    bot = Bot(None, io.StringIO(), adapter=get_adapter("pokerbots"))     # type: ignore[arg-type]
    bot.handle_line('{"type":"init","protocol_version":"1.0","total_hands":400,"starting_stack":200,'
                    '"small_blind":1,"big_blind":2,"time_bank_ms":60000,"per_response_ms":2000}')
    assert bot.timer.reply_s == 2.0 and bot.timer.bank_total == 60.0 and bot.timer.hands_total == 400


@pytest.mark.parametrize("bank,hands", [(60.0, 400), (150.0, 1000)])
@pytest.mark.parametrize("slowdown", [1.0, 2.0, 3.0])
def test_controller_survives_a_slow_machine_with_fixed_overheads(bank, hands, slowdown) -> None:
    """The pacing loop alone, with a simulated clock: every decision costs what it was budgeted
    plus a fixed 3 ms of overhead (reconstruction, IO), times the machine's slowness; 5.6
    decisions per hand (the measured worst). The bank must last and emergency mode must not
    trigger before the last 5 % of the hands."""
    tm = TimeManager(bank, hands)
    left = bank
    for hand in range(hands):
        for _ in range(6 if hand % 2 else 5):                       # 5.5 on average
            tm.observe_timeleft(left)
            assert not tm.emergency() or hand >= 0.95 * hands, (hand, left)
            cost = (tm.budget(hands - hand) + 0.003) * slowdown
            left -= cost
            assert left > 0, f"bank exhausted at hand {hand}"
    assert left > 0.02 * bank


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
