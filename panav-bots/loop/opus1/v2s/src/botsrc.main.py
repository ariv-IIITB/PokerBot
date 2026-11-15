"""The bot's protocol loop (BUILDMAP §9.1, §9.2). Entry point: run(blob_b64, version) from dist/bot.py.

Never crashes: every message is handled inside try/except; requests always get a legal reply
(fallback action / discard on any error); only protocol JSON reaches stdout.
"""
import json
import sys

from shared import abstraction as AB
from shared import blob as BL
from shared import cards as C
from shared import features as F
from shared import infoset as I

from . import hooks
from . import potfold as PF
from . import protocol as P
from .log import log
from .policy import ExploitGuard, Policy
from .state import HandState, replay
from .timeman import TimeManager, now_ms

STREET_ORDER = ("preflop", "flop", "turn", "river", "discard")
EVAL_BUILD_MARK = "DHBOT EVAL BUILD"          # eval/match_checks.py looks for this
EVAL_ONLY = ("sample_seed", "force_mode", "slowdown", "solver_passes", "river_solver_file", "solver_box_ms",
             "solver_buckets")                                                              # evaluation only
DEFAULT_LEG_HANDS = 500       # if init has no usable total_hands: the longest leg (Stage 2), so we under-spend


def leg_hands(msg):
    """This leg's hand count from init (every leg is a fresh process with its own init)."""
    try:
        n = int(msg.get("total_hands"))
    except Exception:
        return DEFAULT_LEG_HANDS
    return n if 1 <= n <= 100000 else DEFAULT_LEG_HANDS


class Stats:
    def __init__(self):
        self.decisions = {s: 0 for s in STREET_ORDER}
        self.levels = {s: {} for s in STREET_ORDER}
        self.river = {}
        self.rules = {}                         # Phase 9 rule counters (preflop all-in, small bets, mix)
        self.rule_first = {}                    # rule event -> hand_id of its first occurrence in this leg
        self.errors = 0
        self.error_kinds = {}
        self.fallback_replies = 0
        self.river_modes = {}                   # river decisions by time-manager mode

    def level(self, street, level):
        self.decisions[street] += 1
        d = self.levels[street]
        d[level] = d.get(level, 0) + 1

    def error(self, where, exc):
        self.errors += 1
        key = f"{where}: {type(exc).__name__}"
        self.error_kinds[key] = self.error_kinds.get(key, 0) + 1
        if self.error_kinds[key] <= 3:
            log(f"error in {where}: {type(exc).__name__}: {exc}")

    def summary(self):
        parts = []
        for s in STREET_ORDER:
            n = self.decisions[s]
            lv = self.levels[s]
            fb = {k: v for k, v in lv.items() if k != "table"}
            share = " ".join(f"{k} {100.0 * v / n:.2f}%" for k, v in sorted(fb.items())) if n else ""
            parts.append(f"{s} {n}" + (f" [{share}]" if share else ""))
        return "decisions (fallback levels as % of decisions): " + "; ".join(parts)


