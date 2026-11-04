"""Tier 3: the "Ivey" style, on top of Tier 2 (Phase G).

    relentless initiative · defend by MDF, not raw equity · floats · light 3-bets and 4-bets with
    blockers · small high-frequency bets on paired/dry boards · size by board and range, never by hand
    strength · mixed (randomised) decisions · capped live adaptation

Tier 3 IS Tier 2 (equity, inference, fast discard, endgame lock, legality, per-spot opponent stats with
the bluff index) with a different policy for the betting rounds:

    preflop     probability tables per spot from the 3-card class table (bot/strategy/preflop.py)
    flop        c-bets by texture as the preflop raiser, MDF defence with check-raises and floats,
                small stabs in position
    turn        polarised barrels, floated hands keep betting, MDF x the bluff index when facing bets
    river       value-bet the top third of our own range, bluffs at the bluff share of the bet;
                FACING a river bet is Tier 2's bluff-catching rule (the bluff index), never MDF:
                Tier 2 loses its big pots at river showdowns to value-heavy bettors
    discard     Tier 2's sampled discard, optionally hiding information (hide_discard)

Every behaviour sits behind a flag in DEFAULTS and every number is a parameter, so `lab.eval
tier3:{json}` can ablate and sweep it. If anything is missing (tables, a feature) or raises, the decision
falls back to Tier 2's, so Tier 3 can never play worse than Tier 2 by crashing. With "t3": false it IS
Tier 2. The default brain stays Tier 2 until the ship decision (docs/PART4_PLAN.md, G8).
"""
from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

from bot.actions import CALL, CHECK, FOLD, RAISE, Action, LegalActions, safe_action
from bot.brains.exploit import EXPLOIT_DEFAULTS, overfolder_lambda, valueonly_lambda
from bot.brains.tier2 import DEFAULTS as TIER2_DEFAULTS
from bot.brains.params import load_params, per_street
from bot.brains.tier2 import Tier2Brain
from bot.log import warn
from bot.sim.inference import DEFAULTS as INFERENCE_DEFAULTS
from bot.sim.inference import Inference
from bot.situation import Situation
from bot.state import ME, OPP, GameState, HandState
from bot.strategy.potmath import bluff_share, mdf
from bot.strategy.preflop import (FOLD_COL, PASSIVE_COL, RAISE_COL, PreflopModel, Spot, blend_above,
                                  preflop_spot)
from bot.strategy.own_range import own_range_weights
from bot.strategy.ranges import OwnRange
from bot.strategy.river_solver import INF, RiverSpot, TreeCfg, hand_ranks, solve_river
from bot.strategy.texture import best_keep, blocker_score, board_texture
from bot.timing import TimingConfig

