import gzip,json,glob,os,math
rows=[]
for f in sorted(glob.glob("/tmp/claude-1000/-home-fioriv-synergy-PokerBot--claude-worktrees-pf-754d2e/965ad31a-7c41-47e0-8763-27877d145454/scratchpad/s0/logs/records/s0_9000/*.json.gz")):
    d=json.load(gzip.open(f)); name=os.path.basename(f)[:-8]
    N=0; tot=0; ended={"we_fold":[0,0],"they_fold":[0,0]}; pre_raise_pots=[0,0]; cats={}
    per=[]
    for p in d["pairs"]:
        s=0;n=0
        for m in p["matches"]:
            for h in m["hands"]:
                n+=1; s+=h["delta"]
                pre=[a for a in h["h"] if a[0]==0]
                last=h["h"][-1]
                if last[0]==0 and last[2]=="F":
                    k="we_fold" if last[1]=="m" else "they_fold"
                    ended[k][0]+=1; ended[k][1]+=h["delta"]
                else:
                    nr=sum(1 for a in pre if a[2]=="R")
                    c="pre_r%d"%min(nr,3)
                    cats.setdefault(c,[0,0]); cats[c][0]+=1; cats[c][1]+=h["delta"]
        per.append(s/n if n else 0); N+=n; tot+=s
    # preflop-ended chips/hand
    pre_end=sum(v[1] for v in ended.values())/N
    print(f"{name:18s} cph={tot/N:6.2f} preflop-ended: wefold {ended['we_fold'][0]/N:.3f}/h {ended['we_fold'][1]/N:+.3f}  theyfold {ended['they_fold'][0]/N:.3f}/h {ended['they_fold'][1]/N:+.3f}  | "+"  ".join(f"{k}:{v[0]/N:.2f}/{v[1]/max(v[0],1):+.1f}" for k,v in sorted(cats.items())))
