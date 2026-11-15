"""Action translation for bet sizes outside our tree (BUILDMAP §9.4).

raise to X: X == max_raise -> allin. Otherwise the candidates are the legal size slots and allin at
the node, with their §5.2.3 amounts, compared as pot fractions:
    opening bet (opp_bet == 0):  f = X / pot
    raise:                       f = (X - opp_bet) / (pot + to_call)
Below the smallest -> smallest; above the largest -> largest. Between neighbours A < x < B:
    P(A) = ((B - x)(1 + A)) / ((B - A)(1 + x))        (pseudo-harmonic mapping)
sampled with random.Random(hash(key)), key = (SALT, hand_id, street index, history index), so the
same action always maps to the same slot within a hand. SALT is drawn once per process: each leg is a
fresh process and replays the same deals under the same hand_ids, and the draws must not repeat across
legs (Rulebook 10.3). Seeded eval builds key by the deal alone (unsalted) so a duplicate pair mirrors.
Range tracking uses the mixture, not the sample.
"""
import random

from shared import betting as B

CANDIDATE_SLOTS = ("sizeA", "sizeB", "raise", "allin")
SALT = random.SystemRandom().getrandbits(61)     # per process (see the docstring)


def fraction(amount, req):
    pot, opp_bet, to_call = req["pot"], req["opp_bet"], req["to_call"]
    if opp_bet == 0:
        return amount / max(pot, 1)
    return (amount - opp_bet) / max(pot + to_call, 1)


def translate_raise(node, opts, amount, req, key, info=None):
    """-> (slot, [(slot, probability), ...]) for a raise to `amount` at `node`.
    info (a dict, optional) receives x (the raise as a pot fraction), x_min (our smallest size at the
    node, same units) and below (True when the raise is smaller than our smallest size)."""
    if amount == req.get("max_raise") and "allin" in node["slots"]:
        return "allin", [("allin", 1.0)]
    cands = [(s, a) for s, ok, a in opts if ok and s in CANDIDATE_SLOTS and a is not None]
    if not cands:   # no legal size: any size slot of the node, else allin (keeps the walk on the tree)
        cands = [(s, a) for s, ok, a in opts if s in CANDIDATE_SLOTS and a is not None]
    if not cands:
        return None, []
    pts = sorted((fraction(a, req), s) for s, a in cands)
    x = fraction(amount, req)
    if info is not None:
        info.update(x=x, x_min=pts[0][0], below=x < pts[0][0] - 1e-9)
    if x <= pts[0][0]:
        return pts[0][1], [(pts[0][1], 1.0)]
    if x >= pts[-1][0]:
        return pts[-1][1], [(pts[-1][1], 1.0)]
    for (fa, sa), (fb, sb) in zip(pts, pts[1:]):
        if x == fb:
            return sb, [(sb, 1.0)]
        if fa < x < fb:
            p_a = ((fb - x) * (1 + fa)) / ((fb - fa) * (1 + x))
            slot = sa if random.Random(hash(key)).random() < p_a else sb
            return slot, [(sa, p_a), (sb, 1.0 - p_a)]
    return pts[-1][1], [(pts[-1][1], 1.0)]


STREET_INDEX = {s: i for i, s in enumerate(B.STREETS)}
