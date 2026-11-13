"""Counterfactual replay: the true value of ONE decision of our bot against the real opponent bot.

Deals are reproducible: lab.engine.deck_for(seed, h, deck) with h = hand_id - 1 (hand_id is 1-based in the
logs); leg m1 has A = player 0 (SB in even h), leg m2 swaps (A is SB in odd h). A "leg log" is what
file_duel.py --logdir writes: every protocol line SENT to A (new_hand, action_request, discard_result,
hand_result with the full action history, opp_discard, ...). A's replies are not logged, but they are the
entries with actor "me" in the hand_result history (and my_discard in discard_result).

replay(decision, forced):
  * rebuilds the exact hand (same cards for both players, same runout) with the lab engine;
  * SCRIPTS both sides up to the decision: our logged actions and discards, and the OPPONENT'S logged actions
    and discard (so we condition on the logged state even when the opponent is random);
  * at the decision our player plays `forced` (fold / call / check / raise-to X) instead of the logged action;
  * afterwards both bots play live: ours = the real build (default final_seeded.py), the opponent = a fresh
    subprocess of the real opponent bot, started for that hand. Every replay uses FRESH processes (restart
    per replay), so in-match learning of BOTH bots (exploit layer SPRT, opponent models) is lost: each
    replay is "the bot at hand 1 of a match from this exact state".
  * returns our chip result for the whole hand (blinds included). Value of an action = mean over N replays.

Commands (run from the repo root, PYTHONPATH=.):
  validate   --log LEG.jsonl --opp BOT [--hands 40]       deal reconstruction + determinism of the opponent
  knownanswer --logdir DIR --opp BOT [--n 12]              forced fold / call at river vs known showdown result
  run        --logdir DIR --opp BOT --out OUT.json [...]   the three decision classes (i) (ii) (iii)
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import random
import re
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

from bot.actions import Action, is_legal
from bot.cards import parse_card
from bot.game.rules_spec import to_rules
from bot.game.runner import LazyRng
from bot.protocol import MatchInfo
from lab.engine import Forfeit, Hand, Seat, deck_for
from lab.harness import load_variant
from lab.players import SubprocessPlayer

OURS_DEFAULT = "panav-bots/loop/evalbuilds/final_seeded.py"
STREETS = ("preflop", "flop", "turn", "river")
_RULES = None


def rules():
    global _RULES
    if _RULES is None:
        _RULES = to_rules(load_variant("discard_holdem"))
    return _RULES


# --------------------------------------------------------------------------- reading a leg log

def parse_leg(path) -> dict:
    """-> {'seed', 'leg', 'hands': {h: {...}}, 'decisions': [...]} from one file_duel leg log.
    A is player 0 in leg 1 (SB in even h) and player 1 in leg 2 (SB in odd h)."""
    path = Path(path)
    m = re.match(r"seed(\d+)_m([12])", path.name)
    seed, leg = int(m.group(1)), int(m.group(2))
    hands: dict[int, dict] = {}
    cur = None
    total = 200
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        t = o.get("type")
        if t == "init":
            total = o["total_hands"]
        elif t == "new_hand":
            h = o["hand_id"] - 1
            cur = hands[h] = dict(h=h, seat=o["seat"], hole3=o["hole_cards"], reqs=[], my_discard=None)
        elif t == "action_request" and cur is not None:
            cur["reqs"].append(o)
        elif t == "discard_result" and cur is not None:
            cur["my_discard"] = o["my_discard"]
        elif t == "hand_result" and cur is not None:
            cur.update(net=o["net"], history=o["history"], board=o["board"], hole2=o["my_hole_cards"],
                       opp_discard=o["opp_discard"], opp_hole=o["opp_hole_cards"], result=o["result"])
            cur = None
    decisions = []
    for h, hd in hands.items():
        if "history" not in hd:
            continue
        hist = hd["history"]
        for r in hd["reqs"]:
            k = len(r["history"])
            if k >= len(hist) or hist[k]["actor"] != "me":
                continue                                   # should not happen; skip defensively
            d = dict(seed=seed, leg=leg, h=h, k=k, street=r["street"], pot=r["pot"], to_call=r["to_call"],
                     my_bet=r["my_bet"], opp_bet=r["opp_bet"], my_stack=r["my_stack"],
                     legal=r["legal_actions"], min_raise=r.get("min_raise"), max_raise=r.get("max_raise"),
                     logged=hist[k], board=r["board"], total_hands=total)
            decisions.append(d)
    return dict(seed=seed, leg=leg, hands=hands, decisions=decisions, total=total)


def a_is_sb(leg: int, h: int) -> bool:
    return (h % 2 == 0) if leg == 1 else (h % 2 == 1)


def to_action(e: dict) -> Action:
    a = e["action"]
    if a == "raise":
        return Action.raise_to(int(e["amount"]))
    return Action(dict(fold="F", check="K", call="C").get(a) or a) if False else _simple(a)


def _simple(a: str) -> Action:
    return {"fold": Action.fold(), "check": Action.check(), "call": Action.call()}[a]


# --------------------------------------------------------------------------- players

class Null:
    """Stands in for a bot that never needs to act (everything of its is scripted)."""

    def __init__(self):
        from bot.protocols import get_adapter
        self.adapter = get_adapter("pokerbots")      # keeps e_hole / history exactly like a real player's

    def notify(self, msg):
        self.adapter.encode_message(msg)

    def act(self, req):
        raise RuntimeError("Null player asked to act")

    def close(self):
        pass


class Scripted:
    """Wraps a SubprocessPlayer (or Null). Betting decisions are taken from `script` (a list of Actions) while
    it lasts, discards from `discard` (card text) if given; everything else goes to the live bot. The live bot
    is told about scripted actions through its adapter's history (what it would have recorded itself)."""

    def __init__(self, inner, script, discard: Optional[str]):
        self.inner, self.script, self.discard = inner, list(script), discard
        self.pos = 0
        self.diverged = False
        self.illegal = False
        self.log = []                       # (street-less) record of every action we gave
        self.state_at_forced = None         # req fields at the last scripted action

    def notify(self, msg):
        self.inner.notify(msg)

    def _ad(self):
        return getattr(self.inner, "adapter", None)

    def act(self, req, timeout=None):
        ad = self._ad()
        if req.legal.can_special:
            if self.discard is None and isinstance(self.inner, Null):
                self.diverged = True
                ad.encode_message(req)
                return Action.special("0")
            if self.discard is not None:
                if ad is not None:
                    ad.encode_message(req)                       # sets e_req (the line is not sent)
                    card = parse_card(self.discard)
                    return Action.special(str(ad.e_hole.index(card)))
                return ("DISCARD", self.discard)
            return self.inner.act(req, timeout) if timeout else self.inner.act(req)
        if self.pos < len(self.script):
            a = self.script[self.pos]
            self.pos += 1
            self.state_at_forced = (req.pot, req.tocall, req.mystack)
            if ad is not None:
                ad.encode_message(req)
                if is_legal(a, req.legal):
                    ad._engine_note("me", a)
                else:
                    self.illegal = True
            return a
        if isinstance(self.inner, Null):          # script exhausted but the hand goes on: the line diverged
            self.diverged = True
            return Action.check() if req.legal.check else Action.fold()
        a = self.inner.act(req)
        self.log.append(a)
        return a

    def close(self):
        self.inner.close()


