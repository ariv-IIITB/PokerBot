"""Decision logic. Pure functions of (obs, equity, context) -> action tuple.

Core ideas
  * equity vs the modelled opponent range is compared with pot odds (+ margin)
  * value-bet / value-raise when equity is high, size by equity and opponent type
  * bluff frequency scales with how often the opponent folds (measured, smoothed)
  * a small random mix keeps us unpredictable; a risk flag tightens or loosens play
"""
from .types import CALL, CHECK, FOLD, RAISE


class Ctx:
    """Everything the strategy needs beyond the raw observation."""
    __slots__ = ("opp", "rng", "s_hand", "risk", "aggr_prev", "suited_or_ace", "eq")

    def __init__(self, opp, rng, s_hand=0.5, risk=0, aggr_prev=False, suited_or_ace=False, eq=0.5):
        self.opp = opp
        self.rng = rng
        self.s_hand = s_hand           # our starting-hand percentile (preflop strength)
        self.risk = risk               # +1 protect a lead, -1 chase, 0 normal
        self.aggr_prev = aggr_prev     # we bet/raised on the previous street
        self.suited_or_ace = suited_or_ace
        self.eq = eq


# ----------------------------------------------------------------- helpers
def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def raise_to(obs, frac):
    """Raise so that we put `frac` of (pot + call) on top of calling. Returns an action tuple."""
    if not obs.can_raise:
        return _passive(obs)
    target = obs.opp_pip + frac * (obs.pot + obs.to_call)
    return _raise_amount(obs, target)


def _raise_amount(obs, target):
    t = int(round(target))
    t = _clamp(t, obs.min_raise, obs.max_raise)
    # leave no awkward crumbs: if the remainder is small relative to the pot, just shove
    after_pot = obs.pot + 2 * (t - obs.hero_pip)
    if obs.max_raise - t <= 0.30 * after_pot:
        t = obs.max_raise
    return (RAISE, t)


def shove(obs):
    return (RAISE, obs.max_raise) if obs.can_raise else _passive(obs)


def _passive(obs):
    if obs.can_check:
        return (CHECK,)
    return (CALL,)


def _check_or_fold(obs):
    return (CHECK,) if obs.can_check else (FOLD,)


def legalize(obs, act):
    """Force any action into the legal set (never return something the engine would reject)."""
    kind = act[0]
    if kind == RAISE:
        if not obs.can_raise:
            kind = CALL if obs.to_call > 0 else CHECK
        else:
            amt = _clamp(int(act[1]), obs.min_raise, obs.max_raise)
            return (RAISE, amt)
    if kind == CHECK:
        if obs.can_check:
            return (CHECK,)
        kind = CALL
    if kind == CALL:
        if obs.to_call <= 0:
            return (CHECK,) if obs.can_check else (FOLD,)
        return (CALL,) if obs.can_call else (FOLD,)
    if kind == FOLD:
        if obs.can_check:
            return (CHECK,)          # never fold when checking is free
        return (FOLD,) if obs.can_fold else (CALL,)
    return _check_or_fold(obs)


# ----------------------------------------------------------------- preflop
def preflop(obs, eq, ctx):
    bb = obs.big_blind
    s = ctx.s_hand
    opp = ctx.opp
    rng = ctx.rng
    protect = ctx.risk > 0
    chase = ctx.risk < 0

    unopened = obs.button and obs.hero_pip < bb and obs.opp_pip <= bb
    bb_vs_limp = (not obs.button) and obs.to_call == 0 and obs.opp_pip <= bb

    if unopened:
        ftb = opp.pf_fold_to_open.value
        cut = 0.28 - 0.5 * (ftb - 0.40) + 0.6 * max(0.0, opp.pf_3bet.value - 0.15)
        cut = _clamp(cut + (0.08 if protect else 0.0) - (0.04 if chase else 0.0), 0.10, 0.50)
        if s >= cut:
            size = rng.choice((2.2, 2.5, 2.5, 3.0)) * bb
            return _raise_amount(obs, size)
        if s >= 0.10:
            return (CALL,)
        return (FOLD,)

    if bb_vs_limp:
        if s >= 0.45 and rng.random() < 0.88:
            return _raise_amount(obs, 3.5 * bb)
        if 0.25 <= s < 0.45 and rng.random() < 0.10 and not protect:
            return _raise_amount(obs, 3.5 * bb)
        return (CHECK,)

    # facing a raise (or a re-raise)
    c = obs.to_call
    if c <= 0:
        return _passive(obs)
    req = c / float(obs.pot + c)
    big = obs.opp_pip >= 0.12 * obs.start_stack
    m = 0.03 + (0.03 if big else 0.0) + (0.03 if protect else 0.0) - (0.015 if chase else 0.0)

    if obs.can_raise and eq >= 0.62 and rng.random() < 0.88:
        tgt = max(3.0 * obs.opp_pip, obs.opp_pip + 3 * bb) if not big else obs.max_raise
        if tgt >= 0.45 * obs.max_raise:
            return shove(obs)
        return _raise_amount(obs, tgt)
    if eq >= req + m:
        return (CALL,)
    # occasional light 3-bet bluff with blocker-ish hands vs openers who fold a lot
    if (obs.can_raise and not big and not protect and 0.30 <= s < 0.62 and ctx.suited_or_ace):
        p3 = _clamp(0.5 * (opp.pf_fold_to_3bet.value - 0.35), 0.0, 0.18)
        if rng.random() < p3:
            return _raise_amount(obs, 3.0 * obs.opp_pip)
    return (FOLD,)


