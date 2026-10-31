"""C5: the Tier 4 brain and its run-time keys (bot/cfr/blueprint.py, bot/brains/tier4.py).

The runtime must key a decision exactly as the trainer does: same abstract history, same menu
(labels and chips) at every node of the v1 tree, from either seat. Off-tree raises are translated
or missed per the contract. With a small trained blueprint, Tier 4 plays legal hands and uses it.
"""
import base64
import dataclasses
import io
import json
from types import SimpleNamespace

import numpy as np
import pytest

from bot.actions import Action
from bot.cards import parse_cards
from bot.cfr import blueprint as BP
from bot.game.rules_spec import to_rules
from bot.protocol import Info
from bot.state import ME, OPP, ActionRecord, HandState
from lab.cfr.fast import tree
from lab.harness import load_variant


@pytest.fixture(scope="module")
def par():
    return tree.Params.from_variant("discard_holdem")


@pytest.fixture(scope="module")
def rpar(par):
    return BP.Params(**dataclasses.asdict(par))


def _hand(me: int, records: list, street: int) -> HandState:
    h = HandState(hand_id=1, seat=me, start_stack=200, opp_start_stack=200)
    h.history = list(records)
    h.street = street
    return h


@pytest.mark.parametrize("me", [0, 1])
def test_runtime_key_and_menu_equal_the_trainer_on_random_lines(par, rpar, me) -> None:
    rng = np.random.default_rng(31 + me)
    checked = 0
    for _ in range(1000):
        n, records = tree.root(par), []
        while not n.done:
            view = BP.abstract_view(_hand(me, records, n.street), rpar)
            assert view is not None and view.history == n.history
            assert view.street.to_call(n.actor) == n.to_call(n.actor)
            assert view.street.stacks == list(n.stacks)
            assert BP.menu(view.street, n.actor, rpar) == tree.actions(n, par)
            checked += 1
            acts = tree.actions(n, par)
            label, kind, amt = acts[int(rng.integers(len(acts)))]
            real_kind = {"F": "F", "K": "K", "C": "C", "R": "R"}[kind]
            records.append(ActionRecord(n.street, ME if n.actor == me else OPP, Action(real_kind, amt)))
            n = tree.child(n, label, par)
    assert checked > 2500


def test_off_menu_raises_are_translated_or_missed(par, rpar) -> None:
    # flop, BB to act first, pot 30 after R R C: menu C H15 P30 A185
    pre = [ActionRecord(0, ME, Action("R", 5)), ActionRecord(0, OPP, Action("R", 15)),
           ActionRecord(0, ME, Action("C"))]
    picks = {BP.abstract_view(_hand(0, pre + [ActionRecord(1, OPP, Action("R", 22))], 1),
                              rpar, SimpleNamespace(random=lambda u=u: u)).history
             for u in (0.01, 0.99)}
    assert picks == {"RRC/H", "RRC/P"}                    # 22 lies between 15 and 30
    v = BP.abstract_view(_hand(0, pre + [ActionRecord(1, OPP, Action("R", 15))], 1), rpar)
    assert v.history == "RRC/H" and v.translated == 0     # an exact menu size
    v = BP.abstract_view(_hand(0, pre + [ActionRecord(1, OPP, Action("R", 185))], 1), rpar)
    assert v.history == "RRC/A"
    # preflop after BB, open and 3-bet only all-in is in the menu: a sized 4-bet is a miss
    capped = [ActionRecord(0, OPP, Action("R", 5)), ActionRecord(0, ME, Action("R", 15)),
              ActionRecord(0, OPP, Action("R", 45))]
    assert BP.abstract_view(_hand(1, capped, 0), rpar) is None
    assert BP.abstract_view(_hand(1, capped[:2] + [ActionRecord(0, OPP, Action("R", 200))], 0),
                            rpar).history == "RRA"


