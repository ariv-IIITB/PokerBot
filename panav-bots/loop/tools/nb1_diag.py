"""NB1 diagnostics from file_duel logs: marginal EV of our calls of opp bets (by street, size), our bets that were
called / folded to, opp bluff index at showdown.  usage: nb1_diag.py DIR [DIR...]"""
import json, sys, collections
from pathlib import Path

ST = ["preflop", "flop", "turn", "river"]
def hands(dirs):
    for d in dirs:
        for f in sorted(Path(d).glob("*.jsonl")):
            seat = None
            for line in f.read_text().splitlines():
                m = json.loads(line)
                if m["type"] == "new_hand": seat = m["seat"]
                elif m["type"] == "hand_result":
                    m["seat"] = seat; yield m

def bucket(x):
    return "<.4" if x < .4 else "<.7" if x < .7 else "<1.1" if x < 1.1 else ">=1.1"

def walk(h):
    """yield events: dict(street, actor, action, facing_frac, pot_before_action, my_inv_before, opp_inv_before)"""
    prev = 0; lv = {"me": 0, "opp": 0}; cur = None
    inv = {"me": 0, "opp": 0}      # chips in from closed streets
    blinds = {"button": (1, 2), "big_blind": (2, 1)}
    sb_me = 1 if h["seat"] == "button" else 2
    lv = {"me": sb_me, "opp": 3 - sb_me}
    street = "preflop"
    out = []
    for a in h["history"]:
        if a["street"] != street:
            inv["me"] += lv["me"]; inv["opp"] += lv["opp"]; lv = {"me": 0, "opp": 0}; street = a["street"]
        who = a["actor"]; oth = "opp" if who == "me" else "me"
        pot = inv["me"] + inv["opp"] + lv["me"] + lv["opp"]
        to_call = lv[oth] - lv[who]
        ev = dict(street=street, actor=who, action=a["action"], to_call=to_call, pot=pot,
                  frac=(to_call / max(pot - to_call, 1)) if to_call > 0 else 0.0,
                  inv=inv[who] + lv[who], oinv=inv[oth] + lv[oth])
        if a["action"] in ("raise", "call"):
            lv[who] = a["amount"]
        ev["bet"] = (a["amount"] - lv[oth]) if a["action"] == "raise" else 0
        ev["betfrac"] = (a["amount"] - lv[oth]) / max(pot, 1) if a["action"] == "raise" else 0
        out.append(ev)
    return out

def main():
    ds = [a for a in sys.argv[1:] if not a.startswith("--")]
    callEV = collections.defaultdict(lambda: [0, 0, 0, 0])   # key -> n, sum marginal, wins, losses
    foldN = collections.defaultdict(lambda: [0, 0])          # we fold to its bet: n, chips saved vs call? (just n, chips lost)
    ourbet = collections.defaultdict(lambda: [0, 0, 0, 0, 0]) # our bet/raise: n, opp fold, called->net sum, called n, called we win
    oppagg_sd = collections.defaultdict(lambda: [0, 0, 0])   # opp last-aggressor showdown: n, we win, net
    nhands = 0
    for h in hands(ds):
        nhands += 1
        ev = walk(h); net = h["net"]
        sd = h["result"] in ("showdown", "win", "loss", "tie", "split") or h.get("opp_hole_cards")
        # who aggressed last
        aggs = [e for e in ev if e["action"] == "raise"]
        for i, e in enumerate(ev):
            if e["actor"] == "me" and e["to_call"] > 0 and e["action"] in ("call", "raise"):
                k = (e["street"], bucket(e["frac"]))
                c = callEV[k]; c[0] += 1; c[1] += net + e["inv"]
                if h["result"] != "fold" or True:
                    c[2] += net > 0; c[3] += net < 0
            if e["actor"] == "me" and e["to_call"] > 0 and e["action"] == "fold":
                foldN[(e["street"], bucket(e["frac"]))][0] += 1
            if e["actor"] == "me" and e["action"] == "raise" and e["to_call"] == 0:
                nxt = ev[i + 1] if i + 1 < len(ev) else None
                k = e["street"]; o = ourbet[k]; o[0] += 1
                if nxt and nxt["actor"] == "opp" and nxt["action"] == "fold": o[1] += 1
                else:
                    o[3] += 1; o[2] += net + e["inv"]; o[4] += net > 0
        if h.get("opp_hole_cards") and aggs:
            last = aggs[-1]
            if last["actor"] == "opp":
                k = (last["street"], bucket(last["betfrac"]))
                o = oppagg_sd[k]; o[0] += 1; o[1] += net > 0; o[2] += net
    print("hands", nhands)
    print("\nOUR CALLS/RAISES facing a bet: street, size(frac of pot before bet) -> n, marginal EV vs folding (sum, per), win%, lose%; and #folds")
    for k in sorted(callEV, key=lambda k: (ST.index(k[0]), k[1])):
        n, s, w, l = callEV[k]
        print(f" {k[0]:8s}{k[1]:6s} n={n:5d} sumEV={s:8d} per={s/n:6.1f} win={w/n:.2f} lose={l/n:.2f}  folds={foldN[k][0]}")
    print("\nOUR first-in BETS: street -> n, opp-fold%, when called: n, mean EV vs check-down(net+inv), win%")
    for k in ST:
        if k in ourbet:
            n, f, s, cn, cw = ourbet[k]
            print(f" {k:8s} n={n:5d} oppfold={f/max(n,1):.2f} called n={cn} sumEV={s} per={s/max(cn,1):.1f} win={cw/max(cn,1):.2f}")
    print("\nSHOWDOWNS where opp made last bet/raise: street,size -> n, we-win%, our net sum")
    for k in sorted(oppagg_sd, key=lambda k: (ST.index(k[0]), k[1])):
        n, w, s = oppagg_sd[k]
        print(f" {k[0]:8s}{k[1]:6s} n={n:4d} wewin={w/n:.2f} net={s}")
if "--rates" not in sys.argv: main()

def rates(dirs):
    """opp bet-size mix when first to bet (not facing bet), per street; big=>=0.7 pot"""
    import collections
    c = collections.defaultdict(lambda: [0, 0, 0])
    for h in hands(dirs):
        for e in walk(h):
            if e["actor"] == "opp" and e["street"] != "preflop" and e["to_call"] == 0 and e["pot"] > 0:
                pass
        ev = walk(h)
        for e in ev:
            if e["actor"] == "opp" and e["street"] != "preflop" and e["to_call"] == 0:
                c[e["street"]][0] += 1
                if e["action"] == "raise":
                    c[e["street"]][1] += 1
                    if e["betfrac"] >= 0.7: c[e["street"]][2] += 1
    for s, (n, b, big) in c.items():
        print(f"opp {s}: decisions-not-facing-bet n={n} bet={b/n:.2f} big(>=.7)={big/n:.2f}")
if "--rates" in sys.argv: rates([a for a in sys.argv[1:] if not a.startswith("--")])
