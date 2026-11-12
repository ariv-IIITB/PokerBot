"""L2 decision-level analysis of OUR folds facing a bet (logs from file_duel --logdir).

  PYTHONPATH=/tmp/l2/pkg .venv/bin/python panav-bots/loop/tools/l2_folds.py DIR [DIR..] [--max N] [--out f.json]

For every hand where we folded facing a bet we know: our cards, the board at that street, our own discard and the
opponent's discard (once shown). The opponent's hole cards are unknown, so we estimate our equity against slices of its
range: its hand is drawn at random from the live cards, scored by expected showdown percentile over the runouts, and the
top share p of them is kept (p = how often it bets that street: a player that bets 70% of flops has a top-70% range).
Pot odds: calling needs equity >= to_call / (pot + to_call). EV(call) = eq*pot - (1-eq)*to_call (this street only).
Also: the opponent's bet / fold / raise frequencies per street and its response to our raises over its bets.
Needs the unpacked bot package in PYTHONPATH (shared.cards / shared.evaluator): built from bundle_tool unpack.
"""
from __future__ import annotations
import itertools, json, sys, random, collections
from pathlib import Path
import numpy as np
from shared import cards as C
from shared.evaluator import evaluate_board_plus

STACK = 200
BL = {"button": 1, "big_blind": 2}
PS = (0.2, 0.35, 0.5, 0.7, 1.0)
NB = {"flop": 3, "turn": 4, "river": 5}


def read(dirs):
    for d in dirs:
        for f in sorted(Path(d).glob("*.jsonl")):
            seat = hole = hole2 = optdisc = mydisc = None
            for line in f.read_text().splitlines():
                m = json.loads(line)
                t = m["type"]
                if t == "new_hand":
                    seat, hole, hole2, optdisc, mydisc = m["seat"], m["hole_cards"], None, None, None
                elif t == "discard_result":
                    hole2, optdisc, mydisc = m["hole_cards"], m["opp_discard"], m["my_discard"]
                elif t == "hand_result":
                    yield f.name, seat, hole, hole2, mydisc, optdisc, m


def steps(history, seat):
    me_b = BL[seat]; op_b = 3 - me_b
    com = {"me": me_b, "opp": op_b}
    out = []; street = None; bets = {}
    for e in history:
        st, a, act = e["street"], e["actor"], e["action"]
        if st != street:
            street = st
            bets = {"me": me_b, "opp": op_b} if st == "preflop" else {"me": 0, "opp": 0}
        o = "opp" if a == "me" else "me"
        tc = bets[o] - bets[a]
        pot = com["me"] + com["opp"]
        frac = None
        pre_com = com[a]
        if act == "call":
            add = min(tc, STACK - com[a]); bets[a] += add; com[a] += add
        elif act == "raise":
            amt = int(e.get("amount") or 0)
            frac = amt / max(pot, 1) if bets[o] == 0 else (amt - bets[o]) / max(pot + tc, 1)
            com[a] += amt - bets[a]; bets[a] = amt
        out.append(dict(street=st, actor=a, action=act, to_call=tc, pot=pot, frac=frac, allin=com[a] >= STACK, pre_com=pre_com))
    return out


def equity_slices(rng, me, board_now, dead, street, n_opp=360, n_run=40):
    """Our equity vs the top-p slices of the opponent's range (p in PS). me: our kept two cards (turn/river) or our
    three cards (flop: we keep the pair with the best mean equity vs all hands). The opponent's flop hand has 3 cards;
    it keeps the pair with the best mean percentile over the runouts (no peeking)."""
    known = set(board_now) | set(dead) | set(me)
    deck = [c for c in range(52) if c not in known]
    k_opp = 3 if street == "flop" else 2
    need = 5 - len(board_now)
    R = [rng.sample(deck, need) if need else [] for _ in range(n_run)]
    keeps = list(itertools.combinations(me, 2)) if street == "flop" else [tuple(me)]
    H = np.array([rng.sample(deck, k_opp) for _ in range(n_opp)])
    okeeps = list(itertools.combinations(range(3), 2)) if k_opp == 3 else [(0, 1)]
    Vopp = np.full((n_run, n_opp, len(okeeps)), -1, np.int64)
    Vme = np.full((n_run, len(keeps)), -1, np.int64)
    for r, run in enumerate(R):
        bd = list(board_now) + run
        for ki, kp in enumerate(keeps):
            Vme[r, ki] = int(evaluate_board_plus(bd, np.array([list(kp)]))[0])
        clash = np.isin(H, run).any(axis=1) if need else np.zeros(n_opp, bool)
        for ki, (a, b) in enumerate(okeeps):
            v = evaluate_board_plus(bd, np.stack([H[:, a], H[:, b]], 1))
            Vopp[r, :, ki] = np.where(clash, -1, v)
    ranks = np.full(Vopp.shape, np.nan)
    for r in range(n_run):
        valid = Vopp[r] >= 0
        srt = np.sort(Vopp[r][valid])
        ranks[r] = np.where(valid, np.searchsorted(srt, Vopp[r]) / max(len(srt), 1), np.nan)
    meanrank = np.nan_to_num(np.nanmean(ranks, axis=0), nan=-1)            # (n_opp, nk)
    kbest = meanrank.argmax(axis=1)
    score = meanrank.max(axis=1)
    Vo = np.take_along_axis(Vopp, kbest[None, :, None], axis=2)[:, :, 0]    # (n_run, n_opp)

    def eq_of(vm, mask):
        win = (vm[:, None] > Vo) * 1.0 + (vm[:, None] == Vo) * 0.5
        ok = (Vo >= 0) & mask[None, :]
        return float((win * ok).sum() / max(ok.sum(), 1))
    allm = np.ones(n_opp, bool)
    ki = int(np.argmax([eq_of(Vme[:, k], allm) for k in range(len(keeps))]))
    vm = Vme[:, ki]
    order = np.argsort(-score)
    out = {}
    for p in PS:
        m = np.zeros(n_opp, bool); m[order[: max(5, int(p * n_opp))]] = True
        out[p] = eq_of(vm, m)
    return out


