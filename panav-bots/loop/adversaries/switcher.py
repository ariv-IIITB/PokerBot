"""L2 exploit-back adversary (stdlib only): for the first SWITCH hands it bets ~75% of its free postflop decisions at ~1.4x pot
(a frequent large bettor, so a 'bettor' trait test says yes); after that it turns tight-value: it bets (pot size) only with a
made pair of tens or better / trips+ and otherwise checks, and it folds weak hands to bets. Tests that a defend move does not
keep calling a style that has changed. Real protocol: JSON lines. Strength is a crude rank-count heuristic."""
import sys, json, random

RANKS = "23456789TJQKA"
SWITCH = 100
rng = random.Random(5)
state = {"hand": 0, "hole": []}


def strength(hole, board):
    ranks = [RANKS.index(c[0]) for c in hole + board]
    cnt = {}
    for r in ranks:
        cnt[r] = cnt.get(r, 0) + 1
    suits = {}
    for c in hole + board:
        suits[c[1]] = suits.get(c[1], 0) + 1
    best = max(cnt.values())
    top_pair = any(cnt[RANKS.index(c[0])] >= 2 and RANKS.index(c[0]) >= 8 for c in hole)
    if best >= 3 or max(suits.values()) >= 5:
        return 3
    if top_pair or sum(1 for v in cnt.values() if v >= 2) >= 2:
        return 2
    if best >= 2:
        return 1
    return 0


def act(req):
    legal = req["legal_actions"]
    board, pot, to_call = req["board"], req["pot"], req["to_call"]
    wide = state["hand"] <= SWITCH
    s = strength(state["hole"], board) if board else 1
    def bet(frac):
        amt = max(req["min_raise"], int(req["my_bet"] + req["to_call"] + frac * (pot + to_call)))
        amt = min(amt, req["max_raise"])
        return {"type": "action", "action": "raise", "amount": amt}
    if to_call == 0:
        if "raise" in legal and ((wide and rng.random() < 0.75) or (not wide and s >= 2)):
            return bet(1.4 if wide else 1.0)
        return {"type": "action", "action": "check"}
    if not board:
        return {"type": "action", "action": "call"}
    if s >= 1 or (wide and rng.random() < 0.6):
        return {"type": "action", "action": "call"}
    return {"type": "action", "action": "fold"}


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
        if t == "new_hand":
            state["hand"] = msg["hand_id"]; state["hole"] = list(msg["hole_cards"])
        elif t == "discard_request":
            h = msg["hole_cards"]
            keep = sorted(h, key=lambda c: RANKS.index(c[0]))[1:]
            worst = [c for c in h if c not in keep][0]
            print(json.dumps({"type": "discard", "card": worst}), flush=True)
            state["hole"] = keep
        elif t == "action_request":
            print(json.dumps(act(msg)), flush=True)
        elif t == "match_end":
            break


if __name__ == "__main__":
    main()
