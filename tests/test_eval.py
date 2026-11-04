"""lab.eval: pool resolution, brain specs, compare verdicts, profile targets, tracking."""
import json

import pytest

from lab import eval as ev
from lab.harness import run_duplicate
from lab.opps import track
from lab.players import PlayerSpec


def test_parse_brain_variants(tmp_path) -> None:
    assert ev.parse_brain("tier2").display == "tier2"
    s = ev.parse_brain("tier2:{\"call_margin\": 0.05}", locks="off")
    assert dict(s.config) == {"call_margin": 0.05, "lock_enabled": False}
    assert s.display.endswith("-nolock")
    f = tmp_path / "cfg.json"
    f.write_text(json.dumps({"bet_pressure": 0.0}))
    assert dict(ev.parse_brain(f"tier2:{f}").config) == {"bet_pressure": 0.0}
    assert dict(ev.parse_brain("tier2:no_pressure").config) == {"bet_pressure": 0.0}
    assert ev.parse_brain("opp1", locks="off").config is None       # no lock key for others
    with pytest.raises(SystemExit):
        ev.parse_brain("tier2:nonsense")


def test_pools(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ev, "POOL_FILE", tmp_path / "missing.json")
    assert ev.resolve_pool(["train"], False) == ev.DEFAULT_TRAIN
    assert ev.resolve_pool(["tight,maniac", "opp3"], False) == ["tight", "maniac", "opp3"]
    with pytest.raises(SystemExit, match="--final"):
        ev.resolve_pool(["heldout"], False)
    with pytest.raises(SystemExit, match="no held-out"):
        ev.resolve_pool(["heldout"], True)
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps({"train": ["a", "b"], "heldout": ["z"]}))
    monkeypatch.setattr(ev, "POOL_FILE", pool)
    assert ev.resolve_pool(["train"], False) == ["a", "b"]
    assert ev.resolve_pool(["heldout"], True) == ["z"]


def _summary(vals: dict) -> dict:
    return {k: v for k, v in vals.items()}


def test_compare_verdicts() -> None:
    before = {"opp1": (4.0, 0.2), "opp3": (-2.7, 0.3)}
    better = {"opp1": (4.1, 0.2), "opp3": (-1.5, 0.3)}
    lines, keep = ev.compare(before, better, target="opp3")
    assert keep and lines[-1] == "verdict: KEEP"
    worse_elsewhere = {"opp1": (3.0, 0.2), "opp3": (-1.5, 0.3)}      # opp1 drops by > 2 SE
    lines, keep = ev.compare(before, worse_elsewhere, target="opp3")
    assert not keep and any("DROPPED" in ln for ln in lines)
    noise = {"opp1": (4.05, 0.2), "opp3": (-2.6, 0.3)}               # target moves < 2 SE
    assert not ev.compare(before, noise, target="opp3")[1]
    assert ev.compare(before, better)[1]                              # no target: sum improves
    assert not ev.compare(before, {"zzz": (0, 1)})[1]


def test_parse_summary_reads_lab_eval_lines(tmp_path) -> None:
    f = tmp_path / "r.txt"
    f.write_text("tier2-nolock vs opp1-nolock: +4.40 ± 0.16 chips/hand | match score 0.980 ± 0.014"
                 " over 100 matches | errors A/B 0/0 | forfeits A/B 0/0 | 40000 hands in 213.1s\n"
                 "--- profile: x\n")
    assert ev.parse_summary(f) == {"opp1": (4.4, 0.16)}


def test_check_profile_lines_pass_and_fail() -> None:
    merged = {"A": {"spots": {"pre/open": {"R": 70, "C": 25, "F": 5},
                              "flop/vs_bet": {"F": 90, "C": 10}}, "profile": {}, "acct": {}}}
    text = "\n".join(ev.check_profile_lines(merged, "x"))
    assert "pre/open         R:  70.0%  target 65-75%  PASS" in text
    assert "flop/vs_bet      F:  90.0%  target 30-45%  FAIL" in text
    assert "too few decisions" in text                                 # spots never seen


def test_tracking_does_not_change_the_match() -> None:
    a, b = PlayerSpec.brain("calling_station"), PlayerSpec.brain("tight")
    kw = dict(cfg=None, seeds=range(2), hands=40, processes=1)
    plain, tracked = run_duplicate(a, b, **kw), run_duplicate(a, b, track=True, **kw)
    assert [p.a_chips for p in plain.pairs] == [p.a_chips for p in tracked.pairs]
    merged = track.merge([p.track for p in tracked.pairs])
    a_chips = sum(c for _, c in merged["A"]["acct"].values())
    b_chips = sum(c for _, c in merged["B"]["acct"].values())
    assert a_chips == sum(sum(p.a_chips) for p in tracked.pairs) == -b_chips
    assert sum(n for n, _ in merged["A"]["acct"].values()) == 160
    assert merged["A"]["profile"] and "calling_station" in track.format_profile(
        merged, {"A": "calling_station", "B": "tight"})


def test_run_pool_end_to_end(capsys) -> None:
    lines = ev.run_pool("tier0", ["calling_station"], 2, variant="holdem_nl", hands=20,
                        locks="off", report=("accounting", "profile"), check_profile=True,
                        processes=1)
    text = "\n".join(lines)
    assert lines[0].startswith("tier0-nolock vs calling_station-nolock:")
    assert "--- accounting: tier0-nolock" in text and "--- profile targets" in text


def test_stats_report_sums_the_brains_own_counters() -> None:
    lines = ev.run_pool("tier3", ["calling_station"], 1, variant="discard_holdem", hands=12,
                        locks="off", report=("stats",), processes=1)
    text = "\n".join(lines)
    assert "--- brain stats: tier3-nolock:" in text
    stat_line = next(line for line in lines if line.startswith("--- brain stats: tier3"))
    counts = dict(kv.split("=") for kv in stat_line.split(": ", 2)[2].split())
    assert set(counts) == {"t3_decisions", "t3_errors", "t3_fallbacks"}
    assert int(counts["t3_decisions"]) > 0 and int(counts["t3_errors"]) == 0
    assert "calling_station" not in stat_line          # sparring bots keep no stats


def test_accounting_reports_se_over_pairs_and_a_river_line() -> None:
    lines = ev.run_pool("tier0", ["calling_station"], 4, variant="holdem_nl", hands=20,
                        locks="off", report=("accounting",), processes=1)
    text = "\n".join(lines)
    assert "+-" in text and "river-all" in text and "over 4 pairs" in text


def test_river_compare_reads_the_river_all_lines(tmp_path) -> None:
    from lab.opps import river_compare
    txt = ("tier3 vs conv: +0.10 ± 0.20 chips/hand | x\n--- accounting: tier3 (+1 chips over 8 hands, +0.12/hand)\n"
           "  river-all      river  hands=   5 chips=   +9 ({m} +-0.050/hand over 4 pairs)\n"
           "--- accounting: conv (-1 chips over 8 hands, -0.12/hand)\n"
           "  river-all      river  hands=   5 chips=   -9 (-0.900 +-0.050/hand over 4 pairs)\n")
    (tmp_path / "a").write_text(txt.format(m="+0.100"))
    (tmp_path / "b").write_text(txt.format(m="+0.500"))
    assert river_compare.river_all(str(tmp_path / "a")) == {"conv": (0.1, 0.05)}
    assert river_compare.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 0
