import json
import subprocess
import sys
from pathlib import Path

from helpers import scripted_match

from bot.actions import SPECIAL, Action, LegalActions
from bot.brains.params import load_params, per_street
from bot.brains.tier1 import DEFAULTS, Tier1Brain
from bot.cards import parse_cards as P
from bot.protocol import ActRequest, BoardUpdate, HandStart, HoleCards, MatchInfo
from bot.state import GameState
from lab.engine import play_match
from lab.players import InProcessPlayer, PlayerSpec
from lab.versions import create_snapshot
from test_engine import DISCARD_CFG

ROOT = Path(__file__).resolve().parent.parent
NO_BLUFF = {"bluff_freq": 0.0}


def state_with(hole: str, board: str = "-", pot: int = 3, tocall: int = 1,
               mybet: int = 1, street: int = 0) -> GameState:
    st = GameState()
    st.apply(MatchInfo())
    st.apply(HandStart(1, 0, 400, 400))
    st.apply(HoleCards(P(hole)))
    if street:
        st.apply(BoardUpdate(street, P(board)))
    st.apply(ActRequest(pot, tocall, 400 - pot // 2, 400 - pot // 2, LegalActions(), None,
                        mybet, mybet + tocall))
    return st


FACING = LegalActions(fold=True, call=True, raise_min=4, raise_max=400)
FREE = LegalActions(check=True, raise_min=2, raise_max=380)


# --------------------------------------------------------------------------- params

def test_params_missing_entry_uses_defaults(monkeypatch) -> None:
    import bot.embedded
    monkeypatch.setattr(bot.embedded, "PARAMS", {})
    assert load_params("tier1", DEFAULTS) == DEFAULTS


def test_params_embedded_and_overrides(monkeypatch) -> None:
    import bot.embedded
    monkeypatch.setattr(bot.embedded, "PARAMS", {"tier1": {"bluff_freq": 0.3, "bogus": 1}})
    p = load_params("tier1", DEFAULTS, {"call_margin": 0.5})
    assert p["bluff_freq"] == 0.3 and p["call_margin"] == 0.5 and "bogus" not in p


def test_params_broken_embedded_uses_defaults(monkeypatch) -> None:
    import bot.embedded
    monkeypatch.setattr(bot.embedded, "PARAMS", "not a dict")
    assert load_params("tier1", DEFAULTS) == DEFAULTS


def test_shipped_params_are_the_embedded_ones() -> None:
    import bot.embedded
    assert load_params("tier1", DEFAULTS) == {**DEFAULTS, **bot.embedded.PARAMS["tier1"]}


def test_shipped_config_matches_known_keys() -> None:
    data = json.loads((ROOT / "bot" / "config" / "tier1.json").read_text())
    assert {k for k in data if not k.startswith("_")} <= set(DEFAULTS)


def test_per_street() -> None:
    assert per_street([0.1, 0.2], 0) == 0.1 and per_street([0.1, 0.2], 5) == 0.2
    assert per_street(0.4, 3) == 0.4


# --------------------------------------------------------------------------- decisions

def test_aces_raise_preflop() -> None:
    a = Tier1Brain(NO_BLUFF).decide(state_with("Ah,Ad"), FACING, 0.02)
    assert a.kind == "R"


def test_trash_folds_to_big_bet() -> None:
    st = state_with("7h,2d", "Ks,Qs,Jd", pot=200, tocall=150, mybet=0, street=1)
    assert Tier1Brain(NO_BLUFF).decide(st, FACING, 0.02) == Action.fold()


def test_weak_hand_checks_when_free_without_bluffs() -> None:
    st = state_with("7h,2d", "Ks,Qs,Jd", pot=4, tocall=0, mybet=0, street=1)
    assert Tier1Brain(NO_BLUFF).decide(st, FREE, 0.02) == Action.check()


def test_always_bluff_setting_bets() -> None:
    st = state_with("7h,2d", "Ks,Qs,Jd", pot=4, tocall=0, mybet=0, street=1)
    assert Tier1Brain({"bluff_freq": 1.0}).decide(st, FREE, 0.02).kind == "R"


def test_good_price_calls() -> None:
    # Flush draw + overcards facing a tiny bet: easy call.
    st = state_with("Ah,Kh", "2h,7h,Tc", pot=100, tocall=5, mybet=0, street=1)
    assert Tier1Brain(NO_BLUFF).decide(st, FACING, 0.02).kind in ("C", "R")


def test_special_step_legal_choice() -> None:
    # The discard is simulated now (discard_holdem is active), so the pick depends on time; only legality is fixed.
    from bot.actions import SpecialOption
    legal = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))
    a = Tier1Brain().decide(state_with("Ah,Kd,2c"), legal, 0.02)
    assert a.kind == SPECIAL and legal.special.allows(a.choice)


# --------------------------------------------------------------------------- integration

def test_tier1_beats_random_and_plays_legally() -> None:
    m = play_match([PlayerSpec.brain("tier1").build(), PlayerSpec.brain("random_legal").build()],
                   seed=1, hands=150)
    assert m.errors == [0, 0] and m.forfeit is None and m.chips[0] > 0


def test_tier1_in_discard_variant() -> None:
    m = play_match([InProcessPlayer(Tier1Brain(game=DISCARD_CFG)),
                    PlayerSpec.brain("random_legal").build()], DISCARD_CFG, seed=2, hands=60)
    assert m.errors == [0, 0] and m.forfeit is None


def test_runs_with_embedded_params_missing(monkeypatch) -> None:
    import bot.embedded
    monkeypatch.setattr(bot.embedded, "PARAMS", {})
    assert Tier1Brain().p == DEFAULTS
