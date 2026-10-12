import json,collections,sys
sys.path.insert(0,'.')
from analyze import SITES,base,VOLATILE
c=collections.Counter(); ltd=collections.Counter()
def flat(o,p=''):
    if isinstance(o,dict):
        r={}
        for k,v in o.items(): r.update(flat(v,p+'.'+k if p else k))
        return r
    if isinstance(o,list): return {p:json.dumps(o)}
    return {p:o}
for site,path in SITES:
    ds=json.load(open(base+path+'/devicestatus.json'))
    g=collections.defaultdict(list)
    for x in ds: g[(x.get('created_at'),x.get('device'))].append(x)
    for k,v in g.items():
        if len(v)<2: continue
        f=[flat({a:b for a,b in d.items() if a not in VOLATILE}) for d in v]
        if len({json.dumps(x,sort_keys=True) for x in f})==1: continue
        keys=set().union(*f); diff=frozenset(p for p in keys if len({json.dumps(x.get(p,'<absent>')) for x in f})>1)
        c[diff]+=1
        ltd['same loop.timestamp' if len({x.get('loop.timestamp') for x in f})==1 else 'different loop.timestamp']+=1
for k,v in c.most_common(12): print(v,sorted(k)[:8])
print(ltd)