DEFAULTS: dict[str, Any] = dict(TIER2_DEFAULTS)
DEFAULTS.update({
    # ---- switches (False everywhere = Tier 2)
    "t3": True,
    "t3_preflop": True,
    "t3_flop": True,
    "t3_turn": True,
    "t3_river": True,
    "t3_adapt": True,              # use the per-spot opponent stats (gated, capped; always on the prior until 20 samples)
    "hide_discard": False,         # G7: among near-equal discards, reveal the least (A/B before use)
    "hide_margin": 0.01,           # ... "near-equal" = within this much expected share of the best
    "range_samples": 300,          # hands sampled for our own-range percentile
    # ---- guards against wide, big-betting opponents (Phase G fix; see docs/reports/TIER3.md)
    "eq_floor": True,              # never fold (preflop, flop, turn) a hand Tier 2's pot-odds rule calls
    "mdf_eq_slack": 0.05,          # an MDF call needs equity >= pot odds - this (None = no floor)
    "bluff_tilt_scale": True,      # 3-bet / 4-bet bluff mass x (1 + tilt): none vs players who never fold
    "value_floor": True,           # postflop, never check or just call a hand Tier 2 would value-raise ...
    "value_floor_size": "t2",      # ... "t2": Tier 2 takes the decision (its adapted sizes); "t3": texture sizes
    "value_floor_gate": True,      # ... only as often as the opponent fails to fold to turn/river bets (gated, capped)
    # ---- preflop (G2): shares of ALL starting hands, positions are heads-up
    "pf_band": 0.04,               # linear blend width around every cutoff (no hard edges)
    "pf_play_weight": 0.35,        # playability's weight against strength in the combined percentile
    "pf_open_fold": 0.05,          # button first in: fold the bottom ...
    "pf_open_limp": 0.25,          # ... limp the next, raise the rest (~70 %)
    "pf_open_size_bb": 2.5,
    "pf_trap_zone": 0.04,          # the best hands limp as traps ...
    "pf_trap_prob": 0.25,          # ... this often
    "pf_bb_defend": 0.70,          # big blind vs a 2.5 bb raise: call + 3-bet
    "pf_defend_slope": 0.20,       # less defence per extra big blind of raise (more vs min-raises)
    "pf_ratio_slope": 0.12,        # button vs a 3-bet: less continuing per unit of 3-bet size ratio
    "pf_size_pressure": False,     # scale both slopes like Tier 2's bet_pressure (to 0 vs players who raise nearly always)
    "pf_3bet": 0.16,               # total 3-bet share: value + blocker bluffs
    "pf_3bet_value": 0.08,
    "pf_3bet_mult": 3.6,           # 3-bet to this x their raise (2.5 bb -> ~9 bb)
    "pf_iso": 0.40,                # big blind vs a limp: raise this share ...
    "pf_iso_size_bb": 4.0,         # ... to this many big blinds
    "pf_btn_continue": 0.60,       # button vs a 3-bet: continue (mostly call) ...
    "pf_4bet": 0.08,               # ... re-raise this share (top 3 % value + blocker bluffs) ...
    "pf_4bet_value": 0.03,
    "pf_4bet_mult": 2.2,           # ... to this x their 3-bet
    "pf_adapt_open_limp": 0.05,    # limp share left when the big blind raises our limps a lot
    "pf_adapt_3bet": 0.06,         # more 3-bet bluffs per unit of "they fold to 3-bets"
    # ---- flop (G3, G4)
    "cbet_dry_freq": 0.80,         # range-bet this share of hands on dry, paired and high-card boards ...
    "cbet_dry_size": 0.33,         # ... at this x pot
    "cbet_wet_size": 0.70,         # polarised on wet boards
    "cbet_value_eq": 0.62,
    "cbet_semi_strong": 0.65,      # semi-bluff share with a flush or open-ended draw
    "cbet_semi_gut": 0.40,
    "cbet_air_wet": 0.12,
    "cbet_wet_cut": 0.35,          # wet score above which a board is "wet"
    "checkback_medium": 0.70,      # medium hands check back on boards that favour the caller
    "medium_lo": 0.35,
    "lead_freq": 0.04,             # big blind leads into the preflop raiser with its strongest hands
    "stab_dry_freq": 0.45,         # in position after a check: small bet on dry / paired boards ...
    "stab_dry_size": 0.33,
    "stab_wet_freq": 0.20,
    "stab_wet_size": 0.50,
    "mdf_flop": 0.95,              # continue this share of the MDF with the top slice of our range
    "mdf_turn": 0.90,
    "mdf_band": 0.06,
    "cont_min_eq": 0.10,           # below this equity (and no outs) we do not pay, MDF or not
    "raise_value_eq": 0.80,        # raise a bet with at least this equity ...
    "raise_value_prob": 0.65,
    "raise_semi_prob": 0.35,       # ... or semi-bluff-raise strong draws this often (flop only)
    "raise_gut_prob": 0.15,
    "raise_frac": 0.80,
    "float_freq": 0.35,            # in position, call a bet without showdown value but with outs / overcards ...
    "float_max_bet": 0.75,         # ... a bet up to this x pot ...
    "float_turnbet_max": 0.50,     # ... when they give up the turn this often (their turn bet rate when checked to)
    # ---- turn (G5)
    "barrel_size": 0.70,
    "barrel_value_eq": 0.65,
    "barrel_semi_prob": 0.70,
    "barrel_bluff_prob": 0.15,     # air with blockers
    "float_bet_prob": 0.65,        # a floated hand bets when checked to ...
    "float_bet_prob_max": 0.85,    # ... more if they fold the turn a lot
    # ---- river (G5)
    "river_value_share": 1 / 3,    # value-bet the top third of our range ...
    "river_size_lo": 0.66,         # ... for 66 % of the pot ...
    "river_size_hi": 1.00,         # ... up to a pot-sized bet with the best of it
    "river_overbet": 1.25,         # a rare overbet with the nuts
    "river_overbet_prob": 0.30,
    "river_air_eq": 0.18,          # bluff only with less equity than this
    "river_air_share": 0.35,       # roughly how much of our range that is
    # ---- river solver (Tier 4, sub-plan R): off unless asked for, falls back to the rules above
    "t3_river_solver": False,      # solve each river decision (CFR+ on bucketed ranges) instead of the rules above
    "river_budget_s": TimingConfig.river_budget_s,    # ceiling of the time box (ranges + solve), seconds
    "river_box_mult": TimingConfig.river_box_mult,    # box = min(this x the decision budget, river_budget_s)
    "river_max_iters": 0,          # >0: stop at this many passes (lab gates pin the work by passes, not by a wall-clock box)
    "river_min_iters": 20,         # fewer CFR+ passes than this: Tier 3's own river decides
    "t3_river_rnr": False,         # restricted river: mix the solved strategy with our best response to the opponent's OBSERVED fold rate,
    "rnr_pmax": 0.5,               #   weight pmax * n / (n + n0) from the n river bets they answered (nothing below rnr_min_n), and
    "rnr_n0": 40,                  #   the weak-hand share of their betting range set to the observed bluff index
    "rnr_min_n": 20,
    "rnr_temp": 0.05,              # soft best response: softmax of the action values / this (pot units)
    "t3_river_narrow": False,      # facing a river bet: their range = the top slice their bet rate and this bet's SIZE RANK (among the river bets
    "narrow_lam": 0.4,             #   they made so far) allow, plus the bluff share seen at showdown (weak hands); blended in by sample size
    "narrow_k": 8,                 #   prior weight (in faced bets) of the size rank, centred at 0.5
    "narrow_n0": 30,               #   showdown-seen bets worth half the weight of the observed profile
    "t3_river_shifts": False,      # stack the X1-X3 counter-moves (over-folder: bluff more, value-only bettor: fold more) on the solver's root strategy
    "river_face_base": False,      # facing a river bet / raise: Tier 3's own logic decides (x_narrow in tier3x), the solver acts only when nothing is to call
    "river_own_fit": True,         # our own range from the fitted model (bot/strategy/own_range.py); False: the generic inference model
    "river_opp_beta": 6.0,         # opponent range for the solver: fixed discard / bet sharpness (None: the trust-scaled model).
    "river_opp_gamma": 0.6,        # Fitted on 12k showdowns: pooled log(N*w) of their real hand +0.26 vs +0.11 for the trust-scaled model
})

SPOT_STREET = {1: "flop", 2: "turn", 3: "river"}


def mixed(probs, r: float) -> int:
    """Index drawn from `probs` (sums to ~1) with the uniform draw r."""
    acc = 0.0
    for i, p in enumerate(probs):
        acc += float(p)
        if r < acc:
            return i
    return len(probs) - 1


def last_aggressor(history, before_street: int) -> Optional[str]:
    """Who made the last raise on any street before `before_street` (None: nobody did)."""
    for r in reversed(history):
        if r.street < before_street and r.action.kind == RAISE:
            return r.actor
    return None


