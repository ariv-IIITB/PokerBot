"""Time manager (BUILDMAP §9.8), driven by costs measured on this machine, in this leg.

Each leg is a fresh process with its own bank (init.time_bank_ms) and hand count (init.total_hands).
Two budgets per remaining hand (hands_left = total_hands - hand_id + 1):
    B      = (time_left_ms - HARD_RESERVE x bank) / hands_left             hard: 10% is never planned against
    B_plan = (time_left_ms - (1 - TARGET_USE) x bank) / hands_left         the plan: use at most 67% of the bank
Four modes, richest first:
    NORMAL    blueprint + range tracking + river all-in rule + river solver
    NOSOLVER  blueprint + range tracking + river all-in rule; no river solver
    LEAN      blueprint only; no range tracking, so no river rule and no solver
    PANIC     one cheap feature pass per postflop decision
What a hand costs on this machine:
    lean   = our own decision time per hand without range tracking or the solver
    run    = lean + range tracking time per river hand x river hands per hand
    floor  = RIVER_MIN_MS x river decisions per hand (the least the solver is ever given)
    NORMAL    if B_plan >= run + floor + reserve   and B >= run x (1 + MARGIN) + floor + reserve
    NOSOLVER  if B_plan + slack >= run + reserve   and B >= run x (1 + MARGIN) + reserve
    LEAN      if B >= lean x (1 + MARGIN) + reserve
    PANIC     otherwise
NORMAL and NOSOLVER must fit the plan, at the costs as measured: going over the plan is corrected by
the next hands (a smaller B_plan steps them down), so the plan needs no margin, and a margin there
would push a 2x slower server into LEAN although NOSOLVER fits. slack = PLAN_SLACK (1%) x bank /
hands_left lets NOSOLVER run over the plan by at most 1% of the bank: at the end of a leg B_plan
swings by a whole hand's cost per remaining hand, and range tracking should not stop for that.
A leg therefore ends at the plan (+1%) as long as LEAN fits it: LEAN replaces NOSOLVER on as many
hands as needed (3x slower against an opponent who reaches the river every hand: about 60% of the
decisions). Only when even LEAN does not fit the plan (about 4x slower) does LEAN, judged against the
hard budget, spend beyond it; PANIC comes only when LEAN does not fit the hard budget.
MARGIN = 0.25 guards the hard budget. Costs are means of the last 30 hands, and the next hands can
cost more (a run of river hands, more raises, a busier machine). Measured on the M4 (600 hands each,
4 Nov), the mean of 30 hands against the leg mean, p5-p95:
    random     0.75-1.25   (12.9 ms per hand)
    raiser     0.63-1.41   (7.6 ms per hand)
    check/call 0.96-1.04   (26.8 ms per hand; a river every hand)
The opponents whose costs come near the budget (a river every hand) are also the steadiest, and the
volatile ones cost a tenth of the budget. 25% covers the p95 window; beyond it, overspending lowers
B, the next decisions step down, and the 10% hard reserve is the backstop.
TARGET_USE = 0.67, not 0.70: the plan converges on its target, and the end of a leg adds noise. With
a solver that sleeps for every budget, a 70% plan ended 24 legs at 69.6-70.3% of the bank; 0.67
keeps the worst leg under the 70% limit (BUILDMAP §11) with 3 points to spare.

Warm-up: in the first WARMUP_HANDS hands of a leg the bot stays NORMAL unless the bank itself is low
(B < LOW_BANK x the B it had at the start of the leg). The start-up speed reading can be several
times too slow when many processes start at once; it must not push a healthy bank into LEAN or PANIC.
After the warm-up the costs are our own measured decision times in this leg: lean = mean over the
last WINDOW hands, ranges = mean over the last WINDOW river hands, rates over the leg so far. A cost
not measured yet uses its M4 prior scaled by the speed this leg's measured lean cost shows
(lean / LEAN_M4); before any measurement, by the start-up speed factor (the fastest of 5 turn
street_rows passes / REF_MS). reserve: RESERVE_M4 x speed until 20 replies have been charged, then
the measured overhead per reply x replies per hand x (1 + MARGIN), at least RESERVE_MIN_MS; the
overhead is the engine-charged time (time_left_ms drops between our requests) minus our own timers
(0.15-0.3 ms per reply on the M4, 4 Nov). The prior scaled by speed would assume a 3x slower server
also has 3x the pipe overhead, and reserve 15 ms per hand that is never spent.

River solver budget in NORMAL (the solver takes what is left of the plan):
    afford_plan = (B_plan - run - reserve) / river decisions per hand
    afford_real = (B - run x (1 + MARGIN) - reserve) / river decisions per hand
budget = min(max(RIVER_MIN_MS, afford_plan), afford_real), at most RIVER_MAX_MS, 40% of the
per-reply limit and 2% of the bank left; 0 (skip the solver) if afford_real or the caps are under
RIVER_MIN_MS. After the warm-up NORMAL implies afford_plan >= RIVER_MIN_MS. A solver that always
spends its whole budget ends a leg near 67% of the bank.

Eval-only build switches (tools/build_bot.py refuses them for dist/): force_mode pins one mode for a
whole leg; slowdown K makes our own work K times slower (waits (K - 1) x each measured piece, see
wait_ms), to emulate a slower server.
"""
import collections
import time

