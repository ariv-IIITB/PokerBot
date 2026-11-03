"""PC: tier4p member selection, bail-out, stop-loss (bot/brains/tier4p_select.py) and the adversary bot."""
from types import SimpleNamespace as NS

import pytest

from bot.brains import tier4p_select as S
from bot.brains.tier4p import MEMBER_NAMES, Tier4PBrain


class FakeTypes:
    def __init__(self, fam: str = "unknown", mass: float = 1.0, n: int = 100) -> None:
        self.fam, self.mass, self.n = fam, mass, n

    def families(self):
        return {self.fam: self.mass, "unknown": 1.0 - self.mass} if self.mass < 1.0 else {self.fam: 1.0}


class FakeBrain:
    """Just what choose_member reads: state, opponent.types/traits, stats, locked_decisions."""

    def __init__(self, total: int = 400) -> None:
        self.state = NS(hand=NS(hand_id=0), hands_played=0, bankroll=0, match=NS(hands=total))
        self.opponent = NS(types=FakeTypes(), traits=NS(tests={"overfolder": NS(verdict="open", alarms=0)}))
        self.stats = {"p_errors": 0}
        self.locked_decisions = 0
        self.hand_no = 0

    def set(self, fam=None, mass=None, n=None, verdict=None) -> None:
        t = self.opponent.types
        t.fam = fam or t.fam
        t.mass = t.mass if mass is None else mass
        t.n = t.n if n is None else n
        if verdict is not None:
            self.opponent.traits.tests["overfolder"].verdict = verdict

    def decide_hand(self, delta: int = 0, decisions: int = 1) -> str:
        """Start a new hand (the previous one ended with `delta`), make `decisions` decisions."""
        gs = self.state
        if self.hand_no:
            gs.hands_played += 1
            gs.bankroll += delta
        self.hand_no += 1
        gs.hand = NS(hand_id=self.hand_no)
        out = "base"
        for _ in range(decisions):
            out = S.choose_member(self, 1)
        return out

    def warm(self, hands: int = 20, **kw) -> str:
        out = "base"
        for _ in range(hands):
            out = self.decide_hand(**kw)
        return out


CASES = [   # family, verdict, n -> member
    ("overfolder", "yes", 100, "anti_folder"),
    ("valueonly", "no", 100, "anti_value"),
    ("trapper", "no", 100, "anti_value"),
    ("aggressor", "no", 100, "anti_aggro"),
    ("unknown", "yes", 100, "base"),
    ("nit", "yes", 100, "base"),
    ("station", "yes", 100, "base"),
]


@pytest.mark.parametrize("fam,verdict,n,member", CASES)
def test_each_family_picks_its_member(fam, verdict, n, member) -> None:
    b = FakeBrain()
    b.set(fam=fam, mass=0.95, n=n, verdict=verdict)
    assert b.warm(20) == member
    assert member in MEMBER_NAMES


def test_needs_the_mass_for_the_last_20_decisions() -> None:
    b = FakeBrain()
    b.set(fam="aggressor", mass=0.95)
    assert b.warm(19) == "base"                  # 19 decisions: not yet
    b2 = FakeBrain()
    b2.set(fam="aggressor", mass=0.95)
    assert b2.warm(20) == "anti_aggro"
    b2.set(mass=0.79)                            # one decision under 0.8 ...
    b2.decide_hand()
    b2.set(mass=0.95)
    assert b2.warm(19) == "base"                 # ... keeps it out for the next 19 decisions
    assert b2.decide_hand() == "anti_aggro"      # 20 clean ones again


def test_the_family_must_not_change_inside_the_window() -> None:
    b = FakeBrain()
    b.set(fam="aggressor", mass=0.95)
    b.warm(10)
    b.set(fam="valueonly")
    assert b.warm(10) == "base"                  # 10 + 10: mixed window
    assert b.warm(10) == "anti_value"


def test_anti_folder_needs_the_sprt_yes() -> None:
    b = FakeBrain()
    b.set(fam="overfolder", mass=0.95, verdict="open")
    assert b.warm(25) == "base"
    b.set(verdict="yes")
    assert b.decide_hand() == "anti_folder"


@pytest.mark.parametrize("fam,member", [("valueonly", "anti_value"), ("aggressor", "anti_aggro")])
def test_value_and_aggro_need_60_opponent_decisions(fam, member) -> None:
    b = FakeBrain()
    b.set(fam=fam, mass=0.95, n=59)
    assert b.warm(25) == "base"
    b.set(n=60)
    assert b.decide_hand() == member


