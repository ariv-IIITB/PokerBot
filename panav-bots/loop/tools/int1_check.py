"""INT1 safety harness: per-reply timing, illegal/forfeit counts, peak RSS for one bot FILE vs an opponent FILE or lab opponent.
  PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/int1_check.py BOT.py OPP --hands 200 --total 400 --bank 60 --seeds 2 [--fuzz]
OPP is a .py path (real protocol) or 'weird:<style>' (engine-side misbehaving opponent from lab.fuzz)."""
import argparse, json, resource, sys, time
from pathlib import Path
import lab.engine as LE
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import SubprocessPlayer
import lab.players as LP


class Timed(SubprocessPlayer):
    def __init__(self, *a, **k):
        self.times = []; super().__init__(*a, **k)
    def act(self, req, timeout=None):
        t0 = time.perf_counter()
        try:
            return super().act(req, timeout)
        finally:
            self.times.append(time.perf_counter() - t0)


def mk(path, cls=SubprocessPlayer):
    p = Path(path).resolve()
    return cls([sys.executable, str(p)], cwd=str(p.parent), name=p.stem, protocol="pokerbots")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot"); ap.add_argument("opp")
    ap.add_argument("--hands", type=int, default=200); ap.add_argument("--total", type=int, default=None)
    ap.add_argument("--bank", type=float, default=None); ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--first-seed", type=int, default=0)
    a = ap.parse_args()
    _MI = LE.MatchInfo
    LE.MatchInfo = lambda hands, *r: _MI(a.total or hands, *r)      # init says total_hands = --total, only --hands are played
    cfg = load_variant("discard_holdem")
    total = a.total or a.hands
    bank = a.bank if a.bank is not None else 0.15 * total
    allt, ill, ff, chips, hands, banks, score = [], 0, 0, 0, 0, [], 0.0
    for s in range(a.first_seed, a.first_seed + a.seeds):
        for seat in (0, 1):
            me = mk(a.bot, Timed)
            if a.opp.startswith("weird:"):
                from lab.fuzz import WeirdPlayer
                op = WeirdPlayer(a.opp[6:], s)
            else:
                op = mk(a.opp)
            ps = [me, op] if seat == 0 else [op, me]
            m = play_match(ps, cfg, s, a.hands, "fold", time_bank_s=bank, reply_limit_s=5.0)
            me.close()
            if hasattr(op, "close"): op.close()
            allt += me.times
            ill += m.errors[seat]
            ff += int(m.forfeit == seat)
            chips += m.chips[seat]; hands += m.hands_played; score += m.score(seat)
            banks.append(bank - m.bank_left[seat])
    ru = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    ts = sorted(allt); n = len(ts)
    out = dict(bot=Path(a.bot).stem, opp=a.opp, legs=a.seeds * 2, hands=hands, total_hands=total, bank=bank, decisions=n,
               mean_ms=1000 * sum(ts) / n, p99_ms=1000 * ts[int(.99 * (n - 1))], max_ms=1000 * ts[-1],
               bank_used_max_s=max(banks), bank_used_mean_s=sum(banks) / len(banks), illegal=ill, forfeits=ff,
               chips=chips, score_sum=score, rss_children_mb=ru)
    print(json.dumps(out))

main()
