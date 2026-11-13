"""Scripted exploit-back adversary (stdlib only). Hands 0-99 ("loose" phase): calls/raises preflop wide, bets ~45% when first
to act and otherwise checks, and FOLDS 75% to any bet after it has checked (feeds a "folds-after-checking" read).
From hand 100 on ("tight-value" phase): checks every first-in decision (traps), then raises hard (check-raise, 3x) when it
has a pair or better, calls with a decent pair, and folds air; bets only with pair+ when it bets at all. Legal replies only."""
import sys, json, random
R = "23456789TJQKA"
rng = random.Random(7)
hand = -1

def pairish(req):
    hole = [c[0] for c in req.get("hole_cards", [])]
    board = [c[0] for c in req.get("board", [])]
    allr = hole + board
    cnt = max((allr.count(r) for r in set(allr)), default=0)
    top = max((R.index(r) for r in hole), default=0)
    return cnt, top

def rz(req, amt):
    if "raise" in req["legal_actions"]:
        return {"type": "action", "action": "raise", "amount": int(max(req["min_raise"], min(req["max_raise"], amt)))}
    return None

def act(req):
    L = req["legal_actions"]; tc = req.get("to_call", 0); pot = req.get("pot", 0)
    cnt, top = pairish(req); pre = req["street"] == "preflop"
    loose = hand < 100
    chk = "check" in L
    hist = [e for e in req.get("history", []) if e.get("street") == req["street"]]
    i_checked = any(e.get("actor") == "me" and e.get("action") == "check" for e in hist)
    if loose:
        if pre:
            r = rng.random()
            if tc > 0 and r < 0.15: return {"type": "action", "action": "fold"} if "fold" in L else {"type": "action", "action": "call"}
            a = rz(req, req.get("opp_bet", 0) + max(4, pot)) if r > 0.6 else None
            return a or {"type": "action", "action": "check" if chk else "call"}
        if tc == 0:
            a = rz(req, req.get("opp_bet", 0) + int(0.7 * max(pot, 2))) if rng.random() < 0.45 else None
            return a or {"type": "action", "action": "check"}
        if i_checked and rng.random() < 0.75 and "fold" in L: return {"type": "action", "action": "fold"}
        return {"type": "action", "action": "call"}
    strong = cnt >= 2 and (not pre) ; mid = cnt >= 2 or top >= 10
    if pre:
        if tc > 0 and not mid and "fold" in L and rng.random() < 0.5: return {"type": "action", "action": "fold"}
        a = rz(req, req.get("opp_bet", 0) + max(4, pot)) if (cnt >= 2 or top >= 12) else None
        return a or {"type": "action", "action": "check" if chk else "call"}
    if tc == 0:
        return {"type": "action", "action": "check"}                 # trap: never leads
    if cnt >= 3 or (cnt == 2 and i_checked):
        a = rz(req, req.get("opp_bet", 0) + 3 * tc + pot)            # check-raise
        if a: return a
    if cnt >= 2 and "call" in L: return {"type": "action", "action": "call"}
    return {"type": "action", "action": "fold" if "fold" in L else "call"}

def disc(req):
    c = req["hole_cards"]
    return {"type": "discard", "card": min(c, key=lambda x: R.index(x[0]))}

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try: m = json.loads(line)
    except ValueError: continue
    t = m.get("type")
    if t == "new_hand": hand += 1; continue
    if t == "action_request": out = act(m)
    elif t == "discard_request": out = disc(m)
    elif t == "match_end": break
    else: continue
    print(json.dumps(out), flush=True)