# ----------------------------------------------------------------- postflop
def _value_frac(eq, ctx):
    if eq < 0.66:
        f = 0.40
    elif eq < 0.75:
        f = 0.55
    elif eq < 0.85:
        f = 0.75
    else:
        f = 1.00
    st = ctx.opp.stationness()
    fold = ctx.opp.fold_to_bet.value
    f *= 1.0 + 0.30 * st
    if fold > 0.55:
        f *= 0.85
    return _clamp(f, 0.25, 1.5)


def postflop(obs, eq, ctx):
    st = obs.street
    opp = ctx.opp
    rng = ctx.rng
    protect = ctx.risk > 0
    chase = ctx.risk < 0
    pot, c = obs.pot, obs.to_call
    si = st - 1

    if c > 0:
        pot_before = max(1, pot - c)
        f = c / float(pot_before)
        req = c / float(pot + c)
        m = (0.025, 0.02, 0.015)[si] + 0.05 * max(0.0, f - 0.6)
        m -= 0.04 * opp.bluffiness()
        m += 0.03 if protect else 0.0
        m -= 0.01 if chase else 0.0
        thr_raise = (0.74, 0.77, 0.82)[si] + (0.03 if protect else 0.0)
        if obs.can_raise and eq >= thr_raise and rng.random() < 0.80:
            return raise_to(obs, 0.80)
        if eq >= req + m:
            return (CALL,)
        # occasional semi-bluff raise with real draw equity
        if obs.can_raise and st < 3 and 0.28 <= eq < 0.50 and not protect:
            pb = _clamp(0.5 * (opp.fold_to_raise.value - 0.35), 0.0, 0.16)
            if rng.random() < pb:
                return raise_to(obs, 0.80)
        return (FOLD,)

    # ---- no bet to face: we may check or bet
    thr_v = (0.60, 0.62, 0.64)[si] - 0.04 * opp.stationness() + (0.03 if protect else 0.0)
    ftb = opp.fold_to_bet.value
    bluff_scale = 0.0 if protect else (1.3 if chase else 1.0)

    if eq >= thr_v:
        if eq >= 0.88 and st < 3 and not obs.button:
            trap = 0.30 + (0.20 if opp.bet.value > 0.5 else 0.0)
            if rng.random() < trap:
                return (CHECK,)
        return raise_to(obs, _value_frac(eq, ctx))

    if not obs.can_raise:
        return (CHECK,)

    p_air = _clamp(0.30 + 1.0 * (ftb - 0.40), 0.05, 0.65) * bluff_scale
    if st < 3 and 0.28 <= eq < thr_v - 0.02:
        p_semi = _clamp(0.25 + 1.2 * (ftb - 0.35), 0.10, 0.70) * bluff_scale
        if rng.random() < p_semi:
            return raise_to(obs, 0.55)
    if st == 1 and eq < 0.40 and rng.random() < p_air:
        return raise_to(obs, 0.50)
    if st == 2 and eq < 0.30 and ctx.aggr_prev and rng.random() < 0.6 * p_air:
        return raise_to(obs, 0.55)
    if st == 3 and eq < 0.15:
        p_riv = _clamp(1.2 * (ftb - 0.30), 0.0, 0.35) * bluff_scale
        if rng.random() < p_riv:
            return raise_to(obs, 0.70)
    return (CHECK,)


# ----------------------------------------------------------------- entry points
def decide(obs, eq, ctx):
    if obs.street == 0:
        act = preflop(obs, eq, ctx)
    else:
        act = postflop(obs, eq, ctx)
    return legalize(obs, act)


def panic_action(obs, s_hand):
    """Zero-compute fallback used when the time bank is nearly gone."""
    if obs.can_check:
        return (CHECK,)
    if obs.street == 0:
        if s_hand >= 0.55:
            return (CALL,)
        return (FOLD,)
    if obs.to_call <= 0.33 * max(1, obs.pot - obs.to_call):
        return (CALL,)
    return (FOLD,)
