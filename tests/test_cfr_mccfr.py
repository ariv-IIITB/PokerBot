"""C3: the fast MCCFR trainer (lab/cfr/fast/mccfr.py, train.py).

Validated exactly on Kuhn poker written as a flat tree (equilibrium value -1/18), then smoke-tested
on the real v1 tree with a small deal pool, and the CLI end to end (checkpoint, resume, export).
"""
import json

import numpy as np
import pytest

pytest.importorskip("numba")

from lab.cfr.fast import deals as D                   # noqa: E402
from lab.cfr.fast import mccfr, toy, train            # noqa: E402


def test_kuhn_converges_to_the_known_value() -> None:
    g = toy.kuhn()
    tr = mccfr.Trainer(g, seed=1, threads=1)
    tr.train(150_000, batch=10_000)
    v = mccfr.exact_values(g, tr.average())
    assert abs(v["value0"] - toy.KUHN_VALUE) < 0.005
    assert v["exploitability"] < 0.01


def test_exact_values_of_the_uniform_kuhn_profile() -> None:
    g = toy.kuhn()
    v = mccfr.exact_values(g, mccfr.normalize(np.zeros((g.rows, mccfr.MAX_ACT)), g))
    assert v["value0"] == pytest.approx(0.125)
    assert v["br0"] >= v["value0"] and v["br1"] >= -v["value0"]


@pytest.fixture(scope="module")
def small_pool(tmp_path_factory):
    feats, sd = D.make_pool(3000, pool_seed=5, chunk=3000, log=False)
    path = tmp_path_factory.mktemp("pool") / "pool.npz"
    np.savez(path, feats=feats, sd=sd, seed=5)
    return path


def test_real_tree_smoke(small_pool) -> None:
    game, cuts, par = train.load_game(str(small_pool), "lab/cfr/fast/cuts_v1.json")
    assert game.rows == 502_060
    tr = mccfr.Trainer(game, seed=2, threads=1)
    tr.train(20_000, batch=10_000)
    assert np.isfinite(tr.regret).all() and tr.visits.sum() > 0
    avg = tr.average()
    mask = mccfr.legal_mask(game)
    legal_rows = mask.any(axis=1)
    assert np.allclose(avg[legal_rows].sum(axis=1), 1.0) and (avg[~mask] == 0).all()
    q = mccfr.export_uint8(avg, game, tr.visits, min_visits=1)
    sums = q.astype(np.int64).sum(axis=1)
    assert set(np.unique(sums)) <= {0, 255} and (q[~mask] == 0).all()
    assert (sums[tr.visits >= 1] == 255).all() and (sums[tr.visits < 1] == 0).all()


def test_train_cli_checkpoints_resumes_and_exports(small_pool, tmp_path) -> None:
    out = tmp_path / "run"
    args = ["--pool", str(small_pool), "--iters", "4000", "--batch", "2000", "--threads", "1",
            "--out", str(out), "--min-visits", "1"]
    assert train.main(args) == 0
    bp = np.load(out / "blueprint_v1.npz")
    meta = json.loads(str(bp["meta"]))
    assert meta["version"] == "v1" and meta["iterations"] == 4000
    assert meta["n_buckets"] == [1755, 100, 100, 50] and len(meta["histories"][3]) == 6964
    assert meta["params"]["sized_raise_cap"] == 3 and meta["thresholds"]["grid"] == 10
    assert bp["probs"].shape == (502_060, mccfr.MAX_ACT) and bp["probs"].dtype == np.uint8
    assert train.main(args + ["--resume"]) == 0
    assert json.loads(str(np.load(out / "blueprint_v1.npz")["meta"]))["iterations"] == 8000
    assert "rows visited < 10x" in (out / "progress.log").read_text()