def main():
    args = [a for a in sys.argv[1:] if a != '--calls']
    mx = None; outf = None; dirs = []
    i = 0
    while i < len(args):
        if args[i] == "--max": mx = int(args[i + 1]); i += 2
        elif args[i] == "--out": outf = args[i + 1]; i += 2
        else: dirs.append(args[i]); i += 1
    rng = random.Random(7)
    freq = collections.defaultdict(collections.Counter); raise_resp = collections.Counter()
    folds = []; pre = collections.Counter()
    for fn, seat, hole, hole2, mydisc, optdisc, m in read(dirs):
        st = steps(m["history"], seat)
        for s in st:
            if s["actor"] == "opp" and s["street"] != "preflop":
                c = freq[s["street"]]
                if s["to_call"] == 0:
                    c["unf"] += 1; c["bet"] += s["action"] == "raise"
                    if s["action"] == "raise":
                        c["bet_big"] += (s["frac"] or 0) >= 0.9
                else:
                    c["vsbet"] += 1; c[s["action"] + "_vsbet"] += 1
        for i, s in enumerate(st):
            if s["actor"] == "me" and s["action"] == "raise" and s["to_call"] > 0 and s["street"] != "preflop" and i + 1 < len(st) \
                    and st[i + 1]["street"] == s["street"] and st[i + 1]["actor"] == "opp":
                raise_resp[(s["street"], st[i + 1]["action"])] += 1
        last = st[-1] if st else None
        if m["result"] == "fold" and last and last["actor"] == "me" and last["action"] == "fold":
            if last["street"] == "preflop":
                pre[(seat, "fold")] += 1
            folds.append((seat, hole, hole2, mydisc, optdisc, m, last))
        if st and st[0]["street"] == "preflop":
            pre[(seat, "hands")] += 1
    print(f"folds facing a bet (all streets): {len(folds)}; by street:",
          dict(collections.Counter(f[6]["street"] for f in folds)))
    print("preflop folds by seat:", {k: v for k, v in pre.items()})
    if "--calls" in sys.argv:
        return calls_mode(dirs, mx, rng)
    cand = [f for f in folds if f[6]["street"] != "preflop"]
    rng.shuffle(cand)
    if mx: cand = cand[:mx]
    rows = []
    for seat, hole, hole2, mydisc, optdisc, m, last in cand:
        street = last["street"]; board = C.parse_cards(m["board"][: NB[street]])
        dead = []
        if street == "flop":
            me = C.parse_cards(hole)
        else:
            me = C.parse_cards(hole2 or [])
            dead = C.parse_cards([x for x in (mydisc, optdisc) if x])
        if len(me) != (3 if street == "flop" else 2):
            continue
        eqs = equity_slices(rng, me, board, dead, street)
        req = last["to_call"] / (last["pot"] + last["to_call"])
        rows.append(dict(street=street, to_call=last["to_call"], pot=last["pot"],
                         frac=last["to_call"] / max(last["pot"] - last["to_call"], 1), req=req,
                         eq={str(p): e for p, e in eqs.items()}, net=m["net"], allin=last["allin"], seat=seat,
                         cards=hole if street == "flop" else hole2, board=board))
    if outf:
        Path(outf).write_text(json.dumps(rows, default=int))
    print("\nOpponent frequencies (postflop):")
    pbet = {}
    for s in ("flop", "turn", "river"):
        c = freq[s]
        pbet[s] = c["bet"] / max(c["unf"], 1)
        print(f"  {s}: unfaced n={c['unf']} bet {pbet[s]:.2f} (>=0.9 pot {c['bet_big'] / max(c['bet'], 1):.2f});"
              f" vs our bet n={c['vsbet']} fold {c['fold_vsbet'] / max(c['vsbet'], 1):.2f} call {c['call_vsbet'] / max(c['vsbet'], 1):.2f} raise {c['raise_vsbet'] / max(c['vsbet'], 1):.2f}")
    print("Our raise over its bet -> its response:", dict(raise_resp))
    print("\nFolds analysed:", len(rows))
    for s in ("flop", "turn", "river"):
        Rw = [r for r in rows if r["street"] == s]
        if not Rw: continue
        pk = min(PS, key=lambda p: abs(p - pbet[s]))
        print(f"\n== {s}  n={len(Rw)}  (opp bets {pbet[s]:.2f} -> slice p={pk})  mean req eq {np.mean([r['req'] for r in Rw]):.3f}  mean net of those hands {np.mean([r['net'] for r in Rw]):+.2f}")
        for p in PS:
            e = np.array([r["eq"][str(p)] for r in Rw]); req = np.array([r["req"] for r in Rw])
            ev = np.array([r["eq"][str(p)] * (r["pot"] + r["to_call"]) - r["to_call"] for r in Rw])
            ok = e >= req
            print(f"   range top {p:.2f}: mean eq {e.mean():.3f}  folds with eq>=req {int(ok.sum()):4d} ({ok.mean():.2f})  "
                  f"sumEV(call) all {ev.sum():+8.0f}  over eq>=req {ev[ok].sum():+7.0f}")
        e = np.array([r["eq"][str(pk)] for r in Rw]); req = np.array([r["req"] for r in Rw])
        ev = np.array([r["eq"][str(pk)] * (r["pot"] + r["to_call"]) - r["to_call"] for r in Rw])
        fr = np.array([r["frac"] for r in Rw])
        print("   by margin (eq-req) at matched slice:")
        for lo, hi in ((-1, -0.15), (-0.15, -0.05), (-0.05, 0.0), (0.0, 0.05), (0.05, 0.15), (0.15, 1.01)):
            k = (e - req >= lo) & (e - req < hi)
            if k.any(): print(f"     [{lo:+.2f},{hi:+.2f})  n={int(k.sum()):4d}  meanEV {ev[k].mean():+6.2f}  sumEV {ev[k].sum():+8.0f}")
        print("   by bet size (to_call / pot before the bet):")
        for lo, hi in ((0, 0.5), (0.5, 0.9), (0.9, 1.4), (1.4, 99)):
            k = (fr >= lo) & (fr < hi)
            if k.any(): print(f"     size [{lo},{hi})  n={int(k.sum()):4d}  mean eq {e[k].mean():.3f} req {req[k].mean():.3f}  folds eq>=req {(e[k] >= req[k]).mean():.2f}  sumEV(eq>=req) {ev[k & (e >= req)].sum():+6.0f}")


