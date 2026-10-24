import subprocess
import sys
from pathlib import Path

import pytest
from helpers import decode_replies, encode, scripted_messages

from bot.actions import Action, LegalActions, pot_fraction_raise
from bot.cards import parse_cards as P
from lab.engine import play_match
from lab.harness import run_duplicate
from lab.players import BRAINS, PlayerSpec, load_brain
from lab.sparring.bots import Tight
from lab.versions import create_snapshot, list_snapshots, snapshot_player

SPARRING = ["random_legal", "all_in", "calling_station", "tight", "maniac"]
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", SPARRING)
def test_sparring_bot_plays_legally(name: str) -> None:
    m = play_match([PlayerSpec.brain(name).build(),
                    PlayerSpec.brain("random_legal", {"seed": 7}).build()], seed=3, hands=200)
    assert m.errors == [0, 0] and m.hands_played == 200 and m.forfeit is None


def test_styles_behave_as_named() -> None:
    legal = LegalActions(fold=True, call=True, raise_min=4, raise_max=400)
    from bot.state import GameState
    st = GameState()
    assert load_brain("all_in").decide(st, legal, 0.01) == Action.raise_to(400)
    assert load_brain("calling_station").decide(st, legal, 0.01) == Action.call()


def test_tight_preflop_scores() -> None:
    assert Tight.preflop_score(P("Ah,Ad")) == 2 and Tight.preflop_score(P("Ah,Kd")) == 2
    assert Tight.preflop_score(P("8h,8d")) == 1 and Tight.preflop_score(P("Ah,5h")) == 1
    assert Tight.preflop_score(P("7h,2d")) == 0


def test_pot_fraction_raise() -> None:
    legal = LegalActions(fold=True, call=True, raise_min=10, raise_max=200)
    # pot 20, to call 4, our street bet 2: raise to 2 + 4 + 0.5 * 24 = 18
    assert pot_fraction_raise(0.5, 20, 4, 2, legal) == Action.raise_to(18)
    assert pot_fraction_raise(50, 20, 4, 2, legal) == Action.raise_to(200)   # clamped
    assert pot_fraction_raise(0.5, 20, 4, 2, LegalActions(fold=True)) is None


def test_sparring_results_are_sane() -> None:
    # Tier 0 (check/fold) bleeds blinds against constant aggression.
    rep = run_duplicate(PlayerSpec.brain("tier0"), PlayerSpec.brain("maniac"),
                        seeds=range(2), hands=100, processes=1)
    assert rep.chips_per_hand[0] < 0   # folding everything loses to a maniac


def test_registry_has_all() -> None:
    assert set(SPARRING) <= set(BRAINS)


def test_run_brain_subprocess() -> None:
    msgs = scripted_messages(hands=2)
    data = ("\n".join(encode(msgs)) + "\n").encode()
    proc = subprocess.run([sys.executable, "-m", "lab.run_brain", "calling_station"],
                          input=data, capture_output=True, cwd=ROOT, timeout=30)
    replies = decode_replies(msgs, proc.stdout.decode().splitlines())
    assert proc.returncode == 0 and len(replies) == 8
    assert replies[0] == Action.call() and replies[1] == Action.check()
    assert replies[2].kind == "S"


# --------------------------------------------------------------------------- versions

def test_snapshot_from_working_tree_runs(tmp_path) -> None:
    create_snapshot("v_test", root=tmp_path)
    assert list_snapshots(tmp_path) == ["v_test"]
    assert "source:" in (tmp_path / "v_test" / "META.txt").read_text()
    with pytest.raises(FileExistsError):
        create_snapshot("v_test", root=tmp_path)
    spec = snapshot_player("v_test", root=tmp_path)
    m = play_match([spec.build(), PlayerSpec.brain("random_legal").build()], seed=0, hands=20)
    assert m.forfeit is None and m.errors[0] == 0


def test_snapshot_from_git_ref(tmp_path) -> None:
    create_snapshot("v_git", ref="HEAD", root=tmp_path)
    assert (tmp_path / "v_git" / "bot" / "main.py").is_file()
    assert (tmp_path / "v_git" / "variant" / "rules.py").is_file()
    assert "git HEAD" in (tmp_path / "v_git" / "META.txt").read_text()


def test_missing_snapshot(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        snapshot_player("nope", root=tmp_path)
