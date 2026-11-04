import gzip,json,glob,os
for f in sorted(glob.glob("/tmp/claude-1000/-home-fioriv-synergy-PokerBot--claude-worktrees-pf-754d2e/965ad31a-7c41-47e0-8763-27877d145454/scratchpad/s0/logs/records/s0_9000/*.json.gz")):
    name=os.path.basename(f)[:-8]
    if name in ("all_in","calling_station","starter","maniac","random_legal"): continue
    d=json.load(gzip.open(f)); N=0
    st={"open":[0,0,0],"3b":[0,0,0],"limp":[0,0],"bbdef":[0,0,0]}  # n, they folded, ...
    wefoldBB=[0,0]
    for p in d["pairs"]:
        for m in p["matches"]:
            for h in m["hands"]:
                N+=1
                pre=[a for a in h["h"] if a[0]==0]
                if len(pre)<2: continue
                a0,a1=pre[0],pre[1]
                if a0[1]=="m" and a0[2]=="R":
                    st["open"][0]+=1; st["open"][1]+= a1[2]=="F"; st["open"][2]+= a1[2]=="R"
                if a0[1]=="m" and a0[2]=="C":
                    st["limp"][0]+=1
                if a0[1]=="o" and a0[2]=="R":
                    st["bbdef"][0]+=1; st["bbdef"][1]+= a1[2]=="F"; st["bbdef"][2]+=a1[2]=="R"
    o=st["open"]; b=st["bbdef"]
    print(f"{name:16s} our SB opens {o[0]/N:.2f}/h: they fold {o[1]/o[0]:.2f} 3bet {o[2]/o[0]:.2f}; our SB limps {st['limp'][0]/N:.2f}/h; their SB opens {b[0]/N:.2f}/h: we fold {b[1]/b[0]:.2f} 3bet {b[2]/b[0]:.2f}")
