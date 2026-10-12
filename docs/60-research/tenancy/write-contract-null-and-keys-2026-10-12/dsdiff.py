import json,collections,sys
sys.path.insert(0,'.')
from analyze import SITES,base,VOLATILE
sizes=collections.Counter(); diffk=collections.Counter(); sites_with=collections.Counter(); identical_sizes=collections.Counter()
mixed=0
for site,path in SITES:
    ds=json.load(open(base+path+'/devicestatus.json'))
    g=collections.defaultdict(list)
    for x in ds: g[(x.get('created_at'),x.get('device'))].append(x)
    for k,v in g.items():
        if len(v)<2: continue
        bodies={}
        for d in v: bodies.setdefault(json.dumps({a:b for a,b in d.items() if a not in VOLATILE},sort_keys=True),d)
        if len(bodies)==1: identical_sizes[min(len(v),10)]+=1; continue
        sites_with[site]+=1; sizes[(min(len(v),10),min(len(bodies),10))]+=1
        bl=list(bodies.values())
        paths=set()
        for d in bl[1:]:
            a=bl[0]
            for key in set(a)|set(d):
                if key in VOLATILE: continue
                if a.get(key)!=d.get(key):
                    if isinstance(a.get(key),dict) and isinstance(d.get(key),dict):
                        for k2 in set(a[key])|set(d[key]):
                            if a[key].get(k2)!=d[key].get(k2): paths.add(key+'.'+k2)
                    else: paths.add(key)
        for p in paths: diffk[p]+=1
print('sites with distinct-body groups:',len(sites_with),'of',len(SITES))
print('(group size, distinct bodies) top:',sizes.most_common(12))
print('identical-only group sizes:',sorted(identical_sizes.items()))
print('differing paths (groups):',diffk.most_common(25))
