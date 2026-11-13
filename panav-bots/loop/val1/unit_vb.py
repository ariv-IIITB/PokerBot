"""unit test of the valuebet move via the unpacked sources: python unit_vb.py SRCDIR"""
import sys, types; sys.dont_write_bytecode = True
import sys, types, importlib.util
src = sys.argv[1] + "/src"
sys.path.insert(0, ".")
# load shared + botsrc modules from the bundle as packages
import importlib.machinery
def load(name, fn):
    spec = importlib.util.spec_from_file_location(name, f"{src}/{fn}"); m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
for pk in ("shared", "botsrc"):
    p = types.ModuleType(pk); p.__path__ = []; sys.modules[pk] = p
for f in ("shared.cards.py", "shared.showdown.py"):
    pass
import numpy  # noqa
for fn in sorted(__import__("os").listdir(src)):
    n = fn[:-3]
    if n.startswith("shared.") and n.count(".") == 1 and n not in ("shared.blob",):
        try: load(n, fn); setattr(sys.modules["shared"], n.split(".")[1], sys.modules[n])
        except Exception as e: pass
X = load("botsrc.exploit", "botsrc.exploit.py")
class A: flop_v = 4; gap = 1; flop_s1 = 10; turn_v = 2; turn_s1 = 10
class Ctx: pass
def ctx(street, bucket, to_call, legal):
    c = Ctx(); c.street = street; c.bucket = bucket; c.rule = None; c.source = "blueprint"; c.node_id = 5
    c.request = {"to_call": to_call, "pot": 10}; c.options = {k: 1 for k in legal}; return c
X.setup({"exploit": "valuebet", "vb_gate": "off", "vb_bet": 0.5, "vb_raise": 0.5}, A)
X._model.seat = "button"
d = X.adjust(ctx("flop", 38, 0, ["check", "sizeA", "sizeB"]), {"check": 0.8, "sizeA": 0.2})
print("open strong", d); assert d["check"] < 0.5 and d["sizeA"] > 0.4
d = X.adjust(ctx("flop", 5, 0, ["check", "sizeA"]), {"check": 0.8, "sizeA": 0.2}); print("open weak", d); assert d["check"] == 0.8
d = X.adjust(ctx("turn", 19, 4, ["fold", "call", "raise"]), {"fold": 0.1, "call": 0.9}); print("facing strong", d); assert d.get("raise", 0) > 0.4
X.setup({"exploit": "valuebet"}, A); X._model.seat = "button"
d = X.adjust(ctx("flop", 38, 0, ["check", "sizeA"]), {"check": 0.8, "sizeA": 0.2}); print("gated, no trait", d); assert d["check"] == 0.8
for i in range(30): X._model.traits["caller"].add(1, i)
print("caller verdict", X._model.traits["caller"].verdict, X._model.traits["caller"].strength)
d = X.adjust(ctx("flop", 38, 0, ["check", "sizeA"]), {"check": 0.8, "sizeA": 0.2}); print("gated, caller yes", d); assert d["check"] < 0.8
print("OK")
