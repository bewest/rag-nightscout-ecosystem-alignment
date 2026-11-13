import os
import json,pathlib,re
state=pathlib.Path(os.environ['CLINICAL_STATE'])
results=[]
for plugins in ['deploy','full']:
 a=(state/f'within-{plugins}-base.log').read_text().splitlines()
 b=(state/f'within-{plugins}-candidate.log').read_text().splitlines()
 verdict=lambda ls:[s for s in ls if 'EQUIVALENT' in s]
 assert verdict(a)==verdict(b), (plugins,verdict(a),verdict(b))
 assert not any(x.startswith('FAIL') for x in verdict(a)), verdict(a)
 assert all(x.startswith('PASS') for x in verdict(a) if 'ALARM_SET' in x), verdict(a)
 if plugins=='deploy': assert all(x.startswith('PASS') for x in verdict(a)), verdict(a)
 ja=json.loads((state/f'within-{plugins}-base.json').read_text())
 jb=json.loads((state/f'within-{plugins}-candidate.json').read_text())
 for mode in ja:
  assert ja[mode]['transitions']==jb[mode]['transitions'],(plugins,mode)
 results.append({'plugins':plugins,'crossTreeVerdicts':'IDENTICAL','crossTreeTransitions':'IDENTICAL','verdicts':verdict(a)})
print(json.dumps(results,indent=2))
