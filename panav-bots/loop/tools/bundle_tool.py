"""Unpack / repack a single-file bot (panav-bots/final/bot.py style: _SOURCES dict + _BLOB + CONFIG).

  .venv/bin/python panav-bots/loop/tools/bundle_tool.py unpack panav-bots/final/bot.py OUTDIR   # OUTDIR/src/<module>.py, config.json
  .venv/bin/python panav-bots/loop/tools/bundle_tool.py pack   panav-bots/final/bot.py OUTDIR NEW_BOT.py
Pack = the original file with _SOURCES (and CONFIG, from config.json) replaced by the edited ones. The blob is untouched.
"""
from __future__ import annotations
import ast, json, re, sys
from pathlib import Path


def _split(text: str):
    i = text.index("_SOURCES = {")
    j = text.index("\n}\n", i) + 3
    return text[:i], text[i:j], text[j:]


def unpack(bot: str, out: str) -> None:
    text = Path(bot).read_text()
    pre, srcs, post = _split(text)
    d = ast.literal_eval(srcs[len("_SOURCES = "):])
    o = Path(out); (o / "src").mkdir(parents=True, exist_ok=True)
    order = []
    for name, (is_pkg, source) in d.items():
        (o / "src" / (name + ".py")).write_text(source)
        order.append([name, is_pkg])
    (o / "order.json").write_text(json.dumps(order))
    m = re.search(r"^CONFIG = (\{.*\})$", pre, re.M)
    (o / "config.json").write_text(json.dumps(ast.literal_eval(m.group(1)), indent=1))
    print(f"{len(d)} modules -> {o}/src ; config -> {o}/config.json")


def pack(bot: str, out: str, new: str) -> None:
    text = Path(bot).read_text()
    pre, srcs, post = _split(text)
    o = Path(out)
    order = json.loads((o / "order.json").read_text())
    d = {name: (is_pkg, (o / "src" / (name + ".py")).read_text()) for name, is_pkg in order}
    cfg = json.loads((o / "config.json").read_text())
    pre = re.sub(r"^CONFIG = \{.*\}$", lambda _m: "CONFIG = " + repr(cfg), pre, flags=re.M)
    body = "_SOURCES = {\n" + "".join(f"    {k!r}: ({v[0]!r}, {v[1]!r}),\n" for k, v in d.items()) + "}\n"
    Path(new).write_text(pre + body + post)
    compile(Path(new).read_text(), new, "exec")
    print("wrote", new)


if __name__ == "__main__":
    {"unpack": lambda: unpack(sys.argv[2], sys.argv[3]), "pack": lambda: pack(*sys.argv[2:5])}[sys.argv[1]]()
