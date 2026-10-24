"""Static checks on bot/: only allowed imports, no network modules, no file writes."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT_FILES = sorted((ROOT / "bot").rglob("*.py"))

ALLOWED_THIRD_PARTY = {"numpy", "scipy"}
LOCAL = {"bot", "variant"}     # variant/ ships with the bot
FORBIDDEN = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib",
             "telnetlib", "xmlrpc", "socketserver", "asyncio", "webbrowser", "requests",
             "subprocess", "multiprocessing", "sqlite3", "tempfile", "shutil"}
WRITE_CALLS = {"save", "savez", "savez_compressed", "savetxt", "tofile", "write_text",
               "write_bytes", "mkdir", "makedirs", "remove", "unlink", "rename"}


def _imports(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_bot_files_exist() -> None:
    assert len(BOT_FILES) >= 5


def test_only_allowed_imports() -> None:
    allowed = set(sys.stdlib_module_names) | ALLOWED_THIRD_PARTY | LOCAL
    for f in BOT_FILES:
        mods = _imports(ast.parse(f.read_text()))
        bad = {m for m in mods if m not in allowed or m in FORBIDDEN}
        assert not bad, f"{f.relative_to(ROOT)} imports {bad}"


def test_scipy_only_imported_lazily() -> None:
    # A top-level `import scipy` would slow startup; it must live inside a function.
    for f in BOT_FILES:
        tree = ast.parse(f.read_text())
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert "scipy" not in _imports(node), f"{f.relative_to(ROOT)}: top-level scipy"


def test_no_file_writes() -> None:
    for f in BOT_FILES:
        for node in ast.walk(ast.parse(f.read_text())):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            assert name not in WRITE_CALLS, f"{f.relative_to(ROOT)}:{node.lineno} calls {name}"
            if name == "open":
                modes = [a for a in node.args[1:2]] + [k.value for k in node.keywords if k.arg == "mode"]
                for m in modes:
                    assert isinstance(m, ast.Constant) and not set(str(m.value)) & set("wax+"), \
                        f"{f.relative_to(ROOT)}:{node.lineno} opens a file for writing"
