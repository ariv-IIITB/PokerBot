"""Quick versions of the phase 9 tools (the real runs are CLI jobs)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lab.fuzz import WeirdPlayer, run_fuzz
from lab.sweep import format_table, grid, random_candidates, run_sweep
from lab.timing_bench import run_timing

ROOT = Path(__file__).resolve().parent.parent


def test_fuzz_quick_in_process() -> None:
    rep = run_fuzz(total_hands=1600, hands_per_match=20, processes=1)
    assert rep.failures == [], rep.failures[:3]
    assert rep.hands > 1000 and rep.opp_errors > 0      # weird bots really misbehaved


def test_fuzz_quick_subprocess_with_junk_input() -> None:
    rep = run_fuzz(total_hands=100, hands_per_match=10, variants=["holdem", "discard3"],
                   processes=1, subprocess_bot=True)
    assert rep.failures == [], rep.failures[:3]
    assert rep.matches == 2 * len(WeirdPlayer.STYLES)


@pytest.mark.slow
def test_fuzz_big() -> None:
    rep = run_fuzz(total_hands=100_000, hands_per_match=200)
    assert rep.failures == [], rep.failures[:3]


def test_timing_bench_quick() -> None:
    rep = run_timing(hands=20, opponent="random_legal")
    assert rep.ok and rep.decisions > 0 and 0 < rep.startup_s < 3
    assert "startup" in rep.summary()


def test_memory_check_cli() -> None:
    proc = subprocess.run([sys.executable, "-m", "lab.memory_check", "--hands", "20"],
                          cwd=ROOT, capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode()[-500:]
    mb = float(proc.stdout.decode().split("RSS:")[1].split("MB")[0])
    assert 5 < mb < 1024


def test_sweep_space_expansion() -> None:
    space = {"a": [1, 2], "b": {"low": 0.0, "high": 1.0}, "c": 7}
    g = grid(space, points=3)
    assert len(g) == 2 * 3 and g[0] == {"a": 1, "b": 0.0, "c": 7}
    r = random_candidates(space, 5, seed=1)
    assert len(r) == 5 and all(0 <= c["b"] <= 1 and c["a"] in (1, 2) for c in r)
    assert r == random_candidates(space, 5, seed=1)


def test_sweep_quick() -> None:
    res = run_sweep("tier1", {"bluff_freq": [0.0, 0.3]}, ["random_legal"], seeds=range(1),
                    hands=20, processes=1)
    assert len(res) == 3                                    # baseline + 2 candidates
    assert res[0].chips_per_hand >= res[-1].chips_per_hand
    table = format_table(res)
    assert "(baseline)" in table and json.dumps({"bluff_freq": 0.3}) in table
