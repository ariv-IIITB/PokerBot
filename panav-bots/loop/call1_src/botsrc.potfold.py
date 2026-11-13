"""potfold: a bounded shift from call to fold against pot-size postflop bets, with a within-match ledger.

Facing a postflop bet or raise of FMIN..FMAX pot (translate's size definition, not all-in), when the move would
CALL with a hand whose equity vs a random hand (the bot's own S1 proxy, s1 / MAX_S1) is below CUT, fold instead
with probability p_eff = P[street, seat] * g. g in [0, 1] is the ledger: the realised chips (decision to hand end,
net + chips already committed; a fold is 0) of the calls of this class that we did make. Their mean is shrunk to a
prior (MU0, with PRIOR_N pseudo-calls: normal-normal, sigma SIGMA): g = clip(posterior mean / MU0, 0, 1), so when
the calls win in this match (the opponent bluffs a lot) the shift goes to 0. A leg has only a handful of such calls
(about 3-10 per 200 hands), so the shift is mostly prior-driven; it is bounded by P (< 1 on purpose: the calls
that are still made feed the ledger). Never touches the river solver's range or the discard; only a call -> fold.
"""
from . import exploit as X

FMIN, FMAX = 0.75, 1.2     # v2 (config pf_vs=on): 0.70-1.2
VS_FMIN = 0.70
VS_MIN_N, VS_SHARE, VS_RAMP = 4, 0.60, 4.0   # value-share gate: shown big bets needed, share needed, ramp length
MAX_S1 = {"flop": 47 * 2 * 1035, "turn": 46 * 2 * 990, "river": 2 * 990}
DEFAULTS = {
    "pf_p": {"flop:0": 0.75, "flop:1": 0.75, "turn:0": 0.75, "turn:1": 0.75, "river:0": 0.75, "river:1": 0.75},
    "pf_cut": {"flop": 0.9, "turn": 0.9, "river": 0.9},
    "pf_mu0": -15.0, "pf_sigma": 70.0, "pf_prior_n": 25.0,
}


def size_fraction(req):
    """f of the bet or raise we face (D1 / translate's definition), or None. Postflop only."""
    if req["to_call"] <= 0 or req["street"] == "preflop":
        return None
    street, X, mine = req["street"], req["opp_bet"], req["my_bet"]
    prev = [a for a in req["history"] if a.get("street") == street and a.get("actor") == "opp"]
    before = [a for a in prev[:-1] if a.get("action") in ("raise", "call")]
    p0 = before[-1]["amount"] if before else 0
    pot_r = req["pot"] - (X - p0)            # pot at the raiser's decision
    tc_r = mine - p0                         # the raiser's to_call
    if mine <= p0 or tc_r <= 0:
        return X / max(pot_r, 1)
    return (X - mine) / max(pot_r + tc_r, 1)


class PotFold:
    def __init__(self, config):
        d = DEFAULTS
        self.p = dict(d["pf_p"]); self.p.update(config.get("pf_p") or {})
        self.cut = dict(d["pf_cut"]); self.cut.update(config.get("pf_cut") or {})
        self.mu0 = float(config.get("pf_mu0", d["pf_mu0"]))
        self.sigma = float(config.get("pf_sigma", d["pf_sigma"]))
        self.n0 = float(config.get("pf_prior_n", d["pf_prior_n"]))
        self.ledger_on = config.get("pf_ledger", "on") == "on"
        self.gate = config.get("pf_gate", "on") == "on"
        self.vs = config.get("pf_vs", "off") == "on"      # v2: value-share gate and a lower equity band
        self.lo = float(config.get("pf_lo", 0.0))
        self.fmin = VS_FMIN if self.vs else FMIN
        self.shown = 0                                    # shown big bets of theirs that we called (net != 0)
        self.value = 0                                    # ... that beat us
        self.big_pending = set()
        self.n = 0
        self.sum = 0.0
        self.pending = {}            # hand_id -> [committed chips at each kept call]
        self.stats = {"eligible": 0, "folded": 0, "kept": 0, "gated": 0, "vs_off": 0}

    def g(self):
        """Ledger factor in [0, 1]."""
        if not self.ledger_on:
            return 1.0
        post = (self.mu0 * self.n0 + self.sum) / (self.n0 + self.n)   # shrunk mean of the calls made so far
        return max(0.0, min(1.0, post / self.mu0))

    def maybe(self, hs, req, reply, proxy, draw):
        """-> reply (the original, or a fold). proxy: s1 / MAX_S1 of this decision (None: no data); draw: u in [0, 1)."""
        if proxy is None or reply.get("action") != "call" or req["street"] == "preflop":
            return reply
        if req["opp_stack"] == 0 or "fold" not in req["legal_actions"]:
            return reply
        f = size_fraction(req)
        if f is None or not (self.fmin <= f <= FMAX):
            return reply
        street = req["street"]
        if proxy >= self.cut.get(street, 0.9) or proxy < self.lo:
            if self.vs:
                self.big_pending.add(hs.hand_id)        # a big bet of theirs that we call: its showdown feeds the value share
            return reply
        self.stats["eligible"] += 1
        if self.gate and (X.trait_yes("aggressor") or X.trait_yes("riverbluff")):
            self.stats["gated"] += 1        # a frequent big bettor: their bets are not all value, the shift stays off
            return reply
        w = self.vs_weight() if self.vs else 1.0
        if w <= 0.0:
            self.stats["vs_off"] += 1
        p = self.p.get(f"{street}:{hs.seat}", 0.0) * self.g() * w
        if draw < p:
            self.stats["folded"] += 1
            return {"type": "action", "action": "fold"}
        self.stats["kept"] += 1
        if self.vs:
            self.big_pending.add(hs.hand_id)
        self.pending.setdefault(hs.hand_id, []).append(self.start_stack - int(req["my_stack"]))
        return reply

    start_stack = 200

    def vs_weight(self):
        """Ramp 0..1: needs >= VS_MIN_N shown big bets of theirs with a value share >= VS_SHARE (they bet big with value, not bluffs)."""
        if self.shown < VS_MIN_N or self.value / self.shown < VS_SHARE:
            return 0.0
        return min(1.0, (self.shown - VS_MIN_N + 1) / VS_RAMP)

    def on_hand_result(self, msg):
        if self.vs and msg.get("hand_id") in self.big_pending:
            self.big_pending.discard(msg.get("hand_id"))
            net = msg.get("net")
            if msg.get("opp_hole_cards") and isinstance(net, (int, float)) and net != 0:
                self.shown += 1
                self.value += 1 if net < 0 else 0
        pend = self.pending.pop(msg.get("hand_id"), None)
        if not pend or not isinstance(msg.get("net"), (int, float)):
            return
        for committed in pend:
            self.n += 1
            self.sum += float(msg["net"]) + committed

    def summary(self):
        return dict(self.stats, shown=self.shown, value=self.value, ledger_n=self.n, ledger_mean=(self.sum / self.n if self.n else None), g=round(self.g(), 3))