def calls_mode(dirs, mx, rng):
    """Our calls facing a bet: equity at the matched slice vs the realised value of continuing (net + chips already in)."""
    pk = {"flop": 0.7, "turn": 0.5, "river": 0.35}
    items = []
    for fn, seat, hole, hole2, mydisc, optdisc, m in read(dirs):
        st = steps(m["history"], seat)
        for s in st:
            if s["actor"] == "me" and s["action"] == "call" and s["street"] != "preflop" and s["to_call"] > 0:
                items.append((seat, hole, hole2, mydisc, optdisc, m, s))
    rng.shuffle(items)
    if mx: items = items[:mx]
    rows = []
    for seat, hole, hole2, mydisc, optdisc, m, s in items:
        street = s["street"]; board = C.parse_cards(m["board"][: NB[street]])
        if street == "flop":
            me = C.parse_cards(hole); dead = []
        else:
            me = C.parse_cards(hole2 or []); dead = C.parse_cards([x for x in (mydisc, optdisc) if x])
        if len(me) != (3 if street == "flop" else 2): continue
        e = equity_slices(rng, me, board, dead, street)[pk[street]]
        req = s["to_call"] / (s["pot"] + s["to_call"])
        rows.append((street, e - req, m["net"] + s["pre_com"], s["to_call"] / max(s["pot"] - s["to_call"], 1), m["result"], e * (s["pot"] + s["to_call"]) - s["to_call"]))
    print("calls analysed", len(rows))
    for street in ("flop", "turn", "river"):
        R = [r for r in rows if r[0] == street]
        if not R: continue
        print(f"== {street} n={len(R)}  realised continuation value mean {np.mean([r[2] for r in R]):+.2f}   predicted street-EV mean {np.mean([r[5] for r in R]):+.2f}")
        for lo, hi in ((-1, -0.15), (-0.15, -0.05), (-0.05, 0.05), (0.05, 0.15), (0.15, 1.01)):
            k = [r for r in R if lo <= r[1] < hi]
            if len(k) > 2:
                v = np.array([r[2] for r in k]); pr = np.array([r[5] for r in k])
                print(f"   margin [{lo:+.2f},{hi:+.2f}) n={len(k):4d} realised value {v.mean():+7.2f} +-{v.std() / np.sqrt(len(k)):.2f}   predicted street-EV {pr.mean():+7.2f}")


if __name__ == "__main__":
    main()
