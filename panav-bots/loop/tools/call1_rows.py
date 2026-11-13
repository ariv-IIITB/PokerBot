"""call1: one row per postflop decision of the logged bot that FACES a bet/raise of 0.5-1.6 pot, with the bot's own
equity proxy (S1 / max, as in botsrc.policy: best keep on the flop, the kept pair later), its reply and the chips
from the decision on (net + committed; fold = 0).

  PYTHONPATH=panav-bots/loop/tools .venv/bin/python panav-bots/loop/tools/call1_rows.py OUT.json label=DIR [label=DIR ...]
"""
from __future__ import annotations
import ast, importlib.abc, importlib.util, json, sys
from pathlib import Path
import d1_lib as L

SRC = ast.literal_eval(next(n.value for n in ast.parse(L.BOT.read_text()).body
                            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_SOURCES"))


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        return importlib.util.spec_from_loader(name, self, is_package=SRC[name][0]) if name in SRC else None
    def create_module(self, spec): return None
    def exec_module(self, m): exec(compile(SRC[m.__name__][1], m.__name__, "exec"), m.__dict__)


sys.meta_path.insert(0, _F())
from shared import features as F  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
from botsrc_pf import size_fraction  # noqa: E402  (copy of botsrc.potfold.size_fraction)

MAX_S1 = {"flop": 47 * 2 * 1035, "turn": 46 * 2 * 990, "river": 2 * 990}


def proxy(street, board, hole3, kept):
    n = {"flop": 3, "turn": 4, "river": 5}[street]
    b = L.cards(board[:n])
    rows = F.street_rows(b, street != "river")
    if street == "flop":
        pairs = F.hand_pairs(sorted(L.cards(hole3)))
        return max(x[0] for x in F.own_features(rows, pairs)) / MAX_S1[street]
    pr = sorted(L.cards(kept))
    return F.own_features(rows, [tuple(pr)])[0][0] / MAX_S1[street]


def main():
    out = sys.argv[1]; rows = []
    for spec in sys.argv[2:]:
        label, d = spec.split("=", 1)
        for h in L.parse_dir(d):
            net = h["res"]["net"]; kept = h["dres"]["hole_cards"] if h["dres"] else None
            for r in h["reqs"]:
                if r["street"] == "preflop" or r["to_call"] <= 0 or r.get("reply") is None:
                    continue
                f = size_fraction(r)
                if f is None or not (0.5 <= f <= 1.6):
                    continue
                if r["street"] != "flop" and kept is None:
                    continue
                rows.append(dict(bot=label, seed=h["seed"], leg=h["leg"], hand=h["hand_id"], seat=0 if h["seat"] == "button" else 1,
                                 street=r["street"], f=f, allin=r["opp_stack"] == 0, pot=r["pot"], to_call=r["to_call"],
                                 px=proxy(r["street"], r["board"], h["hole3"], kept), act=r["reply"]["action"],
                                 out=net + h["start"] - r["my_stack"], net=net,
                                 raises=len([a for a in r["history"] if a["street"] == r["street"] and a["action"] == "raise"])))
        print(label, len(rows), flush=True)
    Path(out).write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
