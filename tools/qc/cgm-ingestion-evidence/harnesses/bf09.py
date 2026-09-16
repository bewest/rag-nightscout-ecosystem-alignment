import json,glob,os,collections
FIELDS=['insulin','carbs','percent','absolute','duration']
tot=collections.Counter(); zero=collections.Counter(); pres=collections.Counter()
docs=0; sites=0
falsy_only=0   # docs where every present amount field is falsy -> selected stays False
for p in sorted(glob.glob('externals/ns-data/patients/*/raw/treatments.json')):
    try: d=json.load(open(p))
    except Exception: continue
    if not isinstance(d,list): continue
    sites+=1
    for doc in d:
        if not isinstance(doc,dict): continue
        docs+=1
        any_present=False; any_truthy=False
        for f in FIELDS:
            if f in doc and doc[f] is not None:
                pres[f]+=1; any_present=True
                v=doc[f]
                if v==0 or v=='0' or v=='': zero[f]+=1
                else: any_truthy=True
        if doc.get('NSCLIENT_ID'): any_truthy=True
        if any_present and not any_truthy: falsy_only+=1
print("sites",sites,"treatment docs",docs)
for f in FIELDS:
    print(f"  {f:9s} present {pres[f]:8d}  zero/empty {zero[f]:8d}  ({100.0*zero[f]/pres[f] if pres[f] else 0:.1f}% of present)")
print("docs where every present amount field is falsy (dedup falls back to eventType only):",falsy_only)