class Bot:
    def __init__(self, blob_b64, version, config=None):
        t0 = now_ms()
        header, arrays = BL.decode_blob(blob_b64)
        meta = header["meta"]
        A = AB.get(meta.get("abstraction"))           # a1 blobs have no such key
        L = I.layout(A)
        th = F.Thresholds.from_json_bytes(arrays["THRESHOLDS"].tobytes(), expect_sha=meta["thresholds_sha"],
                                          abstraction=A)
        tables = {}
        for t in L.TABLES:
            a = arrays[t]
            if a.shape != (L.PREFIXES[t], L.SLOTS[t]):
                raise ValueError(f"strategy table {t} has shape {a.shape}")
            tables[t] = a
        self.abstraction = A.name
        canon3 = arrays["CANON3"]
        if canon3.shape != (22100,):
            raise ValueError("CANON3 has the wrong shape")
        self.config = dict(config or {})
        self.policy = Policy(tables, th, canon3, self.config)
        self.decode_ms = now_ms() - t0
        slowdown = float(self.config.get("slowdown", 1.0) or 1.0)
        self.speed_factor = self.calibrate(slowdown)
        self.tm = TimeManager(self.speed_factor, force_mode=self.config.get("force_mode"), slowdown=slowdown,
                              river_min_ms=self.config.get("river_min_ms"))
        self.guard = ExploitGuard()
        self.potfold = PF.PotFold(self.config) if self.config.get("potfold") == "on" else None
        self.stats = Stats()
        self.version = version
        self.total_hands = DEFAULT_LEG_HANDS
        self.hs = None
        self.startup_ms = now_ms() - t0
        import numpy
        log(f"bot ready: numpy {numpy.__version__}; {json.dumps(version, sort_keys=True)}; strategy {meta.get('mode')} from "
            f"{meta.get('source')}; abstraction {self.abstraction}; config {self.config}; decode {self.decode_ms:.0f} ms, "
            f"start-up {self.startup_ms:.0f} ms, speed factor {self.speed_factor:.2f}")
        pol = self.policy
        if pol.solver_mode != "off":
            log(f"river solver setup: mode {pol.solver_mode}, " + (
                f"loaded (teammate's river_solver.py behind river_glue; pinned passes "
                f"{self.config.get('solver_passes')}; steps aside when raised {'on' if pol.solver_out else 'off'}, "
                f"fold read {'on' if pol.solver_fold else 'off'})"
                if pol.solver is not None else f"NOT LOADED ({pol.solver_error}): the stub plays"))
        evals = {k: self.config[k] for k in EVAL_ONLY if self.config.get(k) is not None}
        if evals:
            log(f"{'!' * 78}\n{EVAL_BUILD_MARK}: {evals} (eval-only switches: seeded sampling, forced mode or "
                f"emulated slowdown).\nNEVER UPLOAD THIS FILE: tournament builds must not use them.\n{'!' * 78}")

    @staticmethod
    def calibrate(slowdown=1.0):
        """speed_factor = one turn street_rows pass in ms / REF_MS (the M4 reference), §9.1. The fastest
        of five passes after a warm-up: contention can only add time, so the fastest pass is closest to
        the machine's own speed (idle M4: 7.0-9.1 ms at p10-p90, against 7.4-13.2 for a median of 3).
        It is only a prior: after the warm-up the time manager uses the leg's own measured times."""
        from .timeman import REF_MS, wait_ms
        board = [0, 13, 26, 39]
        F.street_rows(board, True)                      # warm-up
        times = []
        for _ in range(5):
            t0 = now_ms()
            F.street_rows(board, True)
            dt = now_ms() - t0
            if slowdown > 1.0:                          # eval builds: emulate a slower machine
                wait_ms((slowdown - 1.0) * dt)
            times.append(now_ms() - t0)
        return min(20.0, max(0.25, min(times) / REF_MS))

    # ---------------- messages

    def handle(self, msg):
        t = msg.get("type")
        reply = None
        if t == "action_request":
            reply = self.on_action(msg)
        elif t == "discard_request":
            reply = self.on_discard(msg)
        else:
            try:
                if t == "init":
                    self.total_hands = leg_hands(msg)
                    if self.potfold is not None and isinstance(msg.get("starting_stack"), int):
                        self.potfold.start_stack = msg["starting_stack"]
                    self.tm.set_match(self.total_hands, msg.get("per_response_ms", 5000), msg.get("time_bank_ms"))
                elif t == "new_hand":
                    self.hs = None
                    self.tm.begin_hand(msg.get("hand_id"))
                    self.hs = HandState(msg, mirror=self.policy.mirror)
                elif t == "discard_result" and self.hs is not None:
                    self.hs.on_discard_result(msg)
                elif t == "notice" and self.hs is not None:
                    self.hs.on_notice(msg)
                elif t == "hand_result" and self.hs is not None:
                    if self.potfold is not None:
                        self.potfold.on_hand_result(msg)
                    self.on_hand_end(msg)
                elif t == "match_end":
                    self.finish()
            except Exception as e:
                self.stats.error(t or "message", e)
        self.forward(msg)
        return reply

    def forward(self, msg):
        if self.guard.disabled:
            return
        t0 = now_ms()
        try:
            hooks.on_event(msg)
        except Exception:
            self.guard.errors += 1
        self.guard.charge(now_ms() - t0)

    def on_action(self, req):
        t0 = now_ms()
        self.tm.observe(req)
        street = req.get("street") if isinstance(req.get("street"), str) else "?"
        counted = self.stats.decisions.get(street)
        self.tm.begin_decision()
        reply = None
        try:
            hs = self.hs
            if hs is None or req.get("hand_id") != hs.hand_id:
                raise ValueError("action_request for an unknown hand")
            rep = replay(hs, req["history"])
            if rep.error is not None or rep.lost:
                raise ValueError(f"history replay: {rep.error or 'action off the tree'}")
            if rep.current_street != street or rep.current_node is None or rep.current_node < 0 \
                    or rep.current_state is None or rep.current_state.actor != hs.seat:
                raise ValueError("history does not lead to our decision on this street")
            mode = self.tm.mode(req, hs.hand_id, self.total_hands)
            if street == "river":
                self.stats.river_modes[mode] = self.stats.river_modes.get(mode, 0) + 1
            reply, slot, node_id = self.policy.decide_action(hs, req, rep, mode, self.guard, self.stats, self.tm)
            if self.potfold is not None:
                try:
                    px = hs.cache.get("pf_proxy")
                    new = self.potfold.maybe(hs, req, reply, px, self.policy.draw((hs.deal, hs.seat, 11, len(req["history"]))))
                    if new is not reply and P.legal_reply(new, req):
                        reply, slot = new, "fold"
                except Exception as e:
                    self.stats.error("potfold", e)
            if not P.legal_reply(reply, req):
                raise ValueError(f"policy produced an illegal reply {reply}")
            hs.record_own(req, reply, node_id, slot)
        except Exception as e:
            self.stats.error(f"action/{street}", e)
            self.stats.fallback_replies += 1
            if counted is not None and self.stats.decisions[street] == counted:
                self.stats.level(street, "error")
            reply = P.fallback_action(req)
            try:
                if self.hs is not None:
                    self.hs.record_own(req, reply, None, None)
            except Exception:
                pass
        dec = self.tm.dec
        self.tm.emulate(now_ms() - t0 - dec["range"] - dec["solver"])      # eval: slower machine (no-op)
        total = now_ms() - t0
        self.tm.add(own_ms=total - dec["range"] - dec["solver"], range_ms=dec["range"], solver_ms=dec["solver"],
                    river_decision=street == "river")
        self.tm.record(street, total)
        self.tm.replied(now_ms() - t0)
        return reply

    def on_discard(self, req):
        t0 = now_ms()
        self.tm.observe(req)
        counted = self.stats.decisions["discard"]
        reply = None
        try:
            hs = self.hs
            if hs is None or req.get("hand_id") != hs.hand_id:
                raise ValueError("discard_request for an unknown hand")
            rep = replay(hs, hs.history_after)
            fagg = rep.fagg if rep.error is None else 0
            card, k = self.policy.decide_discard(hs, req, fagg, self.guard, self.stats)
            if card not in req["hole_cards"]:
                raise ValueError("discard is not one of our hole cards")
            hs.keep_slot = k
            reply = {"type": "discard", "card": card}
        except Exception as e:
            self.stats.error("discard", e)
            self.stats.fallback_replies += 1
            if self.stats.decisions["discard"] == counted:
                self.stats.level("discard", "error")
            reply = self.fallback_discard(req)
        self.tm.emulate(now_ms() - t0)                                    # eval: slower machine (no-op)
        total = now_ms() - t0
        self.tm.add(own_ms=total)
        self.tm.record("discard", total)
        self.tm.replied(now_ms() - t0)
        return reply

    def on_hand_end(self, msg):
        """Per-match opponent counts the preflop all-in rule and the 'mix' river rule need (only when
        one of them is on). Timed as "hand_end" in the time-per-decision log."""
        if not self.policy.wants_hand_end or msg.get("hand_id") != self.hs.hand_id:
            return
        t0 = now_ms()
        try:
            hist = msg.get("history")
            if isinstance(hist, list):
                rep = replay(self.hs, hist)
                if rep.error is None:
                    board = C.parse_cards(msg.get("board") or [])
                    self.policy.observe_hand_end(self.hs, rep, board)
        except Exception as e:
            self.stats.error("hand_result", e)
        self.tm.emulate(now_ms() - t0)
        ms = now_ms() - t0
        self.tm.record("hand_end", ms)
        self.tm.add(own_ms=ms)                  # it delays our next reply, so it is our own time

    def fallback_discard(self, req):
        """§9.2: keep slot 0 if the flop features exist, else the engine's own default card."""
        hole = req.get("hole_cards") if isinstance(req, dict) else None
        try:
            hs = self.hs
            fi = self.policy.flop_info(hs, C.parse_cards(req["board"]))
            card = C.format_card(next(c for c in hs.hole3 if c not in fi["slots"][0]))
            if card in hole:
                return {"type": "discard", "card": card}
        except Exception:
            pass
        card = P.default_discard(hole)
        return {"type": "discard", "card": card if card is not None else ""}

    def emergency(self, msg):
        """Last resort if handle() itself raised: a legal-looking reply for requests, else nothing."""
        t = msg.get("type") if isinstance(msg, dict) else None
        if t == "action_request":
            return P.fallback_action(msg)
        if t == "discard_request":
            card = P.default_discard(msg.get("hole_cards"))
            return {"type": "discard", "card": card if card is not None else ""}
        return None

    def finish(self):
        if getattr(self, "_finished", False):
            return
        self._finished = True
        tm = self.tm
        per = "; ".join(f"{s} {tm.street_ms[s] / tm.street_n[s]:.1f} ms (max {tm.street_max.get(s, 0.0):.1f}) x "
                        f"{tm.street_n[s]}" for s in STREET_ORDER + ("hand_end",) if tm.street_n.get(s))
        log(self.stats.summary())
        log(f"time: {tm.summary()}")
        log(f"river: {self.stats.river}")
        log(f"rules: {self.stats.rules}; preflop spots {self.policy.pre_stats}; mix {self.policy.mix}; "
            f"aggression {self.policy.aggr}")
        log(f"rules first acted at hand: {self.stats.rule_first}")
        log(f"fallbacks: {self.stats.fallback_replies} fallback replies, {self.stats.errors} errors "
            f"{self.stats.error_kinds}; modes {tm.modes}; time per decision: {per}")
        g = self.guard
        log(f"exploit hook: {g.calls} calls, {g.total_ms:.1f} ms, {g.over} over {5} ms, {g.errors} errors, "
            f"{g.capped} capped, disabled {g.disabled}")
        try:
            xs = hooks.exploit_summary()
            if xs is not None:
                log(f"exploit layer: {xs}")
        except Exception as e:
            log(f"exploit layer: summary failed ({type(e).__name__})")
        if self.potfold is not None:
            log(f"potfold: {self.potfold.summary()}")
        log(self.match_end_line())
        if self.policy.solver is not None:              # last: the eval harness needs the lines above first
            try:
                log(f"river solver summary: {dict(self.policy.solver.summary(), river_folds=list(self.policy.river_folds))}")
            except Exception as e:
                log(f"river solver summary: failed ({type(e).__name__})")
        if log.dropped:
            log(f"log: {log.dropped} lines dropped at the {log.limit} byte cap")


    def match_end_line(self):
        """stderr at match_end: the speed factors and who played our river decisions. The measured speed
        is the time manager's (own time per hand in this leg / its M4 prior, after the warm-up); the
        shares split our river decisions into: the solver's answer, NORMAL without it (no budget, a
        fallback, or the rule / blueprint in a spot the solver leaves alone), NOSOLVER, LEAN, PANIC."""
        from .timeman import LEAN, NORMAL, NOSOLVER, PANIC
        n = self.stats.decisions.get("river", 0)
        rm = self.stats.river_modes
        solver = self.stats.levels.get("river", {}).get("solver", 0)
        parts = {"solver": solver, "NORMAL without the solver": rm.get(NORMAL, 0) - solver,
                 "NOSOLVER": rm.get(NOSOLVER, 0), "LEAN": rm.get(LEAN, 0), "PANIC": rm.get(PANIC, 0)}
        other = n - sum(rm.values())
        if other > 0:
            parts["no mode (an error first)"] = other
        share = ", ".join(f"{k} {100.0 * v / n:.1f}%" for k, v in parts.items()) if n else "none"
        return (f"match end: speed factor {self.speed_factor:.2f} at start-up, {self.tm.speed():.2f} measured; "
                f"river decisions {n}: {share}")


