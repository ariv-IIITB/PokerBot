"""Tier 4P: Tier 3 with a portfolio of members, each a set of parameter overrides for one opponent
family (docs/TIER4_PLAN.md, P1). Members are pure functions over `adjusted()`'s parameter dict, the
same mechanism as bot/brains/exploit.py. With `member: "base"` it plays exactly like Tier 3.

  base         Tier 3 unchanged.
  anti_folder  over-folder: the over-folder move at full strength, plus the value-only move when the
               posterior's implied river bluff share is <= x_vo_cut (what tier3x does at lambda = 1).
  anti_value   value-only bettor / trapper: the value-only move at full strength, and fold medium hands
               to a raise on a street where we had already acted (`av_raise_fold_eq`).
  anti_aggro   aggressor: call down wider (lower call margin, higher MDF share), bluff less.

`member` (default "auto") forces one member: `tier4p:{"member": "anti_folder"}`. In "auto",
bot/brains/tier4p_select.choose_member decides. Numbers live in MEMBERS (one dict per member); the
`members` parameter holds partial overrides per member, e.g. `tier4p:{"members": {"anti_aggro":
{"aa_call_margin": -0.04}}}`. Any error in a member -> Tier 3's parameters for that decision.
"""
from __future__ import annotations

from typing import Any, Optional

from bot.actions import RAISE, Action
from bot.brains.exploit import EXPLOIT_DEFAULTS, apply_overfolder, apply_valueonly
from bot.brains.tier3 import Tier3Brain
from bot.log import warn
from bot.state import ME, OPP

MEMBER_NAMES = ("base", "anti_folder", "anti_value", "anti_aggro")

# Every member's numbers. Keys of the x_* family are exploit.py's parameters; the others are new.
MEMBERS: dict[str, dict[str, Any]] = {
    "base": {},
    "anti_folder": {
        "x_bluff_max": 0.60,           # pure-bluff frequencies move to this
        "x_river_bluff_mult": 2.5,     # river bluffs x this
        "x_vo_cut": 0.10,              # value-only move only if the implied river bluff share is <= this
        "x_vo_margin": 0.12,           # extra equity to call a river bet
        "x_vo_min_obs": 60,
    },
    "anti_value": {
        "x_vo_margin": 0.12,
        "av_raise_fold_eq": 0.80,      # fold below this equity to a raise on a street we had acted on (0 = off)
    },
    "anti_aggro": {
        "aa_call_margin": -0.03,       # added to call_margin on every street
        "aa_mdf_mult": 1.00,           # x mdf_flop / mdf_turn (capped at 1.0)
        "aa_bluff_mult": 0.75,         # x pure-bluff frequencies; river_air_share / this
    },
}
BLUFF_PARAMS = ("cbet_air_wet", "stab_dry_freq", "stab_wet_freq", "barrel_bluff_prob", "bluff_freq")


def member_numbers(name: str, overrides: Optional[dict]) -> dict[str, Any]:
    """The member's numbers: MEMBERS[name] with the partial overrides from the `members` parameter."""
    d = dict(MEMBERS.get(name, {}))
    if isinstance(overrides, dict) and isinstance(overrides.get(name), dict):
        d.update(overrides[name])
    return d


def implied_river_bluff_share(types) -> Optional[float]:
    """Posterior-weighted river bluff share of the known types (None with no evidence)."""
    if types is None or types.n == 0:
        return None
    post = types.posterior()
    num = den = 0.0
    for name, x, slow in zip(post, post.values(), types.slow):
        if name != "unknown":
            num += x * float(slow.get("river_bluff", 1.0))
            den += x
    return num / den if den > 1e-9 else None


def apply_member(name: str, p: dict, street: int, types=None, overrides: Optional[dict] = None) -> dict:
    """Parameters for member `name` (a new dict; `p` is not modified)."""
    if name == "base" or name not in MEMBERS:
        return p
    m = member_numbers(name, overrides)
    q = dict(p)
    if name == "anti_folder":
        q.update({k: m[k] for k in ("x_bluff_max", "x_river_bluff_mult", "x_vo_cut", "x_vo_margin") if k in m})
        apply_overfolder(q, 1.0)
        share = implied_river_bluff_share(types)
        if share is not None and share <= float(m["x_vo_cut"]):
            n = types.n if types is not None else 0
            apply_valueonly(q, street, min(1.0, n / max(1.0, float(m["x_vo_min_obs"]))))
    elif name == "anti_value":
        q["x_vo_margin"] = m["x_vo_margin"]
        apply_valueonly(q, street, 1.0)
        q["av_raise_fold_eq"] = float(m["av_raise_fold_eq"])
    elif name == "anti_aggro":
        q["call_margin"] = float(q["call_margin"]) + float(m["aa_call_margin"])
        for k in ("mdf_flop", "mdf_turn"):
            if k in q:
                q[k] = min(1.0, float(q[k]) * float(m["aa_mdf_mult"]))
        bm = max(1e-6, float(m["aa_bluff_mult"]))
        for k in BLUFF_PARAMS:
            if k in q:
                q[k] = float(q[k]) * bm
        if "river_air_share" in q:
            q["river_air_share"] = float(q["river_air_share"]) / bm
    return q


class Tier4PBrain(Tier3Brain):
    name = "tier4p"
    param_file = "tier3"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.stats.update({"p_errors": 0, "p_raise_folds": 0})
        for m in MEMBER_NAMES:
            self.stats[f"hands_{m}"] = 0
            self.stats[f"decisions_{m}"] = 0
        self._counted_hand: Any = object()

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier3Brain.defaults()
        d.update({k: v for k, v in EXPLOIT_DEFAULTS.items() if k not in d})
        d.update({"member": "auto", "members": {}, "av_raise_fold_eq": 0.0})
        return d

    def choose_member(self, street: int) -> str:
        forced = self.p.get("member", "auto")
        if forced != "auto":
            return forced if forced in MEMBER_NAMES else "base"
        try:
            from bot.brains.tier4p_select import choose_member
            name = choose_member(self, street)
            return name if name in MEMBER_NAMES else "base"
        except Exception as e:
            self.stats["p_errors"] += 1
            warn(f"tier4p selection failed: {e!r}")
            return "base"

    def adjusted(self, street: int = 0) -> dict[str, Any]:
        p = super().adjusted(street)
        member = "base"
        try:
            member = self.choose_member(street)
            q = apply_member(member, p, street, self.opponent.types, self.p.get("members"))
        except Exception as e:                    # a member must never cost a hand: Tier 3's params
            self.stats["p_errors"] += 1
            warn(f"tier4p member {member} failed: {e!r}")
            member, q = "base", p
        self.stats[f"decisions_{member}"] += 1
        hid = self._hand_id
        if hid != self._counted_hand:
            self._counted_hand = hid
            self.stats[f"hands_{member}"] += 1
        return q

    def _facing_bet(self, c, s, legal, p) -> Optional[Action]:
        """anti_value: fold a medium hand to a raise on a street where we had already acted."""
        thr = float(p.get("av_raise_fold_eq", 0.0) or 0.0)
        if thr > 0.0 and legal.fold and c.eq < thr:
            try:
                acts = [r for r in c.hand.history if r.street == c.street]
                mine = any(r.actor == ME for r in acts)
                theirs_raise = any(r.actor == OPP and r.action.kind == RAISE for r in acts)
                if mine and theirs_raise:
                    self.stats["p_raise_folds"] += 1
                    return Action.fold()
            except Exception as e:
                self.stats["p_errors"] += 1
                warn(f"tier4p raise-fold failed: {e!r}")
        return super()._facing_bet(c, s, legal, p)
