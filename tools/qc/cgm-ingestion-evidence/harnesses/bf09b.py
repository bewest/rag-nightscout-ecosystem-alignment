import json,glob,datetime,collections
def key_shipped(d):
    k={}
    sel=False
    for f in ['insulin','carbs','percent','absolute','duration']:
        v=d.get(f)
        if v: k[f]=v; sel=True          # truthiness, as shipped
    if d.get('NSCLIENT_ID'): k['NSCLIENT_ID']=d['NSCLIENT_ID']; sel=True
    if not sel: k['eventType']=d.get('eventType')
    return tuple(sorted(k.items()))
def key_presence(d):
    k={}
    sel=False
    for f in ['insulin','carbs','percent','absolute','duration']:
        if f in d and d[f] is not None: k[f]=d[f]; sel=True   # presence
    if d.get('NSCLIENT_ID'): k['NSCLIENT_ID']=d['NSCLIENT_ID']; sel=True
    if not sel: k['eventType']=d.get('eventType')
    return tuple(sorted(k.items()))
def ts(d):
    s=d.get('created_at')
    if not isinstance(s,str): return None
    try: return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
    except Exception: return None
collide=0; would_not=0; examined=0; sites=0
for p in sorted(glob.glob('externals/ns-data/patients/*/raw/treatments.json')):
    try: d=json.load(open(p))
    except Exception: continue
    if not isinstance(d,list): continue
    sites+=1
    rows=[]
    for doc in d:
        if not isinstance(doc,dict): continue
        t=ts(doc)
        if t is None: continue
        rows.append((t,doc))
    rows.sort(key=lambda r:r[0])
    n=len(rows)
    for i,(t,doc) in enumerate(rows):
        # only docs that carry a falsy-but-present amount field are at risk
        risk=any((f in doc and doc[f] is not None and not doc[f]) for f in ['insulin','carbs','percent','absolute','duration'])
        if not risk: continue
        examined+=1
        ks=key_shipped(doc); kp=key_presence(doc)
        j=i-1; hit_s=False; hit_p=False
        while j>=0 and t-rows[j][0]<=2.0:
            o=rows[j][1]
            if o is not doc:
                if key_shipped(o)==ks: hit_s=True
                if key_presence(o)==kp: hit_p=True
            j-=1
        j=i+1
        while j<n and rows[j][0]-t<=2.0:
            o=rows[j][1]
            if o is not doc:
                if key_shipped(o)==ks: hit_s=True
                if key_presence(o)==kp: hit_p=True
            j+=1
        if hit_s and not hit_p: collide+=1
        if hit_p and not hit_s: would_not+=1
print("sites",sites)
print("at-risk docs (carry a present-but-falsy amount field):",examined)
print("  shipped key finds a 'similar' doc that presence key would NOT  ->",collide)
print("  presence key finds one that shipped key would not              ->",would_not)
