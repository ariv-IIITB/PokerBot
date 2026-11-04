"""PA: tier4p (bot/brains/tier4p.py): Tier 3 + forced members. `base` is Tier 3; each member changes
only its own parameters; a failing member falls back to Tier 3's parameters."""
import pytest

from bot.brains import tier4p as T
from bot.brains.exploit import EXPLOIT_DEFAULTS
from bot.brains.tier3 import Tier3Brain
from bot.brains.tier4p import MEMBER_NAMES, MEMBERS, Tier4PBrain

CHANGES = {   # the parameters each member may touch (everything else must equal base)
    "anti_folder": {"cbet_air_wet", "stab_dry_freq", "stab_wet_freq", "barrel_bluff_prob", "bluff_freq",
                    "river_air_share", "call_margin", "x_bluff_max", "x_river_bluff_mult", "x_vo_cut",
                    "x_vo_margin", "x_vo_min_obs"},
    "anti_value": {"call_margin", "x_vo_margin", "av_raise_fold_eq"},
    "anti_aggro": {"call_margin", "mdf_flop", "mdf_turn", "cbet_air_wet", "stab_dry_freq", "stab_wet_freq",
                   "barrel_bluff_prob", "bluff_freq", "river_air_share"},
}


def _cfg(member: str, **kw) -> dict:
    return {"member": member, "lock_enabled": False, **kw}


def test_registry_and_locks() -> None:
    from bot.main import BRAINS
    from lab.eval import LOCK_BRAINS, parse_brain
    assert BRAINS["tier4p"].endswith("Tier4PBrain") and "tier4p" in LOCK_BRAINS
    assert dict(parse_brain('tier4p:{"member":"anti_folder"}', "off").config)["lock_enabled"] is False


def test_four_members_with_numbers() -> None:
    assert set(MEMBER_NAMES) == set(MEMBERS) == {"base", "anti_folder", "anti_value", "anti_aggro"}


def test_auto_stub_selects_base() -> None:
    b = Tier4PBrain(config={"lock_enabled": False})
    assert b.choose_member(2) == "base"
    t3 = Tier3Brain(config={"lock_enabled": False})
    assert all(b.adjusted(3)[k] == v for k, v in t3.adjusted(3).items())


@pytest.mark.parametrize("street", range(4))
def test_base_member_has_tier3s_parameters(street: int) -> None:
    t3, t4 = Tier3Brain(config={"lock_enabled": False}), Tier4PBrain(config=_cfg("base"))
    a, b = t3.adjusted(street), t4.adjusted(street)
    assert all(b[k] == v for k, v in a.items())


@pytest.mark.parametrize("member", sorted(CHANGES))
@pytest.mark.parametrize("street", range(4))
def test_member_changes_only_its_own_params(member: str, street: int) -> None:
    base = Tier4PBrain(config=_cfg("base")).adjusted(street)
    q = Tier4PBrain(config=_cfg(member)).adjusted(street)
    changed = {k for k in set(base) | set(q) if base.get(k) != q.get(k)} - {"member"}
    assert changed <= CHANGES[member], changed - CHANGES[member]
    assert changed, "a forced member must move something"


def test_anti_aggro_directions() -> None:
    base = Tier4PBrain(config=_cfg("base")).adjusted(3)
    q = Tier4PBrain(config=_cfg("anti_aggro")).adjusted(3)
    assert q["call_margin"] < base["call_margin"] and q["bluff_freq"] < base["bluff_freq"]
    assert q["mdf_flop"] >= base["mdf_flop"] and q["river_air_share"] > base["river_air_share"]


