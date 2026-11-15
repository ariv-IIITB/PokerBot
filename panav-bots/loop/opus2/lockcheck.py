"""Replay a recorded input stream (total_hands set to 1000, hand 1's net set to NET) through a bot and check
that every reply after the lock keeps the hand's chips within the risk budget. Exit 1 on a violation."""
import json, subprocess, sys
bot, src, NET = sys.argv[1], sys.argv[2], int(sys.argv[3])
msgs = []
for line in open(src):
    m = json.loads(line)
    if m["type"] == "init": m["total_hands"] = 1000
    if m["type"] == "hand_result" and m["hand_id"] == 1: m["net"] = NET
    msgs.append(m)
out = subprocess.run([sys.executable, bot], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                     capture_output=True, text=True, timeout=600)
replies = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
net, R, k, bad, checked, clamps = 0, None, 0, 0, 0, 0
for m in msgs:
    t = m["type"]
    if t == "new_hand":
        left = 1000 - m["hand_id"] + 1
        R = net - 2 * (left - 1) - 1 if net > 2 * left else None
    elif t == "hand_result":
        net += m["net"]
    elif t in ("action_request", "discard_request"):
        r = replies[k]; k += 1
        if t == "action_request":
            if r["action"] not in m["legal_actions"]: bad += 1
            if R is not None:
                put = 200 - m["my_stack"]
                c = r.get("amount", 0) - m["my_bet"] if r["action"] == "raise" else min(m["to_call"], m["my_stack"]) if r["action"] == "call" else 0
                checked += 1
                if put + c > R: bad += 1
print(f"replies {k}/{len(replies)} locked decisions checked {checked} violations {bad}")
print([l for l in out.stderr.splitlines() if "lock" in l][:3])
sys.exit(1 if bad or k != len(replies) else 0)
