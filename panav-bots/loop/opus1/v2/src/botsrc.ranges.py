"""Range tracking at the start of the river (BUILDMAP §9.6), vectorised over candidate hands.

Opponent range (our belief): candidates are pairs k from the cards not on the board, not in our 3
hole cards and not their discard d; their 3-card hand is H = k + {d}. The likelihood of k is the
product, over their preflop / flop / turn actions, of the blueprint probability of what they did
(off-tree raises: the §9.4 translation mixture), times the probability of their discard (keeping k
from H). Unvisited infosets give a uniform factor over the legal slots; every factor is floored at
1/1020 and raised to tau (default 0.7, hooks.range_tau()). opp_range = 0.9 tracked + 0.1 flat.

Our range (the opponent's view of us): the same with our actions and our discard, candidates
excluding only the board and both discards, tau = 1 and no flat mix (we know how we play).
"""
import math
import numbers

import numpy as np

from shared import betting as B
from shared import cards as C
from shared import features as F
from shared import infoset as I
from shared import showdown as SD

from . import hooks
from . import translate as TR

FLOOR = 1.0 / 1020
LIK_FLOOR = 1e-12          # floor of the river solver's own action probabilities in our range (own_river)
FLAT_MIX = 0.1
DEFAULT_TAU = 0.7
_C3 = np.array([math.comb(n, 3) for n in range(52)], dtype=np.int64)
_C2 = np.array([math.comb(n, 2) for n in range(52)], dtype=np.int64)


def idx3_rows(H):
    """Vectorised idx3 for rows of sorted triples (n, 3)."""
    return _C3[H[:, 2]] + _C2[H[:, 1]] + H[:, 0]


def valid_tau(x):
    try:
        x = float(x)
    except Exception:
        return DEFAULT_TAU
    return x if 0.0 < x <= 1.0 and math.isfinite(x) else DEFAULT_TAU


def all_pairs(policy, hs, street, board):
    """S1, S2 for all 1326 pairs on the flop or the turn (lookahead), cached per hand."""
    key = ("all", street, tuple(board[:3 if street == "flop" else 4]))
    if key not in hs.cache:
        if street == "flop":
            rows = policy.flop_info(hs, board)["rows"]
        else:
            rows = policy.later_info(hs, "turn", board)["rows"]     # cached by our own turn decision
        hs.cache[key] = F.all_features(rows)
    return hs.cache[key]


def river_buckets(policy, hs, board):
    key = ("br_all", tuple(board[:5]))
    if key not in hs.cache:
        E, _ = F.all_features(F.street_rows(board[:5], False))
        hs.cache[key] = F.river_bucket_all(E, policy.th)
    return hs.cache[key]


def action_records(rep, hs, seat, streets=("preflop", "flop", "turn")):
    """The actions of `seat` on these streets: node, legal mask, and slot weights (one slot for exact
    actions, the §9.4 mixture for off-tree raises)."""
    out = []
    for index, st in enumerate(rep.steps):
        if st.seat != seat or st.street not in streets or st.node is None or st.node < 0:
            continue
        node = B.template_for(st.street)[st.node]
        opts = B.slot_options_req(st.street, node, st.req)
        legal = np.array([1.0 if ok else 0.0 for _, ok, _ in opts])
        if st.action == "raise":
            if seat == hs.seat and st.slot is not None:
                mix = {st.slot: 1.0}                       # our own raise: exactly the slot we played
            else:
                _, pairs = TR.translate_raise(node, opts, st.amount, st.req,
                                              (hs.hand_id, TR.STREET_INDEX[st.street], index))
                mix = dict(pairs)
        else:
            mix = {st.action: 1.0}
        w = np.array([mix.get(s, 0.0) for s in node["slots"]])
        out.append({"street": st.street, "node": node, "legal": legal, "w": w, "action": st.action,
                    "amount": st.amount, "req": st.req, "index": index})
    return out


def table_factor(rows_u8, legal, w):
    """Per candidate: sum over slots of w * (strategy row masked to the legal slots, normalised);
    a row with no legal mass (unvisited) counts as uniform over the legal slots."""
    p = rows_u8.astype(np.float64) * legal
    s = p.sum(axis=1, keepdims=True)
    uniform = legal / legal.sum()
    sigma = np.where(s > 0, p / np.where(s > 0, s, 1.0), uniform)
    return sigma @ w