NORMAL, NOSOLVER, LEAN, PANIC = "NORMAL", "NOSOLVER", "LEAN", "PANIC"
MODES = (NORMAL, NOSOLVER, LEAN, PANIC)
RANGE_MODES = (NORMAL, NOSOLVER)           # modes that track ranges and apply the river all-in rule

# M4 (Apple, numpy 1.26). REF_MS: fastest of 5 turn street_rows passes after a warm-up, median of 40
# fresh processes on the idle laptop, 4 Nov 2026 (95% CI 7.17-7.41 ms). Cost priors: Phase 7, the most
# expensive opponent measured (check/call, a river on nearly every hand); idle on 4 Nov: own 15.3
# ms/hand and ranges 11.6 ms per river hand vs check/call, own 10.7 vs random.
REF_MS = 7.26
LEAN_M4 = 16.0           # own ms per hand without range tracking
RANGE_M4 = 12.0          # range tracking ms per river hand
RIVER_HAND_RATE = 0.6    # share of hands with a river decision (prior; random 0.44, check/call 0.98)
RIVER_DECISION_RATE = 0.7  # river decisions per hand (prior; random 0.51, check/call 0.98)

RIVER_MIN_MS = 50.0      # the solver must be usable at this budget (§10, anytime); build flag --river-min-ms
RIVER_MAX_MS = 1500.0
TARGET_USE = 0.67        # plan to use at most this share of the bank (BUILDMAP §11: worst leg <= 70%)
HARD_RESERVE = 0.10      # never plan against this share of the starting bank (modes and budgets)
RESERVE_M4 = 3.0         # prior per-hand overhead the decision timers do not see (scaled by speed)
RESERVE_MIN_MS = 0.5     # the measured overhead per hand (with the margin) replaces the prior, at least this
PLAN_SLACK = 0.01        # NOSOLVER may run over the plan by at most this share of the bank
MARGIN = 0.25            # hard-budget thresholds: measured cost x (1 + MARGIN), see the docstring
WARMUP_HANDS = 20        # hands of a leg played NORMAL unless the bank itself is low
LOW_BANK = 0.5           # "the bank is low": B under this share of the B at the start of the leg
WINDOW = 30              # measured costs: mean over the last WINDOW hands (WINDOW river hands for ranges)
SPEED_MIN, SPEED_MAX = 0.25, 20.0


def now_ms():
    return time.perf_counter() * 1000.0


def wait_ms(ms):
    """Wait ms milliseconds, precisely (eval builds' emulated slowdown). macOS's time.sleep takes about
    1.5x what it is asked (5 ms -> 7.5 ms), which made a '2x' emulation about 2.5x: sleep for half of
    what is left while more than 2 ms remain, then spin."""
    end = time.perf_counter() + ms / 1000.0
    while True:
        rest = end - time.perf_counter()
        if rest <= 0:
            return
        if rest > 0.002:
            time.sleep(rest * 0.5)