def test_runtime_buckets_of_the_worked_example() -> None:
    rules = to_rules(load_variant("discard_holdem"))
    from bot.sim.tables import load_tables
    classes = load_tables(rules).classes
    cuts = json.loads(open("lab/cfr/fast/cuts_v1.json").read())
    bp = SimpleNamespace(cuts=cuts)

    def hand(hole, board, reveals=()):
        h = HandState(hand_id=1, seat=0, start_stack=200, opp_start_stack=200)
        h.hole, h.board = tuple(parse_cards(hole)), tuple(parse_cards(board)) if board else ()
        h.info = [Info("reveal", w, tuple(parse_cards(c))) for w, c in reveals]
        return h

    rv = (("me", "7c"), ("opp", "3d"))
    assert BP.bucket(hand("As,Kd,7c", ""), 0, bp, rules.evaluator, classes) == 1486
    assert BP.bucket(hand("As,Kd,7c", "Kh,8d,2c"), 1, bp, rules.evaluator, classes) == 93
    assert BP.bucket(hand("As,Kd", "Kh,8d,2c,5s", rv), 2, bp, rules.evaluator, classes) == 89
    assert BP.bucket(hand("As,Kd", "Kh,8d,2c,5s,Jh", rv), 3, bp, rules.evaluator, classes) == 40
    assert BP.bucket(hand("As,Kd", "Kh,8d,2c,5s"), 2, bp, rules.evaluator, classes) is None  # no discards


# --------------------------------------------------------------------------- with a trained table

@pytest.fixture(scope="module")
def small_blueprint(tmp_path_factory):
    pytest.importorskip("numba")
    from lab.cfr.fast import deals as D
    from lab.cfr.fast import mccfr, train
    feats, sd = D.make_pool(4000, pool_seed=9, chunk=4000, log=False)
    path = tmp_path_factory.mktemp("bp") / "pool.npz"
    np.savez(path, feats=feats, sd=sd, seed=9)
    game, cuts, tpar = train.load_game(str(path), "lab/cfr/fast/cuts_v1.json")
    tr = mccfr.Trainer(game, seed=4, threads=1)
    tr.train(60_000, batch=20_000)
    probs = mccfr.export_uint8(tr.average(), game, tr.visits, min_visits=1)
    meta = train.blueprint_meta(game, cuts, tpar, "discard_holdem", tr.iterations, 1)
    return BP.Blueprint(meta, probs)


def test_blueprint_artifact_round_trip(small_blueprint) -> None:
    buf = io.BytesIO()
    np.save(buf, small_blueprint.probs, allow_pickle=False)
    art = {"meta": small_blueprint.meta, "files": {"probs": base64.b64encode(buf.getvalue()).decode()}}
    again = BP.Blueprint.from_artifact(art)
    assert np.array_equal(again.probs, small_blueprint.probs) and again.ids == small_blueprint.ids
    bad = dict(small_blueprint.meta, version="v0")
    with pytest.raises(ValueError):
        BP.Blueprint(bad, small_blueprint.probs)


def _play(blueprint, config, opponent="calling_station", hands=40, seed=3):
    from bot.brains.tier4 import Tier4Brain
    from lab.engine import play_match
    from lab.players import InProcessPlayer, PlayerSpec
    cfg = load_variant("discard_holdem")
    brain = Tier4Brain(config=dict(config, lock_enabled=False))
    brain.set_blueprint(blueprint)
    res = play_match([InProcessPlayer(brain, "tier4"), PlayerSpec.brain(opponent).build(cfg)],
                     cfg, seed, hands)
    return brain, res


@pytest.mark.parametrize("opponent", ["calling_station", "maniac", "tier1"])
def test_tier4_plays_legal_hands_from_the_blueprint(small_blueprint, opponent) -> None:
    brain, res = _play(small_blueprint, {"cfr_streets": [0, 1, 2, 3]}, opponent)
    assert res.errors == [0, 0] and res.forfeit is None and res.hands_played == 40
    st = brain.stats
    assert st["t4_hits"] > 20 and st["t4_errors"] == 0 and st["t4_miss_state"] == 0


def test_no_cfr_streets_never_uses_the_blueprint(small_blueprint) -> None:
    brain, res = _play(small_blueprint, {"cfr_streets": []})
    assert res.errors == [0, 0]
    assert sum(v for k, v in brain.stats.items() if k.startswith("t4_")) == 0
    assert brain.stats["t3_decisions"] > 0
