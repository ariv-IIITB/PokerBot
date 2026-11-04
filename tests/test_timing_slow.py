"""Phase D step 5: the slow-machine guard. The lab engine charges every reply double (a server
2x slower than this laptop), Tier 2 plays the whole match with the endgame lock off (the
worst case: the lock would end a won match early), and the bank must last.

These replay the red flag found in Phase C (one Tier 2 used ~34 s of its 60 s bank in a
400-hand self-play match). Slow: ~1 minute each. Run with `-m slow`."""
import sys

import pytest

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec, SubprocessPlayer

NO_LOCK = {"lock_enabled": False}


def check_bank(m, hands, bank, *bots) -> None:
    assert m.forfeit is None, m.forfeit_reason
    assert m.hands_played == hands
    for i, bot in enumerate(bots):
        used = bank - m.bank_left[i]
        # at 2x the bank must be well inside the limit: never out, never near emergency mode
        assert used <= 0.65 * bank, f"player {i} used {used:.1f}s of {bank}s (charged x2)"
        assert bot is None or bot.emergency_decisions == 0, "emergency mode (Tier 0) was needed"
        assert m.worst_decision_s[i] <= 1.5, f"a single reply took {m.worst_decision_s[i]:.2f}s (x2)"


@pytest.mark.slow
@pytest.mark.parametrize("hands,bank", [(400, 60.0), (1000, 150.0)])
def test_tier2_self_play_on_a_machine_twice_as_slow(hands, bank) -> None:
    a = PlayerSpec.brain("tier2", NO_LOCK).build()
    b = PlayerSpec.brain("tier2", NO_LOCK).build()
    m = play_match([a, b], load_variant("discard_holdem"), seed=3, hands=hands, time_bank_s=bank,
                   clock_scale=2.0, reply_limit_s=5.0)
    check_bank(m, hands, bank, a.bot, b.bot)


@pytest.mark.slow
@pytest.mark.parametrize("opponent", ["maniac", "all_in", "calling_station"])
def test_tier2_against_the_most_decisions_per_hand_at_2x(opponent) -> None:
    a = PlayerSpec.brain("tier2", NO_LOCK).build()
    m = play_match([a, PlayerSpec.brain(opponent).build()], load_variant("discard_holdem"),
                   seed=4, hands=400, time_bank_s=60.0, clock_scale=2.0, reply_limit_s=5.0)
    check_bank(m, 400, 60.0, a.bot, None)


@pytest.mark.slow
@pytest.mark.parametrize("hands,bank,opponent", [(400, 60.0, "tier3"), (1000, 150.0, "tier2"),
                                                 (400, 60.0, "maniac"), (400, 60.0, "calling_station")])
def test_tier3_on_a_machine_twice_as_slow(hands, bank, opponent) -> None:
    """Phase G: Tier 3 adds an own-range sample to every postflop decision; the bank must still last."""
    a = PlayerSpec.brain("tier3", NO_LOCK).build()
    b = PlayerSpec.brain(opponent, NO_LOCK if opponent.startswith("tier") else None).build()
    m = play_match([a, b], load_variant("discard_holdem"), seed=6, hands=hands, time_bank_s=bank,
                   clock_scale=2.0, reply_limit_s=5.0)
    check_bank(m, hands, bank, a.bot, b.bot if opponent.startswith("tier") else None)


@pytest.mark.slow
def test_the_real_subprocess_bot_over_the_real_protocol_at_2x() -> None:
    """The shipped path: `bot.main` as a subprocess speaking the official wire format."""
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main"], protocol="pokerbots",
                           brain_config=NO_LOCK)
    m = play_match([bot, PlayerSpec.brain("maniac").build()], load_variant("discard_holdem"),
                   seed=5, hands=400, time_bank_s=60.0, clock_scale=2.0, reply_limit_s=5.0)
    check_bank(m, 400, 60.0, None, None)


@pytest.mark.slow
@pytest.mark.parametrize("hands,bank", [(400, 60.0), (1000, 150.0)])
@pytest.mark.parametrize("opponent", ["calling_station", "d_new_trapper"])
def test_tier4p_on_a_machine_twice_as_slow(hands, bank, opponent) -> None:
    """Gate P item 7: tier4p (auto selection) keeps the bank at 2x slower, against a station and the trapper."""
    a = PlayerSpec.brain("tier4p", NO_LOCK).build()
    m = play_match([a, PlayerSpec.brain(opponent).build()], load_variant("discard_holdem"), seed=7, hands=hands,
                   time_bank_s=bank, clock_scale=2.0, reply_limit_s=5.0)
    check_bank(m, hands, bank, a.bot, None)
