"""Offline mutations of actual native captures, never a live worker mutation."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,'<alignment>/externals/work/alignment-m7-evaluator-progress-20261112/tools/mt-bench/m7-joined')
import evaluator_progress as p
root=Path(__file__).parent;value=json.loads((root/'observation.private.json').read_text());proof=value['proof'];services=sorted(value['containers']);columns=p.COLUMNS

def verify(record):return p.verify(record,2,services,'idle')
assert verify(proof)==value['result'];controls=[]
for mode in ('frozen-success-counters','hidden-failure','foreign-work','runtime-reset','missing-foreign-row'):
    broken=copy.deepcopy(proof)
    if mode=='frozen-success-counters':
        baseline={(r[0],r[1]):r for r in broken['rounds'][0]['rows']}
        for snapshot in broken['rounds'][1:]:
            for row in snapshot['rows']:
                for key in ('completedAcquisitions','completedTimeCycles','legacyCycles'):
                    row[columns.index(key)]=baseline[(row[0],row[1])][columns.index(key)]
    elif mode=='hidden-failure':
        row=next(r for r in broken['rounds'][-1]['rows'] if r[columns.index('admitted')]);row[columns.index('failedCompletions')]+=1
    elif mode=='foreign-work':
        row=next(r for r in broken['rounds'][-1]['rows'] if not r[columns.index('admitted')]);row[columns.index('completedTimeCycles')]+=1
    elif mode=='runtime-reset':broken['rounds'][-1]['instances'][services[0]]['runtimeId']='99999999-9999-4999-8999-999999999999'
    else:
        rows=broken['rounds'][-1]['rows'];rows.remove(next(r for r in rows if not r[columns.index('admitted')]))
    try:verify(broken)
    except p.Refused as error:controls.append({'control':mode,'verdict':error.verdict,'code':str(error)})
    else:raise AssertionError('NATIVE_CAPTURE_FALSE_PASS '+mode)
    assert verify(proof)==value['result']
raw=(root/'observation.private.json').read_bytes();compressed=(root/'observation.private.json.gz').read_bytes()
assert gzip.decompress(compressed)==raw
result={'scope':'offline mutants of actual captured rows; no live stopped-worker or restart claim','restored':'PASS','controls':controls,'rawSha256':hashlib.sha256(raw).hexdigest(),'gzipSha256':hashlib.sha256(compressed).hexdigest()}
(root/'controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