def test_one_member_per_hand() -> None:
    b = FakeBrain()
    b.set(fam="aggressor", mass=0.95)
    b.warm(19)
    first = b.decide_hand(decisions=1)           # 20th decision: switches on at the hand start
    assert first == "anti_aggro"
    b.set(mass=0.1)                              # evidence collapses mid-hand
    assert S.choose_member(b, 2) == "anti_aggro"  # same hand: unchanged
    assert b.decide_hand() == "base"


def _alarm(b: FakeBrain) -> None:
    t = b.opponent.traits.tests["overfolder"]
    t.alarms += 1
    t.verdict = "open"


def test_cusum_alarm_blocks_anti_folder_for_50_hands() -> None:
    b = FakeBrain(total=1000)
    b.set(fam="overfolder", mass=0.95, verdict="yes")
    assert b.warm(20) == "anti_folder"
    _alarm(b)
    assert S.choose_member(b, 2) == "base"       # mid-hand: off at once
    b.set(verdict="yes")                         # the SPRT says yes again straight away
    outs = [b.decide_hand() for _ in range(49)]
    assert set(outs) == {"base"}                 # hands_played 0..49 after the alarm at hands_played 19
    # the alarm was seen at hands_played == 19, so the block ends when hands_played reaches 69
    assert b.state.hands_played == 68               # still blocked on the 49th hand after the alarm
    assert b.decide_hand() == "anti_folder"         # hands_played 69: block over
    assert b.stats["sel_bailouts"] == 1


def test_alarm_does_not_block_the_other_members() -> None:
    b = FakeBrain()
    b.set(fam="aggressor", mass=0.95)
    b.warm(20)
    _alarm(b)
    assert b.decide_hand() == "anti_aggro"


def _stop_setup(total: int = 400):
    b = FakeBrain(total=total)
    b.set(fam="aggressor", mass=0.95)
    return b


def test_stop_loss_fires_only_at_checkpoints_and_only_on_a_2se_loss() -> None:
    # member on from hand 20; hands lose 5 per hand on average (SD 10): -400 over 80 hands = -4.5 SE at hand 100
    b = _stop_setup()
    b.warm(20)
    assert b.decide_hand(delta=0) == "anti_aggro"
    for i in range(79):
        assert b.decide_hand(delta=-15 if i % 2 else 5) == "anti_aggro"   # a loss, but no checkpoint yet
    assert b.state.hands_played == 99
    out = b.decide_hand(delta=5)                 # hands_played 100: the 25 % checkpoint
    assert out == "base" and b.stats["sel_stoploss"] == 1
    assert b.warm(40) == "base"                  # for the rest of the match
    assert b.decide_hand() == "base"


def test_stop_loss_not_on_a_small_loss_and_not_between_checkpoints() -> None:
    b = _stop_setup()
    b.warm(20)
    b.decide_hand()
    for i in range(78):
        b.decide_hand(delta=10 if i % 2 else -10)
    b.state.bankroll -= 20                       # ~ -20 over ~80 hands with SD 10: -0.2 SE... fine
    assert b.decide_hand() == "anti_aggro"       # at the checkpoint, loss is within 2 SE: stays on
    assert b.stats.get("sel_stoploss", 0) == 0
    b.state.bankroll -= 5000                     # huge loss, but 100 < hands < 200: no checkpoint
    for _ in range(50):
        assert b.decide_hand(delta=0) == "anti_aggro"
    assert b.stats.get("sel_stoploss", 0) == 0


def test_stop_loss_ignores_a_win_and_a_base_stretch() -> None:
    b = _stop_setup()
    for i in range(130):                         # never switched on (hist window not satisfied)
        b.opponent.types.mass = 0.5
        b.decide_hand(delta=10 if i % 2 else -10)
    b.state.bankroll -= 5000
    b.opponent.types.mass = 0.95
    b.warm(1)
    assert b.stats.get("sel_stoploss", 0) == 0   # base members are not stop-lossed


def test_a_lock_inside_the_segment_disables_the_stop_loss() -> None:
    b = _stop_setup()
    b.warm(20)
    b.decide_hand()
    for i in range(78):
        b.decide_hand(delta=10 if i % 2 else -10)
    b.locked_decisions = 3
    b.state.bankroll -= 500
    assert b.decide_hand() == "anti_aggro" and b.stats.get("sel_stoploss", 0) == 0