def _custom_factor(action_rec, K):
    """hooks.opp_action_likelihood: a float64[1326] over candidate pairs, or None (blueprint)."""
    try:
        arr = hooks.opp_action_likelihood({k: action_rec[k] for k in ("street", "action", "amount", "index")}
                                          | {"node_id": action_rec["node"]["id"],
                                             "slot_weights": dict(zip(action_rec["node"]["slots"],
                                                                      action_rec["w"].tolist()))})
    except Exception:
        return None
    if arr is None:
        return None
    try:
        arr = np.asarray(arr, dtype=np.float64)
    except Exception:
        return None
    if arr.shape != (1326,) or not np.isfinite(arr).all() or (arr < 0).any():
        return None
    return arr[K]


def is_allin(rec):
    """Was this action record an all-in (all its slot weight on the allin slot)?"""
    slots = rec["node"]["slots"]
    return "allin" in slots and rec["w"][slots.index("allin")] >= 0.5


def log_likelihood(policy, hs, rep, board, whose, tau=None, include_river=False, allin_weight=1.0, own_river=None):
    """(K, logL): candidate pair indices (idx2) and log-likelihoods, before normalisation.
    allin_weight scales the exponent of river all-in factors (the 'mix' river rule trusts an
    opponent's river all-ins less when they shove far more often than the blueprint would).
    own_river (our range only): {history index: float64[1326]} for our river actions the river solver
    chose: the probability each combo takes that action under the solver's strategy, used instead of
    the RIVER table (floored at LIK_FLOOR, not FLOOR: no combo's weight underflows)."""
    opp = whose == "opp"
    seat_w = 1 - hs.seat if opp else hs.seat
    d = hs.opp_discard if opp else hs.my_discard
    other = hs.my_discard if opp else hs.opp_discard
    excluded = list(board[:5]) + [d, other] + (list(hs.hole3) if opp else [])
    K = np.nonzero(~np.isin(C.COMBO, excluded).any(axis=1))[0]
    pairs = C.COMBO[K]
    H = np.sort(np.column_stack([pairs, np.full(len(K), d, dtype=np.int64)]), axis=1)
    if tau is None:
        tau = valid_tau(hooks.range_tau()) if opp else 1.0
    th, T, L = policy.th, policy.tables, getattr(policy, "L", None) or I.LAYOUT_A1
    S1f, S2f = all_pairs(policy, hs, "flop", board)
    b3, slots = F.bucket3_all(H, S1f, F.class2_all(S1f, S2f, th), th)
    S1t, S2t = all_pairs(policy, hs, "turn", board)
    bt = F.turn_bucket_all(S1t, S2t, th)[K]
    flop = board[:3]
    od_w, md_w = F.dcls(other, flop), F.dcls(d, flop)      # from seat_w's point of view
    pc_flop = B.pot_class(rep.pot_start["flop"])
    pc_turn = B.pot_class(rep.pot_start["turn"])
    logL = np.zeros(len(K))

    def add(f, scale=1.0):
        nonlocal logL
        logL = logL + scale * tau * np.log(np.maximum(f, FLOOR))

    streets = ("preflop", "flop", "turn", "river") if include_river else ("preflop", "flop", "turn")
    br = river_buckets(policy, hs, board)[K] if include_river else None
    for rec in action_records(rep, hs, seat_w, streets):
        if own_river and not opp and rec["street"] == "river" and rec["index"] in own_river:
            logL = logL + tau * np.log(np.maximum(np.asarray(own_river[rec["index"]])[K], LIK_FLOOR))
            continue
        scale = allin_weight if (rec["street"] == "river" and is_allin(rec)) else 1.0
        if opp:
            custom = _custom_factor(rec, K)
            if custom is not None:
                add(custom, scale)
                continue
        node = rec["node"]
        off, k = node["offset"], len(node["slots"])
        st = rec["street"]
        if st == "preflop":
            rows = T["PRE"][policy.canon3[idx3_rows(H)].astype(np.int64), off:off + k]
        elif st == "flop":
            rows = T["FLOP"][L.flop_prefix(b3, pc_flop, rep.pagg), off:off + k]
        elif st == "turn":
            rows = T["TURN"][L.turn_prefix(bt, od_w, md_w, pc_turn, rep.fagg), off:off + k]
        else:
            pc_river = B.pot_class(rep.pot_start["river"])
            rows = T["RIVER"][L.river_prefix(br, od_w, pc_river), off:off + k]
        add(table_factor(rows, rec["legal"], rec["w"]), scale)
    # the discard: keeping k from H, at the DISC infoset of seat_w
    keep = np.argmax(slots == K[:, None], axis=1)
    pc_end = B.pot_class(rep.pot_start["turn"])                 # pot at the end of flop betting
    rows = T["DISC"][L.disc_prefix(b3, pc_end, rep.fagg, seat_w), 0:3].astype(np.float64)
    s = rows.sum(axis=1)
    sigma = np.where(s[:, None] > 0, rows / np.where(s > 0, s, 1.0)[:, None], 1.0 / 3.0)
    add(sigma[np.arange(len(K)), keep])
    return K, logL


