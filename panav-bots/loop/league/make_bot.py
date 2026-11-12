"""make_bot.py PARAMS.json OUT.py -- write a standalone league bot (common.py + param_bot body + baked PARAMS).

PARAMS.json may be a flat dict of params (missing keys take the defaults). Unknown keys are an error.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON = HERE.parent.parent / "eval_bots" / "spar" / "common.py"


def build(params: dict) -> str:
    body = (HERE / "param_bot.py").read_text()
    body = re.sub(r"# ---- BEGIN-IMPORT.*?# ---- END-IMPORT\n", "", body, flags=re.S)
    body = re.sub(r"# ---- BEGIN-MAIN.*?# ---- END-MAIN\n", "", body, flags=re.S)
    # param_bot's header imports (os, sys) duplicate common's; harmless.
    ns = {"__name__": "league_check"}
    exec(compile(COMMON.read_text(), "common", "exec"), ns)
    exec(compile(body, "param_bot", "exec"), ns)
    bad = set(params) - set(ns["SPACE"])
    if bad:
        raise SystemExit(f"unknown params: {sorted(bad)}")
    p = {k: float(v) for k, v in params.items()}
    body = body.replace("PARAMS = {}  ", f"PARAMS = {json.dumps(p, sort_keys=True)}  ", 1)
    assert "PARAMS = {" in body and json.dumps(p, sort_keys=True) in body
    return (COMMON.read_text() + "\n\n# ================= league param bot =================\n" + body
            + "\n\nif __name__ == \"__main__\":\n    run(Bot)\n")


def main():
    params = json.loads(Path(sys.argv[1]).read_text())
    Path(sys.argv[2]).write_text(build(params))


if __name__ == "__main__":
    main()
