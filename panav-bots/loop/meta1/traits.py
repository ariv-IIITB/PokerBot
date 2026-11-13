"""META1: opponent trait counts from file_duel leg logs (hand_result lines), restricted to the first N hands of a leg.
Everything here is observable by the bot (own actions + opponent actions + showdown cards).
  PYTHONPATH=. .venv/bin/python panav-bots/loop/meta1/traits.py LOGDIR N  -> prints pooled features
`legs(logdir, N)` -> list of per-leg count dicts; `pooled(legs)` -> feature dict (rates)."""
import json, sys
from pathlib import Path
sys.path.insert(0, "panav-bots/loop/tools")
from cf_replay import rules
from bot.cards import parse_card

BIG = 0.7
KEYS = ["fb_flop", "fb_turn", "fb_river", "fb_all",      # first-in bet: (bets, chances)
        "fold_flop", "fold_turn", "fold_river", "fold_all",   # opp fold when facing OUR bet
        "raise_fb",                                       # opp raise when facing our bet
        "big_share",                                      # opp bets/raises that are >= 0.7 pot (num), all opp bets (den)
        "pre_open", "pre_fold_open", "pre_fold_vs_raise", "pre_3bet",
        "xr",                                             # check-raise: opp raises after checking into our bet (num), opp checks then faces a bet (den)
        "sd_value", "sd_big_value", "sd_weak"]            # showdown evidence: opp beats us when it bet / bet big; opp bet but hand < pair of 8s... (see code)


def _eval(theirs, mine, board):
    ev = rules().evaluator
    t = [parse_card(c) for c in theirs]; m = [parse_card(c) for c in mine]; b = [parse_card(c) for c in board]
    a, c = ev.evaluate(t, b), ev.evaluate(m, b)
    return a, c


def _hand(hr, seat, cnt):
    hist = hr["history"]
    # preflop commits: button posts 1, big blind 2
    commit = {"me": 1 if seat == "button" else 2, "opp": 2 if seat == "button" else 1}
    pot_prev = 0
    street = "preflop"
    bets_opp = []         # (street, big?)
    opp_bet_streets = set()
    first_in_seen = {}
    st_hist = []
    for k, e in enumerate(hist):
        if e["street"] != street:
            pot_prev += commit["me"] + commit["opp"]
            commit = {"me": 0, "opp": 0}
            street = e["street"]
            st_hist = []
        a, who = e["action"], e["actor"]
        oth = "opp" if who == "me" else "me"
        pot_before = pot_prev + commit["me"] + commit["opp"]
        facing = commit[oth] - commit[who]      # chips to call
        prior = [x for x in st_hist]            # earlier actions this street
        aggressor_before = any(x[1] == "raise" for x in prior)
        if street != "preflop":
            if who == "opp":
                if facing == 0:                  # first-in or after our check: a bet chance
                    cnt["fb_all"][1] += 1; cnt["fb_" + street][1] += 1
                    if a == "raise":
                        cnt["fb_all"][0] += 1; cnt["fb_" + street][0] += 1
                else:                            # facing a bet of ours (or ours raised over theirs)
                    last = prior[-1] if prior else None
                    if last and last[0] == "me" and last[1] == "raise":
                        cnt["fold_all"][1] += 1; cnt["fold_" + street][1] += 1
                        cnt["fold_all"][0] += a == "fold"; cnt["fold_" + street][0] += a == "fold"
                        cnt["raise_fb"][1] += 1; cnt["raise_fb"][0] += a == "raise"
                        if len(prior) >= 2 and prior[0] == ("opp", "check"):
                            cnt["xr"][1] += 1; cnt["xr"][0] += a == "raise"
                if a == "raise":
                    inc = e["amount"] - commit["me"]
                    frac = inc / max(1, pot_before + max(0, commit["me"] - commit["opp"]))
                    bets_opp.append(frac >= BIG); opp_bet_streets.add(street)
                    cnt["big_share"][1] += 1; cnt["big_share"][0] += frac >= BIG
        else:
            pass
        st_hist.append((who, a))
        commit[who] = e.get("amount", commit[who]) if a in ("raise", "call") else commit[who]
    # preflop features from the first actions
    pre = [e for e in hist if e["street"] == "preflop"]
    if pre:
        if seat == "big_blind":                   # opp is the button: first to act
            cnt["pre_open"][1] += 1; cnt["pre_open"][0] += pre[0]["action"] == "raise"
            cnt["pre_fold_open"][1] += 1; cnt["pre_fold_open"][0] += pre[0]["action"] == "fold"
        if seat == "button" and pre[0]["actor"] == "me" and pre[0]["action"] == "raise" and len(pre) > 1:
            cnt["pre_fold_vs_raise"][1] += 1; cnt["pre_fold_vs_raise"][0] += pre[1]["action"] == "fold"
            if pre[1]["action"] != "fold":
                cnt["pre_3bet"][1] += 1; cnt["pre_3bet"][0] += pre[1]["action"] == "raise"
    if hr.get("opp_hole_cards") and len(hr["board"]) == 5 and bets_opp and hr["my_hole_cards"]:
        a, c = _eval(hr["opp_hole_cards"], hr["my_hole_cards"], hr["board"])
        w = 1.0 if a > c else 0.5 if a == c else 0.0
        cnt["sd_value"][1] += 1; cnt["sd_value"][0] += w
        if any(bets_opp):
            cnt["sd_big_value"][1] += 1; cnt["sd_big_value"][0] += w


def legs(logdir, N):
    out = []
    for f in sorted(Path(logdir).glob("seed*_m*.jsonl")):
        cnt = {k: [0.0, 0] for k in KEYS}
        seat = None
        for line in open(f):
            if not line.startswith('{"type":"new_hand"') and not line.startswith('{"type":"hand_result"'):
                continue
            d = json.loads(line)
            if d["type"] == "new_hand":
                seat = d["seat"]; continue
            if d["hand_id"] > N: break
            _hand(d, seat, cnt)
        out.append(cnt)
    return out


def pooled(ls):
    tot = {k: [0.0, 0] for k in KEYS}
    for c in ls:
        for k in KEYS:
            tot[k][0] += c[k][0]; tot[k][1] += c[k][1]
    return {k: (v[0] / v[1] if v[1] else float("nan")) for k, v in tot.items()}, {k: v[1] for k, v in tot.items()}


if __name__ == "__main__":
    ls = legs(sys.argv[1], int(sys.argv[2]))
    r, n = pooled(ls)
    for k in KEYS:
        print(f"{k:18s} {r[k]:.3f}  (n={n[k]})")
