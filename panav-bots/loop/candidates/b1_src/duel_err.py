import sys, multiprocessing as mp
sys.path.insert(0, "/home/user/pokerbot/panav-bots/loop/tools"); sys.path.insert(0, "/home/user/pokerbot")
from pathlib import Path
import file_duel as fd
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import SubprocessPlayer
def mk(path, err=None):
    p = Path(path).resolve()
    return SubprocessPlayer([sys.executable, str(p)], cwd=str(p.parent), name=p.stem, protocol="pokerbots", stderr_to=err)
def run(t):
    a, b, seed, hands, d = t
    cfg = load_variant("discard_holdem")
    m1 = play_match([mk(a, f"{d}/s{seed}_1.err"), mk(b)], cfg, seed, hands, "fold")
    m2 = play_match([mk(b), mk(a, f"{d}/s{seed}_2.err")], cfg, seed, hands, "fold")
    return (m1.chips[0] + m2.chips[1]) / (m1.hands_played + m2.hands_played)
if __name__ == "__main__":
    a, b, n, d = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    Path(d).mkdir(parents=True, exist_ok=True)
    with mp.get_context("spawn").Pool(3) as p:
        r = p.map(run, [(a, b, s, 200, d) for s in range(500, 500 + n)], chunksize=1)
    print(b, sum(r) / len(r))
