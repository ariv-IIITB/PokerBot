import gzip,json,glob,os
for f in sorted(glob.glob("/tmp/claude-1000/-home-fioriv-synergy-PokerBot--claude-worktrees-pf-754d2e/965ad31a-7c41-47e0-8763-27877d145454/scratchpad/s0/logs/records/s0_9000/d_*.json.gz")):
    name=os.path.basename(f)[:-8]
    d=json.load(gzip.open(f)); N=0
    b={}
    for p in d["pairs"]:
        for m in p["matches"]:
            for h in m["hands"]:
                N+=1
                pre=[a for a in h["h"] if a[0]==0]
                rs=[a for a in pre if a[2]=="R"]
                if len(rs)<2 or h["h"][-1][0]==0: continue   # saw a flop in a 3bet+ pot
                k="we-3bet" if rs[1][1]=="m" else "they-3bet"
                v=b.setdefault(k,[0,0]); v[0]+=1; v[1]+=h["delta"]
    print(name, "  ".join(f"{k}: {v[0]/N:.3f}/h mean {v[1]/v[0]:+.1f} total {v[1]/N:+.3f}/h" for k,v in sorted(b.items())))
