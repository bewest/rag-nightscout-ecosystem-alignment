# classify.py BASELINE.json PREVIEW.json GROUPS.yaml OUT.json
# Classifies every cell that differs between the single-site baseline and the
# multitenant preview with tools/qc/compat/classify_compat.py (the mechanical
# effect letter), then decides whether the difference is explained by an entry
# in GROUPS.yaml `explanations:` (a regex on the cell key, optionally limited
# to the differing fields). A differing cell with no matching explanation is
# unexplained; the lab exits 1 while any exists. Prints a JSON summary.
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qc', 'compat'))
from classify_compat import rows, GROUPS  # noqa: E402
import yaml  # noqa: E402

baseline, preview, groups_file, out = sys.argv[1:5]
A, B = json.load(open(baseline)), json.load(open(preview))
G = yaml.safe_load(open(groups_file))
explanations = G.get('explanations') or []
classified = rows(A, B)
unexplained = []
for r in classified:
    if 'documents' in r['diff_fields']:
        r['group'] = 'h'
    r['explained'] = None
    for e in explanations:
        if not re.search(e['match'], r['cell']):
            continue
        fields = e.get('fields')
        if fields and not set(r['diff_fields']) <= set(fields):
            continue
        r['explained'] = {'verdict': e['verdict'], 'basis': e['basis'], 'match': e['match']}
        break
    r['group_verdict'] = (G.get('groups') or {}).get(r['group'], {}).get('verdict')
    if r['explained'] is None:
        unexplained.append(r['cell'])
missing_in_baseline = [k for k in B['cells'] if k not in A['cells']]
missing_in_preview = [k for k in A['cells'] if k not in B['cells']]
json.dump({'rows': classified, 'unexplained': unexplained, 'missing_in_preview': missing_in_preview,
           'missing_in_baseline': missing_in_baseline, 'cells_baseline': len(A['cells']), 'cells_preview': len(B['cells'])}, open(out, 'w'), indent=1)
print(json.dumps({'differing': len(classified), 'unexplained': len(unexplained), 'unexplained_cells': unexplained,
                  'missing_in_preview': missing_in_preview, 'missing_in_baseline': missing_in_baseline}))
