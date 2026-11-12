import json,sys,glob,collections
D=sys.argv[1]
R=collections.defaultdict(lambda:[0,0,0,0.0]) # n, opp folds, opp call, size
NET=collections.defaultdict(lambda:[0,0])
for f in glob.glob(D+'/*.jsonl'):
    for line in open(f):
        m=json.loads(line)
        if m['type']!='hand_result': continue
        h=m['history']; net=m['net']
        # pot tracking
        for i,a in enumerate(h):
            s=a['street']
            if s=='preflop' or a['actor']!='me' or a['action']!='raise': continue
            prev=[x for x in h[:i] if x['street']==s]
            if any(x['action']=='raise' for x in prev): continue   # open bet only
            ctx='opp_checked' if prev else 'we_first'
            nxt=h[i+1] if i+1<len(h) else None
            resp=nxt['action'] if nxt and nxt['street']==s and nxt['actor']=='opp' else 'end'
            r=R[(s,ctx)]; r[0]+=1; r[1]+= resp=='fold'; r[2]+= resp=='call'
            NET[(s,ctx,'bet')][0]+=1; NET[(s,ctx,'bet')][1]+=net
            NET[(s,ctx,'bet_'+('fold' if resp=='fold' else 'nofold'))][0]+=1
            NET[(s,ctx,'bet_'+('fold' if resp=='fold' else 'nofold'))][1]+=net
for k in sorted(R): print(k,R[k][:3],'foldrate %.2f'%(R[k][1]/R[k][0]))
for k in sorted(NET): print(k,NET[k][0],'avg %.2f'%(NET[k][1]/NET[k][0]))