def spawn(path, bank_s: float, total_hands: int):
    p = Path(path).resolve()
    pl = SubprocessPlayer([sys.executable, str(p)], cwd=str(p.parent), name=p.stem, protocol="pokerbots")
    pl.notify(MatchInfo(total_hands, bank_s, 1, 2, 200))
    return pl


class NullAdapter:
    pass


def play_hand(leg: int, seed: int, hd: dict, script_ours, script_opp, discard_ours, discard_opp,
              ours_path: Optional[str], opp_path: str, bank_per_hand=0.15, total_hands=200,
              opp_player=None):
    """Play hand hd['h'] of (seed, leg) with the given scripts. -> dict(delta, opp_actions, ours_actions, ...)."""
    h = hd["h"]
    sb_is_a = a_is_sb(leg, h)
    bank = max(8.0, bank_per_hand * (total_hands - h))
    opp = opp_player if opp_player is not None else spawn(opp_path, bank, total_hands)
    ours = spawn(ours_path, bank, total_hands) if ours_path else Null()
    try:
        so = Scripted(ours, script_ours, discard_ours)
        sp = Scripted(opp, script_opp, discard_opp)
        role_a = 0 if sb_is_a else 1
        seats = [None, None]
        seats[role_a] = Seat(so, bank)
        seats[1 - role_a] = Seat(sp, bank)
        hand = Hand(rules(), seats, [200, 200], deck_for(seed, h, rules().deck), h, "fold",
                    rng=LazyRng([seed, h, 1]))
        try:
            res = hand.play()
        except Forfeit as f:
            return dict(error=f"forfeit role {f.role}: {f.reason}", delta=None)
        ev = hand.st.events
        return dict(delta=res.deltas[role_a], showdown=res.showdown, folded=res.folded, pot=res.pot,
                    hole_a=list(hand.st.hole[role_a]), hole_opp=list(hand.st.hole[1 - role_a]),
                    board=list(hand.st.board), consumed=(so.pos == len(so.script), sp.pos == len(sp.script)),
                    state_at_forced=so.state_at_forced, role_a=role_a, opp_live=list(sp.log), diverged=so.diverged, illegal=so.illegal or sp.illegal)
    finally:
        for p in (ours, opp if opp_player is None else Null()):
            try:
                p.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- the replay of one decision

