"""trapper2 (VAL1 exploit-back adversary): a scripted TRAPPER. With strong hands it checks when first to act and
check-RAISES (to ~3x) when the opponent bets; after the opponent checks behind it fires 2/3 pot. With a medium hand it
checks/calls small bets and folds to big ones; with air it folds to bets and bluffs 25% when checked to.
It is the player a value-betting bot should be punished by: one who slow-plays and raises our bets.
Self-contained (stdlib only); real protocol."""
import sys, json, random, itertools
from collections import Counter
R = "23456789TJQKA"
rng = random.Random(7)


def v(c):
    return R.index(c[0])


def score5(cs):
    vs = sorted((v(c) for c in cs), reverse=True)
    cnt = Counter(vs)
    groups = sorted(cnt.items(), key=lambda kv: (-kv[1], -kv[0]))
    flush = len({c[1] for c in cs}) == 1
    uniq = sorted(set(vs), reverse=True)
    straight = len(uniq) == 5 and uniq[0] - uniq[4] == 4
    if uniq == [12, 3, 2, 1, 0]:
        straight, vs = True, [3, 2, 1, 0, -1]
    shape = tuple(c for _, c in groups)
    ranks = tuple(k for k, _ in groups)
    if straight and flush: cat = 8
    elif shape == (4, 1): cat = 7
    elif shape == (3, 2): cat = 6
    elif flush: cat = 5
    elif straight: cat = 4
    elif shape == (3, 1, 1): cat = 3
    elif shape == (2, 2, 1): cat = 2
    elif shape == (2, 1, 1, 1): cat = 1
    else: cat = 0
    return (cat, ranks)


def best(cards):
    if len(cards) < 5:
        return (0, tuple(sorted((v(c) for c in cards), reverse=True)))
    return max(score5(c) for c in itertools.combinations(cards, 5))


def strength(hole, board):
    """0 air, 1 medium, 2 strong."""
    if len(board) < 3:
        return 1
    cat, ranks = best(list(hole) + list(board))
    bmax = max(v(c) for c in board)
    if cat >= 2:
        return 2
    if cat == 1:
        top = ranks[0]
        return 2 if top >= bmax and top >= 9 and any(v(c) == top for c in hole) else 1
    return 0


def clamp(x, req):
    return int(max(req["min_raise"], min(req["max_raise"], x)))


def act(req):
    legal = req["legal_actions"]
    st = req["street"]
    hole = req.get("hole_cards") or HOLE[0]
    board = req["board"]
    pot, tc = req["pot"], req["to_call"]
    can_raise = "raise" in legal and req.get("raises_left", 1) > 0
    if st == "preflop":
        a, b = sorted((v(c) for c in hole), reverse=True)[:2]
        pair = v(hole[0]) == v(hole[1])
        if can_raise and (pair and a >= 8 or a >= 11 and b >= 10) and rng.random() < 0.7:
            return {"type": "action", "action": "raise", "amount": clamp(req["opp_bet"] * 3, req)}
        if tc > 0 and a < 7 and tc > 2:
            return {"type": "action", "action": "fold"}
        return {"type": "action", "action": "call" if tc > 0 else "check"}
    s = strength(hole, board)
    hist = req.get("history") or []
    opp_checked = any(e.get("street") == st and e.get("actor") == "opp" and e.get("action") == "check" for e in hist)
    if tc == 0:
        if s == 2:
            if opp_checked and can_raise:
                return {"type": "action", "action": "raise", "amount": clamp(pot * 2 // 3, req)}
            return {"type": "action", "action": "check"}                       # the trap
        if s == 0 and opp_checked and can_raise and rng.random() < 0.25:
            return {"type": "action", "action": "raise", "amount": clamp(pot // 2, req)}
        return {"type": "action", "action": "check"}
    frac = tc / max(pot - tc, 1)
    if s == 2:
        if can_raise and rng.random() < 0.8:
            return {"type": "action", "action": "raise", "amount": clamp(req["opp_bet"] * 3, req)}
        return {"type": "action", "action": "call"}
    if s == 1 and frac <= 0.75:
        return {"type": "action", "action": "call"}
    return {"type": "action", "action": "fold"}


def disc(req):
    hole, board = req["hole_cards"], req["board"]
    bestk, bi = None, 0
    for i in range(3):
        keep = [c for j, c in enumerate(hole) if j != i]
        sc = best(keep + board)
        k = (sc, sorted((v(c) for c in keep), reverse=True))
        if bestk is None or k > bestk:
            bestk, bi = k, i
    HOLE[0] = [c for j, c in enumerate(hole) if j != bi]
    return {"type": "discard", "card": hole[bi]}


HOLE = [None]


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        t = msg.get("type")
        if t == "action_request":
            try:
                reply = act(msg)
                if reply["action"] == "check" and "check" not in msg["legal_actions"]:
                    reply = {"type": "action", "action": "call"}
                if reply["action"] == "raise" and "raise" not in msg["legal_actions"]:
                    reply = {"type": "action", "action": "call" if "call" in msg["legal_actions"] else "check"}
            except Exception:
                reply = {"type": "action", "action": "check" if "check" in msg["legal_actions"] else "call"}
        elif t == "discard_request":
            reply = disc(msg)
        elif t == "discard_result":
            HOLE[0] = msg.get("hole_cards")
            continue
        elif t == "new_hand":
            HOLE[0] = msg.get("hole_cards") or msg.get("my_hole_cards")
            continue
        elif t == "match_end":
            break
        else:
            continue
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
