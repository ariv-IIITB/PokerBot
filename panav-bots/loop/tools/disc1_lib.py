"""DISC1 helpers: import the bot's own shared.* modules from an evalbuild file (no file system, same code as the bot)."""
from __future__ import annotations
import ast, importlib.abc, importlib.util, sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1] / "evalbuilds" / "final_seeded.py"
_SRC = None


def load_sources(path=BOT):
    global _SRC
    if _SRC is None:
        tree = ast.parse(Path(path).read_text())
        for n in tree.body:
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_SOURCES":
                _SRC = ast.literal_eval(n.value)
    return _SRC


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        s = load_sources()
        if fullname in s:
            return importlib.util.spec_from_loader(fullname, self, is_package=s[fullname][0])
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(compile(load_sources()[module.__name__][1], "<bot:" + module.__name__ + ">", "exec"), module.__dict__)


def install():
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())


_BP = None


def blueprint(path=BOT):
    """(tables, th, layout, pot_class_fn) decoded from the bot's own blob."""
    global _BP
    if _BP is None:
        install()
        tree = ast.parse(Path(path).read_text())
        blob = None
        for n in tree.body:
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_BLOB":
                blob = ast.literal_eval(n.value)
        import shared.blob as BL, shared.infoset as I, shared.features as F, shared.abstraction as AB, shared.betting as B
        header, arrays = BL.decode_blob(blob)
        meta = header["meta"]
        A = AB.get(meta.get("abstraction"))
        Lay = I.layout(A)
        th = F.Thresholds.from_json_bytes(arrays["THRESHOLDS"].tobytes(), expect_sha=meta["thresholds_sha"], abstraction=A)
        tables = {t: arrays[t] for t in Lay.TABLES}
        _BP = (tables, th, Lay, B.pot_class)
    return _BP
