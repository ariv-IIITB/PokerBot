"""DB, part 1 (lab only): what does an opponent's discard tell us?

D0 rule fit: for every recorded hand where the opponent discarded, compare the card they really
threw away with what each candidate keep rule would throw away, on their real deal (the recorder's
`opp_hole3` is there on every hand, so there is no showdown bias). D4: do they react to the rank of
the card WE discarded (their turn fold rate by low / mid / high, chi-square, Holm across bots)?

    .venv/bin/python -m lab.opps.discard_rules [--dir logs/records/s0_9000] [--train ...] [--md OUT.md]

A rule scores each of the 3 possible drops; the rule "accepts" the drops with the top score (ties
give a set). `hit` = the real drop is in that set; `set` = mean set size (hit is only meaningful
against it: `random` accepts everything). `opponent_keeps` is the baseline we play against today and
is deterministic (first best pair), exactly as in bot/sim/discard.py.
"""
from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

import numpy as np

from bot.evaluator import PAIR, category
from bot.sim.discard import RANK_WEIGHT
from lab.opps import record

ROOT = Path(__file__).resolve().parents[2]
RULES = ("opponent_keeps", "drop_lowest", "keep_pair", "keep_flush_draw", "keep_straight_draw", "random")

# ----------------------------------------------------------------------------- rules


def _rank(c: int) -> int:
    return c >> 2


def _flush_draw(kept: Sequence[int], flop: Sequence[int]) -> bool:
    """Both kept cards share a suit that also holds at least two flop cards (4+ to a flush)."""
    s = kept[0] & 3
    return kept[1] & 3 == s and sum(1 for c in flop if c & 3 == s) >= 2


def _straight_draw(kept: Sequence[int], flop: Sequence[int]) -> bool:
    """Both kept cards sit in a 5-rank window that holds at least four of the distinct ranks of
    kept + flop (open-ended, gutshot or made). The ace also counts low."""
    ranks = {_rank(c) for c in kept} | {_rank(c) for c in flop}
    low = {(-1 if r == 12 else r) for r in ranks}
    for rs, ks in ((ranks, {_rank(c) for c in kept}), (low, {(-1 if _rank(c) == 12 else _rank(c)) for c in kept})):
        for lo in range(-1, 9):
            win = set(range(lo, lo + 5))
            if len(rs & win) >= 4 and ks <= win:
                return True
    return False


def drop_scores(rule: str, ev, hole3: Sequence[int], flop: Sequence[int]) -> list:
    """One comparable score per drop index 0..2 (higher = the rule prefers that drop)."""
    out = []
    for i in range(3):
        kept = [c for k, c in enumerate(hole3) if k != i]
        low = -_rank(hole3[i])                       # dropping a lower card is better
        if rule == "opponent_keeps":
            v = int(ev.evaluate(kept, list(flop))) * RANK_WEIGHT + sum(_rank(c) for c in kept)
            out.append((v,))
        elif rule == "drop_lowest":
            out.append((low,))
        elif rule == "keep_pair":
            out.append((int(category(int(ev.evaluate(kept, list(flop)))) >= PAIR), low))
        elif rule == "keep_flush_draw":
            out.append((int(_flush_draw(kept, flop)), low))
        elif rule == "keep_straight_draw":
            out.append((int(_straight_draw(kept, flop)), low))
        elif rule == "random":
            out.append((0,))
        else:
            raise ValueError(rule)
    return out


def accepted_drops(rule: str, ev, hole3: Sequence[int], flop: Sequence[int]) -> list[int]:
    """Drop indices the rule accepts (all tied-best). `opponent_keeps` keeps the first best pair
    (pairs in combinations order), like bot/sim/discard.opponent_keeps, so it returns one index."""
    sc = drop_scores(rule, ev, hole3, flop)
    if rule == "opponent_keeps":
        # opponent_keeps loops pairs (0,1),(0,2),(1,2) and replaces only on a strictly better value
        best, pick = None, 0
        for pair in combinations(range(3), 2):
            drop = ({0, 1, 2} - set(pair)).pop()
            if best is None or sc[drop] > best:
                best, pick = sc[drop], drop
        return [pick]
    top = max(sc)
    return [i for i, s in enumerate(sc) if s == top]


