"""Phase 1 sanity checks: right interpreter, runtime deps importable, layout present."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_python_is_311() -> None:
    # The competition runtime is Python 3.11; develop against exactly that.
    assert sys.version_info[:2] == (3, 11), sys.version


def test_runtime_deps_import() -> None:
    import numpy  # noqa: F401
    import scipy  # noqa: F401


def test_layout_exists() -> None:
    for d in ["variant", "bot", "bot/brains", "bot/config", "lab", "lab/sparring",
              "snapshots", "docs", "tests"]:
        assert (ROOT / d).is_dir(), d