def scripts_for(hd: dict, d: Optional[dict], forced: Optional[Action]):
    """Scripts up to decision d (our k-th history entry): both sides' logged actions before it, then `forced`.
    d=None: the whole logged hand scripted for both sides (deal-reconstruction check)."""
    hist = hd["history"]
    end = d["k"] if d is not None else len(hist)
    ours = [to_action(e) for e in hist[:end] if e["actor"] == "me"]
    opp = [to_action(e) for e in hist[:end] if e["actor"] == "opp"]
    if d is not None:
        ours.append(forced)
    street = d["street"] if d is not None else "river"
    discarded = street in ("turn", "river") or (d is None and hd.get("my_discard") is not None)
    dour = hd["my_discard"] if discarded else None
    dopp = hd["opp_discard"] if discarded else None
    return ours, opp, dour, dopp


def replay(leg_info: dict, d: dict, forced: Action, ours_path, opp_path):
    hd = leg_info["hands"][d["h"]]
    so, sp, do_, dp = scripts_for(hd, d, forced)
    r = play_hand(leg_info["leg"], leg_info["seed"], hd, so, sp, do_, dp, ours_path, opp_path,
                  total_hands=leg_info["total"])
    if r.get("delta") is None:
        return r
    st = r["state_at_forced"]
    r["state_ok"] = not r.get("illegal") and bool(st and st[0] == d["pot"] and st[1] == d["to_call"] and st[2] == d["my_stack"])
    return r


def mean_se(xs):
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan")
    m = sum(xs) / n
    if n < 2:
        return m, float("nan")
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


def value(leg_info, d, forced, ours_path, opp_path, n_min=6, n_max=30, se_target=1.0, deterministic=False):
    """Mean chips (and SE) of `forced` at decision d. Adaptive N: at least n_min, stops when SE <= se_target
    or n_max; a forced fold / all-values-equal runs stop at n_min (sd = 0)."""
    xs, bad = [], 0
    while len(xs) < n_max:
        r = replay(leg_info, d, forced, ours_path, opp_path)
        if r.get("delta") is None or not r.get("state_ok", False):
            bad += 1
            if bad >= 3:
                break
            continue
        xs.append(r["delta"])
        if deterministic or forced.kind == "F":
            break
        if len(xs) >= n_min:
            m, se = mean_se(xs)
            if se <= se_target or len(set(xs)) == 1 and len(xs) >= n_min:
                break
    m, se = mean_se(xs)
    return dict(mean=m, se=se, n=len(xs), bad=bad, xs=xs)


# --------------------------------------------------------------------------- hand strength bucket

def equity_vs_random(d: dict, hd: dict, seed=0) -> float:
    """Our equity vs a random hand (bot.equity): flop = best of the 3 discard choices, turn/river = the 2 kept cards."""
    from bot.equity import equity
    board = [parse_card(c) for c in d["board"]]
    if d["street"] == "flop":
        h3 = [parse_card(c) for c in hd["hole3"]]
        subs = [[h3[i] for i in range(3) if i != j] for j in range(3)]
    else:
        subs = [[parse_card(c) for c in hd["hole2"]]]
    rng = np.random.default_rng(seed)
    return max(equity(s, board, rng=rng, max_samples=600).equity if "max_samples" in equity.__code__.co_varnames
               else equity(s, board, rng=rng).equity for s in subs)


