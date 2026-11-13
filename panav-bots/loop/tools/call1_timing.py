"""call1: mean reply time per decision from the bot's own stderr summary lines ("time per decision: preflop 0.1 ms (max 0.6) x 217; ...").
  call1_timing.py ERRDIR [ERRDIR ...]  -> mean ms over all decisions (hand_end excluded), worst max, error counts, forfeits-by-fallback."""
import re, sys
from pathlib import Path

tot = n = 0.0; worst = 0.0; errs = fb = 0
for d in sys.argv[1:]:
    for f in Path(d).glob("*.err"):
        for line in f.read_text(errors="replace").splitlines():
            if line.startswith("fallbacks:"):
                m = re.match(r"fallbacks: (\d+) fallback replies, (\d+) errors", line)
                if m:
                    fb += int(m.group(1)); errs += int(m.group(2))
            if "time per decision:" in line:
                for st, ms, mx, k in re.findall(r"(preflop|flop|turn|river|discard) ([\d.]+) ms \(max ([\d.]+)\) x (\d+)", line.split("time per decision:")[1]):
                    tot += float(ms) * int(k); n += int(k); worst = max(worst, float(mx))
print(f"decisions {int(n)} mean {tot / max(n, 1):.2f} ms worst {worst:.1f} ms; fallback replies {fb}, errors {errs}")
