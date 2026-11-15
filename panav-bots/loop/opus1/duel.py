"""OPUS1 copy of tools/file_duel.py plus --errdir (stderr of bot A per leg kept). Duplicate match between two bot FILES (real 'pokerbots' protocol) on discard_holdem.

  PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py A.py B.py --seeds 8 --hands 200 [--first-seed N] [--processes 3]
        [--logdir DIR] [--out summary.json]
A = the bot under test (its protocol messages are logged to DIR/seed<S>_m<1|2>.jsonl when --logdir is given).
Prints chips/hand for A (SE over duplicate pairs) and the match score. Every deal is played twice, seats swapped.
Only use the bot's own cwd (spar bots import common.py from their folder).
"""
from __future__ import annotations
import argparse, json, math, multiprocessing as mp, os, sys
from pathlib import Path
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import SubprocessPlayer


class LoggedPlayer(SubprocessPlayer):
    def __init__(self, *a, log=None, **k):
        self._log = open(log, "w") if log else None
        super().__init__(*a, **k)

    def _send(self, line):
        if self._log:
            self._log.write(line if line.endswith("\n") else line + "\n")
        return super()._send(line)

    def close(self):
        super().close()
        if self._log:
            self._log.close()


def make(path, log=None, err=None):
    p = Path(path).resolve()
    return LoggedPlayer([sys.executable, str(p)], cwd=str(p.parent), name=p.stem,
                        protocol="pokerbots", log=log, stderr_to=err)


def pair(args):
    a, b, seed, hands, logdir, bank, errdir = args
    cfg = load_variant("discard_holdem")
    la = (Path(logdir) / f"seed{seed}_m1.jsonl") if logdir else None
    lb = (Path(logdir) / f"seed{seed}_m2.jsonl") if logdir else None
    e1 = (Path(errdir) / f"seed{seed}_m1.err") if errdir else None
    e2 = (Path(errdir) / f"seed{seed}_m2.err") if errdir else None
    m1 = play_match([make(a, la, e1), make(b)], cfg, seed, hands, "fold", time_bank_s=bank)
    m2 = play_match([make(b), make(a, lb, e2)], cfg, seed, hands, "fold", time_bank_s=bank)
    ffa = int(m1.forfeit == 0) + int(m2.forfeit == 1)
    ffb = int(m1.forfeit == 1) + int(m2.forfeit == 0)
    W = 100
    d1 = m1.hand_deltas; d2 = [-x for x in m2.hand_deltas]      # A's chips per hand in each leg
    win = [sum(d1[i:i + W]) + sum(d2[i:i + W]) for i in range(0, max(len(d1), len(d2)), W)]
    return dict(seed=seed, win=win, chips=m1.chips[0] + m2.chips[1], hands=m1.hands_played + m2.hands_played,
                score=(m1.score(0) + m2.score(1)) / 2, ff_a=ffa, ff_b=ffb,
                reasons=[r for r in (m1.forfeit_reason, m2.forfeit_reason) if r])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--processes", type=int, default=3)
    ap.add_argument("--bank", type=float, default=None)
    ap.add_argument("--logdir")
    ap.add_argument("--out")
    ap.add_argument("--errdir")
    a = ap.parse_args()
    if a.logdir:
        Path(a.logdir).mkdir(parents=True, exist_ok=True)
    if a.errdir:
        Path(a.errdir).mkdir(parents=True, exist_ok=True)
    if a.bank is None:
        a.bank = 0.15 * a.hands        # real bank: 30 s per 200-hand leg, 75 s per 500-hand leg (the lab default is 60 s)
    tasks = [(a.a, a.b, s, a.hands, a.logdir, a.bank, a.errdir) for s in range(a.first_seed, a.first_seed + a.seeds)]
    with mp.get_context("spawn").Pool(min(a.processes, len(tasks))) as pool:
        rs = pool.map(pair, tasks, chunksize=1)
    per = [r["chips"] / max(1, r["hands"]) for r in rs]
    n = len(per); m = sum(per) / n
    se = math.sqrt(sum((x - m) ** 2 for x in per) / (n - 1) / n) if n > 1 else float("nan")
    sc = sum(r["score"] for r in rs) / n
    print(f"{Path(a.a).stem} vs {Path(a.b).parent.name if Path(a.b).name=='bot.py' else Path(a.b).stem}: "
          f"{m:+.2f} ± {se:.2f} chips/hand | match score {sc:.3f} | pairs {n} | "
          f"forfeits A/B {sum(r['ff_a'] for r in rs)}/{sum(r['ff_b'] for r in rs)}", flush=True)
    nwin = max(len(r["win"]) for r in rs)
    cols = [sum(r["win"][i] for r in rs if len(r["win"]) > i) / (2 * 100 * n) for i in range(nwin)]
    print("  chips/hand by 100-hand window (A, avg of 2 legs): " + " ".join(f"{c:+.2f}" for c in cols), flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(dict(a=a.a, b=a.b, hands=a.hands, mean=m, se=se, score=sc, pairs=rs)))


if __name__ == "__main__":
    main()