class FallbackBot:
    """Used only if the strategy could not be loaded: plays the §9.2 fallback, never crashes."""

    def __init__(self, error):
        self.stats = Stats()
        banner = "!" * 78
        log(f"{banner}\nDHBOT DEGRADED: the strategy failed to load ({type(error).__name__}: {error})\n"
            f"Playing fallback actions only: this match does NOT use the strategy.\n{banner}")

    def handle(self, msg):
        t = msg.get("type")
        if t == "action_request":
            return P.fallback_action(msg)
        if t == "discard_request":
            card = P.default_discard(msg.get("hole_cards"))
            return {"type": "discard", "card": card if card is not None else ""}
        return None

    def emergency(self, msg):
        return self.handle(msg)

    def finish(self):
        pass


def run(blob_b64, version, config=None):
    out = sys.stdout
    sys.stdout = sys.stderr                     # nothing but protocol replies reaches the real stdout
    try:
        bot = Bot(blob_b64, version, config)
    except Exception as e:
        bot = FallbackBot(e)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        try:
            reply = bot.handle(msg)
        except Exception:
            reply = bot.emergency(msg)
        if reply is not None:
            try:
                out.write(json.dumps(reply) + "\n")
                out.flush()
            except Exception:
                pass
        if msg.get("type") == "match_end":
            break
    try:
        bot.finish()
    except Exception:
        pass
