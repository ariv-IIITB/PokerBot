"""Protocol-level fuzz of any bot file: spawns `python bot.py`, feeds it random valid messages for the real
protocol (init, new_hand, action_request, discard_request, discard_result, hand_result, match_end) and checks that
every reply is legal and fast, and that nothing but protocol JSON reaches stdout.

    python eval/bots/spar/fuzz.py path/to/bot.py [--hands 150]

Prints decisions, illegal replies, the mean and worst reply time, and PASS / FAIL.
"""
import argparse
import json
import pathlib
import random
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
PY = ROOT / ".venv311" / "bin" / "python"
RANKS, SUITS = "23456789TJQKA", "shdc"
DECK = [r + s for r in RANKS for s in SUITS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot")
    ap.add_argument("--hands", type=int, default=150)
    a = ap.parse_args()
    bot = pathlib.Path(a.bot).resolve()
    p = subprocess.Popen([str(PY), str(bot)], cwd=bot.parent, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)
    rng = random.Random(7)
    lat, bad, n = [], 0, 0

    def send(m):
        p.stdin.write(json.dumps(m) + "\n")
        p.stdin.flush()

    def ask(m, check):
        nonlocal bad, n
        t = time.perf_counter()
        send(m)
        line = p.stdout.readline()
        lat.append((time.perf_counter() - t) * 1000)
        n += 1
        try:
            r = json.loads(line)
            ok = check(r)
        except Exception:
            ok = False
        if not ok:
            bad += 1
            print("ILLEGAL/garbled reply:", line.strip()[:120], "for", {k: m[k] for k in m if k != "history"}, flush=True)

    send({"type": "init", "protocol_version": "1.0", "total_hands": 200, "starting_stack": 200, "small_blind": 1,
          "big_blind": 2, "time_bank_ms": 30000, "per_response_ms": 5000})
    for h in range(1, a.hands + 1):
        cards = rng.sample(DECK, 9)
        hole = cards[:3]
        seat = rng.choice(["button", "big_blind"])
        send({"type": "new_hand", "hand_id": h, "seat": seat, "hole_cards": hole, "stack": 200, "opp_stack": 200})
        hist = []
        for street, nb in (("preflop", 0), ("flop", 3), ("turn", 4), ("river", 5)):
            if street == "turn" or street == "river":
                hole = hole[:2] if len(hole) == 3 else hole
            for _ in range(rng.choice([1, 1, 2])):
                opp_bet = rng.choice([0, 0, 2, 4, 8, 20, 60, 200]) if street != "preflop" else rng.choice([2, 6, 18, 200])
                my_bet = 0 if street != "preflop" else rng.choice([1, 2, 6])
                my_bet = min(my_bet, opp_bet) if rng.random() < 0.7 else my_bet
                tc = max(0, opp_bet - my_bet)
                legal = ["fold", "call"] if tc > 0 else ["check"]
                req = {"type": "action_request", "hand_id": h, "street": street, "board": cards[3:3 + nb], "pot": max(3, 2 * max(my_bet, opp_bet) + rng.choice([0, 6, 20])),
                       "my_bet": my_bet, "opp_bet": opp_bet, "to_call": tc, "my_stack": 200 - my_bet, "opp_stack": 200 - opp_bet,
                       "legal_actions": legal, "raises_left": rng.choice([0, 1, 2, 3, 4]), "history": list(hist)}
                if rng.random() < 0.8 and opp_bet < 200:
                    mn = min(opp_bet + max(2, tc), 200)
                    legal.append("raise")
                    req["min_raise"], req["max_raise"] = mn, 200
                    if mn > 200:
                        legal.remove("raise"); del req["min_raise"], req["max_raise"]

                def chk(r, req=req):
                    if r.get("type") != "action" or r.get("action") not in req["legal_actions"]:
                        return False
                    return r["action"] != "raise" or (isinstance(r.get("amount"), int) and req["min_raise"] <= r["amount"] <= req["max_raise"])
                ask(req, chk)
                hist.append({"street": street, "actor": rng.choice(["me", "opp"]), "action": rng.choice(["check", "call", "raise"]), "amount": 4})
            if street == "flop":
                ask({"type": "discard_request", "hand_id": h, "hole_cards": hole, "board": cards[3:6], "pot": 8, "my_stack": 196, "opp_stack": 196},
                    lambda r, hole=list(hole): r.get("type") == "discard" and r.get("card") in hole)
                keep = hole[1:]
                send({"type": "discard_result", "hand_id": h, "my_discard": hole[0], "opp_discard": cards[8], "hole_cards": keep})
                hole = keep
        showdown = rng.random() < 0.5
        send({"type": "hand_result", "hand_id": h, "result": "showdown" if showdown else "fold", "net": rng.choice([-20, 8, 0, 150]),
              "board": cards[3:8], "my_hole_cards": hole, "opp_hole_cards": cards[6:8] if showdown else None,
              "opp_discard": cards[8], "history": hist})
    send({"type": "match_end", "reason": "complete"})
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    extra = p.stdout.read().strip()
    if extra:
        bad += 1
        print("EXTRA STDOUT after match_end:", extra[:100])
    ok = bad == 0
    print(f"{n} replies, {bad} illegal, mean {sum(lat) / len(lat):.1f} ms, worst {max(lat):.1f} ms -> {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
