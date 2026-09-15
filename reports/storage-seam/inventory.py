# T1.1 — enumerate every storage call site in cgm-remote-monitor.
#
# Counting this correctly is harder than it looks and two earlier counts were wrong:
#   - excluding `.find(` entirely (to dodge Array.find) drops real collection reads -> 68
#   - excluding `.find(<identifier>)` drops `col.find(filter)` too -> 82
# The exclusions below keep `.find(filter)` and drop only jQuery selectors and
# Array.find callbacks; lib/plugins/pluginbase.js:45 survives as a known DOM
# false positive and is removed in classify.py.
#
# Usage: python3 inventory.py <path-to-cgm-remote-monitor>  > inventory.json
import re, os, json, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
UNAMBIG = r'\.(findOne|insertOne|insertMany|updateOne|updateMany|deleteOne|deleteMany|countDocuments|aggregate|replaceOne|findOneAndUpdate|createIndex|bulkWrite|estimatedDocumentCount|distinct)\s*\('
DOMISH = re.compile(r"\.find\(\s*['\"]|\.find\(\s*function|\.find\(\s*\(|\.find\(\s*[A-Za-z_$][\w$]*\s*=>")
rows = []
for dp, _, fns in os.walk(os.path.join(ROOT, 'lib')):
    rel = os.path.relpath(dp, ROOT)
    if rel.startswith('lib/client'): continue
    for fn in fns:
        if not fn.endswith('.js'): continue
        p = os.path.join(rel, fn)
        for i, line in enumerate(open(os.path.join(dp, fn), encoding='utf8', errors='replace').read().split('\n'), 1):
            t = line.strip()
            if t.startswith('//') or t.startswith('*'): continue
            m = re.search(UNAMBIG, line)
            if m: rows.append({'file': p, 'line': i, 'op': m.group(1), 'src': t[:120]})
            elif re.search(r'\.find\s*\(', line) and not DOMISH.search(line):
                rows.append({'file': p, 'line': i, 'op': 'find', 'src': t[:120]})
print(json.dumps(rows, indent=1))