def test_hands_without_our_decision_are_counted_in_the_loss() -> None:
    b = _stop_setup()
    b.warm(20)
    b.decide_hand()
    for i in range(70):
        b.decide_hand(delta=10 if i % 2 else -10)
    b.state.hands_played += 5                    # 5 hands the opponent folded: no decision of ours
    b.state.bankroll += 30
    out = b.decide_hand()
    assert out == "anti_aggro"                   # a gain; 76+ hands: still before 100
    assert b.state.hands_played > 90


def test_sd_helper() -> None:
    assert S._sd([(1, 10)] * 5) is None          # too few samples
    blocks = [(1, 10), (1, -10)] * 10
    assert S._sd(blocks) == pytest.approx(10.26, abs=0.1)
    assert S._sd([(2, 20), (2, -20)] * 6) == pytest.approx(S._sd([(1, 10), (1, -10)] * 6) * 2 ** 0.5, rel=0.3)


def test_any_error_in_selection_gives_base() -> None:
    class Broken:
        stats = {"p_errors": 0}
        state = None
    assert S.choose_member(Broken(), 1) == "base" and Broken.stats["p_errors"] == 1
    b = FakeBrain()
    b.set(fam="aggressor", mass=0.95)
    b.warm(20)
    b.opponent.types = None                      # lost the posterior: still fine
    assert b.decide_hand() == "base"
    b.opponent.traits = None
    assert b.decide_hand() == "base"


def test_fresh_brain_without_state_is_base() -> None:
    b = Tier4PBrain(config={"lock_enabled": False})
    assert b.choose_member(2) == "base"


def test_new_match_on_the_same_brain_resets() -> None:
    b = FakeBrain()
    b.set(fam="aggressor", mass=0.95)
    b.warm(30)
    b.state.hands_played, b.state.bankroll, b.hand_no = 0, 0, 0
    assert b.decide_hand() == "base"


def test_locked_hands_never_reach_selection(monkeypatch) -> None:
    """Tier2.decide returns before adjusted() when the lock is on, so choose_member is not called."""
    from bot.actions import LegalActions
    from bot.brains import tier4p as T4
    from bot.situation import Situation
    calls = []
    monkeypatch.setattr(T4, "__name__", T4.__name__)
    brain = Tier4PBrain(config={"lock_enabled": True})
    monkeypatch.setattr(brain, "choose_member", lambda street: calls.append(street) or "base")
    monkeypatch.setattr(Situation, "locked", lambda self: True)
    legal = LegalActions(fold=True, call=True)
    from bot.state import GameState
    brain.decide(GameState(), legal, 1.0)
    assert calls == [] and brain.locked_decisions == 1


# ---- adversary bot

def test_adversary_switches_at_hand_100() -> None:
    from bot.actions import FOLD
    from lab.sparring.adversary import Adversary
    a = Adversary()

    class Rules:
        evaluator = None
    a.rules = Rules()
    a._has_pair = lambda state: False
    legal = NS(can_special=False, fold=True, call=True, check=False)
    mk = lambda hp: NS(hands_played=hp, hand=NS(street=1, tocall=20, board=(1, 2, 3)))
    assert a.decide(mk(0), legal, 1.0).kind == FOLD
    assert a.decide(mk(99), legal, 1.0).kind == FOLD
    assert a.decide(mk(100), legal, 1.0).kind != FOLD
    a._has_pair = lambda state: True
    assert a.decide(mk(0), legal, 1.0).kind != FOLD          # a pair continues
    pre = NS(hands_played=0, hand=NS(street=0, tocall=20, board=()))
    a._has_pair = lambda state: False
    assert a.decide(pre, legal, 1.0).kind != FOLD            # calls preflop


def test_adversary_is_registered_and_plays_a_match() -> None:
    from lab.engine import play_match
    from lab.harness import load_variant
    from lab.players import BRAINS, PlayerSpec
    assert "adversary" in BRAINS
    cfg = load_variant("discard_holdem")
    res = play_match([PlayerSpec.brain("adversary").build(cfg), PlayerSpec.brain("calling_station").build(cfg)],
                     cfg, 3, 150)
    assert res.errors == [0, 0] and res.forfeit is None
