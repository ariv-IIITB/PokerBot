"""Static sandbox scan: calls that read files or start processes/threads (the contest sandbox
forbids them in the submitted bot). Shared by tests/test_imports.py and tools/package_submission.

A file may be allow-listed (the `allow` set of repo-relative paths); every flagged call in an
allowed file must then carry a `# sandbox-allow: <reason>` comment. Phase D emptied the list."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

READ_CALLS = {"open", "load", "fromfile", "read_text", "read_bytes", "listdir", "scandir",
              "glob", "rglob", "iterdir", "system", "fork", "popen", "Popen", "spawn",
              "posix_spawn", "Thread", "Timer", "start_new_thread", "ThreadPoolExecutor"}
FLAGGED_PREFIXES = ("exec",)                       # os.execv, os.execvp, ...
ALLOW_MARK = "# sandbox-allow:"
# Shipped files that still contain a file-reading helper for the lab (never called by the bot;
# the audit-hook run proves it). Each flagged line carries the allow comment.
SHIPPED_ALLOW = {"variant/spec.py"}


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
