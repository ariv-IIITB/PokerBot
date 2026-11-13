"""Blueprint decisions (BUILDMAP §9.5, §9.10): table lookups with legality masks, the fallback chain,
purification, the exploit hook (behind a safety net) and sampling."""
import math
import numbers
import random

import numpy as np

from shared import betting as B
from shared import cards as C
from shared import features as F
from shared import infoset as I

from . import hooks
from . import ranges as RG
from . import river_api
from .timeman import NORMAL, PANIC, RANGE_MODES, now_ms

PURIFY_EPS = 0.03
TV_CAP = 0.3
EXPLOIT_MS = 5.0
EXPLOIT_KILL_MS = 50.0
MAX_S1 = {"flop": 47 * 2 * 1035, "turn": 46 * 2 * 990, "river": 2 * 990}
DISC_NODE = {"id": 0, "offset": 0, "slots": ["keep0", "keep1", "keep2"], "kind": "DISC"}
SAMPLE_STREET = {"preflop": 0, "flop": 1, "turn": 2, "river": 3, "discard": 4}
RIVER_RULES = ("off", "start", "updated", "mix")
RIVER_SOLVER_MODES = ("off", "s1", "s2")   # Phase 10 build flag: s1 the solver plays every river decision it
                                           # gets a budget for; s2 the same except facing an all-in (the rule)
PRE_MIN_N = 20             # preflop all-in rule: opponent opportunities in a spot before the rule may act
MIX_MIN_N = 15             # 'mix' river rule: opponent river all-in opportunities before it may distrust shoves
SMALL_BET_MARGIN = 0.10    # small-bet 'equity' option: never fold when equity > price + this
AGGR_MIN_N = 30            # small-bet 'gated': postflop raise opportunities each side before the gate may open
AGGR_RATIO = 2.0           # ... and the opponent must raise at least this many times as often as we do


def wilson_low(k, n, z=1.96):
    """Lower end of the 95% Wilson interval of a rate k/n."""
    if n <= 0:
        return 0.0
    p = k / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    rad = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, (centre - rad) / den)


class DecisionContext:
    """What hooks.exploit_adjust sees (§9.9)."""

    def __init__(self, **kw):
        self.street = kw.get("street")
        self.request = kw.get("request")
        self.node_id = kw.get("node_id")
        self.options = kw.get("options", {})
        self.slot_amounts = kw.get("slot_amounts", {})
        self.bucket = kw.get("bucket")
        self.prefix_key = kw.get("prefix_key")
        self.pc = kw.get("pc")
        self.pagg = kw.get("pagg")
        self.fagg = kw.get("fagg")
        self.my_discard = kw.get("my_discard")
        self.opp_discard = kw.get("opp_discard")
        self.opp_range = kw.get("opp_range")
        self.our_range = kw.get("our_range")
        self.mode = kw.get("mode")
        self.source = kw.get("source", "blueprint")
        # set when one of our rules chose (or reshaped) this decision: "river_allin_<start|updated|mix>",
        # "preflop_allin" or "small_bet". The exploit layer should return dist unchanged for these.
        self.rule = kw.get("rule")
        self.rule_detail = kw.get("rule_detail") or {}


def purify(dist, eps=PURIFY_EPS):
    """Zero probabilities below eps, renormalise (§9.5). Keeps the largest entry if all are below."""
    kept = {k: (v if v >= eps else 0.0) for k, v in dist.items()}
    s = sum(kept.values())
    if s <= 0:
        best = max(dist, key=dist.get)
        return {k: (1.0 if k == best else 0.0) for k in dist}
    return {k: v / s for k, v in kept.items()}


class ExploitGuard:
    """Safety net around hooks.exploit_adjust (§9.9): legal labels only, renormalised, total-variation
    cap 0.3, exceptions -> identity, time budget (disabled after a call > 50 ms or a mean > 5 ms)."""

    def __init__(self):
        self.calls = 0
        self.total_ms = 0.0
        self.over = 0
        self.errors = 0
        self.capped = 0
        self.disabled = False

    def charge(self, ms):
        self.total_ms += ms
        if ms > EXPLOIT_KILL_MS:
            self.disabled = True

    def apply(self, fn, ctx, base):
        if self.disabled:
            return base
        t0 = now_ms()
        try:
            out = fn(ctx, dict(base))
        except Exception:
            self.errors += 1
            out = None
        dt = now_ms() - t0
        self.calls += 1
        self.charge(dt)
        if dt > EXPLOIT_MS:
            self.over += 1
        if self.calls >= 20 and self.total_ms / self.calls > EXPLOIT_MS:
            self.disabled = True
        if not isinstance(out, dict):
            return base
        allowed = set(ctx.options) if ctx is not None and getattr(ctx, "options", None) else set(base)
        clean = {}
        for k, v in out.items():
            if k in allowed and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0:
                clean[k] = float(v)
        s = sum(clean.values())
        if s <= 0:
            return base
        labels = list(dict.fromkeys(list(base) + list(clean)))
        new = {k: clean.get(k, 0.0) / s for k in labels}
        old = {k: base.get(k, 0.0) for k in labels}
        tv = 0.5 * sum(abs(new[k] - old[k]) for k in labels)
        if tv > TV_CAP:
            f = TV_CAP / tv
            new = {k: old[k] + f * (new[k] - old[k]) for k in labels}
            self.capped += 1
        return new