def bucket(eq: float) -> str:
    return "<0.4" if eq < 0.4 else "0.4-0.55" if eq < 0.55 else "0.55-0.7" if eq < 0.7 else "0.7-0.85" if eq < 0.85 else ">0.85"


# --------------------------------------------------------------------------- classes

def pot_fraction_faced(d: dict) -> float:
    return d["to_call"] / max(1, d["pot"] - d["to_call"])


def min_bet_amount(d: dict) -> Optional[int]:
    """Smallest bet in OUR tree at an open node (shared.betting.raw_size: flop pot/3, turn/river pot/2,
    clamped to the legal min raise); None if raising is not legal or the size would be an all-in."""
    if "raise" not in d["legal"]:
        return None
    pot = d["pot"]
    raw = (pot + 1) // 3 if d["street"] == "flop" else (pot + 1) // 2
    amt = max(raw, d["min_raise"])
    return amt if amt < d["max_raise"] else None


def classify(d: dict) -> list[str]:
    out = []
    lg = d["logged"]["action"]
    if d["street"] in ("flop", "turn") and d["to_call"] > 0:
        if lg == "fold":
            out.append("i_fold")
        if lg == "call" and pot_fraction_faced(d) >= 0.7:
            out.append("ii_bigcall")
    if d["street"] in ("turn", "river") and lg == "check" and d["to_call"] == 0 and "raise" in d["legal"]:
        # check-behind: the opponent has already checked this street
        out.append("iii_checkbehind")
    return out


def is_check_behind(leg_info, d) -> bool:
    hd = leg_info["hands"][d["h"]]
    return any(e["street"] == d["street"] and e["actor"] == "opp" and e["action"] == "check"
               for e in hd["history"][:d["k"]])


def alternatives(cls: str, d: dict):
    """-> (logged Action, alternative Action or None)."""
    lg = to_action(d["logged"])
    if cls == "i_fold":
        return lg, Action.call()
    if cls == "ii_bigcall":
        return lg, Action.fold()
    if cls == "iii_checkbehind":
        a = min_bet_amount(d)
        return lg, (Action.raise_to(a) if a else None)
    raise ValueError(cls)


def work(args):
    """Worker: (leg file, decision index tuple, cls, ours, opp, n_max) -> result dict."""
    legf, key, cls, ours, opp, n_max, se_t = args
    li = _LEGS.get(legf)
    if li is None:
        li = _LEGS[legf] = parse_leg(legf)
    d = next(x for x in li["decisions"] if (x["h"], x["k"]) == key)
    hd = li["hands"][d["h"]]
    lg, alt = alternatives(cls, d)
    if alt is None:
        return None
    try:
        vl = value(li, d, lg, ours, opp, n_max=n_max, se_target=se_t)
        va = value(li, d, alt, ours, opp, n_max=n_max, se_target=se_t)
        eq = equity_vs_random(d, hd, seed=d["h"] * 7 + d["seed"])
    except Exception as e:                                    # never lose a whole run to one decision
        return dict(error=repr(e), cls=cls, seed=d["seed"], leg=d["leg"], h=d["h"], k=d["k"])
    return dict(cls=cls, seed=d["seed"], leg=d["leg"], h=d["h"], k=d["k"], street=d["street"], pot=d["pot"],
                to_call=d["to_call"], logged=d["logged"], alt=alt.kind if alt.kind != "R" else f"R{alt.amount}",
                actual_net=hd["net"], v_logged=vl, v_alt=va, eq=eq, bucket=bucket(eq))


_LEGS: dict = {}


# --------------------------------------------------------------------------- commands

