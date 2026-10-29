"""Runtime sandbox check: play a transcript through the real entry point under an audit hook
(tests/kit/sandbox_run.py) and fail on any file read, socket or process the sandbox forbids.

Phase D embedded the data files (bot/embedded.py) and emptied the allow-list in
test_imports.py, so this test must pass.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT = ROOT / "tests" / "fixtures" / "protocol" / "placeholder_hand.txt"
RUNNER = ROOT / "tests" / "kit" / "sandbox_run.py"


def run_sandboxed(protocol: str, transcript: Path, brain: str = "tier2") -> tuple[list[str], str]:
    """(violation lines, stdout) of the bot on the E> lines of `transcript`."""
    lines = [ln[3:] for ln in transcript.read_text().splitlines() if ln.startswith("E> ")]
    proc = subprocess.run([sys.executable, str(RUNNER), "--protocol", protocol, "--brain", brain],
                          input="\n".join(lines) + "\n", capture_output=True, text=True,
                          cwd=ROOT, timeout=120)
    bad = [ln for ln in proc.stderr.splitlines() if ln.startswith("SANDBOX-VIOLATION")]
    return bad, proc.stdout


def test_runner_reports_violations(tmp_path) -> None:
    # The hook itself: a tiny program that reads a file and forks must be reported.
    script = tmp_path / "prog.py"
    script.write_text("import os, sys\nsys.path.insert(0, %r)\n"
                      "from kit.sandbox_run import _hook\nsys.addaudithook(_hook)\n"
                      "open(%r).read()\nos.system('true')\n" % (str(ROOT / "tests"), str(script)))
    proc = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True)
    events = [ln.split()[1] for ln in proc.stderr.splitlines() if "SANDBOX-VIOLATION" in ln]
    assert "os.system" in events and "subprocess.Popen" not in events


def test_bot_runs_inside_the_sandbox() -> None:
    bad, out = run_sandboxed("placeholder", TRANSCRIPT)
    assert out.strip(), "the bot sent no actions"
    assert not bad, "\n".join(bad)


def test_bot_runs_inside_the_sandbox_over_the_real_protocol() -> None:
    """The Protocol section 10 hand, real wire format, the shipped brain: no forbidden event."""
    example = ROOT / "tests" / "fixtures" / "protocol" / "example_hand.txt"
    bad, out = run_sandboxed("pokerbots", example)
    assert len(out.splitlines()) == 5, out               # raise, raise, discard, check, raise
    assert not bad, "\n".join(bad)
