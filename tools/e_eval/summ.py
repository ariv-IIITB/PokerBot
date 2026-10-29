import re, sys, glob, os
d = sys.argv[1]
pat = re.compile(r"^tier2\[?.*?\]?-nolock vs (\S+): ([+-][\d.]+) ± ([\d.]+) chips/hand \| match score ([\d.]+)")
rows = {}
for f in sorted(glob.glob(os.path.join(d, "*.log"))):
    name = re.sub(r"_p\d$", "", os.path.basename(f)[:-4])
    for line in open(f, errors="replace").read().replace("\r", "\n").splitlines():
        m = pat.match(line)
        if m: rows.setdefault(name, {})[m[1].removesuffix("-nolock")] = (float(m[2]), float(m[3]), float(m[4]))
opps = []
for r in rows.values():
    for o in r:
        if o not in opps: opps.append(o)
print(f"{'':14}" + "".join(f"{o:>20}" for o in opps))
for n, r in rows.items():
    print(f"{n:14}" + "".join((f"{r[o][0]:+7.2f}±{r[o][1]:.2f} ({r[o][2]:.2f})".rjust(20) if o in r else " " * 20) for o in opps))
