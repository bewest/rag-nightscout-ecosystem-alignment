import os
import pathlib,json
p=pathlib.Path(os.environ['CLINICAL_STATE'])
a=(p/'deploy-due-60000-candidate.trace').read_text().splitlines()
b=(p/'control-mutant.trace').read_text().splitlines()
c=(p/'control-restored.trace').read_text().splitlines()
parts=lambda s:s.split(' ',3)
r={'cycles':len(a),'mutantCycles':len(b),'differingHashes':sum(parts(x)[2]!=parts(y)[2] for x,y in zip(a,b)), 'sameInstantsKindsAlarms':len(a)==len(b) and all(parts(x)[:2]==parts(y)[:2] and parts(x)[3:]==parts(y)[3:] for x,y in zip(a,b)), 'restoredIdentical':a==c}
assert r['differingHashes']>0 and r['sameInstantsKindsAlarms'] and r['restoredIdentical'],r
print(json.dumps(r,indent=2))
