import json,collections,sys
sys.path.insert(0,'.')
from analyze import SITES,base,cls_entry,VOLATILE
c=collections.Counter()
for site,path in SITES:
    E=json.load(open(base+path+'/entries.json'))
    for keyname,kf in (('date+type',lambda x:(x.get('date'),x.get('type'))),('sysTime+type',lambda x:(x.get('sysTime'),x.get('type')))):
        g=collections.defaultdict(list)
        for x in E: g[kf(x)].append(x)
        for k,v in g.items():
            if len(v)<2: continue
            b={json.dumps({a:y for a,y in d.items() if a not in VOLATILE},sort_keys=True) for d in v}
            c[(keyname,cls_entry(v[0]),'identical' if len(b)==1 else 'distinct','groups')]+=1
            c[(keyname,cls_entry(v[0]),'identical' if len(b)==1 else 'distinct','docs')]+=len(v)
for k,v in sorted(c.items()): print(v,k)
