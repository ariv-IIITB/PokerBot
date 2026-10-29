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


# --------------------------------------------------------------------------- sandbox guard
# The real engine runs the bot in a sandbox: no file reads, no processes, no threads. Every
# data file the bot needs must be embedded in bot/embedded.py (tools/embed_data.py).
# Calls below are flagged by name; a temporary allow-list holds the loaders that still read
# files. Each allowed line must carry a `# sandbox-allow: <reason>` comment; Phase D removes
# the allow-list.
READ_CALLS = {"open", "load", "fromfile", "read_text", "read_bytes", "listdir", "scandir",
              "glob", "rglob", "iterdir", "system", "fork", "popen", "Popen", "spawn",
              "posix_spawn", "Thread", "Timer", "start_new_thread", "ThreadPoolExecutor"}
FLAGGED_PREFIXES = ("exec",)                       # os.execv, os.execvp, ...
SANDBOX_ALLOW: set[str] = set()   # Phase D removed the loaders' allow-list: nothing may read files
ALLOW_MARK = "# sandbox-allow:"


def _call_name(node: ast.Call) -> str:
    fn = node.func
    return fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")


def sandbox_violations(path: Path, source: str, allow: set[str]) -> list[str]:
    """Calls in `source` that read files or start processes/threads, minus the allowed ones."""
    rel = path.relative_to(ROOT).as_posix() if path.is_absolute() else path.as_posix()
    lines = source.splitlines()
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in READ_CALLS and not name.startswith(FLAGGED_PREFIXES):
            continue
        if name == "load" and not _is_file_load(node):
            continue
        line = lines[node.lineno - 1]
        if rel in allow:
            if ALLOW_MARK not in line:
                out.append(f"{rel}:{node.lineno}: {name}() in an allowed file lacks "
                           f"'{ALLOW_MARK} <reason>'")
        else:
            out.append(f"{rel}:{node.lineno}: {name}() is not allowed in the submitted bot")
    return out


def _is_file_load(node: ast.Call) -> bool:
    """`load` is only a file read for np.load / VariantSpec.load (json.load takes a handle,
    and a handle needs open(), which is flagged on its own)."""
    fn = node.func
    return (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
            and fn.value.id in {"np", "numpy", "VariantSpec"})


def test_sandbox_no_file_reads_or_processes() -> None:
    bad = []
    for f in BOT_FILES:
        bad += sandbox_violations(f, f.read_text(), SANDBOX_ALLOW)
    assert not bad, "\n".join(bad)


def test_sandbox_guard_catches_violations() -> None:
    """The scanner itself: each forbidden call is found, and allowed lines need the comment."""
    p = Path("bot/x.py")
    for src in ("open('f')", "np.load('a.npy')", "path.read_text()", "os.listdir('.')",
                "glob.glob('*')", "os.system('ls')", "os.fork()", "os.execv('a', [])",
                "os.popen('ls')", "threading.Thread(target=f)", "VariantSpec.load('x')"):
        assert sandbox_violations(p, src, set()), src
    assert not sandbox_violations(p, "json.load(f); threading.current_thread()", set())
    allowed = {"bot/x.py"}
    assert sandbox_violations(p, "open('f')", allowed)
    assert not sandbox_violations(p, "open('f')  # sandbox-allow: tables", allowed)


def test_sandbox_allow_list_is_not_stale() -> None:
    # Every allowed file really contains a flagged call (so the list shrinks as files are fixed).
    for rel in SANDBOX_ALLOW:
        marked = [ln for ln in (ROOT / rel).read_text().splitlines() if ALLOW_MARK in ln]
        assert marked, f"{rel} is allow-listed but has no '{ALLOW_MARK}' line"