# ----------------------------------------------------------------------------- D0


def discard_cases(d: dict) -> Iterable[tuple]:
    """(hole3, flop, dropped card, hand) for every hand where the opponent discarded one card."""
    for h in record.iter_hands(d):
        h3, dis = h.get("opp_hole3"), h.get("opp_dis") or []
        if h3 is None or len(h3) != 3 or len(dis) != 1 or dis[0] not in h3 or len(h["board"]) < 3:
            continue
        yield h3, h["board"][:3], dis[0], h


def fit_rules(d: dict, ev) -> dict:
    """Per-rule hit share, mean set size and the share of the real discards, plus the disagreement
    with the baseline. Also hits on the hands where the baseline disagrees."""
    n = 0
    hit = {r: 0 for r in RULES}
    size = {r: 0 for r in RULES}
    dis_n = 0
    dis_hit = {r: 0 for r in RULES}
    for h3, flop, dropped, _ in discard_cases(d):
        n += 1
        idx = h3.index(dropped)
        base = accepted_drops("opponent_keeps", ev, h3, flop)
        disagree = idx not in base
        dis_n += disagree
        for r in RULES:
            acc = accepted_drops(r, ev, h3, flop)
            size[r] += len(acc)
            if idx in acc:
                hit[r] += 1
                dis_hit[r] += disagree
    out = {"n": n, "disagree": dis_n / n if n else float("nan"), "n_disagree": dis_n}
    for r in RULES:
        out[r] = {"hit": hit[r] / n if n else float("nan"), "set": size[r] / n if n else float("nan"),
                  "hit_on_disagree": dis_hit[r] / dis_n if dis_n else float("nan")}
    return out


def go_decision(rows: dict, train: Sequence[str]) -> tuple[bool, list[str]]:
    """Go for part 2 only if some training bot disagrees with `opponent_keeps` on >= 15 % of its
    discards AND one non-baseline, non-random rule explains >= 80 % of its discards."""
    notes, go = [], False
    for b in train:
        r = rows.get(b)
        if not r or not r["n"]:
            continue
        best = max((x for x in RULES if x not in ("opponent_keeps", "random")), key=lambda x: r[x]["hit"])
        ok = r["disagree"] >= 0.15 and r[best]["hit"] >= 0.80
        go = go or ok
        notes.append(f"{b}: disagree {r['disagree']:.1%}, best other rule {best} {r[best]['hit']:.1%} -> "
                     + ("GO" if ok else "no"))
    return go, notes


# ----------------------------------------------------------------------------- D4


def card_class(c: int) -> str:
    """Our discarded card by rank: low 2-5, mid 6-T, high J-A."""
    r = _rank(c)
    return "low" if r <= 3 else ("mid" if r <= 8 else "high")


def turn_fold_counts(d: dict) -> dict:
    """{class: [folds, decisions]} for the opponent's decisions facing our bet on the turn
    (street 2), by the class of the card we discarded. Hands where we did not discard are skipped."""
    out = {"low": [0, 0], "mid": [0, 0], "high": [0, 0]}
    for h in record.iter_hands(d):
        mine = [cards for who, cards in h["rv"] if who == "m"]
        if len(mine) != 1 or len(mine[0]) != 1:
            continue
        cls = card_class(mine[0][0])
        last = None
        for street, who, kind, _, _ in h["h"]:
            if street == 2 and who == "o" and last == ("m", "R"):
                out[cls][1] += 1
                out[cls][0] += kind == "F"
            if street == 2:
                last = (who, kind)
    return out


def chi2_p(counts: dict) -> Optional[float]:
    from scipy.stats import chi2_contingency
    rows = [[f, n - f] for f, n in counts.values() if n > 0]
    if len(rows) < 2 or any(sum(r) == 0 for r in rows):
        return None
    tab = np.array(rows)
    if (tab.sum(axis=0) == 0).any():                 # nobody folded (or everybody did): no test
        return None
    return float(chi2_contingency(tab)[1])