class TimeManager:
    def __init__(self, speed_factor=1.0, force_mode=None, slowdown=1.0, river_min_ms=None):
        self.speed_factor = speed_factor
        self.river_min_ms = float(river_min_ms) if river_min_ms else RIVER_MIN_MS   # build flag --river-min-ms
        self.forced = force_mode if force_mode in MODES else None
        self.slowdown = max(1.0, float(slowdown or 1.0))
        self.total_hands = 500             # until init says otherwise: the longest leg (Stage 2)
        self.per_response_ms = 5000.0
        self.bank_ms = None
        self.B0 = None                     # B at the start of the leg
        self.modes = {m: 0 for m in MODES}
        self.street_ms = {}
        self.street_n = {}
        self.street_max = {}
        # per-hand accounting (current hand) and the leg so far
        self.cur = None
        self.hands = 0
        self.own_ms = 0.0                  # all our decision time except range tracking and the solver
        self.range_ms = 0.0
        self.range_hands = 0
        self.river_hands = 0
        self.river_decisions = 0
        self.solver_ms = 0.0
        self.solver_calls = 0
        self.budget_ms = 0.0
        self.recent_own = collections.deque(maxlen=WINDOW)
        self.recent_range = collections.deque(maxlen=WINDOW)
        self.dec = {"range": 0.0, "solver": 0.0}
        # engine-charged time vs our own timers (overhead), and the bank used
        self.first_time_left = None
        self.last_time_left = None
        self.last_reply_ms = None
        self.final_reply_ms = 0.0
        self.charged_ms = 0.0
        self.timed_ms = 0.0
        self.replies_obs = 0
        self.replies = 0

    def set_match(self, total_hands, per_response_ms, time_bank_ms=None):
        """From init: this leg's hand count, reply limit and bank."""
        self.total_hands = max(1, int(total_hands))
        self.per_response_ms = float(per_response_ms)
        if time_bank_ms:
            self.bank_ms = float(time_bank_ms)

    # ---------------- emulated slowdown (eval builds only)

    def emulate(self, ms):
        """Sleep (slowdown - 1) x ms: our own work, K times slower."""
        if self.slowdown > 1.0 and ms > 0:
            wait_ms((self.slowdown - 1.0) * ms)

    # ---------------- accounting

    def begin_hand(self, hand_id):
        self.end_hand()
        self.cur = {"own": 0.0, "range": 0.0, "river": 0}

    def end_hand(self):
        c = self.cur
        if c is None:
            return
        self.hands += 1
        self.own_ms += c["own"]
        self.recent_own.append(c["own"])
        if c["range"] > 0:
            self.range_ms += c["range"]
            self.range_hands += 1
            self.recent_range.append(c["range"])
        if c["river"]:
            self.river_hands += 1
            self.river_decisions += c["river"]
        self.cur = None

    def add(self, own_ms=0.0, range_ms=0.0, solver_ms=0.0, river_decision=False):
        if self.cur is None:
            self.cur = {"own": 0.0, "range": 0.0, "river": 0}
        self.cur["own"] += own_ms
        self.cur["range"] += range_ms
        self.cur["river"] += 1 if river_decision else 0
        self.solver_ms += solver_ms

    def observe(self, req):
        """Call when a request arrives: the drop in time_left_ms since the previous request is what the
        engine charged for our previous reply."""
        try:
            tl = float(req["time_left_ms"])
        except Exception:
            return
        if self.bank_ms is None:
            self.bank_ms = tl
        if self.first_time_left is None:
            self.first_time_left = tl
        if self.last_time_left is not None and self.last_reply_ms is not None:
            charged = self.last_time_left - tl
            if charged > 0:                     # 0 inside the engine's free start-up window
                self.charged_ms += charged
                self.timed_ms += self.last_reply_ms
                self.replies_obs += 1
        self.last_time_left = tl
        self.last_reply_ms = None

    def replied(self, ms):
        self.last_reply_ms = ms
        self.final_reply_ms = ms
        self.replies += 1

    def begin_decision(self):
        self.dec = {"range": 0.0, "solver": 0.0}

    def note_range(self, ms):
        self.dec["range"] += ms

    def note_solver(self, ms, budget):
        self.dec["solver"] += ms
        self.solver_calls += 1
        self.budget_ms += budget

    def record(self, street, ms):
        self.street_ms[street] = self.street_ms.get(street, 0.0) + ms
        self.street_n[street] = self.street_n.get(street, 0) + 1
        self.street_max[street] = max(self.street_max.get(street, 0.0), ms)

    # ---------------- estimates (ms per hand on this machine)

    def speed(self):
        """Machine speed vs the M4: from our own measured lean cost after the warm-up, else start-up."""
        if self.hands >= WARMUP_HANDS and self.recent_own:
            s = (sum(self.recent_own) / len(self.recent_own)) / LEAN_M4
            return min(SPEED_MAX, max(SPEED_MIN, s))
        return self.speed_factor

    def costs(self):
        s = self.speed()
        warm = self.hands >= WARMUP_HANDS
        n = self.hands
        lean = sum(self.recent_own) / len(self.recent_own) if (warm and self.recent_own) else LEAN_M4 * s
        rng = (sum(self.recent_range) / len(self.recent_range) if (warm and self.recent_range)
               else RANGE_M4 * s)
        hand_rate = self.river_hands / n if warm else RIVER_HAND_RATE
        dec_rate = self.river_decisions / n if warm else RIVER_DECISION_RATE
        reserve = RESERVE_M4 * s
        if self.replies_obs >= 20 and n:              # measured: what the engine charged beyond our timers
            per_reply = max(0.0, (self.charged_ms - self.timed_ms) / self.replies_obs)
            reserve = max(RESERVE_MIN_MS, (1.0 + MARGIN) * per_reply * self.replies / n)
        run = lean + rng * hand_rate
        return {"lean": lean, "range": rng, "hand_rate": hand_rate, "river_rate": max(dec_rate, 0.05),
                "run": run, "full": run * (1.0 + MARGIN), "lean_m": lean * (1.0 + MARGIN), "reserve": reserve,
                "speed": s}

    def budgets(self, req, hand_id, total_hands):
        """(B, B_plan, hands_left): ms per remaining hand of the leg above the hard reserve, and within the
        plan."""
        hands_left = max(1, int(total_hands) - int(hand_id) + 1)
        time_left = float(req["time_left_ms"])
        if self.bank_ms is None:
            self.bank_ms = time_left
        B = (time_left - HARD_RESERVE * self.bank_ms) / hands_left
        B_plan = (time_left - (1.0 - TARGET_USE) * self.bank_ms) / hands_left
        if self.B0 is None:
            self.B0 = (self.bank_ms - HARD_RESERVE * self.bank_ms) / max(1, int(total_hands))
        return B, B_plan, hands_left

    def per_hand(self, req, hand_id, total_hands):
        """B: ms per remaining hand of the leg, after setting aside the hard reserve."""
        return self.budgets(req, hand_id, total_hands)[0]

    def pick(self, B, B_plan, hands_left=None):
        """The richest mode the budgets afford (after the warm-up): NORMAL and NOSOLVER must fit the plan
        at measured cost (NOSOLVER with the slack) and the hard budget with the margin; LEAN the hard
        budget with the margin."""
        c = self.costs()
        floor = c["river_rate"] * self.river_min_ms
        slack = PLAN_SLACK * self.bank_ms / hands_left if (hands_left and self.bank_ms) else 0.0
        if B_plan >= c["run"] + floor + c["reserve"] and B >= c["full"] + floor + c["reserve"]:
            return NORMAL
        if B_plan + slack >= c["run"] + c["reserve"] and B >= c["full"] + c["reserve"]:
            return NOSOLVER
        if B >= c["lean_m"] + c["reserve"]:
            return LEAN
        return PANIC

    def mode(self, req, hand_id, total_hands=None):
        if self.forced:
            m = self.forced
        else:
            try:
                B, B_plan, hands_left = self.budgets(req, hand_id, total_hands or self.total_hands)
            except Exception:
                m = NORMAL
            else:
                if self.hands < WARMUP_HANDS and B >= LOW_BANK * self.B0:
                    m = NORMAL                  # warm-up: only a low bank leaves NORMAL
                else:
                    m = self.pick(B, B_plan, hands_left)
        self.modes[m] += 1
        return m

    def river_budget_ms(self, req, hand_id, total_hands=None):
        try:
            total = total_hands or self.total_hands
            time_left = float(req["time_left_ms"])
            B, B_plan, _ = self.budgets(req, hand_id, total)
        except Exception:
            return 0.0
        c = self.costs()
        afford_real = (B - c["full"] - c["reserve"]) / c["river_rate"]
        floor = self.river_min_ms
        if afford_real < floor:
            return 0.0
        afford_plan = (B_plan - c["run"] - c["reserve"]) / c["river_rate"]
        budget = min(max(floor, afford_plan), afford_real)
        budget = min(budget, RIVER_MAX_MS, 0.4 * self.per_response_ms, 0.02 * time_left)
        return budget if budget >= floor else 0.0

    def bank_used_ms(self):
        """Engine-charged time so far: the bank minus the last time_left_ms, plus our last reply."""
        if self.bank_ms is None or self.last_time_left is None:
            return 0.0
        return max(0.0, self.bank_ms - self.last_time_left + self.final_reply_ms)

    def summary(self):
        self.end_hand()
        n = max(1, self.hands)
        c = self.costs()
        over = (self.charged_ms - self.timed_ms) / self.replies_obs if self.replies_obs else 0.0
        used = self.bank_used_ms()
        pct = 100.0 * used / self.bank_ms if self.bank_ms else 0.0
        return (f"overhead {over:.2f} ms per reply (engine-charged minus own timers, {self.replies_obs} replies); "
                f"own time per hand {self.own_ms / n:.1f} ms + ranges {self.range_ms / max(1, self.range_hands):.1f} ms "
                f"per river hand ({self.range_hands} hands), river decisions/hand {self.river_decisions / n:.2f}, "
                f"solver {self.solver_calls} calls {self.solver_ms:.0f} ms (budget {self.budget_ms:.0f} ms); "
                f"estimates lean {c['lean']:.1f} full {c['full']:.1f} ms/hand at speed {c['speed']:.2f}; "
                f"bank used {used:.0f} of {self.bank_ms or 0:.0f} ms ({pct:.1f}%); "
                f"forced {self.forced}; slowdown {self.slowdown:g}; solver floor {self.river_min_ms:g} ms; modes {self.modes}")
