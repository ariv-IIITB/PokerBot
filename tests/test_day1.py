"""Phase 20: day-1 tools (new_variant scaffolding, submission packaging)."""
import json
import sys

import pytest

from lab import new_variant
from lab.engine import play_match
from lab.players import PlayerSpec, SubprocessPlayer
from tools import package_submission as pkg
from variant.spec import default_program, load_catalog


def test_new_variant_from_preset_validates_and_explains(tmp_path, capsys) -> None:
    spec = tmp_path / "active.json"
    assert new_variant.main(["--from", "mit2026_discard", "--spec", str(spec), "--hands", "80"]) == 0
    out = capsys.readouterr().out
    assert "discards 1 hole card(s) to the board" in out and "smoke fuzz: OK" in out
    # Refuses to overwrite without --force.
    assert new_variant.main(["--from", "holdem_nl", "--spec", str(spec), "--hands", "0"]) == 1


def test_new_variant_reports_invalid_and_unsupported(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"betting": {"structure": "FL"}}))
    assert new_variant.main(["--spec", str(bad), "--hands", "0"]) == 1
    assert "fixed-limit needs betting.fixed_bets" in capsys.readouterr().out
    prog = default_program()
    prog.insert(3, {"type": "swap", "n": 2})
    bad.write_text(json.dumps({"program": prog, "hole_cards": 2}))
    assert new_variant.main(["--spec", str(bad), "--hands", "0"]) == 1
    assert "NEEDS A NEW PLUGIN" in capsys.readouterr().out


def test_package_contains_only_what_the_variant_needs(tmp_path) -> None:
    spec_path = pkg.ROOT / "variant" / "catalog" / "mit2026_discard.json"
    out = tmp_path / "submission"
    info = pkg.build(spec_path, "tier2", "placeholder", out)
    files = {str(p.relative_to(out)) for p in out.rglob("*.py")}
    assert "bot.py" in files and "bot/main.py" in files and "bot/game/steps/cards.py" in files
    assert "bot/game/steps/side.py" not in files            # no auctions/markets here
    assert "bot/protocols/jsonl.py" not in files and "bot/game/steps/redraw.py" not in files
    assert not any(f.startswith(("lab/", "tests/")) for f in files)
    assert not (out / "bot" / "config").exists() and not (out / "data").exists()   # embedded instead
    assert pkg.check_imports(out) == []
    assert pkg.check_sandbox(out, "placeholder") == []
    assert info["protocol"] == "placeholder"
    # The packaged bot plays the variant embedded in its own bot/embedded.py.
    ns: dict = {}
    exec(compile((out / "bot" / "embedded.py").read_text(), "embedded", "exec"), ns)
    assert ns["SPEC"]["name"] == "mit2026_discard"
    bot = SubprocessPlayer([sys.executable, "bot.py"], cwd=str(out), protocol="placeholder")
    m = play_match([bot, PlayerSpec.brain("random_legal").build()], load_catalog()["mit2026_discard"],
                   seed=1, hands=15, audit=True)
    assert m.forfeit is None and m.errors[0] == 0


def test_package_never_touches_foreign_folders(tmp_path) -> None:
    out = tmp_path / "precious"
    out.mkdir()
    (out / "keep.txt").write_text("do not delete")
    with pytest.raises(SystemExit):
        pkg.build(pkg.ROOT / "variant" / "catalog" / "holdem_nl.json", "tier2", "placeholder", out)
    assert (out / "keep.txt").read_text() == "do not delete"


def test_package_with_other_protocol_and_side_plugins(tmp_path) -> None:
    out = tmp_path / "sub"
    pkg.build(pkg.ROOT / "variant" / "catalog" / "auction_card.json", "tier2", "json", out)
    assert (out / "bot" / "game" / "steps" / "side.py").is_file()
    assert (out / "bot" / "protocols" / "jsonl.py").is_file()
    assert 'DEFAULT = "json"' in (out / "bot" / "protocols" / "__init__.py").read_text()
    bot = SubprocessPlayer([sys.executable, "bot.py"], cwd=str(out), protocol="json")
    m = play_match([bot, PlayerSpec.brain("maniac").build()], load_catalog()["auction_card"],
                   seed=2, hands=10, audit=True)
    assert m.forfeit is None and m.errors[0] == 0


def test_zip_has_bot_py_at_the_top_is_small_and_reproducible(tmp_path) -> None:
    import zipfile
    spec = pkg.ROOT / "variant" / "active.json"
    hashes = []
    for name in ("a", "b"):                                  # two builds of the same sources
        out = tmp_path / name
        pkg.build(spec, "tier2", "pokerbots", out)
        (out / "bot" / "__pycache__").mkdir(exist_ok=True)   # never shipped
        (out / "bot" / "__pycache__" / "x.pyc").write_bytes(b"junk")
        hashes.append(pkg.make_zip(out, tmp_path / f"{name}.zip"))
    assert hashes[0] == hashes[1]
    z = tmp_path / "a.zip"
    assert z.stat().st_size <= pkg.ZIP_CAP_BYTES
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert names[0] == "bot.py" and "bot/main.py" in names and "bot/embedded.py" in names
    assert not any("__pycache__" in n or n == "PACKAGE.json" for n in names)


@pytest.mark.slow
def test_full_package_checks(tmp_path) -> None:
    rc = pkg.main(["--out", str(tmp_path / "s"), "--zip", "--opponents", "starter"])
    assert rc == 0


def test_cfr_is_lab_only_and_never_packaged(tmp_path) -> None:
    # CFR is a no-go for the submitted bot (docs/PART3_ROADMAP.md "CFR status"): its brain is
    # registered only in the lab, no bot/ module holds it, and the packager can't ship it.
    from bot.main import BRAINS as BOT_BRAINS
    from lab.players import BRAINS as LAB_BRAINS
    assert "cfr" not in BOT_BRAINS and LAB_BRAINS["cfr"].startswith("lab.")
    assert not [p for p in (pkg.ROOT / "bot").rglob("*.py") if "cfr" in p.name]
    with pytest.raises(SystemExit):
        pkg.main(["--brain", "cfr", "--out", str(tmp_path / "never")])
    from tools import embed_data
    assert set(embed_data.TABLE_FILES) == {"classes", "eq_random", "eq_range"}   # never a CFR strategy