def cmd_validate(a):
    """A1: every action scripted -> deal reconstruction + engine reproduce hole cards and net exactly.
    A2: our side scripted, the opponent LIVE in ONE persistent process fed the whole leg in order (so its in-match
    learning and RNG stream evolve as in the match): does it reproduce its logged actions and the result?"""
    leg = parse_leg(a.log)
    hs = sorted(h for h, hd in leg["hands"].items() if "history" in hd)[: a.hands]
    ok_full = 0
    for h in hs:
        hd = leg["hands"][h]
        so, sp, do_, dp = scripts_for(hd, None, None)
        r = play_hand(leg["leg"], leg["seed"], hd, so, sp, do_, dp, None, a.opp, total_hands=leg["total"])
        hole_ok = r.get("delta") is not None and set(r["hole_a"]) <= {parse_card(c) for c in hd["hole3"]} and \
            set(r["hole_a"]) == {parse_card(c) for c in hd["hole2"]}
        ok_full += int(hole_ok and r.get("delta") == hd["net"])
    print(f"A1 deal reconstruction + engine: {ok_full}/{len(hs)} hands reproduce hole cards and net exactly", flush=True)
    opp = None if a.fresh else spawn(a.opp, 0.15 * leg["total"], leg["total"])
    same_net = same_act = 0
    first_bad = None
    for h in hs:
        hd = leg["hands"][h]
        so, _, do_, dp = scripts_for(hd, None, None)
        so = [to_action(e) for e in hd["history"] if e["actor"] == "me"]
        r = play_hand(leg["leg"], leg["seed"], hd, so, [], hd["my_discard"], None, None, a.opp,
                      total_hands=leg["total"], opp_player=opp)
        if r.get("delta") is None:
            first_bad = first_bad or (h, r.get("error")); break
        if r.get("diverged"):
            first_bad = first_bad or (h, "opponent deviated from the logged line"); continue
        logged_opp = [to_action(e) for e in hd["history"] if e["actor"] == "opp"]
        # the opponent's live actions that were actually requested (the engine may end the hand earlier)
        n_same = r["opp_live"] == logged_opp[: len(r["opp_live"])] and len(r["opp_live"]) == len(logged_opp)
        same_act += int(n_same)
        same_net += int(r["delta"] == hd["net"])
        if not (n_same and r["delta"] == hd["net"]) and first_bad is None:
            first_bad = (h, f"opp live {r['opp_live']} vs logged {logged_opp}; delta {r['delta']} vs {hd['net']}")
    print(f"A2{' (FRESH opponent process per hand)' if a.fresh else ''} opponent live, ours scripted: {same_act}/{len(hs)} hands same opponent actions, "
          f"{same_net}/{len(hs)} same net chips; first mismatch: {first_bad}", flush=True)
    if opp is not None:
        opp.close()


def load_decisions(logdir):
    legs = {}
    for f in sorted(Path(logdir).glob("seed*_m*.jsonl")):
        legs[str(f)] = parse_leg(f)
    return legs


def cmd_knownanswer(a):
    legs = load_decisions(a.logdir)
    rnd = random.Random(5)
    cands = []
    for f, li in legs.items():
        for d in li["decisions"]:
            hd = li["hands"][d["h"]]
            if d["street"] == "river" and d["to_call"] > 0 and hd.get("opp_discard") and hd.get("my_discard"):
                cands.append((f, d))
    rnd.shuffle(cands)
    cands = cands[: a.n]
    ev = rules().evaluator
    fold_ok = call_ok = 0
    win_calls = lose_calls = 0
    rows = []
    for f, d in cands:
        li = legs[f]
        rf = replay(li, d, Action.fold(), None, a.opp)           # ours=None: only scripts are needed to land here...
        rc = replay(li, d, Action.call(), None, a.opp)
        if rf.get("delta") is None or rc.get("delta") is None:
            rows.append((d["h"], "error", rf.get("error"), rc.get("error"))); continue
        my_inv = 200 - d["my_stack"]
        opp_inv = d["pot"] - my_inv
        fold_ok += int(rf["delta"] == -my_inv)
        mine = [c for c in rc["hole_a"]]
        thr = [c for c in rc["hole_opp"]]
        va, vo = ev.evaluate(mine, rc["board"]), ev.evaluate(thr, rc["board"])
        expect = opp_inv if va > vo else (-(my_inv + d["to_call"]) if va < vo else 0)
        call_ok += int(rc["delta"] == expect)
        win_calls += int(va > vo); lose_calls += int(va < vo)
        rows.append((d["h"], d["seed"], "win" if va > vo else "lose" if va < vo else "tie", rf["delta"], rc["delta"], expect))
    n = len(rows)
    print(f"known-answer on {n} river decisions facing a bet ({win_calls} where our hand wins at showdown, "
          f"{lose_calls} where it loses):")
    print(f"  forced FOLD  == -(chips already in): {fold_ok}/{n}")
    print(f"  forced CALL  == +opp stake if we win / -(stake+call) if we lose: {call_ok}/{n}")
    for r in rows[:6]:
        print("   ", r)


