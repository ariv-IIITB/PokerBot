"""S0: lab.opps.score_compare on synthetic and real lab.eval files."""
from pathlib import Path

import pytest

from lab.opps import score_compare as sc

ROOT = Path(__file__).resolve().parent.parent


def line(bot: str, opp: str, score: float, se: float) -> str:
    return (f"{bot} vs {opp}: +0.10 ± 0.20 chips/hand | match score {score:.3f} ± {se:.3f} "
            f"over 100 matches | errors A/B 0/0 | forfeits A/B 0/0 | 40000 hands in 1.0s (1/s)")


def write(tmp_path, name, rows) -> str:
    p = tmp_path / name
    p.write_text("\n".join(line("x", o, s, se) for o, s, se in rows) + "\n--- accounting: x\n")
    return str(p)


def test_keep_when_not_lower(tmp_path) -> None:
    a = write(tmp_path, "a.txt", [("o1", 0.50, 0.05), ("o2", 0.60, 0.05)])
    b = write(tmp_path, "b.txt", [("o1", 0.55, 0.05), ("o2", 0.58, 0.05)])
    lines, keep = sc.compare(sc.parse_scores(a), sc.parse_scores(b))
    assert keep and lines[-1] == "verdict: KEEP-score"


def test_drop_when_lower_by_more_than_2se(tmp_path) -> None:
    a = write(tmp_path, "a.txt", [("o1", 0.70, 0.03), ("o2", 0.70, 0.03)])
    b = write(tmp_path, "b.txt", [("o1", 0.50, 0.03), ("o2", 0.50, 0.03)])
    lines, keep = sc.compare(sc.parse_scores(a), sc.parse_scores(b))
    assert not keep and lines[-1] == "verdict: DROP-score"
    assert "-0.200" in lines[-2]


def test_small_drop_within_noise_is_keep(tmp_path) -> None:
    a = write(tmp_path, "a.txt", [("o1", 0.60, 0.05)])
    b = write(tmp_path, "b.txt", [("o1", 0.55, 0.05)])
    assert sc.compare(sc.parse_scores(a), sc.parse_scores(b))[1]


def test_no_common_opponents_is_not_keep(tmp_path) -> None:
    a = write(tmp_path, "a.txt", [("o1", 0.6, 0.05)])
    b = write(tmp_path, "b.txt", [("o2", 0.6, 0.05)])
    assert not sc.compare(sc.parse_scores(a), sc.parse_scores(b))[1]


def test_real_files() -> None:
    t2, t3 = ROOT / "logs/g/recheck/pool_t2.txt", ROOT / "logs/g/recheck/pool_t3.txt"
    if not (t2.is_file() and t3.is_file()):
        pytest.skip("recheck files not present")
    before, after = sc.parse_scores(t2), sc.parse_scores(t3)
    assert before and set(before) == set(after)
    lines, keep = sc.compare(before, after)
    assert keep and "overall" in lines[-2]      # tier3 scores higher than tier2 there
