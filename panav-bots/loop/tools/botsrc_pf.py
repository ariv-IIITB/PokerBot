"""copy of botsrc.potfold.size_fraction for offline analysis"""

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


