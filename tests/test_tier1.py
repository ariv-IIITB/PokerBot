import json
import subprocess
import sys
from pathlib import Path

from helpers import scripted_match

from bot.actions import Action, LegalActions
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

def test_params_missing_file_uses_defaults(tmp_path) -> None:
    assert load_params("tier1", DEFAULTS, config_dir=tmp_path) == DEFAULTS


def test_params_file_and_overrides(tmp_path) -> None:
    (tmp_path / "tier1.json").write_text(json.dumps({"bluff_freq": 0.3, "bogus": 1, "_c": "x"}))
    p = load_params("tier1", DEFAULTS, {"call_margin": 0.5}, config_dir=tmp_path)
    assert p["bluff_freq"] == 0.3 and p["call_margin"] == 0.5 and "bogus" not in p


def test_params_broken_file_uses_defaults(tmp_path) -> None:
    (tmp_path / "tier1.json").write_text("{not json")
    assert load_params("tier1", DEFAULTS, config_dir=tmp_path) == DEFAULTS


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


def test_special_step_first_choice() -> None:
    from bot.actions import SpecialOption
    legal = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))
    assert Tier1Brain().decide(state_with("Ah,Kd,2c"), legal, 0.02) == Action.special("0")


# --------------------------------------------------------------------------- integration

def test_tier1_beats_random_and_plays_legally() -> None:
    m = play_match([PlayerSpec.brain("tier1").build(), PlayerSpec.brain("random_legal").build()],
                   seed=1, hands=150)
    assert m.errors == [0, 0] and m.forfeit is None and m.chips[0] > 0


def test_tier1_in_discard_variant() -> None:
    m = play_match([InProcessPlayer(Tier1Brain(game=DISCARD_CFG)),
                    PlayerSpec.brain("random_legal").build()], DISCARD_CFG, seed=2, hands=60)
    assert m.errors == [0, 0] and m.forfeit is None


def test_runs_with_config_files_missing(tmp_path) -> None:
    # In-process with an empty config dir...
    brain = Tier1Brain(config_dir=tmp_path / "nothing_here")
    assert brain.p == DEFAULTS
    # ...and as a subprocess from a snapshot whose bot/config/ has been removed.
    snap = create_snapshot("nocfg", root=tmp_path)
    for f in (snap / "bot" / "config").iterdir():
        f.unlink()
    data = ("\n".join(scripted_match(hands=3)) + "\n").encode()
    proc = subprocess.run([sys.executable, "-m", "bot.main", "--brain", "tier1"], input=data,
                          capture_output=True, cwd=snap, timeout=60)
    assert proc.returncode == 0 and len(proc.stdout.decode().splitlines()) == 12
