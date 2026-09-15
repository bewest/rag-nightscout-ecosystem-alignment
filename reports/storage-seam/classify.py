import json, csv, sys, re
rows=[r for r in json.load(open('/tmp/inventory.json'))
      if not r['file'].endswith('pluginbase.js')]   # jQuery DOM, verified

def tier(r):
    f=r['file']
    if '/api3/generic/' in f: return 'T0-consumer'
    if 'mongoCachedCollection' in f: return 'T0-consumer'
    if 'mongoCollection/index.js' in f: return 'T1-interface'
    if 'mongoCollection/find.js' in f or 'mongoCollection/modify.js' in f: return 'T1-adapter'
    if f=='lib/storage/mongo-storage.js': return 'T3-factory'
    if f=='lib/server/websocket.js': return 'T3-socket-write-path'
    return 'T2-v1-domain'

def classify(r):
    s, op, f, ln = r['src'], r['op'], r['file'], r['line']
    # --- must-change: driver semantics that cannot cross a backend boundary
    if 'ObjectId(' in s or 'ObjectID(' in s:
        return 'must-change','ObjectId construction — identifier must be opaque to the caller'
    if '$set' in s or '$unset' in s:
        return 'must-change','Mongo update operators — needs an explicit patch contract (jsonb_set / - key)'
    if 'ctx.store.collection(' in s:
        return 'must-change','raw collection handle — the §2.5 leak itself'
    if 'self.col = ' in s or re.search(r'self\.col\.find', s):
        return 'must-change','exposes the driver cursor; getLastModified must go through the adapter'
    if op=='find' and ('$and' in s or '$in' in s):
        return 'must-change','literal Mongo filter document in domain code'
    if op=='find' and 'query_for(opts)' in s:
        return 'must-change','filter is a Mongo query document built by query.js — must become a neutral filter'
    if op in ('deleteMany',) and 'query_for(opts)' in s:
        return 'must-change','delete by Mongo query document — same filter problem'
    # --- escape hatch: real capability the interface must name explicitly
    if op=='bulkWrite':   return 'needs-escape-hatch','batch upsert — Postgres INSERT ... ON CONFLICT'
    if op=='aggregate':   return 'needs-escape-hatch','aggregation pipeline — needs a declared contract, not pass-through'
    if op=='insertMany':  return 'needs-escape-hatch','batch insert'
    if op=='deleteMany':  return 'needs-escape-hatch','delete by filter (non-query_for callers)'
    if op=='createIndex': return 'needs-escape-hatch','schema management — becomes migrations on Postgres'
    if 'upsert: true' in s or 'upsert:true' in s:
        return 'needs-escape-hatch','upsert semantics must be explicit in the interface'
    if op=='find' and 'projection' in s:
        return 'needs-escape-hatch','projection — findMany already takes one, caller must stop chaining'
    if op=='find' and ('.sort(' in s or '.limit(' in s):
        return 'needs-escape-hatch','cursor chaining — must become findMany args'
    if op=='find':        return 'needs-escape-hatch','bare find — map to findMany'
    # --- fits
    return 'fits','maps onto the existing api3 storage interface'

out=[]
for r in rows:
    c,why=classify(r)
    out.append({**r,'tier':tier(r),'class':c,'reason':why})

w=csv.DictWriter(open('/tmp/t1-1-classification.tsv','w'),
    fieldnames=['tier','class','file','line','op','reason','src'],delimiter='\t')
w.writeheader()
for r in sorted(out,key=lambda x:(x['tier'],x['file'],x['line'])):
    w.writerow({k:r[k] for k in ['tier','class','file','line','op','reason','src']})

from collections import Counter
print(f"TOTAL CLASSIFIED: {len(out)}\n")
print("by class:");  [print(f"  {k:22s} {v}") for k,v in Counter(r['class'] for r in out).most_common()]
print("\nby tier:");  [print(f"  {k:22s} {v}") for k,v in Counter(r['tier'] for r in out).most_common()]
print("\ntier x class:")
for t,c in sorted(Counter((r['tier'],r['class']) for r in out).items()):
    print(f"  {t[0]:22s} {t[1]:22s} {c}")