class Policy:
    def __init__(self, tables, th, canon3, config=None):
        self.tables = tables
        self.th = th
        self.L = I.layout(getattr(th, "A", None))   # the tables' layout: the thresholds' abstraction (a1, a2)
        self.canon3 = canon3
        self.config = dict(config or {})
        hooks.setup(self.config, self.L.A)          # the exploit layer (config "exploit"; off by default)
        self.rng = random.Random()
        # Eval builds only (tools/build_bot.py --sample-seed): every decision draws its random number
        # from (seed, deal, seat, street, history index), so the two plays of a duplicate deal (hand k of
        # leg 1 and of leg 2) play the same spot the same way. Tournament builds use the process RNG,
        # seeded from the OS per process, so the two legs draw independently (Rulebook 10.3).
        self.mirror = self.config.get("sample_seed") is not None
        self.purify_eps = float(self.config.get("purify_eps", PURIFY_EPS))
        self.river_rule = self.config.get("river_allin_rule", "off")
        self.small_mode = self.config.get("small_bet", "off")
        self.pre_table = self.load_preflop_table() if self.config.get("preflop_allin_rule", "off") == "on" else None
        self.pre_stats = {}                     # opponent preflop node id -> [all-in opportunities, all-ins]
        self.mix = {"n": 0, "E": 0.0, "V": 0.0, "O": 0}   # opponent river all-ins vs the blueprint's rate
        self.aggr = {"us": [0, 0], "opp": [0, 0]}   # postflop: [opportunities with raise legal, raises]
        self.wants_hand_end = self.pre_table is not None or self.river_rule == "mix" or self.small_mode == "gated"
        self.solver_mode = self.config.get("river_solver", "off")
        self.solver_error = None
        self.solver = self.load_solver() if self.solver_mode in ("s1", "s2") else None
        river_api.use(self.solver)              # None: river_api.decide asks the stub (always None)
        # Phase 10 options (build flags --solver-out / --solver-fold): F-out, once the opponent raises a bet
        # or raise of ours on the river the solver steps aside for the rest of the hand; F-fold, the glue
        # mixes in a best response to the opponent's fold rate to our river bets and raises in this leg.
        self.solver_out = self.config.get("solver_out", "off") == "on"
        self.solver_fold = self.config.get("solver_fold", "off") == "on"
        self.river_folds = [0, 0]               # F-fold: [our river bets and raises they answered, their folds]
        self.wants_hand_end = self.wants_hand_end or self.solver_fold

    def load_solver(self):
        """The glue around the teammate's river solver (bundled only when the build's river_solver flag
        is on). None (the stub plays) if it cannot be set up."""
        try:
            from . import river_glue
            river_glue.setup(pinned_passes=self.config.get("solver_passes"),     # eval builds only
                             slowdown=self.config.get("slowdown", 1.0),
                             box_cap_ms=self.config.get("solver_box_ms"),         # eval builds only
                             pin_buckets=self.config.get("solver_buckets"))       # eval builds only
            return river_glue
        except Exception as e:
            self.solver_error = f"{type(e).__name__}: {e}"
            return None

    @staticmethod
    def load_preflop_table():
        """(f_grid, eq[1755, len(f_grid)]) from the bundled botsrc.preflop_table, or None."""
        try:
            import base64
            import zlib
            from . import preflop_table as PT
            raw = zlib.decompress(base64.b64decode(PT.DATA))
            eq = np.frombuffer(raw, np.uint8).reshape(PT.SHAPE).astype(np.float64) / 255.0
            return np.asarray(PT.F_GRID, dtype=np.float64), eq
        except Exception:
            return None

    # ---------------- fallback candidates (§9.10): (level, prefix), nearest first

    def flop_candidates(self, b3, pc, pagg):
        L, ng = self.L, self.L.A.gap
        c = [("table", L.flop_prefix(b3, pc, pagg))]
        c += [("pc", L.flop_prefix(b3, p, pagg)) for p in (pc - 1, pc + 1) if 0 <= p < 6]
        g = b3 % ng
        c += [("bucket", L.flop_prefix(b3 + d, pc, pagg)) for d in (-1, 1) if 0 <= g + d < ng]
        return c

    def disc_candidates(self, b3, pc, fagg, seat):
        L, ng = self.L, self.L.A.gap
        c = [("table", L.disc_prefix(b3, pc, fagg, seat))]
        c += [("pc", L.disc_prefix(b3, p, fagg, seat)) for p in (pc - 1, pc + 1) if 0 <= p < 6]
        g = b3 % ng
        c += [("bucket", L.disc_prefix(b3 + d, pc, fagg, seat)) for d in (-1, 1) if 0 <= g + d < ng]
        return c

    def turn_candidates(self, bt, od, md, pc, fagg=0):
        """a2's turn key has the flop aggressor: an unvisited row tries pc +- 1, then the other two flop
        aggressors (level "agg"), then the neighbouring S1 bins (a1: no "agg" level)."""
        L, nv = self.L, self.L.A.turn_v
        c = [("table", L.turn_prefix(bt, od, md, pc, fagg))]
        c += [("pc", L.turn_prefix(bt, od, md, p, fagg)) for p in (pc - 1, pc + 1) if 0 <= p < 6]
        if L.N_TAGG > 1:
            c += [("agg", L.turn_prefix(bt, od, md, pc, f)) for f in range(3) if f != fagg]
        c += [("bucket", L.turn_prefix(bt + d, od, md, pc, fagg)) for d in (-nv, nv) if 0 <= bt + d < L.N_BT]
        return c

    def river_candidates(self, br, od, pc):
        L = self.L
        c = [("table", L.river_prefix(br, od, pc))]
        c += [("pc", L.river_prefix(br, od, p)) for p in (pc - 1, pc + 1) if 0 <= p < 6]
        c += [("bucket", L.river_prefix(br + d, od, pc)) for d in (-1, 1) if 0 <= br + d < L.N_BR]
        return c

    def first_usable(self, table, cands, node, legal_mask):
        """First candidate row with probability mass on a legal slot -> (probabilities over the
        node's slots, level); (None, None) if none."""
        off, k = node["offset"], len(node["slots"])
        mask = np.asarray(legal_mask, dtype=np.float64)
        for level, prefix in cands:
            row = self.tables[table][prefix, off:off + k].astype(np.float64) * mask
            s = row.sum()
            if s > 0:
                return row / s, level
        return None, None

    # ---------------- street features (cached per hand, §9.5)

    def flop_info(self, hs, board):
        flop = board[:3]
        key = ("flop", tuple(flop), tuple(hs.hole3))
        if key not in hs.cache:
            if len(set(flop) | set(hs.hole3)) != 6:
                raise ValueError("flop overlaps our hole cards")
            rows = F.street_rows(flop, True)
            pairs = F.hand_pairs(hs.hole3)
            f = F.own_features(rows, pairs)
            s1 = [x[0] for x in f]
            b3, slots = F.bucket3(hs.hole3, s1, [x[1] for x in f], self.th)
            hs.cache[key] = {"rows": rows, "b3": b3, "slots": slots, "s1_best": s1[pairs.index(slots[0])]}
        return hs.cache[key]

    def later_info(self, hs, street, board):
        n = 4 if street == "turn" else 5
        cards = board[:n]
        key = (street, tuple(cards), tuple(hs.hole))
        if key not in hs.cache:
            if len(hs.hole) != 2 or len(set(cards) | set(hs.hole)) != n + 2:
                raise ValueError(f"{street}: bad kept pair or board")
            rows = F.street_rows(cards, street == "turn")
            s1, s2 = F.own_features(rows, [tuple(hs.hole)])[0]
            if street == "turn":
                bucket = F.turn_bucket(s1, F.turn_v(s1, s2), self.th)
            else:
                bucket = F.river_bucket(s1, self.th)
            hs.cache[key] = {"rows": rows, "bucket": bucket, "s1": s1}
        return hs.cache[key]

    # ---------------- decisions

    def decide_action(self, hs, req, rep, mode, guard, stats, tm=None):
        street = req["street"]
        board = C.parse_cards(req["board"])
        node = B.template_for(street)[rep.current_node]
        opts = B.slot_options_req(street, node, req)
        legal_mask = [ok for _, ok, _ in opts]
        if not any(legal_mask):
            raise ValueError("no legal slot at this node")
        amounts = {s: a for s, ok, a in opts if ok and a is not None}
        if mode == PANIC and street != "preflop":
            stats.level(street, "panic")
            return self.panic_action(hs, req, street, board), None, node["id"]
        hs.cache.pop("pf_proxy", None)
        info = {"street": street, "node": node["id"]}
        pc = proxy = None
        if street == "preflop":
            table = "PRE"
            cands = [("table", int(self.canon3[C.idx3(*hs.hole3)]))]
        elif street == "flop":
            fi = self.flop_info(hs, board)
            pc = B.pot_class(rep.pot_start["flop"])
            table, cands, proxy = "FLOP", self.flop_candidates(fi["b3"], pc, rep.pagg), fi["s1_best"] / MAX_S1["flop"]
            info["bucket"] = fi["b3"]
        else:
            li = self.later_info(hs, street, board)
            flop = board[:3]
            od, md = F.dcls(hs.opp_discard, flop), F.dcls(hs.my_discard, flop)
            pc = B.pot_class(rep.pot_start[street])
            if street == "turn":
                table, cands = "TURN", self.turn_candidates(li["bucket"], od, md, pc, rep.fagg)
            else:
                table, cands = "RIVER", self.river_candidates(li["bucket"], od, pc)
            proxy = li["s1"] / MAX_S1[street]
            info["bucket"] = li["bucket"]
        hs.cache["pf_proxy"] = proxy               # S1 / max: equity vs a random hand (potfold reads it)
        row, level = self.first_usable(table, cands, node, legal_mask)
        if row is None:
            label = self.heuristic(node, req, opts, proxy)
            raw = {label: 1.0}
        else:
            raw = {s: float(p) for s, p in zip(node["slots"], row) if p > 0}
        options = {s: self.action_for(s, amounts, req) for s, ok, _ in opts if ok}
        if street == "preflop" and self.pre_table is not None:
            out = self.preflop_allin(hs, req, rep, node, options, guard, stats, mode)
            if out is not None:
                return out
        rr = None
        if street == "river" and mode in RANGE_MODES and tm is not None:
            rr = self.river_ranges(hs, rep, board, tm)
            out = self.river_special(hs, req, rep, board, node, raw, rr, guard, stats, tm, mode)
            if out is not None:
                return out
        stats.level(street, "heuristic" if row is None else level)
        dist = purify(raw, self.purify_eps) if row is not None else raw
        rule = detail = None
        if self.small_mode != "off":
            if self.small_mode == "gated" and "small_bet_gate_open" not in getattr(stats, "rule_first", {}) \
                    and street != "preflop" and self.opp_hyper_aggressive():
                self.first(stats, "small_bet_gate_open", hs.hand_id)
            dist, rule, detail = self.small_bet(hs, req, street, dist, rr, proxy, board)
            if rule:
                stats.rules["small_bet"] = stats.rules.get("small_bet", 0) + 1
                self.first(stats, "small_bet", hs.hand_id)
        ctx = DecisionContext(street=street, request=req, node_id=node["id"], options=options, slot_amounts=amounts,
                              bucket=info.get("bucket"), prefix_key=(table, cands[0][1]), pc=pc, pagg=rep.pagg,
                              fagg=rep.fagg, my_discard=hs.my_discard, opp_discard=hs.opp_discard, mode=mode,
                              opp_range=rr.opp if rr else None, our_range=rr.our if rr else None,
                              source="rule" if rule else "blueprint", rule=rule, rule_detail=detail)
        dist = guard.apply(hooks.exploit_adjust, ctx, dist)
        label = self.sample(dist, self.sample_key(hs, street, len(req["history"])))
        return options[label], label, node["id"]

    # ---------------- river (BUILDMAP §9.6, §9.7, §10)

    def river_ranges(self, hs, rep, board, tm):
        """Both ranges at the start of the river, computed once per hand (NORMAL and NOSOLVER)."""
        if "ranges" not in hs.cache:
            t0 = now_ms()
            hs.cache["ranges"] = RG.river_ranges(self, hs, rep, board)
            tm.emulate(now_ms() - t0)                   # eval builds: a slower machine (no-op otherwise)
            tm.note_range(now_ms() - t0)
        return hs.cache["ranges"]

    def river_special(self, hs, req, rep, board, node, blueprint, rr, guard, stats, tm, mode=NORMAL):
        """River (§9.7, §10): in NORMAL the solver first; when it gives nothing (None, invalid, error,
        no budget) or in NOSOLVER, the river all-in rule (flag); None -> the blueprint river."""
        legal = req["legal_actions"]
        rule = self.river_rule
        facing_allin = req["to_call"] > 0 and req["opp_stack"] == 0 and "call" in legal
        if mode == NORMAL:
            if self.solver_mode == "s2" and facing_allin and rule in ("start", "updated", "mix"):
                stats.river["solver_left_to_rule"] = stats.river.get("solver_left_to_rule", 0) + 1
            elif self.solver_out and self.solver is not None and self.opp_raised_us_on_river(req["history"]):
                stats.river["solver_stepped_aside"] = stats.river.get("solver_stepped_aside", 0) + 1
            else:
                out = self.river_solver(hs, req, rep, board, node, blueprint, rr, guard, stats, tm)
                if out is not None:
                    return out
        else:
            stats.river["solver_nosolver_mode"] = stats.river.get("solver_nosolver_mode", 0) + 1
        if rule not in ("start", "updated", "mix") or not facing_allin:
            return None
        opp, weight = self.rule_opp_range(hs, req, rep, board, rr, tm)
        eq = RG.equity(board[:5], hs.hole, opp)
        odds = req["to_call"] / max(req["pot"] + req["to_call"], 1)
        label = "call" if eq > odds else "fold"
        options = {"call": {"type": "action", "action": "call"}, "fold": {"type": "action", "action": "fold"}}
        ctx = DecisionContext(street="river", request=req, node_id=node["id"], options=options, pagg=rep.pagg,
                              fagg=rep.fagg, my_discard=hs.my_discard, opp_discard=hs.opp_discard, opp_range=opp,
                              our_range=rr.our, mode=mode, source="rule", rule=f"river_allin_{rule}",
                              rule_detail={"equity": eq, "price": odds, "allin_weight": weight})
        dist = guard.apply(hooks.exploit_adjust, ctx, {label: 1.0})
        label = self.sample(dist, self.sample_key(hs, "river", len(req["history"])))
        stats.level("river", "allin_rule")
        stats.river[f"allin_rule_{label}"] = stats.river.get(f"allin_rule_{label}", 0) + 1
        if rule == "mix" and weight < 1.0:
            stats.rules["mix_distrust"] = stats.rules.get("mix_distrust", 0) + 1
            self.first(stats, "mix_distrust", hs.hand_id)
        return options[label], label, node["id"]

    def rule_opp_range(self, hs, req, rep, board, rr, tm):
        """(range, all-in weight): the opponent range the river all-in rule uses. 'start': the river-start
        range; 'updated' and 'mix' (and 'off', for the solver): also their river actions so far
        (blueprint RIVER table), for 'mix' with the shove factor's exponent scaled by mix_weight().
        Computed once per decision (the solver and the rule share it); the time counts as range time."""
        if self.river_rule == "start":
            return rr.opp, 1.0
        weight = self.mix_weight() if self.river_rule == "mix" else 1.0
        key = ("opp_now", len(req["history"]), weight)
        if key not in hs.cache:
            t0 = now_ms()
            hs.cache[key] = RG.opp_range_now(self, hs, rep, board, rr.tau, allin_weight=weight)
            tm.emulate(now_ms() - t0)
            tm.note_range(now_ms() - t0)
        return hs.cache[key], weight

    def our_range_now(self, hs, req, rep, board, rr, tm):
        """Our range given our river actions so far (§9.6, no tempering, no flat mix); the river-start
        range while we have not acted on the river. An action the solver chose counts with the solver's
        own probability of it for each combo (hs.cache["solver_lik"], set in river_solver()), any other
        with the blueprint RIVER table."""
        if not any(isinstance(e, dict) and e.get("street") == "river" and e.get("actor") == "me"
                   for e in req["history"]):
            return rr.our
        key = ("our_now", len(req["history"]))
        if key not in hs.cache:
            t0 = now_ms()
            hs.cache[key] = RG.our_range_now(self, hs, rep, board, own_river=hs.cache.get("solver_lik"))
            tm.emulate(now_ms() - t0)
            tm.note_range(now_ms() - t0)
        return hs.cache[key]

    @staticmethod
    def opp_raised_us_on_river(history):
        """F-out: has the opponent raised a bet or raise of ours on this river?"""
        bets = {"me": 0, "opp": 0}
        for e in history:
            if not isinstance(e, dict) or e.get("street") != "river" or e.get("actor") not in bets:
                continue
            who, a = e["actor"], e.get("action")
            if a == "raise":
                if who == "opp" and bets["me"] > bets["opp"]:
                    return True
                bets[who] = int(e.get("amount") or 0)
            elif a == "call":
                bets[who] = bets["opp" if who == "me" else "me"]
        return False

    def river_solver(self, hs, req, rep, board, node, blueprint, rr, guard, stats, tm):
        """The river solver through river_api (§10): validated, through the exploit hook, sampled; None
        when it is skipped, returns None or something invalid, or raises."""
        legal = req["legal_actions"]
        budget = tm.river_budget_ms(req, hs.hand_id)
        if budget <= 0:
            stats.river["solver_skipped"] = stats.river.get("solver_skipped", 0) + 1
            return None
        min_raise = req.get("min_raise")
        if "raise" in legal and not any(s in node["slots"] for s in ("sizeA", "sizeB", "raise", "allin")):
            # The template has this spot as capped (an opponent raise translated to allin) while the engine
            # still allows a raise: offer the solver the shove only. A smaller raise would put the replay
            # off the template; after a shove we never decide again in this hand.
            min_raise = req.get("max_raise")
            stats.river["solver_allin_only"] = stats.river.get("solver_allin_only", 0) + 1
        ctx = river_api.RiverContext(
            hand_id=hs.hand_id, seat="button" if hs.seat == 0 else "big_blind", board=list(board[:5]),
            hole=list(hs.hole), my_discard=hs.my_discard, opp_discard=hs.opp_discard, pot=req["pot"],
            my_bet=req["my_bet"], opp_bet=req["opp_bet"], to_call=req["to_call"], my_stack=req["my_stack"],
            opp_stack=req["opp_stack"], legal_actions=list(legal), min_raise=min_raise,
            max_raise=req.get("max_raise"), raises_left=req["raises_left"],
            pot_at_river_start=rep.pot_start["river"],
            river_history=[dict(e) for e in req["history"] if isinstance(e, dict) and e.get("street") == "river"],
            my_range=rr.our.copy(), opp_range=rr.opp.copy(), time_budget_ms=float(budget),
            blueprint_dist=dict(blueprint), opp_model=self.opp_model())
        if self.solver is not None:                     # the glue needs both ranges at this decision
            ctx.opp_range_now = self.rule_opp_range(hs, req, rep, board, rr, tm)[0].copy()
            ctx.my_range_now = self.our_range_now(hs, req, rep, board, rr, tm).copy()
            try:                                        # the exploit layer may change the solver's input
                adj = hooks.solver_opp_range(ctx.opp_range_now, rr.opp, list(board[:5]), req, hs.hand_id)
                if adj is not None:
                    adj = np.asarray(adj, dtype=np.float64)
                    if adj.shape == (1326,) and np.isfinite(adj).all() and (adj >= 0).all() and adj.sum() > 0:
                        ctx.opp_range_now = adj
                        stats.river["exploit_range"] = stats.river.get("exploit_range", 0) + 1
            except Exception:
                stats.river["exploit_range_errors"] = stats.river.get("exploit_range_errors", 0) + 1
            if self.solver_fold:
                ctx.opp_river_folds = tuple(self.river_folds)
        t0 = now_ms()
        try:
            out = river_api.decide(ctx)
        except Exception:
            out = None
            stats.river["solver_errors"] = stats.river.get("solver_errors", 0) + 1
        dt = now_ms() - t0
        tm.note_solver(dt, budget)
        if dt > budget:
            stats.river["solver_over_budget"] = stats.river.get("solver_over_budget", 0) + 1
        dist, options = self.solver_dist(out, req)
        if dist is None:
            key = "solver_none" if out is None else "solver_invalid"
            stats.river[key] = stats.river.get(key, 0) + 1
            return None
        dctx = DecisionContext(street="river", request=req, node_id=node["id"], options=options, pc=None,
                               pagg=rep.pagg, fagg=rep.fagg, my_discard=hs.my_discard, opp_discard=hs.opp_discard,
                               opp_range=rr.opp, our_range=rr.our, mode=NORMAL, source="river_solver")
        dist = guard.apply(hooks.exploit_adjust, dctx, dist)
        label = self.sample(dist, self.sample_key(hs, "river", len(req["history"])))
        stats.level("river", "solver")
        self.keep_solver_likelihood(hs, req, ctx, options[label], stats)
        return options[label], label, node["id"]

    def keep_solver_likelihood(self, hs, req, ctx, action, stats):
        """Our range after the action we play here (a bug fix, Phase 10): the solver's probability of it
        for every combo of ours replaces the blueprint RIVER table for it in our_range_now()."""
        if self.solver is None:
            return
        try:
            lik = self.solver.taken_likelihood(hs.hand_id, len(ctx.river_history), action["action"],
                                               action.get("amount"))
        except Exception:
            lik = None
        if lik is None:
            stats.river["solver_no_likelihood"] = stats.river.get("solver_no_likelihood", 0) + 1
            return
        hs.cache.setdefault("solver_lik", {})[len(req["history"])] = lik

    @staticmethod
    def first(stats, key, hand_id):
        """Remember the hand of a rule event's first occurrence in this leg (opponent models restart
        every leg, so this is how long each one needs before it acts)."""
        try:
            stats.rule_first.setdefault(key, int(hand_id))
        except Exception:
            pass

    def mix_weight(self):
        """'mix' river rule: 1 (trust river all-ins as the blueprint would) unless the opponent has gone
        all-in on the river more than 2 standard errors above the blueprint's rate; then expected/observed."""
        m = self.mix
        if m["n"] < MIX_MIN_N or m["O"] <= 0 or m["O"] - m["E"] <= 2.0 * math.sqrt(max(m["V"], 1e-12)):
            return 1.0
        return max(0.0, min(1.0, m["E"] / m["O"]))

    # ---------------- preflop all-in rule (Phase 9 b)

    @staticmethod
    def last_opp_node(hs, rep, street):
        for st in reversed(rep.steps):
            if st.street == street and st.seat != hs.seat and st.node is not None and st.node >= 0:
                return st.node
        return None

    def preflop_allin(self, hs, req, rep, node, options, guard, stats, mode):
        """Facing a preflop all-in: once the opponent's spot has PRE_MIN_N observations, call when our
        equity beats the price against their top-f range, f = the low end of the 95% interval of their
        shove rate there (the strongest range that fits). Otherwise (or if not) the blueprint decides."""
        if not (req["to_call"] > 0 and req["opp_stack"] == 0 and "call" in options):
            return None
        spot = self.last_opp_node(hs, rep, "preflop")
        n, k = self.pre_stats.get(spot, (0, 0))
        if n < PRE_MIN_N:
            stats.rules["preflop_allin_waiting"] = stats.rules.get("preflop_allin_waiting", 0) + 1
            return None
        self.first(stats, "preflop_allin_ready", hs.hand_id)
        f_low = wilson_low(k, n)
        grid, table = self.pre_table
        cls = int(self.canon3[C.idx3(*hs.hole3)])
        eq = float(np.interp(max(f_low, grid[0]), grid, table[cls]))
        price = req["to_call"] / max(req["pot"] + req["to_call"], 1)
        if eq <= price:
            stats.rules["preflop_allin_blueprint"] = stats.rules.get("preflop_allin_blueprint", 0) + 1
            return None
        ctx = DecisionContext(street="preflop", request=req, node_id=node["id"], options=options, mode=mode,
                              source="rule", rule="preflop_allin",
                              rule_detail={"spot": spot, "n": n, "shoves": k, "f_low": f_low, "equity": eq,
                                           "price": price})
        dist = guard.apply(hooks.exploit_adjust, ctx, {"call": 1.0})
        label = self.sample(dist, self.sample_key(hs, "preflop", len(req["history"])))
        stats.level("preflop", "allin_rule")
        stats.rules["preflop_allin_call"] = stats.rules.get("preflop_allin_call", 0) + 1
        self.first(stats, "preflop_allin_call", hs.hand_id)
        return options[label], label, node["id"]

    # ---------------- small bets (Phase 9 c)

    def small_bet(self, hs, req, street, dist, rr, proxy, board):
        """Facing an opponent raise smaller than our smallest size at the node (translation maps it up to
        that size): 'scale' multiplies the fold probability by x / x_min and moves the rest to call;
        'equity' never folds when our equity (river: vs opp_range; else the bucket proxy) beats the
        price by SMALL_BET_MARGIN; 'both' does both; 'gated' does both, but only against an opponent who
        bets or raises after the flop far more often than we do (opp_hyper_aggressive).
        -> (dist, rule or None, detail)."""
        if self.small_mode == "gated" and not self.opp_hyper_aggressive():
            return dist, None, None
        hist = req["history"]
        idx = len(hist) - 1
        if (req["to_call"] <= 0 or dist.get("fold", 0.0) <= 0 or "call" not in req["legal_actions"] or idx < 0
                or not isinstance(hist[idx], dict) or hist[idx].get("actor") != "opp"):
            return dist, None, None
        small = hs.small.get(idx)
        if small is None:
            return dist, None, None
        x, x_min = small
        price = req["to_call"] / max(req["pot"] + req["to_call"], 1)
        new = dict(dist)
        new.setdefault("call", 0.0)
        detail = {"x": x, "x_min": x_min, "price": price}
        if self.small_mode in ("scale", "both", "gated"):
            r = max(0.0, min(1.0, x / x_min)) if x_min > 0 else 1.0
            moved = new["fold"] * (1.0 - r)
            new["fold"] -= moved
            new["call"] += moved
            detail["scale"] = r
        if self.small_mode in ("equity", "both", "gated"):
            eq = RG.equity(board[:5], hs.hole, rr.opp) if (street == "river" and rr is not None) else proxy
            detail["equity"] = eq
            if eq is not None and eq > price + SMALL_BET_MARGIN:
                new["call"] += new["fold"]
                new["fold"] = 0.0
        if all(abs(new.get(k, 0.0) - dist.get(k, 0.0)) < 1e-12 for k in set(new) | set(dist)):
            return dist, None, detail
        return new, "small_bet", detail

    def opp_hyper_aggressive(self):
        """small-bet 'gated': does the opponent bet or raise after the flop far more often than we do (our
        own rate stands in for the blueprint's): at least AGGR_RATIO times as often, and by more than 2
        standard errors? A value-heavy small bettor bets about as often as a tag; a min-raiser always."""
        (no, ko), (nu, ku) = self.aggr["opp"], self.aggr["us"]
        if no < AGGR_MIN_N or nu < AGGR_MIN_N:
            return False
        po, pu = ko / no, ku / nu
        p = (ko + ku) / (no + nu)
        se = math.sqrt(p * (1.0 - p) * (1.0 / no + 1.0 / nu))
        return se > 0 and po >= AGGR_RATIO * pu and (po - pu) / se > 2.0

    # ---------------- per-match opponent counts (hand_result)

    def observe_hand_end(self, hs, rep, board):
        """Opponent counts for the preflop all-in rule (shoves per preflop spot) and the 'mix' river
        rule (river all-ins vs the blueprint's rate under their river-start range)."""
        if self.pre_table is not None:
            for st in rep.steps:
                if st.street != "preflop" or st.seat == hs.seat or st.node is None or st.node < 0:
                    continue
                node = B.PRE[st.node]
                if "allin" not in node["slots"]:
                    continue
                legal = {s: ok for s, ok, _ in B.slot_options_req("preflop", node, st.req)}
                if not legal.get("allin"):
                    continue
                c = self.pre_stats.setdefault(st.node, [0, 0])
                c[0] += 1
                c[1] += int(st.action == "raise" and st.amount == st.req.get("max_raise"))
        if self.small_mode == "gated":
            for st in rep.steps:
                if st.street == "preflop" or st.node is None or st.node < 0 or "raise" not in st.req["legal_actions"]:
                    continue
                a = self.aggr["us" if st.seat == hs.seat else "opp"]
                a[0] += 1
                a[1] += int(st.action == "raise")
        if self.solver_fold:
            steps = rep.steps
            for st, nxt in zip(steps, steps[1:]):
                if st.street == "river" and st.seat == hs.seat and st.action == "raise" \
                        and nxt.street == "river" and nxt.seat != hs.seat:
                    self.river_folds[0] += 1                    # a call or a raise counts as not folding
                    self.river_folds[1] += int(nxt.action == "fold")
        if self.river_rule == "mix" and "ranges" in hs.cache and len(board) == 5:
            w = hs.cache["ranges"].opp
            for rec in RG.action_records(rep, hs, 1 - hs.seat, ("river",)):
                pv = RG.river_allin_probs(self, hs, rep, board, rec)
                if pv is None:
                    continue
                p = float((w * pv).sum() / max(float(w.sum()), 1e-12))
                m = self.mix
                m["n"] += 1
                m["E"] += p
                m["V"] += p * (1.0 - p)
                m["O"] += int(RG.is_allin(rec))

    @staticmethod
    def opp_model():
        try:
            m = hooks.opp_model()
            return m if isinstance(m, dict) else None
        except Exception:
            return None

    @staticmethod
    def solver_dist(out, req):
        """Validate a river-solver distribution (§10) -> ({label: p}, {label: action}) or (None, None)."""
        if not isinstance(out, list) or not out:
            return None, None
        legal = req["legal_actions"]
        dist, options = {}, {}
        for e in out:
            if not isinstance(e, dict):
                continue
            a, p = e.get("action"), e.get("p")
            if a not in legal or isinstance(p, bool) or not isinstance(p, numbers.Real):
                continue
            p = float(p)
            if not math.isfinite(p) or p <= 0:
                continue
            if a == "raise":
                amt = e.get("amount")
                if isinstance(amt, bool) or not isinstance(amt, numbers.Integral):
                    continue
                amt = int(amt)
                if not req["min_raise"] <= amt <= req["max_raise"]:
                    continue
                label = f"raise:{amt}"
                options[label] = {"type": "action", "action": "raise", "amount": amt}
            else:
                label = a
                options[label] = {"type": "action", "action": a}
            dist[label] = dist.get(label, 0.0) + p
        total = sum(dist.values())
        if total <= 0:
            return None, None
        return {k: v / total for k, v in dist.items()}, options

    def decide_discard(self, hs, req, fagg, guard, stats):
        hole3 = sorted(C.parse_cards(req["hole_cards"]))
        if hole3 != hs.hole3:
            raise ValueError("discard_request hole cards differ from new_hand")
        board = C.parse_cards(req["board"])
        fi = self.flop_info(hs, board)
        pc = B.pot_class(req["pot"])
        cands = self.disc_candidates(fi["b3"], pc, fagg, hs.seat)
        row, level = self.first_usable("DISC", cands, DISC_NODE, [True, True, True])
        if row is None:
            stats.level("discard", "heuristic")
            dist = {"keep0": 1.0}
        else:
            stats.level("discard", level)
            dist = purify({f"keep{k}": float(p) for k, p in enumerate(row) if p > 0}, self.purify_eps)
        options = {}
        for k, pair in enumerate(fi["slots"]):
            options[f"keep{k}"] = C.format_card(next(c for c in hs.hole3 if c not in pair))
        ctx = DecisionContext(street="discard", request=req, node_id=0, options=options, bucket=fi["b3"],
                              prefix_key=("DISC", cands[0][1]), pc=pc, fagg=fagg, mode=None, source="discard")
        dist = guard.apply(hooks.exploit_adjust, ctx, dist)
        label = self.sample(dist, self.sample_key(hs, "discard", 0))
        k = int(label[-1])
        return options[label], k

    @staticmethod
    def sample_key(hs, street, index):
        """Integers only: str hashes are salted per process, int tuples hash the same everywhere."""
        return (hs.deal, hs.seat, SAMPLE_STREET.get(street, 9), int(index))

    def draw(self, key=None):
        seed = self.config.get("sample_seed")
        if seed is None or key is None:
            return self.rng.random()
        return random.Random(hash((int(seed),) + tuple(int(k) for k in key))).random()

    def sample(self, dist, key=None):
        labels = [k for k, v in dist.items() if v > 0]
        u = self.draw(key) * sum(dist[k] for k in labels)
        acc = 0.0
        for k in labels:
            acc += dist[k]
            if u < acc:
                return k
        return labels[-1]

    @staticmethod
    def action_for(slot, amounts, req):
        action = B.SLOT_ACTION[slot]
        if action != "raise":
            return {"type": "action", "action": action}
        amt = int(min(max(amounts[slot], req["min_raise"]), req["max_raise"]))
        return {"type": "action", "action": "raise", "amount": amt}

    @staticmethod
    def heuristic(node, req, opts, proxy):
        """§9.10 level 3: OPEN -> check; FACING -> call if the equity proxy beats the pot odds."""
        legal = {s for s, ok, _ in opts if ok}
        if "check" in legal:
            return "check"
        to_call, pot = req["to_call"], req["pot"]
        if proxy is None:                                   # preflop: the §9.2 rule
            good = to_call <= pot / 4
        else:
            good = proxy > to_call / max(pot + to_call, 1)
        if good and "call" in legal:
            return "call"
        return "fold" if "fold" in legal else next(iter(legal))

    def panic_action(self, hs, req, street, board):
        """§9.8 PANIC: one no-lookahead all-hands pass gives our percentile; bet pot if top 15%,
        call if top 50% and to_call <= pot/2, else check or fold."""
        S1, _ = F.all_features(F.street_rows(board, False))
        live = ~np.isin(C.COMBO, board).any(axis=1)
        mine = max(int(S1[C.idx2(*p)]) for p in (F.hand_pairs(hs.hole3) if len(hs.hole) == 3 else [tuple(hs.hole)]))
        pct = float((S1[live] < mine).mean())
        legal = req["legal_actions"]
        if pct >= 0.85 and "raise" in legal:
            target = req["opp_bet"] + req["pot"] + req["to_call"] if req["to_call"] > 0 else req["pot"]
            return {"type": "action", "action": "raise",
                    "amount": int(min(max(target, req["min_raise"]), req["max_raise"]))}
        if pct >= 0.5 and "call" in legal and req["to_call"] <= req["pot"] / 2:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "check" if "check" in legal else "fold"}
