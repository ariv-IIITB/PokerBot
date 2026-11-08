"""Bundle the built package (dist/submission) into ONE self-contained bot.py: every module's source is embedded
and served by an in-memory importer, so the file runs alone with `python3.11 bot.py` (no folders, no file reads).

    .venv/bin/python -m tools.package_submission --zip --stage2     # build dist/submission first
    .venv/bin/python -m tools.single_file                            # -> dist/single/bot.py"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOADER = '''
import importlib.abc
import importlib.util
import sys

sys.dont_write_bytecode = True


class _Embedded(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Serves the embedded modules above from memory."""

    def find_spec(self, name, path=None, target=None):
        if name in _SRC:
            return importlib.util.spec_from_loader(name, self, is_package=name in _PKG)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__
        if name in _PKG:
            module.__path__ = []
        module.__file__ = "<embedded:" + name + ">"
        exec(compile(_SRC[name], module.__file__, "exec"), module.__dict__)


sys.meta_path.insert(0, _Embedded())

from bot.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["--protocol", "pokerbots"]))
'''


def build(src: Path, out: Path) -> Path:
    mods: dict[str, str] = {}
    pkgs: set[str] = set()
    for f in sorted(src.rglob("*.py")):
        rel = f.relative_to(src)
        if rel == Path("bot.py") or "__pycache__" in rel.parts:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
            pkgs.add(".".join(parts))
        mods[".".join(parts)] = f.read_text()
    head = ('"""Synergy PokerBots submission, single file: `python3.11 bot.py` (pokerbots protocol on stdin/stdout).\n'
            f'Built by tools/single_file.py from {src.name}/ ({len(mods)} modules embedded)."""\n')
    body = f"_SRC = {mods!r}\n_PKG = {sorted(pkgs)!r}\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(head + body + LOADER)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "dist" / "submission"))
    ap.add_argument("--out", default=str(ROOT / "dist" / "single" / "bot.py"))
    a = ap.parse_args()
    p = build(Path(a.src), Path(a.out))
    print(f"{p} ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
