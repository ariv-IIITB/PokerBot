"""C2: the training deal pool and the bucket thresholds (docs/cfr/ABSTRACTION_V1.md 4, 5.5, 5.6).

Pool features must equal what the runtime computes for the same cards (with the fixed training
discard), and the committed cuts must give equal-mass flop/turn cells.
"""
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("numba")

from bot import abstraction as A                       # noqa: E402
from bot.cards import parse_cards                      # noqa: E402
from bot.game.rules_spec import to_rules               # noqa: E402
from bot.sim.tables import load_tables                 # noqa: E402
from lab.cfr.fast import deals as D                    # noqa: E402
from lab.harness import load_variant                   # noqa: E402

CUTS = Path(__file__).resolve().parents[1] / "lab" / "cfr" / "fast" / "cuts_v1.json"


@pytest.fixture(scope="module")
def rules():
    return to_rules(load_variant("discard_holdem"))


@pytest.fixture(scope="module")
def cuts() -> dict:
    return json.loads(CUTS.read_text())


@pytest.fixture(scope="module")
def pool():
    return D.make_pool(20_000, pool_seed=7, chunk=20_000, log=False)


def _cards(seed: int, index: int) -> list[int]:
    out = np.empty(11, dtype=np.int64)
    D.draw_deal(seed, index, out)
    return out.tolist()


def test_deals_are_reproducible_and_distinct() -> None:
    a = _cards(7, 123)
    assert a == _cards(7, 123) and len(set(a)) == 11 and all(0 <= c < 52 for c in a)
    assert a != _cards(7, 124) and a != _cards(8, 123)


def test_pool_features_equal_the_runtime_features(rules, pool) -> None:
    feats, sd = pool
    ev, classes = rules.evaluator, load_tables(rules).classes
    for i in range(30):
        cards = _cards(7, i)
        board = cards[6:]
        keeps, discards = [], []
        for p in range(2):
            h3 = cards[3 * p: 3 * p + 3]
            f = feats[i, p]
            assert f[0] == classes.class_of(h3)
            k, fx, fy = A.flop_features(ev, h3, board[:3])
            assert (k, fx, fy) == (f[1], f[2] / D.FLOP_DEN[0], f[3] / D.FLOP_DEN[1])
            keep = [sorted(h3)[j] for j in D.KEEPS[k]]
            keeps.append(keep)
            discards += [c for c in h3 if c not in keep]
        for p in range(2):
            f = feats[i, p]
            tx, ty = A.turn_features(ev, keeps[p], board[:4], discards)
            assert (tx, ty) == (f[4] / D.TURN_DEN[0], f[5] / D.TURN_DEN[1])
            hs, blk = A.river_features(ev, keeps[p], board, discards)
            assert (hs, blk) == (f[6] / D.RIVER_DEN, f[7])
        v = [ev.evaluate(keeps[p], board) for p in range(2)]
        assert sd[i] == (1 if v[0] > v[1] else -1 if v[0] < v[1] else 0)


def test_committed_cuts_give_equal_mass_cells_on_a_fresh_pool(cuts, pool) -> None:
    assert cuts["version"] == "v1" and cuts["grid"] == 10 and cuts["river_bins"] == 25
    assert len(cuts["flop"]["x"]) == 9 and len(cuts["flop"]["y"]) == 10 and len(cuts["river"]) == 24
    b = D.bucket_ids(pool[0], cuts).reshape(-1, 4)
    assert b[:, 0].max() < 1755 and b[:, 3].max() < 50
    for s in (1, 2):
        c = np.bincount(b[:, s], minlength=100)
        assert len(c) == 100 and c.min() > 0.6 * c.mean() and c.max() < 1.4 * c.mean()
    hs_bins = np.bincount(b[:, 3] // 2, minlength=25)
    assert hs_bins.min() > 0.6 * hs_bins.mean() and hs_bins.max() < 1.4 * hs_bins.mean()


def test_bucket_ids_match_the_runtime_bucket_functions(rules, cuts, pool) -> None:
    feats, _sd = pool
    b = D.bucket_ids(feats[:200], cuts)
    f = D.features(feats[:200])
    for i in range(200):
        for p in range(2):
            assert b[i, p, 1] == A.grid_bucket(f["fx"][i, p], f["fy"][i, p], cuts["flop"]["x"], cuts["flop"]["y"])
            assert b[i, p, 2] == A.grid_bucket(f["tx"][i, p], f["ty"][i, p], cuts["turn"]["x"], cuts["turn"]["y"])
            assert b[i, p, 3] == A.river_bucket(f["hs"][i, p], f["blk"][i, p], cuts["river"])


def test_worked_example_bucket_ids(rules, cuts) -> None:
    """docs/cfr/ABSTRACTION_V1.md section 6, with cuts_v1.json."""
    ev = rules.evaluator
    flop = list(parse_cards("Kh,8d,2c"))
    turn, river = list(parse_cards("5s")), list(parse_cards("Jh"))
    dead = list(parse_cards("7c,3d"))
    got = {}
    for who, h3, keep in (("button", "As,Kd,7c", "As,Kd"), ("bb", "Qh,Qs,3d", "Qh,Qs")):
        _k, fx, fy = A.flop_features(ev, parse_cards(h3), flop)
        tx, ty = A.turn_features(ev, parse_cards(keep), flop + turn, dead)
        hs, blk = A.river_features(ev, parse_cards(keep), flop + turn + river, dead)
        got[who] = (A.grid_bucket(fx, fy, cuts["flop"]["x"], cuts["flop"]["y"]),
                    A.grid_bucket(tx, ty, cuts["turn"]["x"], cuts["turn"]["y"]),
                    A.river_bucket(hs, blk, cuts["river"]))
    assert got == {"button": (93, 89, 40), "bb": (80, 74, 32)}