def test_anti_folder_bluffs_more_and_value_only_move_needs_low_bluff_share() -> None:
    base = Tier4PBrain(config=_cfg("base")).adjusted(3)
    q = Tier4PBrain(config=_cfg("anti_folder")).adjusted(3)
    assert q["cbet_air_wet"] > base["cbet_air_wet"] and q["river_air_share"] < base["river_air_share"]
    assert q["call_margin"] == base["call_margin"]               # no posterior evidence: no value-only move

    class Types:                                                  # 100 observations, all "value-only" types
        n = 100
        slow = [{"river_bluff": 0.05}, {"river_bluff": 0.23}, {}]
        def posterior(self): return {"a": 0.9, "b": 0.1, "unknown": 0.0}
    assert T.implied_river_bluff_share(Types()) == pytest.approx(0.9 * 0.05 + 0.1 * 0.23)
    lo = T.apply_member("anti_folder", base, 3, Types())
    assert lo["call_margin"] == pytest.approx(base["call_margin"] + EXPLOIT_DEFAULTS["x_vo_margin"])
    Types.slow = [{"river_bluff": 0.23}, {"river_bluff": 0.23}, {}]
    hi = T.apply_member("anti_folder", base, 3, Types())
    assert hi["call_margin"] == base["call_margin"]               # conv_opp3-like: 0.23 > 0.10
    assert T.apply_member("anti_folder", base, 2, Types())["call_margin"] == base["call_margin"]


def test_partial_overrides_through_members_param() -> None:
    b = Tier4PBrain(config=_cfg("anti_aggro", members={"anti_aggro": {"aa_call_margin": -0.1}}))
    base = Tier4PBrain(config=_cfg("base")).adjusted(3)
    assert b.adjusted(3)["call_margin"] == pytest.approx(base["call_margin"] - 0.1)
    assert b.adjusted(3)["bluff_freq"] == pytest.approx(base["bluff_freq"] * T.MEMBERS["anti_aggro"]["aa_bluff_mult"])


def test_member_error_falls_back_to_tier3(monkeypatch) -> None:
    b = Tier4PBrain(config=_cfg("anti_aggro"))
    base = Tier3Brain(config={"lock_enabled": False}).adjusted(3)
    monkeypatch.setattr(T, "apply_member", lambda *a, **k: 1 / 0)
    q = b.adjusted(3)
    assert all(q[k] == v for k, v in base.items()) and b.stats["p_errors"] == 1


def test_selection_error_falls_back_to_base(monkeypatch) -> None:
    import bot.brains.tier4p_select as sel
    monkeypatch.setattr(sel, "choose_member", lambda *a: 1 / 0)
    b = Tier4PBrain(config={"lock_enabled": False})
    assert b.choose_member(1) == "base" and b.stats["p_errors"] == 1


@pytest.mark.parametrize("member", MEMBER_NAMES)
def test_plays_legal_matches_and_counts_hands(member: str) -> None:
    from lab.engine import play_match
    from lab.harness import load_variant
    from lab.players import InProcessPlayer, PlayerSpec
    cfg = load_variant("discard_holdem")
    brain = Tier4PBrain(config=_cfg(member))
    res = play_match([InProcessPlayer(brain, "tier4p"), PlayerSpec.brain("maniac").build(cfg)], cfg, 5, 60)
    assert res.errors == [0, 0] and res.forfeit is None and brain.stats["p_errors"] == 0
    assert brain.stats[f"hands_{member}"] > 0 and sum(brain.stats[f"hands_{m}"] for m in MEMBER_NAMES) \
        == brain.stats[f"hands_{member}"]


def test_anti_value_folds_medium_hand_to_a_raise(monkeypatch) -> None:
    from bot.actions import FOLD, Action
    from bot.state import ME, OPP, ActionRecord
    monkeypatch.setattr(Tier3Brain, "_facing_bet", lambda self, c, s, legal, p: "tier3")
    b = Tier4PBrain(config=_cfg("anti_value"))

    class H: history = [ActionRecord(1, ME, Action.raise_to(40)), ActionRecord(1, OPP, Action.raise_to(120))]
    class C: hand, street, eq = H(), 1, 0.45
    class L: fold = True
    p = {"av_raise_fold_eq": 0.6}
    assert b._facing_bet(C(), None, L(), p).kind == FOLD and b.stats["p_raise_folds"] == 1
    C.eq = 0.8                                                    # strong hand: Tier 3 decides
    assert b._facing_bet(C(), None, L(), p) == "tier3"
    C.eq = 0.45
    H.history = [ActionRecord(1, OPP, Action.raise_to(40))]       # we had not acted: not a re-raise
    assert b._facing_bet(C(), None, L(), p) == "tier3"
    H.history = [ActionRecord(1, ME, Action.raise_to(40)), ActionRecord(1, OPP, Action.raise_to(120))]
    assert b._facing_bet(C(), None, L(), {"av_raise_fold_eq": 0.0}) == "tier3"   # off by default
