"""Phase 18: canonical classes, the resumable precompute pipeline, and bot-side loading."""
import argparse
import json

import numpy as np

from bot.cards import parse_cards as P
from bot.game.compile import compile_spec
from bot.sim.canonical import HandClasses, canonical
from bot.sim.tables import load_tables
from lab import precompute
from variant.spec import VariantSpec, load_catalog, spec_hash


def test_class_counts() -> None:
    assert HandClasses(tuple(range(52)), 2).n_classes == 169
    assert HandClasses(tuple(range(52)), 3).n_classes == 1755
    short = tuple(c for c in range(52) if c // 4 >= 4)
    assert HandClasses(short, 2).n_classes == 81            # 9 pairs + 36 suited + 36 offsuit


def test_canonical_suit_symmetry() -> None:
    assert canonical(P("Ah,Kh")) == canonical(P("As,Ks"))
    assert canonical(P("Ah,Kh")) != canonical(P("Ah,Ks"))
    hc = HandClasses(tuple(range(52)), 2)
    ci = hc.index()
    holes = np.array([P("Ah,Kh"), P("Ad,Kd"), P("Ah,Ks"), P("7c,2d")])
    ids = ci.class_batch(holes)
    assert ids[0] == ids[1] != ids[2] and ci.class_of(P("2d,7c")) == ids[3]
    assert sum(hc.counts) == 1326


def args(tmp, variant="holdem_nl", **kw):
    a = dict(variant=variant, out=str(tmp), hours=0.0, samples=400, range_top=0.3, buckets=0,
             bucket_samples=40, seed=0, cap_mb=50.0)
    a.update(kw)
    return argparse.Namespace(**a)


def test_pipeline_end_to_end_and_bot_loading(tmp_path, monkeypatch) -> None:
    out = tmp_path / "holdem_nl"
    meta = precompute.run(args(out))
    assert meta["n_classes"] == 169 and meta["complete"]["equity_random"]
    assert meta["complete"]["equity_range"] and meta["total_bytes"] < 50 * 1024 * 1024
    eq = np.load(out / "eq_random.npy")
    hc = HandClasses(tuple(range(52)), 2)
    aa, seven_two = eq[hc.class_of(P("Ah,Ad"))], eq[hc.class_of(P("7h,2d"))]
    assert aa > 0.75 and seven_two < 0.42 and aa > seven_two
    rng_eq = np.load(out / "eq_range.npy")
    assert rng_eq[hc.class_of(P("7h,2d"))] < seven_two      # worse vs a strong range
    # The bot loads it (embedded) for the matching variant only.
    from tools import embed_data
    spec = load_catalog()["holdem_nl"]
    emb, _ = embed_data._tables(spec, tmp_path)
    rules = compile_spec(spec)
    tables = load_tables(rules, emb)
    assert tables is not None and abs(tables.start_share(P("Ah,Ad")) - aa) < 1e-9
    other = compile_spec(VariantSpec.from_dict({"name": "holdem_nl", "betting": {"ante": 1}}))
    assert load_tables(other, emb) is None                   # spec hash differs


def test_resumable_and_time_limited(tmp_path) -> None:
    out = tmp_path / "holdem_nl"
    meta = precompute.run(args(out, hours=1e-9, range_top=0.0))   # stops immediately
    assert meta["complete"].get("classes") and not meta["complete"].get("equity_random")
    partial = np.load(out / "eq_random.npy")
    assert np.isnan(partial).all() or np.isnan(partial).any()
    meta = precompute.run(args(out, range_top=0.0))                # resumes and finishes
    assert meta["complete"]["equity_random"]
    again = precompute.run(args(out, range_top=0.0))               # nothing left to do
    assert again["complete"]["equity_random"]


def test_deterministic(tmp_path) -> None:
    a = precompute.run(args(tmp_path / "a" / "holdem_nl", range_top=0.0, samples=200))
    b = precompute.run(args(tmp_path / "b" / "holdem_nl", range_top=0.0, samples=200))
    ea = np.load(tmp_path / "a" / "holdem_nl" / "eq_random.npy")
    eb = np.load(tmp_path / "b" / "holdem_nl" / "eq_random.npy")
    assert np.array_equal(ea, eb) and a["spec_hash"] == b["spec_hash"]


def test_three_card_variant_classes(tmp_path) -> None:
    out = tmp_path / "mit2026_discard"
    meta = precompute.run(args(out, variant="mit2026_discard", hours=1e-9))
    assert meta["n_classes"] == 1755
    assert json.loads((out / "meta.json").read_text())["spec_hash"] == spec_hash(
        load_catalog()["mit2026_discard"])


def test_missing_or_corrupt_data_falls_back() -> None:
    rules = compile_spec(load_catalog()["holdem_nl"])
    assert load_tables(rules, None) is None                   # nothing embedded
    assert load_tables(rules, {"meta": "{not a dict}", "files": {}}) is None   # unreadable
    assert load_tables(rules, {"meta": {"spec_hash": "x"}, "files": {}}) is None


def test_artifact_lookup_rejects_other_variants() -> None:
    # One staleness rule for every embedded artifact (bot/artifacts.py).
    from bot.artifacts import embedded
    from bot.game.rules_spec import to_rules
    from variant.spec import VariantSpec, spec_hash
    spec = VariantSpec(name="holdem_nl")
    art = {"meta": {"spec_hash": spec_hash(spec)}, "files": {}}
    assert embedded("tables", to_rules(spec), art) is art
    assert embedded("tables", to_rules(VariantSpec(name="omaha", hole_cards=4)), art) is None
    assert embedded("tables", to_rules(spec), None) is None
