"""Action profile: per bot and street, what it does when checked to vs facing a bet.
Usage: python3 -m lab.opps.profile tier2 opp3 3   (3 duplicate pairs, locks off)"""
import sys
from collections import Counter, defaultdict
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

STREET = {0: "pre", 3: "flop", 4: "turn", 5: "river"}

def wrap(player, stats):
    brain = player.bot.brain
    orig = brain.decide
    def decide(state, legal, budget):
        a = orig(state, legal, budget)
        h = state.hand
        st = STREET.get(len(h.board), "?")
        facing = "vs_bet" if h.tocall > 0 else "checked_to"
        if st == "pre":
            facing = "vs_raise" if h.tocall > 1 and (h.opp_bet or 0) > 2 else ("open" if h.seat == 0 and (h.my_bet or 0) == 1 else "other")
        stats[(st, facing)][a.kind] += 1
        return a
    brain.decide = decide
    return player

if __name__ == "__main__":
    v = load_variant("lab/opps/holdem_100bb.json")
    a_name, b_name, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    cfg_b = {"fold_out": False} if b_name == "opp3" else None
    sa, sb = defaultdict(Counter), defaultdict(Counter)
    total = 0
    for seed in range(n):
        for swap in (False, True):
            pa = wrap(PlayerSpec.brain(a_name, {"lock_enabled": False}).build(), sa)
            pb = wrap(PlayerSpec.brain(b_name, cfg_b).build(), sb)
            r = play_match([pb, pa] if swap else [pa, pb], v, seed, 400)
            total += r.chips[1] if swap else r.chips[0]
    print(f"{a_name} chips over {n*2} matches: {total} ({total/(n*800):+.2f}/hand)")
    for name, s in ((a_name, sa), (b_name, sb)):
        print(f"--- {name}")
        for k in sorted(s):
            c = s[k]; t = sum(c.values())
            print(f"  {k[0]:5} {k[1]:10} n={t:5} " + " ".join(f"{x}={c[x]/t:.0%}" for x in sorted(c)))
