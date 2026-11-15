"""Progress driver: usage prog.py STAGE BOT OPP FIRST N HANDS PROCS OUT.json [PROGRESS_FILE]. Prints+appends a line after every 5 pairs."""
import json, math, multiprocessing as mp, sys
sys.path.insert(0, "panav-bots/loop/tools")
from pathlib import Path
from file_duel import pair
def main():
    st, bot, opp, first, n, hands, procs, out = sys.argv[1:9]
    pf = sys.argv[9] if len(sys.argv) > 9 else None
    first, n, hands, procs = int(first), int(n), int(hands), int(procs)
    tasks = [(bot, opp, s, hands, None, 0.15 * hands) for s in range(first, first + n)]
    rs = []
    with mp.get_context("spawn").Pool(procs) as pool:
        for r in pool.imap(pair, tasks, chunksize=1):
            rs.append(r)
            if len(rs) % 5 == 0 or len(rs) == n:
                w = sum(1.0 if x["chips"] > 0 else .5 if x["chips"] == 0 else 0.0 for x in rs); k = len(rs)
                c = [x["chips"] / max(1, x["hands"]) for x in rs]; m = sum(c) / k
                se = math.sqrt(sum((v - m) ** 2 for v in c) / (k - 1) / k) if k > 1 else float("nan")
                ff = sum(x["ff_a"] for x in rs)
                line = f"{st} {k}/{n} MATCH WINS {w:g}/{k} ({100*w/k:.0f}%) chips/hand {m:+.2f}±{se:.2f} ff {ff}"
                print(line, flush=True)
                if pf: open(pf, "a").write(line + "\n")
                Path(out).write_text(json.dumps(dict(a=bot, b=opp, hands=hands, pairs=rs)))
if __name__ == "__main__":
    main()