def cmd_run(a):
    legs = load_decisions(a.logdir)
    rnd = random.Random(a.sample_seed)
    byc = {"i_fold": [], "ii_bigcall": [], "iii_checkbehind": []}
    for f, li in legs.items():
        for d in li["decisions"]:
            for c in classify(d):
                if c == "iii_checkbehind" and not is_check_behind(li, d):
                    continue
                if c == "iii_checkbehind" and min_bet_amount(d) is None:
                    continue
                byc[c].append((f, (d["h"], d["k"])))
    print({c: len(v) for c, v in byc.items()}, "decisions available", flush=True)
    done = set()
    out = Path(a.out)
    if out.exists():
        for line in out.read_text().splitlines():
            o = json.loads(line)
            done.add((o["cls"], o["seed"], o["leg"], o["h"], o["k"]))
    tasks = []
    for c, v in byc.items():
        rnd.shuffle(v)
        for f, key in v[: a.per_class]:
            m = re.match(r"seed(\d+)_m([12])", Path(f).name)
            if (c, int(m.group(1)), int(m.group(2)), key[0], key[1]) in done:
                continue
            tasks.append((f, key, c, a.ours, a.opp, a.n_max, a.se_target))
    rnd.shuffle(tasks)
    print(len(tasks), "decisions to replay", flush=True)
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.processes) as pool, open(out, "a") as fh:
        for i, r in enumerate(pool.imap_unordered(work, tasks, chunksize=1), 1):
            if r is not None:
                fh.write(json.dumps(r) + "\n"); fh.flush()
            if i % 20 == 0:
                print(f"  {i}/{len(tasks)} done, {time.time() - t0:.0f}s", flush=True)


def cmd_report(a):
    rows = [json.loads(l) for l in Path(a.out).read_text().splitlines()]
    rows = [r for r in rows if "v_logged" in r]
    res = {}
    for c in ("i_fold", "ii_bigcall", "iii_checkbehind"):
        rs = [r for r in rows if r["cls"] == c]
        if not rs:
            continue
        gains, better, worse = [], 0, 0
        for r in rs:
            vl, va = r["v_logged"], r["v_alt"]
            g = va["mean"] - vl["mean"]
            se = math.sqrt(sum(x for x in (vl["se"], va["se"]) if x == x and x is not None) ** 2 if False else
                           sum((x if x == x else 0.0) ** 2 for x in (vl["se"], va["se"])))
            gains.append(g)
            if g > max(se, 1e-9) and (se > 0 or g > 0):
                better += 1
            elif -g > max(se, 1e-9):
                worse += 1
        bk = {}
        for r, g in zip(rs, gains):
            bk.setdefault(r["bucket"], []).append(g)
        m, se = mean_se(gains)
        res[c] = dict(n=len(rs), better=better, worse=worse, mean_gain=m, se_gain=se,
                      buckets={b: (len(v), sum(v) / len(v)) for b, v in sorted(bk.items())},
                      mean_logged=mean_se([r["v_logged"]["mean"] for r in rs])[0],
                      mean_actual=mean_se([r["actual_net"] for r in rs])[0])
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--log", required=True); v.add_argument("--opp", required=True); v.add_argument("--hands", type=int, default=40)
    v.add_argument("--fresh", action="store_true", help="A2 with a fresh opponent process per hand (no in-match learning)")
    k = sub.add_parser("knownanswer")
    k.add_argument("--logdir", required=True); k.add_argument("--opp", required=True); k.add_argument("--n", type=int, default=12)
    r = sub.add_parser("run")
    r.add_argument("--logdir", required=True); r.add_argument("--opp", required=True)
    r.add_argument("--ours", default=OURS_DEFAULT); r.add_argument("--out", required=True)
    r.add_argument("--per-class", type=int, default=150); r.add_argument("--processes", type=int, default=3)
    r.add_argument("--n-max", type=int, default=30); r.add_argument("--se-target", type=float, default=1.0)
    r.add_argument("--sample-seed", type=int, default=1)
    q = sub.add_parser("report")
    q.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "validate":
        cmd_validate(a)
    elif a.cmd == "knownanswer":
        cmd_knownanswer(a)
    elif a.cmd == "run":
        cmd_run(a)
    elif a.cmd == "report":
        cmd_report(a)


if __name__ == "__main__":
    main()
