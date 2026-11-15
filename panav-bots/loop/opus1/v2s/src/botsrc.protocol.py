"""Protocol helpers (Protocol Specification §5-§9, BUILDMAP §9.2): safe replies and legality checks.

Everything here works on untrusted input and never raises.
"""
from shared.cards import RANKS, SUITS


def _num(x, default):
    try:
        return float(x)
    except Exception:
        return default


def fallback_action(req):
    """§9.2: check if legal; else call if to_call <= pot/4; else fold."""
    legal = req.get("legal_actions") if isinstance(req, dict) else None
    legal = legal if isinstance(legal, list) else []
    if "check" in legal:
        return {"type": "action", "action": "check"}
    to_call = _num(req.get("to_call"), 1.0) if isinstance(req, dict) else 1.0
    pot = _num(req.get("pot"), 0.0) if isinstance(req, dict) else 0.0
    if "call" in legal and to_call <= pot / 4:
        return {"type": "action", "action": "call"}
    if "fold" in legal:
        return {"type": "action", "action": "fold"}
    if "call" in legal:
        return {"type": "action", "action": "call"}
    return {"type": "action", "action": "check"}


def default_discard(hole):
    """The engine's own default (lowest rank; spades, hearts, diamonds, clubs first), sent explicitly
    so the engine does not need to correct us. None if no hole card is valid."""
    if not isinstance(hole, list):
        return None
    valid = [c for c in hole if isinstance(c, str) and len(c) == 2 and c[0] in RANKS and c[1] in SUITS]
    if not valid:
        return None
    return min(valid, key=lambda c: (RANKS.index(c[0]), SUITS.index(c[1])))


def legal_reply(reply, req):
    """True iff the engine would accept this action reply for this request (engine.parse_action)."""
    try:
        if not isinstance(reply, dict) or reply.get("type") != "action":
            return False
        a = reply.get("action")
        if a not in req["legal_actions"]:
            return False
        if a == "raise":
            amt = reply.get("amount")
            return type(amt) is int and req["min_raise"] <= amt <= req["max_raise"]
        return True
    except Exception:
        return False