def normalise(K, logL, flat_mix):
    L = np.exp(logL - logL.max())
    out = np.zeros(1326)
    out[K] = L / L.sum()
    if flat_mix > 0:
        flat = np.zeros(1326)
        flat[K] = 1.0 / len(K)
        out = (1.0 - flat_mix) * out + flat_mix * flat
    return out


class RiverRanges:
    def __init__(self, opp, our, tau):
        self.opp = opp
        self.our = our
        self.tau = tau


def river_ranges(policy, hs, rep, board):
    """Both ranges at the start of the river (cache them per hand)."""
    tau = valid_tau(hooks.range_tau())
    Ko, lo = log_likelihood(policy, hs, rep, board, "opp", tau=tau)
    Ku, lu = log_likelihood(policy, hs, rep, board, "our", tau=1.0)
    return RiverRanges(normalise(Ko, lo, FLAT_MIX), normalise(Ku, lu, 0.0), tau)


def opp_range_now(policy, hs, rep, board, tau, allin_weight=1.0):
    """The opponent range including their river actions so far (blueprint RIVER table)."""
    K, logL = log_likelihood(policy, hs, rep, board, "opp", tau=tau, include_river=True, allin_weight=allin_weight)
    return normalise(K, logL, FLAT_MIX)


def our_range_now(policy, hs, rep, board, own_river=None):
    """Our range including our river actions so far (tau = 1, no flat mix): those the river solver
    chose with its own strategy (own_river, see log_likelihood), any other with the RIVER table."""
    K, logL = log_likelihood(policy, hs, rep, board, "our", tau=1.0, include_river=True, own_river=own_river)
    return normalise(K, logL, 0.0)


def river_allin_probs(policy, hs, rep, board, rec):
    """float64[1326]: the blueprint's probability of going all-in at this opponent river decision
    (rec from action_records), per candidate pair; 0 for excluded pairs. None if all-in was not legal."""
    node = rec["node"]
    if "allin" not in node["slots"]:
        return None
    j = node["slots"].index("allin")
    if rec["legal"][j] <= 0:
        return None
    excluded = list(board[:5]) + [hs.opp_discard, hs.my_discard] + list(hs.hole3)
    K = np.nonzero(~np.isin(C.COMBO, excluded).any(axis=1))[0]
    br = river_buckets(policy, hs, board)[K]
    od_w = F.dcls(hs.my_discard, board[:3])                   # the other player's discard, from their side
    pc_river = B.pot_class(rep.pot_start["river"])
    off, k = node["offset"], len(node["slots"])
    rows = policy.tables["RIVER"][(getattr(policy, "L", None) or I.LAYOUT_A1).river_prefix(br, od_w, pc_river),
                                  off:off + k]
    w = np.zeros(k)
    w[j] = 1.0
    out = np.zeros(1326)
    out[K] = table_factor(rows, rec["legal"], w)
    return out


def equity(board, hole, opp_weights):
    """Our showdown equity on a 5-card board against a weighted opponent range (ties count half)."""
    values = SD.river_values(board)
    beat, tie = SD.weighted_showdown(values, opp_weights, board)
    h = C.idx2(*hole)
    ok = ~np.isin(C.COMBO, list(hole)).any(axis=1)
    total = float(np.asarray(opp_weights)[ok].sum())
    return float((beat[h] + 0.5 * tie[h]) / total) if total > 0 else 0.0


def is_number(x):
    return isinstance(x, numbers.Real) and not isinstance(x, bool) and math.isfinite(float(x))
