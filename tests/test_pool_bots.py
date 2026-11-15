"""Phase F: the Discard Hold'em opponent pool (Opps/discard/<name>/main_bot.py, registered as d_<name>).

Each bot must start, answer action and discard requests over the real protocol and finish a few
hands without a forfeit, a malformed reply or an illegal action. Strength is not tested here.
"""
import json
from pathlib import Path

import pytest

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec, discard_pool_bots
from lab.pool_health import ProbePlayer

ROOT = Path(__file__).resolve().parent.parent
POOL_FILE = ROOT / "lab" / "opps" / "discard_pool.json"
BOTS = sorted(discard_pool_bots())


def test_pool_bots_are_registered() -> None:
    assert BOTS, "no Opps/discard/*/main_bot.py found"
    assert all(name.startswith("d_") for name in BOTS)
    spec = PlayerSpec.brain(BOTS[0])
    assert spec.kind == "subprocess" and spec.protocol == "pokerbots"


@pytest.mark.parametrize("opponent", ["calling_station", "maniac"])
@pytest.mark.parametrize("name", BOTS)
def test_bot_plays_a_few_hands_over_the_real_protocol(name: str, opponent: str, tmp_path) -> None:
    cfg = load_variant("discard_holdem")
    probe = ProbePlayer(name, discard_pool_bots()[name], str(tmp_path / "stderr.txt"))
    other = PlayerSpec.brain(opponent).build(cfg)
    res = play_match([probe, other], cfg, seed=5, hands=8, time_bank_s=60.0, reply_limit_s=5.0)
    assert res.forfeit is None, f"{name} forfeited: {res.forfeit_reason}"
    assert res.hands_played == 8
    assert probe.malformed == 0 and res.errors[0] == 0
    assert probe.replies >= 8                       # it answered action and discard requests


def test_pool_file_is_consistent() -> None:
    if not POOL_FILE.is_file():
        pytest.skip("the held-out split is not chosen yet")
    pool = json.loads(POOL_FILE.read_text())
    train, held = pool["train"], pool["heldout"]
    assert len(held) >= 2 and train
    assert not set(train) & set(held)
    assert set(train) | set(held) == set(BOTS)
    assert pool["prompt"].startswith("Build a bot for this poker competition.")
    assert set(pool["models"]) == set(train) | set(held)
