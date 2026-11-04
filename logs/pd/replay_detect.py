"""Gate P item 1: replay S0's recordings (seeds 9000-9011) through the posterior, the trait tests and the
real selection (bot/brains/tier4p_select.py), one decision of ours at a time. For each match: share of hands
200-400 played by each member. Needs: right member >= 70 % (base >= 90 % vs random_legal, all_in).

    .venv/bin/python logs/pd/replay_detect.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bot.artifacts import embedded  # noqa: E402
from bot.brains import tier4p_select as S  # noqa: E402
from bot.game.rules_spec import to_rules  # noqa: E402
from bot.state import ME  # noqa: E402
from bot.strategy import types as TY  # noqa: E402
from bot.strategy.traits import TraitTests, classify  # noqa: E402
from lab.harness import load_variant  # noqa: E402
from lab.opps import record  # noqa: E402

RIGHT = {"d_new_exploiter": "anti_folder", "d_conv_opp3": "anti_folder", "d_new_rules": "anti_folder",
         "d_new_minraise": "anti_value", "d_new_trapper": "anti_value",
         "d_new_lag": "anti_aggro", "maniac": "anti_aggro",
         "starter": "base", "calling_station": "base", "tight": "base", "random_legal": "base", "all_in": "base"}
NEED = {"random_legal": 0.90, "all_in": 0.90}


def replay_match(hands: list, library: dict, total: int) -> dict[str, int]:
    tp, tt = TY.TypePosterior(library), TraitTests()
    brain = NS(state=NS(hand=NS(hand_id=0), hands_played=0, bankroll=0, match=NS(hands=total)),
               opponent=NS(types=tp, traits=tt), stats={"p_errors": 0}, locked_decisions=0)
    gs, late = brain.state, {}
    for i, rec in enumerate(hands):
        hs = record.to_hand_state(rec)
        gs.hand, first = NS(hand_id=i), None
        for j, r in enumerate(hs.history):
            if r.actor == ME:
                m = S.choose_member(brain, r.street)
                first = first or m
            ev = classify(hs.history[: j + 1]) if r.actor != ME else None
            if ev is not None:
                tp.observe(ev)
                tt.observe(ev)
        if i >= 200:
            late[first or "base"] = late.get(first or "base", 0) + 1
        gs.hands_played += 1
        gs.bankroll += rec["delta"] or 0
    return late


def main() -> int:
    library = embedded("types", to_rules(load_variant("discard_holdem")))["meta"]
    ok_all = True
    print(f"{'bot':18} {'right':12} {'share 200-400 (mean of matches)':>32} {'min':>6} {'<need':>6} {'matches':>8}  verdict")
    for name, want in RIGHT.items():
        data = record.load(ROOT / "logs/records/s0_9000" / f"{name}.json.gz")
        shares = []
        for pair in data["pairs"]:
            for m in pair["matches"]:
                late = replay_match(m["hands"], library, data["hands_per_match"])
                n = sum(late.values())
                shares.append(late.get(want, 0) / n if n else 0.0)
        need = NEED.get(name, 0.70)
        mean = sum(shares) / len(shares)
        ok = mean >= need
        ok_all &= ok
        print(f"{name:18} {want:12} {mean:32.3f} {min(shares):6.2f} {sum(x < need for x in shares):6} {len(shares):8}  {'PASS' if ok else 'FAIL'} (need {need:.2f})")
    print("ITEM 1:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
