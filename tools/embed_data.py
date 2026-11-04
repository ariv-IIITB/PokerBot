"""Generate bot/embedded.py: everything the submitted bot used to read from disk.

    .venv/bin/python -m tools.embed_data [--variant PATH|CATALOG_NAME] [--out bot/embedded.py]
        [--check]

The sandbox gives the bot no file reads, so the active variant spec, the hyperparameters
(bot/config/*.json) and the precomputed tables (data/<variant>/) are written into one Python
module with three names:

    SPEC       the variant spec as a dict (variant/active.json, else the catalog's holdem_nl)
    PARAMS     {"tier1": {...}, "tier2": {...}}
    ARTIFACTS  {name: {"meta": {...}, "files": {file: <base64 of the .npy file>, ...}}}
               (bot/artifacts.py): "tables" (data/<variant>/, bot/sim/tables.py) and "types"
               (data/<variant>/types.json, the opponent type library, bot/strategy/types.py)

An artifact is embedded only when it was built for the spec (spec hash) and is ready (the
consumer's own rule, e.g. bot.sim.tables.ready). The file is capped at 3 MB (the submission limit is 5 MB). --check exits 1 if the
committed file is out of date. tests/test_embed.py runs the same check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pprint
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.artifacts import built_for, encode_npy  # noqa: E402
from bot.sim import tables as tables_mod  # noqa: E402
from variant.spec import VariantSpec, load_catalog, spec_hash  # noqa: E402,F401

OUT = ROOT / "bot" / "embedded.py"
CONFIG_DIR = ROOT / "bot" / "config"
DATA_DIR = ROOT / "data"
ACTIVE = ROOT / "variant" / "active.json"
MAX_BYTES = 3_000_000
TABLE_FILES = tables_mod.REQUIRED + tables_mod.OPTIONAL   # what bot/sim/tables.py reads
CHUNK = 96                                             # base64 characters per source line


def load_spec(variant: Optional[str] = None) -> tuple[VariantSpec, str]:
    """(spec, label) for a path, a catalog name, or the active variant."""
    if variant is None:
        variant = str(ACTIVE) if ACTIVE.is_file() else "holdem_nl"
    if Path(variant).is_file():
        p = Path(variant).resolve()
        label = p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.name
        return VariantSpec.load(p), label
    return load_catalog()[variant], f"catalog:{variant}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _params(config_dir: Path) -> tuple[dict, dict]:
    """({name: params}, {source: hash}) for every bot/config/*.json (comment keys dropped)."""
    params, sources = {}, {}
    for f in sorted(config_dir.glob("*.json")):
        params[f.stem] = {k: v for k, v in json.loads(f.read_text()).items()
                          if not k.startswith("_")}
        sources[f"bot/config/{f.name}"] = _sha(f.read_bytes())
    return params, sources


def _tables(spec: VariantSpec, data_dir: Path) -> tuple[Optional[dict], dict]:
    """(the "tables" artifact or None, {source: hash}). Embedded only if built for the spec
    and ready by bot/sim/tables.py's own rule."""
    d = data_dir / spec.name
    try:
        meta = json.loads((d / "meta.json").read_text())
    except (OSError, ValueError):
        return None, {}
    if not built_for(meta, spec) or not tables_mod.ready(meta):
        return None, {}
    files, sources = {}, {f"data/{spec.name}/meta.json": _sha((d / "meta.json").read_bytes())}
    for name in TABLE_FILES:
        f = d / f"{name}.npy"
        optional = name in tables_mod.OPTIONAL
        if optional and not tables_mod.ready(meta, name):
            continue
        if not f.is_file():
            if optional:
                continue
            return None, {}
        raw = f.read_bytes()
        files[name] = encode_npy(raw)
        sources[f"data/{spec.name}/{f.name}"] = _sha(raw)
    return {"meta": meta, "files": files}, sources


def _types(spec: VariantSpec, data_dir: Path) -> tuple[Optional[dict], dict]:
    """(the "types" artifact or None, {source: hash}): the opponent type library
    (data/<variant>/types.json, lab/opps/types.py; read by bot/strategy/types.py)."""
    f = data_dir / spec.name / "types.json"
    try:
        raw = f.read_bytes()
        lib = json.loads(raw)
    except (OSError, ValueError):
        return None, {}
    if not built_for(lib, spec):
        return None, {}
    return {"meta": lib, "files": {}}, {f"data/{spec.name}/types.json": _sha(raw)}


def _literal(value) -> str:
    return pprint.pformat(value, width=100, sort_dicts=False)


def _artifacts_literal(artifacts: dict) -> str:
    if not artifacts:
        return "{}"
    out = ["{"]
    for art_name, art in artifacts.items():
        out += [f'    "{art_name}": {{', f'        "meta": {_literal(art["meta"])},', '        "files": {']
        for name, b64 in art["files"].items():
            chunks = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)] or [""]
            out.append(f'            "{name}": (')
            out += [f'                "{c}"' for c in chunks]
            out.append("            ),")
        out += ["        },", "    },"]
    out.append("}")
    return "\n".join(out)


def render(variant: Optional[str] = None, config_dir: Path = CONFIG_DIR,
           data_dir: Path = DATA_DIR) -> str:
    """The text of bot/embedded.py for the current sources."""
    spec, label = load_spec(variant)
    params, src = _params(config_dir)
    tables, tsrc = _tables(spec, data_dir)
    types, ysrc = _types(spec, data_dir)
    artifacts = {"tables": tables} if tables is not None else {}
    if types is not None:
        artifacts["types"] = types
    sources = {f"spec ({label})": _sha(json.dumps(spec.to_dict(), sort_keys=True).encode()),
               **src, **tsrc, **ysrc}
    arg = "" if variant is None else f" --variant {variant}"
    text = (
        '"""GENERATED FILE, do not edit. Everything the bot used to read from disk.\n\n'
        f"Regenerate with:  .venv/bin/python -m tools.embed_data{arg}\n"
        "Checked by tests/test_embed.py; see tools/embed_data.py for the layout.\n"
        '"""\n'
        f"SOURCES = {_literal(sources)}\n\n"
        f"SPEC = {_literal(spec.to_dict())}\n\n"
        f"PARAMS = {_literal(params)}\n\n"
        f"ARTIFACTS = {_artifacts_literal(artifacts)}\n"
    )
    if len(text.encode()) > MAX_BYTES:
        raise SystemExit(f"bot/embedded.py would be {len(text) / 1e6:.1f} MB > cap "
                         f"{MAX_BYTES / 1e6:.0f} MB; drop tables or shrink them")
    return text


def problems(path: Path = OUT, variant: Optional[str] = None, config_dir: Path = CONFIG_DIR,
             data_dir: Path = DATA_DIR) -> list[str]:
    """Why `path` is out of date ([] = current). Table files that are not on this machine
    (data/ is not committed) cannot be re-checked and are skipped; everything else must match."""
    if not path.is_file():
        return [f"{path} is missing"]
    committed, fresh = path.read_text(), render(variant, config_dir, data_dir)
    if committed == fresh:
        return []
    ns_old: dict = {}
    ns_new: dict = {}
    exec(compile(committed, str(path), "exec"), ns_old)      # trusted: our own generated file
    exec(compile(fresh, "<fresh>", "exec"), ns_new)
    out = []
    for key in ("SPEC", "PARAMS"):
        if ns_old.get(key) != ns_new[key]:
            out.append(f"{key} differs from its source")
    old_src = {k: v for k, v in ns_old.get("SOURCES", {}).items() if not k.startswith("data/")}
    new_src = {k: v for k, v in ns_new["SOURCES"].items() if not k.startswith("data/")}
    changed = sorted(k for k in set(old_src) | set(new_src) if old_src.get(k) != new_src.get(k))
    if changed:
        out.append("source files changed: " + ", ".join(changed))
    if ns_new["ARTIFACTS"] and ns_old.get("ARTIFACTS") != ns_new["ARTIFACTS"]:
        out.append("ARTIFACTS differ from data/ on this machine")
    if not ns_new["ARTIFACTS"] and not ns_old.get("ARTIFACTS") and not out:
        out.append("formatting differs from the generator's output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Write bot/embedded.py from the sources.")
    ap.add_argument("--variant", default=None, help="spec path or catalog name "
                    "(default: variant/active.json, else holdem_nl)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="exit 1 if --out is out of date")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.check:
        bad = problems(out, args.variant)
        print("\n".join(bad) if bad else f"{out} is current")
        return 1 if bad else 0
    text = render(args.variant)
    out.write_text(text)
    print(f"wrote {out} ({len(text.encode()) / 1e3:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
