import json,sys,glob,collections
D=sys.argv[1]
chk=collections.defaultdict(lambda:[0,0,0]) # street,kind-> n,showdown, chips
fr=collections.Counter(); ours=collections.Counter(); oppf=collections.Counter()
for f in glob.glob(D+'/*.jsonl'):
    for line in open(f):
        m=json.loads(line)
        if m['type']!='hand_result': continue
        h=m['history']; net=m['net']
        # our decisions
        st=None; bet_open=None; facing=False; lastagg=None
        cnt=collections.defaultdict(int)
        for i,a in enumerate(h):
            s=a['street']
            if s!=st: st=s; lastagg=None
            if a['actor']=='me':
                if lastagg=='opp':
                    ours[(s,'facing_opp_bet',a['action'])]+=1
                    if a['action']=='raise':
                        # opp response
                        nxt=h[i+1] if i+1<len(h) else None
                        if nxt and nxt['street']==s and nxt['actor']=='opp': oppf[(s,'opp_vs_our_raise_over_bet',nxt['action'])]+=1
                        else: oppf[(s,'opp_vs_our_raise_over_bet','end')]+=1
                elif lastagg is None:
                    ours[(s,'unfaced',a['action'])]+=1
                    # was opp checked to us? or we first
                    first = not any(x['street']==s for x in h[:i])
                    key='we_first' if first else 'opp_checked'
                    ours[(s,key,a['action'])]+=1
                    if a['action']=='check':
                        c=chk[(s,key)]; c[0]+=1; c[2]+=net
                        c[1]+= (m['result']=='showdown')
            if a['action']=='raise': lastagg=a['actor']
for k in sorted(ours): print(k,ours[k])
print()
for k in sorted(chk): print(k,chk[k])
for k in sorted(oppf): print(k,oppf[k])
