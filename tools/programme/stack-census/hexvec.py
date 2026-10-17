"""List the hex test vectors in a source tree, for the census's shared-vector counts (device annex §0).

A vector is a quoted string literal of 8 or more hex byte pairs (spaces between pairs allowed),
lower-cased with the spaces removed. Two implementations share a vector when both lists hold it:

    python3 -I hexvec.py <tree-a> tests .swift,.kt,.java > a.txt
    python3 -I hexvec.py <tree-b> tests .swift,.kt,.java > b.txt
    comm -12 <(sort -u a.txt) <(sort -u b.txt) | wc -l

Mode `tests` keeps only paths containing "test" or "Test"; `all` keeps every file. Further
arguments are substrings of directory paths to skip (for example `vendor`). Unquoted hex is not
counted: counting it gives OmniBLE∩OmnipodKit 193 instead of the census's 191.
"""
import os
import re
import sys

root, mode, exts = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
excludes = sys.argv[4:]
literal = re.compile(r'"((?:[0-9A-Fa-f]{2}[ ]?){8,})"')
found = set()
for d, _, files in os.walk(root):
    if any(e in d for e in excludes) or '/.git' in d:
        continue
    for f in files:
        if not any(f.endswith(x) for x in exts):
            continue
        p = os.path.join(d, f)
        if mode == 'tests' and not re.search(r'(test|Test)', p):
            continue
        for m in literal.finditer(open(p, errors='ignore').read()):
            h = m.group(1).replace(' ', '').lower()
            if len(h) >= 16 and len(h) % 2 == 0:
                found.add(h)
for h in sorted(found):
    print(h)
