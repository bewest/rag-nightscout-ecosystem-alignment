import subprocess,sys,re,json
R='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official'
def g(*a): return subprocess.run(['git','-C',R]+list(a),capture_output=True,text=True).stdout
base,seam=sys.argv[1],sys.argv[2]
out=g('merge-tree','--write-tree','--name-only',base,seam)
paths=[l for l in out.split('\n\n')[0].splitlines()[1:] if l]
msgs=out.split('\n\n',1)[1] if '\n\n' in out else ''
mb=g('merge-base',base,seam).strip()
RULES=["srv-dates')","soft-deleted')","object-id-forms')","treatment-fallback-key')"]
BF04={'lib/server/query-operator-allowlist.js','lib/api/shared/query-error.js','tests/api-v1-operator-allowlist.test.js'}
rows=[]
for p in paths:
    kinds=sorted(set(re.findall(r'CONFLICT \(([^)]+)\)[^\n]*?'+re.escape(p)+r'\b',msgs)))
    up=g('show',f'{base}:{p}'); se=g('show',f'{seam}:{p}')
    rules=[r[:-2] for r in RULES if r in up]
    seam_n=len(g('log','--format=%h',f'{mb}..{seam}','--',p).split())
    up_n=len(g('log','--format=%h',f'{mb}..{base}','--',p).split())
    if p in BF04: cat='add/add supersession (BF-04 upstream wins)'
    elif p in ('package.json','package-lock.json','azuredeploy.json'): cat='manifest'
    elif p.startswith('tests/'): cat='test'
    elif p.endswith('.md'): cat='docs'
    elif rules: cat='§4.1 write rule'
    else: cat='other lib'
    rows.append(dict(path=p,kind=','.join(kinds),cat=cat,rules=','.join(rules),seam_commits=seam_n,upstream_commits=up_n))
print(json.dumps(rows))