class Tier3Brain(Tier2Brain):
    name = "tier3"
    param_file = "tier3"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self._model: Optional[PreflopModel] = None
        self._model_key: Any = None
        self._own: Optional[OwnRange] = None
        self._hand_id: Optional[int] = None
        self._line: Optional[np.ndarray] = None        # P(our preflop line | class), product over our decisions
        self._floated = False
        # t3_fallbacks: Tier 2 decided (a spot Tier 3 leaves to it, or an error); t3_errors: the style code threw
        self.stats = {"t3_decisions": 0, "t3_fallbacks": 0, "t3_errors": 0}
        # river solver (all ints, summed by the lab's `--report stats`): decisions it took, CFR+ passes and
        # microseconds over them, and why it handed a decision back to Tier 3's river
        # (only with the flag on, so a flag-off Tier 3 reports exactly the counters it always did)
        if self.p.get("t3_river_solver"):
            self.stats.update({"river_solves": 0, "river_iters": 0, "river_us": 0, "river_fallbacks": 0,
                               "river_errors": 0, "river_few_iters": 0, "river_no_pass": 0, "river_missing": 0,
                               "river_rnr": 0, "river_shifted": 0})
        self._faced: list[float] = []                    # size (x pot) of each river bet we faced, for the size rank
        self.river_iters_log: list[int] = []            # passes per solved decision (capped, for benches)

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """Tier 2's parameters as Tier 2 loads them (its defaults + the shipped bot/config/tier2.json),
        plus Tier 3's own keys: "t3": false then plays exactly like the shipped Tier 2."""
        base = load_params(Tier2Brain.param_file, Tier2Brain.defaults())
        base.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()
                     if k not in TIER2_DEFAULTS})
        return base

    # ---- plumbing
    def _tables(self):
        t = self.perception.tables
        return t if (t is not None and t.classes.size == 3 and self.rules.hole_cards == 3) else None

    def _preflop_model(self) -> Optional[PreflopModel]:
        t = self._tables()
        if t is None:
            return None
        key = (id(t), float(self.p["pf_play_weight"]))
        if self._model is None or self._model_key != key:
            # Build both, then assign together: a hard deadline in between used to leave the model
            # set and _own None, so every later postflop decision fell back to Tier 2.
            model = PreflopModel(t, float(self.p["pf_play_weight"]))
            own = OwnRange(self.rules.evaluator, t, self.rules.deck)
            self._model, self._model_key, self._own = model, key, own
        return self._model

    def _new_hand(self, h: HandState) -> None:
        if self._hand_id != h.hand_id:
            self._hand_id, self._line, self._floated = h.hand_id, None, False

    def _draw(self, probs) -> int:
        return mixed(probs, self.pyrng.random())

    def _chance(self, prob: float) -> bool:
        return self.pyrng.random() < prob

    # ---- entry point
    def play(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Action:
        h = s.hand
        if not p.get("t3") or h is None:
            return super().play(s, legal, budget_s, p)
        if legal.can_special:
            if p.get("hide_discard"):
                a = self._safely(self._hidden_discard, s, legal, budget_s, p)
                if a is not None:
                    return a
            return super().play(s, legal, budget_s, p)
        if not h.hole or self._preflop_model() is None:
            return super().play(s, legal, budget_s, p)
        self._new_hand(h)
        a = self._safely(self._bets, s, legal, budget_s, p)
        if a is None:
            self.stats["t3_fallbacks"] += 1
            return super().play(s, legal, budget_s, p)
        self.stats["t3_decisions"] += 1
        return a

    def _safely(self, fn, *args) -> Optional[Action]:
        try:
            return fn(*args)
        except Exception as e:          # a bug in the style must never cost a hand: Tier 2 decides
            self.stats["t3_errors"] += 1
            warn(f"tier3 {fn.__name__} failed: {e!r}")
            return None

    def _bets(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Optional[Action]:
        h = s.hand
        assert h is not None
        if h.street == 0:
            return self._preflop(s, legal, budget_s, p) if p["t3_preflop"] else None
        flag = {1: "t3_flop", 2: "t3_turn", 3: "t3_river"}.get(h.street)
        if flag is None or not p[flag]:
            return None
        return self._postflop(s, legal, budget_s, p)

    # ======================================================================= preflop (G2)
    def _tilt(self, spot: str, p: dict) -> float:
        return self.opponent.spots.tilt(spot) if p["t3_adapt"] else 0.0

    def _bluff_mass(self, total: float, value: float, slope: float, p: dict) -> float:
        """Total re-raise share (value + bluffs). The bluffs grow by `slope` x tilt when the
        opponent folds to our re-raises a lot; with bluff_tilt_scale they shrink by (1 + tilt)
        when it does not, down to none against a player who never folds."""
        t = self._tilt("fold_to_3bet", p)
        if not p.get("bluff_tilt_scale"):
            return total + slope * t
        bluff = max(0.0, total - value)
        bluff = bluff + slope * t if t >= 0 else bluff * (1.0 + t)
        return value + bluff

    @staticmethod
    def t2_calls(h: HandState, eq: float, p: dict) -> bool:
        """Tier 2's rule for a bet we face: equity >= pot odds + margin + pressure (bot/brains/tier1.py)."""
        to_call = h.tocall
        if to_call <= 0:
            return False
        pot = h.pot
        need = to_call / (pot + to_call) + p["call_margin"] + p["bet_pressure"] * to_call / max(pot, 1)
        return eq >= need

    def _size_scale(self, p: dict) -> float:
        """1, or (pf_size_pressure) the share of Tier 2's "big bets are strong" penalty left after
        its adjustment for players who raise nearly always (bot/brains/tier2.py `adjusted`)."""
        if not p.get("pf_size_pressure"):
            return 1.0
        base = float(self.p["bet_pressure"])
        return min(1.0, max(0.0, float(p["bet_pressure"]) / base)) if base > 0 else 1.0

    def _pf_table(self, spot: Spot, p: dict) -> tuple[np.ndarray, dict]:
        """The [fold, passive, raise] table of this spot after adaptation, and the sizes to use."""
        m = self._preflop_model()
        assert m is not None
        band = float(p["pf_band"])
        sizes: dict = {}
        if spot.name == "btn_open":
            fold, limp = float(p["pf_open_fold"]), float(p["pf_open_limp"])
            size_bb = float(p["pf_open_size_bb"])
            t = self._tilt("fold_to_open", p)             # + : folds to opens a lot
            if t > 0:                                      # raise (almost) everything
                fold, limp = fold * (1 - t), limp * (1 - t)
            elif t < 0:                                    # calls a lot: raise a bit less, make it bigger
                limp = min(0.5, limp - 0.10 * t)
                size_bb += 0.5 * -t
            u = max(0.0, self._tilt("raise_vs_limp", p))   # raises our limps: stop limping
            limp = limp * (1 - u) + float(p["pf_adapt_open_limp"]) * u
            key = ("open", round(fold, 3), round(limp, 3), band)
            tbl = m.probs(key, lambda: m.btn_open(fold, limp, float(p["pf_trap_zone"]),
                                                  float(p["pf_trap_prob"]), band))
            sizes["raise_bb"] = size_bb
        elif spot.name == "bb_vs_limp":
            iso = float(p["pf_iso"])
            key = ("iso", round(iso, 3), band)
            tbl = m.probs(key, lambda: m.bb_vs_limp(iso, band))
            sizes["raise_bb"] = float(p["pf_iso_size_bb"])
        elif spot.name == "bb_vs_open":
            d = float(p["pf_bb_defend"]) - float(p["pf_defend_slope"]) * self._size_scale(p) * (spot.raise_to_bb - 2.5)
            d = min(0.9, max(0.2, d))
            value = float(p["pf_3bet_value"])
            three = self._bluff_mass(float(p["pf_3bet"]), value, float(p["pf_adapt_3bet"]), p)
            three = min(0.30, max(value, three))
            key = ("vs_open", round(d, 2), round(value, 3), round(three, 3), band)
            tbl = m.probs(key, lambda: m.bb_vs_open(d, value, three, band))
            sizes["mult"] = float(p["pf_3bet_mult"])
        elif spot.name == "btn_vs_3bet":
            w = self._tilt("three_bet", p)                  # + : they 3-bet a lot: defend wider, 4-bet more
            cont = (float(p["pf_btn_continue"]) + 0.10 * w
                    - float(p["pf_ratio_slope"]) * self._size_scale(p) * (spot.ratio - float(p["pf_3bet_mult"])))
            cont = min(0.85, max(0.25, cont))
            value = float(p["pf_4bet_value"])
            if p.get("bluff_tilt_scale"):
                four = self._bluff_mass(float(p["pf_4bet"]) + 0.04 * max(0.0, w), value, 0.04, p)
            else:
                four = float(p["pf_4bet"]) + 0.04 * w
            four = max(value, four)
            key = ("vs_3bet", round(cont, 2), round(value, 3), round(four, 3), band)
            tbl = m.probs(key, lambda: m.btn_vs_3bet(cont, value, four, band))
            sizes["mult"] = float(p["pf_4bet_mult"])
        else:
            raise ValueError(spot.name)
        return tbl, sizes

    def _preflop(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Optional[Action]:
        h = s.hand
        assert h is not None
        m = self._preflop_model()
        bb = h.bb or self.rules.big_blind
        spot = preflop_spot(h, bb)
        if spot is None or len(h.hole) != 3 or m is None:
            return None
        tbl, sizes = self._pf_table(spot, p)
        cls = m.class_of(h.hole)
        col = self._draw(tbl[cls])
        if (col == FOLD_COL and p.get("eq_floor") and legal.call and h.tocall > 0
                and self.t2_calls(h, s.equity(budget_s), p)):
            col = PASSIVE_COL                          # the table folds, but the price is right
        action = self._pf_action(spot, col, h, legal, bb, sizes)
        executed = {FOLD: FOLD_COL, CHECK: PASSIVE_COL, CALL: PASSIVE_COL, RAISE: RAISE_COL}.get(action.kind)
        if executed is not None:                       # our range for the rest of the hand
            line = tbl[:, executed]
            self._line = line.copy() if self._line is None else self._line * line
        return action

    @staticmethod
    def _pf_action(spot: Spot, col: int, h: HandState, legal: LegalActions, bb: int, sizes: dict) -> Action:
        def passive() -> Action:
            if legal.check:
                return Action.check()
            return Action.call() if legal.call else safe_action(legal)

        if col == FOLD_COL:
            return Action.fold() if legal.fold else passive()
        if col == RAISE_COL and legal.can_raise:
            if "raise_bb" in sizes:
                target = sizes["raise_bb"] * bb
            else:
                target = (h.opp_bet or 0) * sizes["mult"]
            return Action.raise_to(legal.nearest_raise(int(round(target))))
        return passive()

    # ======================================================================= postflop (G3 to G5)
    def _postflop(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Optional[Action]:
        h = s.hand
        assert h is not None and self._own is not None
        street = h.street
        if street == 3 and p.get("t3_river_solver") and not (p.get("river_face_base") and h.tocall > 0):
            a = self._river_solved(s, legal, budget_s, p)
            if a is not None:
                return a                                           # else: Tier 3's own river below
        eq = s.equity(budget_s)
        board = list(h.board)
        tex = board_texture(board)
        keep, dr = best_keep(h.hole, board)
        dead = sorted(h.dead_cards)
        pr = self._own.percentile(h.hole, board, dead, self._line, self.rng, int(p["range_samples"]))
        if pr is None:
            return None
        ctx = _Ctx(h, street, eq, pr, tex, dr, keep, board, self._initiative(h), h.seat == 0,
                   self.opponent.spots)
        if p.get("value_floor") and self.t2_raises(h, eq, legal, p) and self._value_floor_on(p):
            if h.tocall > 0 or p.get("value_floor_size", "t2") == "t2":
                return None                                        # Tier 2's value raise, Tier 2's size
            check = Action.check() if legal.check else safe_action(legal)
            return self._size(self._texture_size(ctx, p), "value", ctx, s, legal, p) or check
        if h.tocall > 0:
            return self._facing_bet(ctx, s, legal, p)
        return self._unfaced(ctx, s, legal, p)

    # ======================================================================= river solver (Tier 4, R1)
    def _river_solved(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Optional[Action]:
        """The river decision from a live CFR+ solve, or None (the caller plays Tier 3's river).

        Both ranges (theirs: Opponent.range_weights; ours: own_range_weights) and the solve share ONE time
        box of min(river_box_mult x budget, river_budget_s) seconds. None on any exception, when not even
        one pass fits, with fewer than river_min_iters passes, or when a piece is missing (a hand that
        isn't a plain river with two hole cards, unknown street bets, the reconstruction)."""
        t0 = time.perf_counter()
        st = self.stats
        try:
            r = self._river_solve(s, legal, budget_s, p, t0)
        except Exception as e:
            st["river_errors"] += 1
            st["river_fallbacks"] += 1
            warn(f"river solver failed: {e!r}")
            return None
        if r is None:
            st["river_fallbacks"] += 1
        return r

    def _river_solve(self, s: Situation, legal: LegalActions, budget_s: float, p: dict,
                     t0: float) -> Optional[Action]:
        h, rec, st = s.hand, s.rec, self.stats
        if (h is None or rec is None or legal.can_special or len(h.hole) != 2 or len(h.board) != 5
                or len(rec.state.hole[rec.me]) != 2 or h.my_bet is None or h.opp_bet is None):
            st["river_missing"] += 1
            return None
        box = min(float(p["river_box_mult"]) * budget_s, float(p["river_budget_s"]))
        if box <= 0.0:
            st["river_no_pass"] += 1
            return None
        deadline = t0 + box
        ev = self.rules.evaluator
        board = np.array(h.board, dtype=np.intp)
        hole = sorted(int(c) for c in h.hole)
        # their combos: every pair of cards we have not seen; ours: every pair consistent with the public cards
        pool = np.array(sorted(rec.pool), dtype=np.int64)
        i, j = np.triu_indices(len(pool), 1)
        opp_cards = np.stack([pool[i], pool[j]], axis=1)
        seen = set(int(c) for c in rec.mapping.values()) - set(hole)
        mine = np.array([c for c in self.rules.deck if c not in seen], dtype=np.int64)
        i, j = np.triu_indices(len(mine), 1)
        hero_cards = np.stack([mine[i], mine[j]], axis=1)
        idx = int(np.nonzero((hero_cards[:, 0] == hole[0]) & (hero_cards[:, 1] == hole[1]))[0][0])
        w_opp = self.opponent.range_weights(rec, opp_cards, self.rng, self._river_opp_model(p))
        w_hero = own_range_weights(rec, hero_cards, self.rng, None if p["river_own_fit"] else Inference(
            dict(INFERENCE_DEFAULTS, enabled=True)))
        hr_opp = hand_ranks(ev, opp_cards, board)
        fold_obs, pmix = None, 0.0
        if p.get("t3_river_narrow") and self.opponent.spots is not None:
            w_opp = self._narrow_range(w_opp, hr_opp, h, p)
        if p.get("t3_river_rnr") and self.opponent.spots is not None:
            if not p.get("t3_river_narrow"):
                w_opp = self._weak_share(w_opp, hr_opp, h, p)
            fr = self.opponent.spots.spots["fold_river"]
            if fr.n >= int(p["rnr_min_n"]):
                fold_obs, pmix = fr.mean(), float(p["rnr_pmax"]) * fr.n / (fr.n + float(p["rnr_n0"]))
        w_opp = np.maximum(w_opp, 1e-9 * max(float(w_opp.max()), 1e-300))   # no empty buckets
        w_hero = np.maximum(w_hero, 1e-9 * max(float(w_hero.max()), 1e-300))
        spot = RiverSpot(pot=float(h.pot), hero_bet=float(h.my_bet), opp_bet=float(h.opp_bet),
                         hero_stack=float(h.my_stack), opp_stack=float(h.opp_stack),
                         last_raise=float(h.tocall) if h.tocall > 0 else 0.0,
                         aggr_so_far=sum(1 for rr in h.history if rr.street == 3 and rr.action.kind == RAISE),
                         checked=bool(h.tocall <= 0 and any(rr.street == 3 and rr.actor != ME for rr in h.history)))
        cfg = TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF), min_bet=float(h.bb or 2))
        res = solve_river(spot, hero_cards, w_hero, hand_ranks(ev, hero_cards, board), opp_cards, w_opp, hr_opp,
                          idx, deadline, cfg=cfg, auto=True, max_iters=int(p["river_max_iters"]) or 10**9,
                          fold_obs=fold_obs)
        if res is None:
            st["river_no_pass"] += 1
            return None
        st["river_solves"] += 1
        st["river_iters"] += res.iterations
        st["river_us"] += int((time.perf_counter() - t0) * 1e6)
        if len(self.river_iters_log) < 20000:
            self.river_iters_log.append(res.iterations)
        if res.iterations < int(p["river_min_iters"]):
            st["river_few_iters"] += 1
            return None
        probs = res.probs
        if res.values is not None and pmix > 0.0:
            z = np.asarray(res.values, dtype=np.float64)
            br = np.exp((z - z.max()) / float(p["rnr_temp"]))
            probs = (1.0 - pmix) * probs + pmix * br / br.sum()
            st["river_rnr"] += 1
        if p.get("t3_river_shifts"):
            hr_h = hand_ranks(ev, hero_cards, board)
            pct = float(((hr_h < hr_h[idx]).sum() + 0.5 * (hr_h == hr_h[idx]).sum()) / len(hr_h))
            shifted = self._river_shift(probs, res.labels, pct, p)
            st["river_shifted"] += int(not np.allclose(shifted, probs))
            probs = shifted
        k = self._draw(probs)
        kind, level = res.labels[k]
        if kind == FOLD and legal.fold:
            return Action.fold()
        if kind == CALL and legal.call:
            return Action.call()
        if kind == CHECK and legal.check:
            return Action.check()
        if kind == RAISE and legal.can_raise:
            return Action.raise_to(legal.nearest_raise(int(round(level))))
        st["river_missing"] += 1                                   # the tree and the engine disagree
        return None

    def _weak_share(self, w: np.ndarray, rank: np.ndarray, h: HandState, p: dict) -> np.ndarray:
        """Their betting range with the weak-hand share set to what we have SEEN them bet (the bluff index of their
        turn / river bets at showdown, shrunk to the population prior). Only after they bet or raised on this river
        and once the stat is past its sample gate; else the inferred range unchanged."""
        st = self.opponent.spots
        sp = st.spots["bluff_index"]
        if sp.n < st.gate or not any(rr.street == 3 and rr.actor == OPP and rr.action.kind == RAISE
                                     for rr in h.history):
            return w
        srt = np.sort(rank)
        pct = (np.searchsorted(srt, rank, "left") + np.searchsorted(srt, rank, "right")) / (2.0 * len(rank))
        weak = pct < st.weak_below
        m = float(w[weak].sum() / w.sum())
        if not 1e-6 < m < 1 - 1e-6:
            return w
        t = min(0.9, max(0.02, sp.mean()))
        return np.where(weak, w * min(5.0, max(0.2, t * (1 - m) / (m * (1 - t)))), w)

    def _narrow_range(self, w: np.ndarray, rank: np.ndarray, h: HandState, p: dict) -> np.ndarray:
        """Facing their river bet: the range that bets this big. A bet of size rank F (share of the river bets they have made
        that were at least this large; bigger bets are rarer and stronger) comes from the top slice
        f * (lam + (1 - lam) * F) * (1 - b) of all their hands (f = their river bet rate, b = bluff index) plus a
        bluff share b of weak hands. Blended with the inferred range by how many bluff-index showdowns back it."""
        st = self.opponent.spots
        if h.tocall <= 0 or not any(rr.street == 3 and rr.actor == OPP and rr.action.kind == RAISE for rr in h.history):
            return w
        ratio = h.tocall / max(1, h.pot - h.tocall)
        key = (h.hand_id, len(h.history))
        if key != getattr(self, "_faced_key", None):           # one entry per bet, however often we are asked
            self._faced_key = key
            self._faced.append(ratio)
        n, k = len(self._faced), float(p["narrow_k"])
        F = (sum(1 for r in self._faced if r >= ratio) + 0.5 * k) / (n + k)
        f = st.spots["river_bet"].mean()
        b = min(0.9, max(0.0, st.spots["bluff_index"].mean()))
        lam = float(p["narrow_lam"])
        value = min(1.0, max(1e-3, f * (lam + (1.0 - lam) * F) * (1.0 - b)))
        srt = np.sort(rank)
        pct = (np.searchsorted(srt, rank, "left") + np.searchsorted(srt, rank, "right")) / (2.0 * len(rank))
        top, weak = pct >= 1.0 - value, pct < 0.4
        wt, ww = float(w[top].sum()), float(w[weak].sum())
        if wt <= 0 or ww <= 0:
            return w
        target = np.where(top, (1.0 - b) * w / wt, 0.0) + np.where(weak, b * w / ww, 0.0)
        target = target + 0.02 * w / w.sum()                    # a floor: a wrong read must not zero a hand out
        alpha = st.spots["bluff_index"].n / (st.spots["bluff_index"].n + float(p["narrow_n0"]))
        return (1.0 - alpha) * w / w.sum() + alpha * target / target.sum()

    def _river_shift(self, probs: np.ndarray, labels: list, pct: float, p: dict) -> np.ndarray:
        """The exploit layer's counter-moves on the solver's root strategy: an over-folder (X1) gets more bluffs from
        our weak hands, a value-only bettor (X2) more folds from our bluff-catchers. Both scaled by the layer's own
        confidence (zero without evidence, so the strategy comes back unchanged)."""
        q = {**EXPLOIT_DEFAULTS, **p}
        kinds = [k for k, _ in labels]
        out = probs.copy()
        lam_of = overfolder_lambda(self.opponent.traits, q["x_ramp"])
        lam_vo = valueonly_lambda(self.opponent.types, q)
        bets = [i for i, k in enumerate(kinds) if k == RAISE]
        if CHECK in kinds and bets and lam_of > 0 and pct < 0.35:
            b = float(out[bets].sum())
            nb = min(float(q["x_bluff_max"]), b * (1 + lam_of * (float(q["x_river_bluff_mult"]) - 1)))
            if 1e-9 < b < nb:
                out[bets] *= nb / b
                out[kinds.index(CHECK)] = 1.0 - nb
        if FOLD in kinds and CALL in kinds and lam_vo > 0 and pct < 0.85:
            c, f = kinds.index(CALL), kinds.index(FOLD)
            mv = out[c] * min(1.0, 0.5 * lam_vo * float(q["x_vo_margin"]) / 0.12)
            out[c] -= mv
            out[f] += mv
        return out

    def _river_opp_model(self, p: dict) -> Optional[Inference]:
        if p.get("river_opp_beta") is None:
            return None
        key = (float(p["river_opp_beta"]), float(p["river_opp_gamma"]))
        if getattr(self, "_ropp_key", None) != key:
            self._ropp_key = key
            self._ropp = Inference(dict(self.opponent.base, enabled=True, beta=key[0], gamma=key[1]))
        return self._ropp

    @staticmethod
    def t2_raises(h: HandState, eq: float, legal: LegalActions, p: dict) -> bool:
        """Tier 2's value-raise rule (bot/brains/tier1.py `choose`, with the adapted thresholds)."""
        if not legal.can_raise or eq < per_street(p["raise_equity"], h.street):
            return False
        mine = sum(1 for a in h.actions_on(h.street, ME) if a.kind == RAISE)
        return mine < p["max_own_raises"] or eq >= p["strong_equity"]

    def value_floor_weight(self, p: dict) -> float:
        """How much the opponent is a "calling station" (0..1): the gated, capped tilts of its fold
        rate against our turn and river bets, negated. 0 below the sample gate and against players
        who fold normally; 1 against players who (almost) never fold."""
        if not p.get("value_floor_gate", True):
            return 1.0
        if not p["t3_adapt"]:
            return 0.0
        st = self.opponent.spots
        return min(1.0, max(0.0, -(st.tilt("fold_turn") + st.tilt("fold_river")) / 2.0))

    def _value_floor_on(self, p: dict) -> bool:
        w = self.value_floor_weight(p)
        return w >= 1.0 or (w > 0.0 and self._chance(w))

    @staticmethod
    def _texture_size(c: "_Ctx", p: dict) -> float:
        """The style's value size for this street and board (never the hand's strength)."""
        if c.street == 1:
            wet = c.tex.wet >= float(p["cbet_wet_cut"]) and not c.tex.paired
            return float(p["cbet_wet_size"] if wet else p["cbet_dry_size"])
        if c.street == 2:
            return float(p["barrel_size"])
        share = float(p["river_value_share"])
        x = min(1.0, max(0.0, (c.pr - (1.0 - share)) / max(share, 1e-6)))
        return float(p["river_size_lo"]) + (float(p["river_size_hi"]) - float(p["river_size_lo"])) * x

    @staticmethod
    def _initiative(h: HandState) -> Optional[str]:
        """Who bet or raised last on an earlier street (the preflop raiser on the flop)."""
        return last_aggressor(h.history, h.street)

    # ---- nothing to call: bet or check
    def _unfaced(self, c: "_Ctx", s: Situation, legal: LegalActions, p: dict) -> Optional[Action]:
        check = Action.check() if legal.check else safe_action(legal)
        if not legal.can_raise:
            return check
        st = c.stats
        if c.street == 3:
            return self._river_bet(c, s, legal, p, check)
        tilt_fc = st.tilt("fold_to_cbet") if p["t3_adapt"] else 0.0
        have_init = c.initiative == ME
        if have_init:
            if c.street == 1:
                return self._cbet(c, s, legal, p, check, tilt_fc)
            return self._barrel(c, s, legal, p, check)
        if c.initiative == OPP and not c.in_position:
            if c.pr >= 0.85 and self._chance(float(p["lead_freq"])):          # a rare lead from the big blind
                return self._size(float(p["cbet_wet_size"]) if c.tex.wet >= p["cbet_wet_cut"]
                                  else float(p["cbet_dry_size"]), "value", c, s, legal, p) or check
            return check
        if c.in_position:                                                       # they checked to us
            return self._stab(c, s, legal, p, check)
        return check

    def _size(self, frac: float, kind: str, c: "_Ctx", s: Situation, legal: LegalActions, p: dict) -> Optional[Action]:
        return self.sized_raise(frac, kind, c.eq, s.state, legal, p)

    def _is_value(self, c: "_Ctx", p: dict) -> bool:
        return c.eq >= float(p["cbet_value_eq"]) or (c.pr >= 0.80 and c.eq >= 0.45)

    def _cbet(self, c, s, legal, p, check, tilt_fc) -> Action:
        """Flop, we raised preflop: small range bets on dry boards, polarised bets on wet ones."""
        tex, dr = c.tex, c.dr
        wet = tex.wet >= float(p["cbet_wet_cut"]) and not tex.paired
        value = self._is_value(c, p)
        has_draw = dr.outs_class in ("strong", "gutshot") or (dr.outs_class == "backdoor" and dr.overcards >= 1)
        medium = (not value) and c.eq >= float(p["medium_lo"])
        if wet:                                                   # polarised: value and semi-bluffs, ~70 % pot
            size = float(p["cbet_wet_size"])
            if value:
                return self._size(size, "value", c, s, legal, p) or check
            if dr.outs_class == "strong" or (dr.outs_class == "gutshot" and dr.overcards >= 1):
                prob = float(p["cbet_semi_strong"] if dr.outs_class == "strong" else p["cbet_semi_gut"])
            elif has_draw:
                prob = float(p["cbet_semi_gut"]) * 0.5
            elif medium:
                prob = 0.0
            else:
                prob = float(p["cbet_air_wet"])
            prob = self._adapt_bluff(prob, tilt_fc)
            if prob > 0 and self._chance(prob):
                return self._size(size, "bluff", c, s, legal, p) or check
            return check
        # dry, paired or high-card board: bet small with most of the range
        size = float(p["cbet_dry_size"])
        if value:
            return self._size(size, "value", c, s, legal, p) or check
        freq = float(p["cbet_dry_freq"])
        if tilt_fc > 0:
            freq += (1.0 - freq) * tilt_fc                       # they fold a lot: bet everything, small
        else:
            freq += 0.35 * tilt_fc                                # they stick around: value and real draws only
        if tex.low_connected and medium:
            freq *= 1.0 - float(p["checkback_medium"])           # low connected boards favour the caller
        elif not has_draw and not medium and tilt_fc < 0:
            freq *= 1.0 + tilt_fc                                  # no value, no draw, sticky opponent: give up
        if self._chance(max(0.0, min(1.0, freq))):
            return self._size(size, "bluff" if not medium else "value", c, s, legal, p) or check
        return check

    @staticmethod
    def _adapt_bluff(prob: float, tilt: float) -> float:
        """Bluff frequency moved by how much they fold: tilt +1 (folds a lot) -> up to double,
        -1 (never folds) -> none."""
        return prob * (1.0 + tilt) if tilt < 0 else min(1.0, prob * (1.0 + tilt))

    def _barrel(self, c, s, legal, p, check) -> Action:
        """Turn, we bet the flop and were called: polarised, floats keep betting."""
        size = float(p["barrel_size"])
        value = c.eq >= float(p["barrel_value_eq"]) or (c.pr >= 0.85 and c.eq >= 0.5)
        if value:
            return self._size(size, "value", c, s, legal, p) or check
        st = c.stats
        fold_t = st.rate("fold_turn") if p["t3_adapt"] else st.spots["fold_turn"].prior
        if self._floated:                                         # we called with nothing and now take it away
            lo, hi = float(p["float_bet_prob"]), float(p["float_bet_prob_max"])
            prob = lo + (hi - lo) * min(1.0, max(0.0, (fold_t - 0.40) / 0.15))
            if self._chance(prob):
                return self._size(size, "bluff", c, s, legal, p) or check
            return check
        if c.dr.outs_class in ("strong", "gutshot") and c.eq >= 0.25:
            if self._chance(self._adapt_bluff(float(p["barrel_semi_prob"]), st.tilt("fold_turn") if p["t3_adapt"] else 0.0)):
                return self._size(size, "bluff", c, s, legal, p) or check
        elif c.eq < float(p["medium_lo"]) and blocker_score(c.keep, c.board) >= 0.5:
            if self._chance(self._adapt_bluff(float(p["barrel_bluff_prob"]), st.tilt("fold_turn") if p["t3_adapt"] else 0.0)):
                return self._size(size, "bluff", c, s, legal, p) or check
        return check

    def _stab(self, c, s, legal, p, check) -> Action:
        """In position after they check: small, frequent bets on dry and paired boards. The size
        depends on the board only, never on the hand."""
        dry = c.tex.wet < float(p["cbet_wet_cut"]) or c.tex.paired
        size = float(p["stab_dry_size"] if dry else p["stab_wet_size"])
        value = self._is_value(c, p) if c.street == 1 else (c.eq >= float(p["barrel_value_eq"]))
        if value:
            return self._size(size, "value", c, s, legal, p) or check
        freq = float(p["stab_dry_freq"] if dry else p["stab_wet_freq"])
        if c.eq >= float(p["medium_lo"]) and c.street == 1:
            freq *= 0.5                                           # medium hands keep their showdown value
        fold_spot = "fold_flop" if c.street == 1 else "fold_turn"
        if p["t3_adapt"]:
            freq = self._adapt_bluff(freq, c.stats.tilt(fold_spot))
        if self._chance(freq):
            return self._size(size, "bluff", c, s, legal, p) or check
        return check

    def _river_bet(self, c, s, legal, p, check) -> Action:
        """River, nothing to call: value-bet the top third of our range, bluff at the bluff share."""
        st = c.stats
        share = float(p["river_value_share"])
        tilt_riv = st.tilt("fold_river") if p["t3_adapt"] else 0.0        # + folds a lot, - calls a lot
        bi = st.bluff_index() if p["t3_adapt"] else st.spots["bluff_index"].prior
        if tilt_riv < 0:
            share += 0.10 * -tilt_riv                                       # a station: value-bet thinner
        if bi < 0.15:
            share += 0.05                                                    # a value-heavy bettor calls less, bet our best
        cut = 1.0 - share
        if c.pr >= cut and c.eq >= 0.55:
            x = min(1.0, (c.pr - cut) / max(share, 1e-6))
            size = float(p["river_size_lo"]) + (float(p["river_size_hi"]) - float(p["river_size_lo"])) * x
            if c.pr >= 0.98 and c.eq >= 0.9 and self._chance(float(p["river_overbet_prob"])):
                size = float(p["river_overbet"])
            return self._size(size, "value", c, s, legal, p) or check
        if c.eq < float(p["river_air_eq"]) and tilt_riv > -0.5:
            size = float(p["river_size_lo"])
            bs = bluff_share(size, 1.0)
            q = bs / (1.0 - bs) * share / max(float(p["river_air_share"]), 1e-6)
            q *= 0.5 + 0.5 * blocker_score(c.keep, c.board)
            if tilt_riv > 0:
                q *= 1.0 + 0.5 * tilt_riv
            if self._chance(min(1.0, q)):
                return self._size(size, "bluff", c, s, legal, p) or check
        return check

    # ---- facing a bet
    def _facing_bet(self, c: "_Ctx", s: Situation, legal: LegalActions, p: dict) -> Optional[Action]:
        h = c.hand
        if c.street == 3:
            return None                                            # the river: Tier 2's bluff-catching rule
        to_call = h.tocall
        pot_before = max(1, h.pot - to_call)
        frac = to_call / pot_before
        st = c.stats
        # ---- raise: value, or a semi-bluff with a strong draw (check-raise when we are first to act)
        raised = self._raise_a_bet(c, s, legal, p, frac)
        if raised is not None:
            return raised
        # ---- continue with the top MDF slice of our own range
        k = float(p["mdf_flop"] if c.street == 1 else p["mdf_turn"])
        target = mdf(to_call, pot_before) * k
        if c.street == 2 and p["t3_adapt"]:
            adj = max(-0.25, min(0.25, (st.bluff_index() - st.spots["bluff_index"].prior) * 2.0))
            target *= 1.0 + adj                                    # an over-bluffer gets defended more
        target = min(0.95, max(0.05, target))
        pass_prob = float(blend_above(np.array([c.pr]), 1.0 - target, float(p["mdf_band"]))[0])
        outs = c.dr.outs_class != "none" or c.dr.overcards > 0 or c.dr.has_showdown_value
        if c.eq < float(p["cont_min_eq"]) and not outs:
            pass_prob *= 0.2                                       # nothing to continue with
        slack = p.get("mdf_eq_slack")
        if slack is not None and c.eq < to_call / (h.pot + to_call) - float(slack):
            pass_prob = 0.0                                        # MDF never pays a price the equity is far from
        if self._chance(pass_prob) and legal.call:
            return Action.call()
        if p.get("eq_floor") and legal.call and self.t2_calls(h, c.eq, p):
            return Action.call()                                   # outside the MDF slice, but the price is right
        # ---- a float: no showdown value, but outs, in position, against a player who gives up the turn
        if (c.street == 1 and c.in_position and legal.call and frac <= float(p["float_max_bet"])
                and not c.dr.has_showdown_value and (c.dr.outs_class != "none" or c.dr.overcards > 0)
                and c.eq >= float(p["cont_min_eq"])):
            gives_up = (st.rate("turn_bet") if p["t3_adapt"] else st.spots["turn_bet"].prior) \
                <= float(p["float_turnbet_max"])
            if gives_up and self._chance(float(p["float_freq"])):
                self._floated = True
                return Action.call()
        return Action.check() if legal.check else (Action.fold() if legal.fold else safe_action(legal))

    def _raise_a_bet(self, c, s, legal, p, frac) -> Optional[Action]:
        if not legal.can_raise:
            return None
        mine = sum(1 for r in c.hand.history if r.street == c.street and r.actor == ME and r.action.kind == RAISE)
        if mine >= 1:
            return None                                            # one raise per street; then call or fold
        if c.eq >= float(p["raise_value_eq"]) and self._chance(float(p["raise_value_prob"])):
            return self._size(float(p["raise_frac"]), "value", c, s, legal, p)
        if c.street == 1 and 0.20 <= c.eq <= 0.60:
            prob = 0.0
            if c.dr.outs_class == "strong":
                prob = float(p["raise_semi_prob"])
            elif c.dr.outs_class == "gutshot" and c.dr.overcards >= 2:
                prob = float(p["raise_gut_prob"])
            if prob > 0 and self._chance(prob):
                return self._size(float(p["raise_frac"]), "bluff", c, s, legal, p)
        return None

    # ======================================================================= discard hiding (G7)
    def _hidden_discard(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Optional[Action]:
        """Among the discards within `hide_margin` of the best expected share, pick the one whose
        reveal says least about our hand. None = no value information (Tier 2 decides)."""
        from bot.sim.discard import choose_discard
        h = s.hand
        if h is None or s.rec is None or not p["use_sim"]:
            return None
        out: dict = {}
        best = choose_discard(s.rec, legal, self.rng, budget_s * float(p["special_budget_frac"]),
                              self.opponent.model, out=out)
        means = out.get("means")
        if best is None or not means:
            return best
        top = max(means.values())
        near = [o for o, v in means.items() if v >= top - float(p["hide_margin"])]
        if len(near) <= 1:
            return best
        board = list(h.board)
        hole = list(h.hole)
        return Action.special(min(near, key=lambda o: (reveal_info(hole[int(o)], hole, board), -means[o])))


def reveal_info(card: int, hole, board) -> float:
    """How much throwing away `card` tells the opponent about the two we keep (0 = nothing).

    A discarded card of a suit that is two or more on the board says "no flush draw here"; a card
    that pairs the board says "I have no use for the pair"; a card connected to the board says the
    same about a straight; a high card says "I kept something better"."""
    s = 0.0
    suits = [b % 4 for b in board]
    if suits.count(card % 4) >= 2:
        s += 1.0
    ranks = [b // 4 for b in board]
    if card // 4 in ranks:
        s += 1.0
    if any(abs(card // 4 - r) <= 1 for r in ranks):
        s += 0.5
    if card // 4 >= 8:
        s += 0.5
    return s


class _Ctx:
    """What the postflop rules need about this decision."""
    __slots__ = ("hand", "street", "eq", "pr", "tex", "dr", "keep", "board", "initiative",
                 "in_position", "stats")

    def __init__(self, hand, street, eq, pr, tex, dr, keep, board, initiative, in_position, stats) -> None:
        self.hand, self.street, self.eq, self.pr, self.tex, self.dr = hand, street, eq, pr, tex, dr
        self.keep, self.board, self.initiative, self.in_position, self.stats = keep, board, initiative, in_position, stats
