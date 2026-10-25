"""Phase 22: MCCFR-lite — solver validated on Kuhn poker, abstraction, CFR brain."""
import json

import numpy as np

from bot.actions import LegalActions
from bot.game.compile import compile_spec
from lab.cfr.abstraction import Bucketer, abstract_actions, raise_label
from lab.cfr.abstract_game import AbstractGame
from lab.cfr.kuhn import Kuhn
from lab.cfr.mccfr import MCCFR, expected_value, exploitability, export_uint8
from lab.engine import play_match
from lab.players import PlayerSpec
from variant.spec import VariantSpec, load_catalog, spec_hash


def test_kuhn_converges_to_game_value() -> None:
    g = Kuhn()
    m = MCCFR(g, seed=0)
    m.iterate(20000)
    assert abs(expected_value(g, m.average_strategy, 0) - (-1 / 18)) < 0.004
    assert exploitability(g, m.average_strategy) < 0.01
    uniform = lambda key, n: np.full(n, 1.0 / n)  # noqa: E731
    assert exploitability(g, uniform) > 0.2           # the measure is not trivially small


def test_checkpoint_resume_is_identical(tmp_path) -> None:
    g = Kuhn()
    a = MCCFR(g, seed=3)
    a.iterate(500)
    a.save(tmp_path / "c.pkl")
    b = MCCFR.load(tmp_path / "c.pkl", g)
    a.iterate(300)
    b.iterate(300)
    assert all(np.allclose(a.avg[k], b.avg[k]) for k in a.avg)


def test_export_uint8_prunes_and_sums_to_255() -> None:
    g = Kuhn()
    m = MCCFR(g, seed=1)
    m.iterate(2000)
    t = export_uint8(m)
    assert t and all(int(v.sum()) == 255 and v.dtype == np.uint8 for v in t.values())


def test_pseudo_harmonic_mapping() -> None:
    # pot 10, nothing to call: a raise to 5 is exactly 0.5 pot, to 10 exactly pot
    assert raise_label(5, 10, 0, 0) == "H" and raise_label(10, 10, 0, 0) == "P"
    assert raise_label(3, 10, 0, 0) == "H" and raise_label(30, 10, 0, 0) == "P"
    # 0.75 pot: P(H) = (1 - .75)(1.5) / ((.5)(1.75)) = 0.4286
    rng = np.random.default_rng(0)
    labels = [raise_label(15, 20, 0, 0, rng) for _ in range(4000)]     # 0.75 pot
    assert abs(labels.count("H") / 4000 - 0.4286) < 0.03
    assert raise_label(400, 10, 0, 0, all_in=True) == "A"


def test_abstract_actions_and_buckets() -> None:
    legal = LegalActions(fold=True, call=True, raise_min=4, raise_max=400)
    acts = abstract_actions(legal, 3, 1, 1)
    assert [l for l, _ in acts] == ["F", "C", "H", "P", "A"]
    rules = compile_spec(VariantSpec())
    b = Bucketer(rules, 8)
    from bot.cards import parse_cards as P
    assert b.bucket(P("Ah,Ad"), ()) > b.bucket(P("7h,2d"), ())
    assert b.bucket(P("Ah,Ad"), ()) == b.bucket(P("Ad,Ah"), ())       # deterministic


def test_abstract_game_trains_and_brain_uses_it(tmp_path, monkeypatch) -> None:
    spec = load_catalog()["holdem_nl"]
    rules = compile_spec(spec)
    m = MCCFR(AbstractGame(rules, 4), seed=0, epsilon=0.1)
    m.iterate(60)
    table = export_uint8(m)
    d = tmp_path / spec.name
    d.mkdir()
    (d / "cfr_strategy.json").write_text(json.dumps({
        "spec_hash": spec_hash(spec), "buckets": 4, "iterations": 60,
        "table": {k: [int(x) for x in v] for k, v in table.items()}}))
    monkeypatch.setenv("POKERBOT_DATA", str(tmp_path))
    me = PlayerSpec.brain("cfr", {"lock_enabled": False, "rollout_worlds": 12, "pimc_worlds": 2}).build()
    mt = play_match([me, PlayerSpec.brain("random_legal").build()], spec, seed=2, hands=40, audit=True)
    brain = me.bot.brain
    assert mt.errors == [0, 0] and brain.strategy is not None
    assert brain.hits > 0                                    # it really used the table


def test_cfr_brain_without_strategy_is_tier2() -> None:
    m = play_match([PlayerSpec.brain("cfr", {"rollout_worlds": 12, "pimc_worlds": 2}).build(),
                    PlayerSpec.brain("maniac").build()], load_catalog()["mit2026_discard"],
                   seed=3, hands=20, audit=True)
    assert m.errors == [0, 0] and m.forfeit is None


def test_export_prunes_undertrained_infosets() -> None:
    g = Kuhn()
    m = MCCFR(g, seed=1)
    m.iterate(300)
    assert sum(m.visits.values()) > 0
    full = export_uint8(m)
    rare = min(m.visits, key=m.visits.get)
    cut = m.visits[rare] + 1
    pruned = export_uint8(m, min_traverser_visits=cut)
    assert rare not in pruned and set(pruned) <= set(full)
    assert all(m.visits.get(k, 0) >= cut for k in pruned)


def test_fractions_abstraction_and_parse() -> None:
    from lab.cfr.train import parse_fractions
    assert parse_fractions(["P=1.0"]) == {"P": 1.0} and parse_fractions(None) is None
    legal = LegalActions(fold=True, call=True, raise_min=4, raise_max=400)
    acts = abstract_actions(legal, 3, 1, 1, {"P": 1.0})
    assert [l for l, _ in acts] == ["F", "C", "P", "A"]
    assert raise_label(10, 10, 0, 0, fractions={"P": 1.0}) == "P"


def test_diagnose_export_kinds(tmp_path) -> None:
    from lab.cfr.diagnose import export_table, visit_report
    g = Kuhn()
    m = MCCFR(g, seed=2)
    m.iterate(500)
    m.save(tmp_path / "k.ckpt")
    rep = visit_report(str(tmp_path / "k.ckpt"))
    assert rep["infosets"] == 12 and rep["iterations"] == 500
    import pickle
    d = pickle.loads((tmp_path / "k.ckpt").read_bytes())
    fl, u8, cur = (export_table(d, k) for k in ("float", "uint8", "current"))
    assert len(fl) == 12 and all(abs(sum(v) - 1) < 1e-9 for v in fl.values())
    assert all(sum(v) == 255 for v in u8.values()) and set(u8) <= set(fl)
    assert all(abs(sum(v) - 1) < 1e-9 for v in cur.values())


def test_train_cli_snapshots_and_resume(tmp_path) -> None:
    from lab.cfr import train
    out = tmp_path / "s.json"
    argv = ["--variant", "holdem_short30", "--minutes", "0.03", "--buckets", "4",
            "--fractions", "P=1.0", "--export-iters", "20", "--out", str(out)]
    train.main(argv)
    doc = json.loads(out.read_text())
    snap = json.loads((tmp_path / "s_20it.json").read_text())
    assert doc["fractions"] == {"P": 1.0} and doc["iterations"] >= 20 == snap["iterations"]
    assert (tmp_path / "s.ckpt").is_file() and (tmp_path / "s_20it.ckpt").is_file()
    first = doc["iterations"]
    train.main(argv[:-4] + ["--out", str(out)])                    # resumes from the checkpoint
    assert json.loads(out.read_text())["iterations"] > first
