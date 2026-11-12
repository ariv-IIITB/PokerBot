"""Build a variant of the bundled final bot: patch module sources and CONFIG, write a new bot.py.

    python3 -I build_variant.py BASE_BOT OUT_BOT ARM[,ARM...]

Arms:
  rnr   river fold-rate mix as in tier3x (callers only, pmax 0.9, n0 10, min_n 10) in botsrc/river_glue.py
  bigb  size-aware river over-folder move: a trait on their folds to our big (>= 0.8 pot, not all-in) river bets,
        and when it says yes, weak hands move part of their check / shove mass to a 0.85-pot bet that leaves
        them chips (botsrc/exploit.py, botsrc/hooks.py, botsrc/policy.py, config exploit += riverfold)
Every replacement must match exactly once, or the build fails (no silent no-ops)."""
import ast
import sys


def sources(txt):
    for n in ast.parse(txt).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "_SOURCES":
            return ast.literal_eval(n.value)
    raise SystemExit("no _SOURCES")


def sub(src, old, new, what):
    if src.count(old) != 1:
        raise SystemExit(f"{what}: expected one match, found {src.count(old)}")
    return src.replace(old, new)


PATCHES = {
    "rnr": {
        "botsrc.river_glue": [
            ("FOLD_MIN_N = 20 ", "FOLD_MIN_N = 10 "),
            ("FOLD_PMAX = 0.5 ", "FOLD_PMAX = 0.9 "),
            ("FOLD_N0 = 40.0\n", "FOLD_N0 = 10.0\nFOLD_DIR = -1              # tier3x rnr_dir: mix only when they fold LESS than the equilibrium\n"),
            ("""        v, _, _ = s.locked_values(float(fold_obs))
        if v is not None:""",
             """        v, f_eq, f_to = s.locked_values(float(fold_obs))
        if v is not None and (FOLD_DIR == 0 or (f_to - f_eq) * FOLD_DIR > 0):"""),
        ],
    },
    "bigb": {
        "botsrc.exploit": [
            ('    "riverbluff": (0.45, 0.80),     # v2.1 0.36, tag 0.21; overbettor, maniac 1.00, rivershover 0.61\n}',
             '    "riverbluff": (0.45, 0.80),     # v2.1 0.36, tag 0.21; overbettor, maniac 1.00, rivershover 0.61\n'
             '    "riverfold": (0.45, 0.80),      # folds to our big (>= BIG_FOLD_FRAC pot) river bets that leave them chips\n}'),
            ('MOVES = ("overfolder", "station", "prefold", "aggressor", "riverbluff", "rivervalue", "rivernarrow")',
             'MOVES = ("overfolder", "station", "prefold", "aggressor", "riverbluff", "rivervalue", "rivernarrow", "riverfold")\n'
             'BIG_FOLD_FRAC = 0.8     # riverfold: our river bet or raise of at least this pot fraction, not all-in'),
            ("""        if s["facing_us"] and st == "river":
            tr["station"].add(a in ("call", "raise"), hand)""",
             """        if s["facing_us"] and st == "river":
            tr["station"].add(a in ("call", "raise"), hand)
            prev = steps[i - 1] if i >= 1 else None
            if prev is not None and prev["actor"] == "me" and prev["action"] == "raise" and not prev["allin"] \\
                    and (prev["frac"] or 0.0) >= BIG_FOLD_FRAC:
                tr["riverfold"].add(a == "fold", hand)"""),
            ("""def summary():
    m = _model""",
             """def bigbluff_strength():
    \"\"\"riverfold: 0..1, how hard to push big non-all-in river bluffs. 0 unless the move is on, their fold rate
    to our big non-all-in river bets tested "yes", and they are not a river station.\"\"\"
    m = _model
    if m is None or "riverfold" not in _state["moves"] or m.traits["station"].verdict == "yes":
        return 0.0
    return m.strength("riverfold")


def summary():
    m = _model"""),
        ],
        "botsrc.hooks": [
            ("""def exploit_summary():""",
             """def river_bigbluff_strength():
    \"\"\"0..1: the riverfold move's strength (0 with the move off or no evidence).\"\"\"
    return X.bigbluff_strength()


def exploit_summary():"""),
        ],
        "botsrc.policy": [
            ("""AGGR_RATIO = 2.0           # ... and the opponent must raise at least this many times as often as we do
""",
             """AGGR_RATIO = 2.0           # ... and the opponent must raise at least this many times as often as we do
BIG_BLUFF_FRAC = 0.85      # riverfold move: bet this pot fraction ...
BIG_BLUFF_MIN = 0.8        # ... at least this (the size the read is about) and below all-in for them
BIG_BLUFF_EQ = 0.30        # ... with hands below this equity against their range now
BIG_BLUFF_SHIFT = 0.5      # ... moving this share of the check / shove mass at full strength (at most TV_CAP)
"""),
            ("""        dist, options = self.solver_dist(out, req)
        if dist is None:
            key = "solver_none" if out is None else "solver_invalid"
            stats.river[key] = stats.river.get(key, 0) + 1
            return None
""",
             """        dist, options = self.solver_dist(out, req)
        if dist is None:
            key = "solver_none" if out is None else "solver_invalid"
            stats.river[key] = stats.river.get(key, 0) + 1
            return None
        try:
            dist, options = self.big_bluff(hs, req, board, ctx, dist, options, stats)
        except Exception:
            stats.river["big_bluff_errors"] = stats.river.get("big_bluff_errors", 0) + 1
"""),
            ("""    def keep_solver_likelihood(self, hs, req, ctx, action, stats):""",
             """    def big_bluff(self, hs, req, board, ctx, dist, options, stats):
        \"\"\"riverfold move: against an opponent who folds to our big river bets that leave them chips, a weak hand
        moves part of its check and shove mass to a BIG_BLUFF_FRAC-pot bet below all-in.\"\"\"
        s = float(hooks.river_bigbluff_strength())
        legal = req["legal_actions"]
        if s <= 0 or req["to_call"] != 0 or "raise" not in legal or req.get("min_raise") is None:
            return dist, options
        pot, lo, hi = req["pot"], int(req["min_raise"]), int(req["max_raise"])
        amt = max(lo, int(math.ceil(BIG_BLUFF_FRAC * pot)))
        if amt > hi - 2 or amt < BIG_BLUFF_MIN * pot:
            return dist, options                        # no big bet that leaves them chips
        opp = ctx.opp_range_now if ctx.opp_range_now is not None else ctx.opp_range
        if RG.equity(board[:5], hs.hole, opp) >= BIG_BLUFF_EQ:
            return dist, options
        lam = min(TV_CAP, BIG_BLUFF_SHIFT * s)
        label = f"raise:{amt}"
        new, moved = dict(dist), 0.0
        for k, v in dist.items():
            if k == "check" or (k.startswith("raise:") and int(k[6:]) >= hi):
                new[k] = v * (1.0 - lam)
                moved += v * lam
        if moved <= 0:
            return dist, options
        new[label] = new.get(label, 0.0) + moved
        options = dict(options)
        options[label] = {"type": "action", "action": "raise", "amount": amt}
        stats.river["big_bluff"] = stats.river.get("big_bluff", 0) + 1
        return new, options

    def keep_solver_likelihood(self, hs, req, ctx, action, stats):"""),
        ],
    },
}
PATCHES["soft"] = {     # sensitivity probe: a softer opponent range model (tau 0.7 -> 0.5, flat mix 0.1 -> 0.25)
    "botsrc.hooks": [("DEFAULT_TAU = 0.7\n", "DEFAULT_TAU = 0.5\n")],
    "botsrc.ranges": [("FLAT_MIX = 0.1\n", "FLAT_MIX = 0.25\n")],
}
CONFIG_ADD = {"bigb": ("exploit", "riverfold")}


def main():
    base, out, arms = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    txt = open(base).read()
    src = sources(txt)
    for arm in arms:
        for mod, reps in PATCHES[arm].items():
            old = src[mod][1]
            new = old
            for o, n in reps:
                new = sub(new, o, n, f"{arm}/{mod}")
            txt = sub(txt, repr(old), repr(new), f"{arm}/{mod} literal")
            src[mod] = (src[mod][0], new)
            compile(new, mod, "exec")                   # syntax check of the patched module
        if arm in CONFIG_ADD:
            key, item = CONFIG_ADD[arm]
            line = next(l for l in txt.splitlines() if l.startswith("CONFIG = "))
            cfg = ast.literal_eval(line[len("CONFIG = "):])
            cfg[key] = cfg[key] + "," + item
            txt = sub(txt, line, "CONFIG = " + repr(cfg), f"{arm} config")
    open(out, "w").write(txt)
    print(f"wrote {out} with arms {arms}")


if __name__ == "__main__":
    main()
