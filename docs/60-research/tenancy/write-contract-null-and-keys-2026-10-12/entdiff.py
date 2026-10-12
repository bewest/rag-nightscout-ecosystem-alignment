import json,collections,sys,math
sys.path.insert(0,'.')
from analyze import SITES,base,cls_entry,iso_ms
c=collections.Counter(); sitec=collections.defaultdict(set)
for site,path in SITES:
    for x in json.load(open(base+path+'/entries.json')):
        d=x.get('date'); m=iso_ms(x.get('sysTime')) if x.get('sysTime') else None
        if m is None or not isinstance(d,(int,float)) or d==m: continue
        frac = d!=math.floor(d)
        trunc = (math.floor(d)//1000)*1000==m
        c[(cls_entry(x),'date has fractional ms' if frac else 'integer date', 'sysTime = date truncated to the second' if trunc else 'other')]+=1
        sitec[cls_entry(x)].add(site)
for k,v in sorted(c.items()): print(v,k)
print({k:len(v) for k,v in sitec.items()})