def holm(ps: dict, alpha: float = 0.01) -> dict:
    """Holm-Bonferroni across bots: {bot: (p, adjusted p, reject)}; p None -> not testable."""
    items = sorted(((p, b) for b, p in ps.items() if p is not None))
    m, out, run = len(items), {}, 0.0
    for i, (p, b) in enumerate(items):
        run = max(run, min(1.0, p * (m - i)))
        out[b] = (p, run, run < alpha)
    for b, p in ps.items():
        out.setdefault(b, (None, None, False))
    return out


# ----------------------------------------------------------------------------- report


def load_dir(path: Path) -> dict[str, dict]:
    return {p.name.split(".")[0]: record.load(p) for p in sorted(path.glob("*.json.gz"))}


def evaluator():
    from bot.game.rules_spec import to_rules
    from variant.spec import load_catalog
    return to_rules(load_catalog()["discard_holdem"]).evaluator


def build_report(recs: dict[str, dict], train: Sequence[str]) -> tuple[str, bool]:
    ev = evaluator()
    rows = {b: fit_rules(d, ev) for b, d in recs.items()}
    go, notes = go_decision(rows, train)
    lines = ["| bot | discards | disagree w/ opponent_keeps | " + " | ".join(f"{r} hit (set)" for r in RULES) + " |",
             "|---|---:|---:|" + "---:|" * len(RULES)]
    for b in recs:
        r = rows[b]
        cells = " | ".join(f"{r[x]['hit']:.1%} ({r[x]['set']:.2f})" for x in RULES)
        tag = " *(train)*" if b in train else ""
        lines.append(f"| {b}{tag} | {r['n']} | {r['disagree']:.1%} | {cells} |")
    d0 = "\n".join(lines) + "\n\nGo/no-go (training bots): " + ("**GO**" if go else "**NO-GO**") + "\n\n" \
        + "\n".join(f"- {n}" for n in notes)
    counts = {b: turn_fold_counts(d) for b, d in recs.items()}
    ps = {b: chi2_p(c) for b, c in counts.items()}
    tr = {b: p for b, p in ps.items() if b in train}
    h_train, h_all = holm(tr), holm(ps)
    lines = ["| bot | fold% low (n) | fold% mid (n) | fold% high (n) | chi2 p | Holm-adj (train) | Holm-adj (all) |",
             "|---|---|---|---|---:|---:|---:|"]
    for b in recs:
        c = counts[b]
        cells = " | ".join(f"{(c[k][0] / c[k][1] if c[k][1] else float('nan')):.1%} ({c[k][1]})" for k in ("low", "mid", "high"))

        def fmt(t):
            return "-" if t[1] is None else f"{t[1]:.3g}{'*' if t[2] else ''}"
        p = ps[b]
        lines.append(f"| {b} | {cells} | {'-' if p is None else format(p, '.3g')} | "
                     f"{fmt(h_train[b]) if b in train else '-'} | {fmt(h_all[b])} |")
    reacting = sorted(b for b, t in h_all.items() if t[2])
    d4 = "\n".join(lines) + "\n\nBots that react to our discard (Holm-adjusted p < 0.01, all bots): " \
        + (", ".join(reacting) if reacting else "none") + \
        "\nTraining bots only: " + (", ".join(sorted(b for b, t in h_train.items() if t[2])) or "none")
    return d0 + "\n\n### D4\n\n" + d4, go


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=str(ROOT / "logs/records/s0_9000"))
    ap.add_argument("--train", default="d_conv_opp3,d_new_rules,d_new_lag,d_new_trapper,d_new_exploiter,d_new_minraise")
    ap.add_argument("--md", help="write the tables to this file")
    a = ap.parse_args(argv)
    text, go = build_report(load_dir(Path(a.dir)), a.train.split(","))
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n")
    return 0 if go else 1


if __name__ == "__main__":
    sys.exit(main())
