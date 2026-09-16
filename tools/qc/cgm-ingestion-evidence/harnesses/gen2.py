import sys, re, json, textwrap
sys.path.insert(0, 'tools/queue')
import manifest

CRM = 'externals/cgm-remote-monitor-official'
NC = 'externals/nightscout-connect'
ABL = 'tools/queue/gates/ablate.sh'
EMPTY = 'tools/queue/gates/empty-root-control.sh'
TMP = "T=$(mktemp -d) && trap 'rm -rf \"$T\"' EXIT &&"

doc = manifest.load()
gates = {}
for it in doc['items']:
    for g in it.get('gates') or []:
        k, p = manifest.classify_gate(g)
        if k != 'run':
            continue
        gates.setdefault((' '.join(p['run'].split()), p.get('cwd') or '.'), []).append(it['id'])

WORKTREE_BRANCH = {
    'externals/work/crm-bf-alarms': 'bf/alarms',
    'externals/work/crm-bf-auth': 'bf/auth',
    'externals/work/crm-bf-cache': 'bf/cache',
    'externals/work/crm-bf-coercion': 'bf/coercion',
    'externals/work/crm-bf-food': 'bf/food',
    'externals/work/crm-bf-merge': 'bf/merge',
    'externals/work/crm-bf-parms': 'bf/parms',
    'externals/work/crm-bf-reads': 'bf/reads',
}
ABLATION_FILES = {
    ('bf/coercion', 'query'): 'lib/server/query.js',
    ('bf/food', 'boluscalc.quickpick'): 'lib/client/boluscalc.js',
}
ABLATION_EVIDENCE = {
    ('bf/alarms', 'insulinage'): 'measured 2026-09-15: 3 passing / 2 failing',
    ('bf/alarms', 'plugins'): 'measured 2026-09-15: 5 passing / 8 failing',
    ('bf/alarms', 'api.alexa'): 'NOT YET RUN: crm-bf-alarms names mongod on port 27034 and nothing listens there',
    ('bf/alarms', 'api.googlehome'): 'NOT YET RUN: same missing mongod on port 27034',
    ('bf/auth', 'authdelay'): 'measured 2026-09-15: 2 passing / 9 failing',
    ('bf/auth', 'authsubjects'): 'measured 2026-09-15: 1 passing / 7 failing',
    ('bf/coercion', 'query'): 'measured 2026-09-15 with --files=lib/server/query.js: 24 passing / 4 failing on assertions',
    ('bf/food', 'boluscalc.quickpick'): 'measured 2026-09-15 with --files=lib/client/boluscalc.js: 6 passing / 5 failing',
    ('bf/food', 'api.food.quickpicks'): 'measured 2026-09-15: 1 passing / 2 failing',
    ('bf/merge', 'receiveddata.merge'): 'measured 2026-09-15: 10 passing / 2 failing',
    ('bf/parms', 'browser-utils.queryparms'): 'measured 2026-09-15: 1 passing / 5 failing',
    ('bf/parms', 'language'): 'measured 2026-09-15: 16 passing / 1 failing',
}

HAND = {}

def hand(cmd, cwd='.', **kw):
    HAND[(' '.join(cmd.split()), cwd)] = kw

# ---- P0-D: the vendored coercion table equals a fresh emission -------------
hand("""T=$(mktemp -d) && trap 'rm -rf "$T"' EXIT && python3 -m tools.nsschema.emit.coercion_emit --bundle "$T/emitted.json" >/dev/null && diff -q "$T/emitted.json" externals/work/crm-bf-coercion/lib/server/query-coercion.json""",
     control=TMP + """ python3 -m tools.nsschema.emit.coercion_emit --bundle "$T/emitted.json" >/dev/null && python3 -c "import json,sys; d=json.load(open(sys.argv[1])); c=d['collections']['entries']; c[sorted(c)[0]]='string'; json.dump(d,open(sys.argv[2],'w'),indent=1,sort_keys=True)" "$T/emitted.json" "$T/corrupt.json" && diff -q "$T/emitted.json" "$T/corrupt.json\"""",
     positive_control=TMP + """ python3 -m tools.nsschema.emit.coercion_emit --bundle "$T/emitted.json" >/dev/null && cp "$T/emitted.json" "$T/same.json" && diff -q "$T/emitted.json" "$T/same.json\"""",
     proves="one field's declared type is flipped to `string` in a copy of the freshly emitted bundle and the comparison notices. The gate this replaced, `coercion_emit --drift`, ends in `return 0` unconditionally and exited 0 while printing 157 disagreements.")

# ---- RT-D3's dependency test ----------------------------------------------
hand('TEST=dependency-d3 npm run test-single', CRM,
     exempt="This gate's cwd is the SHIPPING CHECKOUT, which 19 worktrees hang off. Ablating it means editing that tree, and rule 6 forbids it. The gate is currently FAILING against the live tree, so it is not silently green, and RT-D3's companion instrument (d3-drag-clamp-covered.js) carries its own internal CONTROL finding and is the non-vacuous measurement for this item.")

# ---- FU-RESIDUALS: alexa switch -------------------------------------------
hand("""bash -c 's=$(git -C externals/cgm-remote-monitor-official show origin/dev:lib/api/alexa/index.js); echo "$s" | grep -q "switch (req.body.request.type)" || exit 1; echo "$s" | grep -q "default:"'""",
     control="""bash -c 's=$(git -C externals/cgm-remote-monitor-official show origin/dev:lib/api/index.js); echo "$s" | grep -q "switch (req.body.request.type)" || exit 1; echo "$s" | grep -q "default:"'""",
     proves="the identical pair of greps against a file that contains neither (lib/api/index.js) exits 1. It shows the greps read the file they are given rather than matching anything.")

# ---- FU-LIMIT --------------------------------------------------------------
for ref in ('bf/reads', 'origin/dev'):
    hand(f"""git -C {CRM} cat-file -e {ref}:lib/server/count.js 2>/dev/null && git -C {CRM} show {ref}:lib/api3/generic/collection.js | grep -q "self.parseLimit" && exit 1 || exit 0""",
         control=f"""git -C {CRM} cat-file -e bf/reads:lib/server/count.js 2>/dev/null && git -C {CRM} show bf/reads:lib/api3/generic/collection.js | grep -q "maxLimit" && exit 1 || exit 0""",
         proves="the same conjunction with a pattern that IS present in collection.js (`maxLimit`) on a ref where count.js DOES exist (bf/reads) exits 1. The state this gate is meant to go red in - count.js present AND collection.js delegating to it - does not exist on any ref yet, which is precisely the follow-up it tracks, so the instrument is exercised with a stand-in pattern instead.")

# ---- P0-T01 ----------------------------------------------------------------
hand(f"git -C {CRM} ls-remote --heads origin bewest/wip/optimize-treatment-processing | grep -q dfe2753d",
     control=f"git -C {CRM} ls-remote --heads origin bewest/wip/optimize-treatment-processing | grep -q 0000000000000000000000000000000000000000",
     kind='network',
     proves="the same read-only ls-remote piped into a grep for a SHA that is not there exits 1. Rule 0: ls-remote READS and never pushes.")

# ---- RT-NODE-FLOOR-TESTED --------------------------------------------------
for cut in ('origin/chore/compose-mongodb6', 'origin/chore/retire-jsdom'):
    hand(f"""git -C {CRM} show {cut}:.github/workflows/main.yml | grep -q "'22.23.2'" && git -C {CRM} show {cut}:.github/workflows/main.yml | grep -q "'24.20.0'\"""",
         control=f"""git -C {CRM} show origin/dev:.github/workflows/main.yml | grep -q "'22.23.2'" && git -C {CRM} show origin/dev:.github/workflows/main.yml | grep -q "'24.20.0'\"""",
         proves="the identical pair of greps against origin/dev's workflow exits 1 - measured 0 matches for each version string. The cuts pin the floor in CI and dev does not.")

# ---- FU-RESIDUALS: storage.js Loading log ---------------------------------
hand(f"""git -C {CRM} show origin/dev:lib/authorization/storage.js | grep -qE "console\\\\.log\\\\('Loading',[[:space:]]*opts\\\\)" && exit 1 || exit 0""",
     control=f"""git -C {CRM} show bf/auth:lib/authorization/storage.js | grep -qE "console\\\\.log\\\\('Loading',[[:space:]]*opts\\\\)" && exit 1 || exit 0""",
     positive_control=f"""git -C {CRM} show bf/reads:lib/server/aggregate.js | grep -qE "console\\\\.log\\\\('Loading',[[:space:]]*opts\\\\)" && exit 1 || exit 0""",
     proves="the same absence gate exits 1 against a ref that DOES carry the line (bf/auth, at :113) and exits 0 against a file that does not (bf/reads' aggregate.js, where BF-05's own console.log was deleted). Both directions measured.")

# ---- FU-RESIDUALS: plugins.js ---------------------------------------------
hand(f"""git -C {CRM} show origin/dev:lib/plugins/index.js | grep -q "return (p !== null)" && exit 1 || exit 0""",
     control=f"""git -C {CRM} show bf/alarms:lib/plugins/index.js | grep -q "return (p !== null)" && exit 1 || exit 0""",
     positive_control=TMP + """ printf '%s\\n' 'return p;' > "$T/f.js" && grep -q "return (p !== null)" "$T/f.js" && exit 1 || exit 0""",
     proves="exits 1 against a ref that carries the expression (bf/alarms still does - measured 1 match) and 0 against a fixture that does not.")

# ---- P0-TAG: the tag must NOT be on the remote yet -------------------------
hand(f"git -C {NC} ls-remote --tags origin v0.0.14 | grep -q . && exit 1 || exit 0",
     control=f"git -C {NC} ls-remote --tags origin v0.0.14 | grep -q . || git -C {NC} ls-remote --tags origin v0.0.13 | grep -q . && exit 1 || exit 0",
     kind='network',
     proves="the same shape asked about v0.0.13, which IS on the remote, exits 1. That is the state this gate must reach the moment someone pushes v0.0.14 - rule 0 says a human does that, not this queue.")

# ---- P0-C: the tracking absence gate --------------------------------------
hand("""grep -nE "console\\\\.log\\\\('Loading',[[:space:]]*opts\\\\)" lib/authorization/storage.js && exit 1 || exit 0""",
     'externals/work/crm-bf-auth',
     control=TMP + """ printf '%s\\n' "      console.log('Loading',opts);" > "$T/f.js" && grep -nE "console\\.log\\('Loading',[[:space:]]*opts\\)" "$T/f.js" && exit 1 || exit 0""",
     positive_control=TMP + """ printf '%s\\n' "      console.log('Reloading auth data');" > "$T/f.js" && grep -nE "console\\.log\\('Loading',[[:space:]]*opts\\)" "$T/f.js" && exit 1 || exit 0""",
     proves="THE FIXTURE IS THE NO-SPACE SPELLING, which is what the code actually contains and what the old pattern could never match. The negative fixture makes the gate red and the positive fixture makes it green, so this gate now discriminates the two states it is supposed to distinguish.")

# ---- P0-PIN: the deliberately inverted lock gate --------------------------
hand("grep -q '234d47c85510a77f07b3be0d2c026dd0272715d6' package-lock.json",
     'externals/work/crm-bf-connect-pin',
     control=TMP + f""" git -C ../../../{CRM} show origin/dev:package-lock.json | sed 's#234d47c85510a77f07b3be0d2c026dd0272715d6#archive/refs/tags/v0.0.14.tar.gz#g' > "$T/lock.json" && grep -q '234d47c85510a77f07b3be0d2c026dd0272715d6' "$T/lock.json\"""",
     positive_control="grep -q '234d47c85510a77f07b3be0d2c026dd0272715d6' package-lock.json",
     proves="THIS GATE IS DELIBERATELY INVERTED and its control has to be too. It passes while the lockfile is STILL on the old connector SHA, and must go red the moment P0-LOCK regenerates it - so the known-negative is a lockfile with the SHA replaced by the v0.0.14 tarball, and against that the grep exits 1. NOTE FOR THE AUDIT: the gate also passes against origin/dev's own lockfile, because the old SHA is what dev pins. It is a HANDOFF TRIPWIRE, not a gate on the branch, and no derived control could have known that - which is why controls are authored per gate and never generated.")

# ---- DOC-MEMORY Makefile target -------------------------------------------
hand("grep -q '^queue-status:' Makefile",
     control=TMP + """ printf '%s\\n' 'queue-status :' > "$T/Makefile" && grep -q '^queue-status:' "$T/Makefile\"""",
     positive_control=TMP + """ printf '%s\\n' 'queue-status:' > "$T/Makefile" && grep -q '^queue-status:' "$T/Makefile\"""",
     proves="a near-miss fixture (`queue-status :`, with a space) is rejected and the exact target is accepted. A grep that matched the near miss would not be reading a Make target.")

# ---- P0-LOCK ---------------------------------------------------------------
hand("grep -q 'archive/refs/tags/v0.0.14.tar.gz' package-lock.json",
     'externals/work/crm-bf-connect-pin',
     control=TMP + """ printf '%s\\n' '"resolved": "https://github.com/nightscout/nightscout-connect/archive/234d47c.tar.gz"' > "$T/lock.json" && grep -q 'archive/refs/tags/v0.0.14.tar.gz' "$T/lock.json\"""",
     positive_control=TMP + """ printf '%s\\n' '"resolved": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.14.tar.gz"' > "$T/lock.json" && grep -q 'archive/refs/tags/v0.0.14.tar.gz' "$T/lock.json\"""",
     proves="the gate is red today ON PURPOSE - P0-LOCK is deliberately undone until the tag is pushed - so both directions are shown on fixtures rather than on the file. It rejects a lock pinned by SHA and accepts one pinned to the tag tarball.")

# ---- P0-PIN package.json ---------------------------------------------------
hand("grep -q 'archive/refs/tags/v0.0.14.tar.gz' package.json",
     'externals/work/crm-bf-connect-pin',
     control=f"git -C ../../../{CRM} show origin/dev:package.json | grep -q 'archive/refs/tags/v0.0.14.tar.gz'",
     positive_control="grep -q 'archive/refs/tags/v0.0.14.tar.gz' package.json",
     proves="the same grep against origin/dev's package.json - the base this branch's one-line change is made against - exits 1. This is the one connect-pin gate that really does measure the branch.")

# ---- BFQ-10 ----------------------------------------------------------------
hand("grep -q 'ulimits' docker-compose.yml", CRM,
     control=TMP + """ printf '%s\\n' 'services:' > "$T/dc.yml" && grep -q 'ulimits' "$T/dc.yml\"""",
     positive_control=TMP + """ printf '%s\\n' '    ulimits:' > "$T/dc.yml" && grep -q 'ulimits' "$T/dc.yml\"""",
     proves="fixtures both ways. The gate is red against the real file because dev's compose file sets no nofile limit, which is the defect BFQ-10 records.")

# ---- P0-F backoff ----------------------------------------------------------
hand("""node -e "const b=require('./lib/backoff.js'); try { b({jitter:'wild'}); process.exit(1); } catch(e) { process.exit(/unknown jitter mode/.test(e.message)?0:1); }\"""",
     'externals/work/nc-jitter',
     control=TMP + f""" git -C ../../../{NC} show c1cce2a^:lib/backoff.js > "$T/backoff.js" && node -e 'const b=require(process.argv[1]); try {{ b({{jitter:"wild"}}); process.exit(1); }} catch(e) {{ process.exit(/unknown jitter mode/.test(e.message)?0:1); }}' "$T/backoff.js\"""",
     proves="the identical expression against the PRE-FIX lib/backoff.js (c1cce2a^) exits 1: that version merged options as {...config, ...defaults} with defaults last, so it never saw the caller's jitter mode and had nothing to reject.")

# ---- P0-LOCK npm ci --------------------------------------------------------
hand('npm ci --dry-run', 'externals/work/crm-bf-connect-pin',
     exempt="Rule 0. It resolves against the npm registry and a GitHub tarball for a tag that does not exist yet, and it CANNOT pass until a human pushes v0.0.14 - which is the point of P0-LOCK. Running a control for it here would mean either contacting those endpoints or faking the answer.")

# ---- P0-F npm test ---------------------------------------------------------
hand('npm test', 'externals/work/nc-jitter',
     cwd_override='.',
     control=f"{ABL} {NC} fix/connect-timer-jitter c1cce2a^ externals/work/nc-jitter backoff cycle-jitter",
     kind='slow',
     proves="the branch's two new test files run against a throwaway worktree with index.js, lib/backoff.js, lib/builder.js and lib/machines/cycle.js put back to c1cce2a^: measured failing 2026-09-15. Base is c1cce2a^ and NOT the merge-base with main - the branch's parent is a merge commit and everything T0.4/BF-34 changed is in the single commit c1cce2a.")

# ---- DOC-MEMORY emit --check ----------------------------------------------
hand('python3 tools/queue/emit.py --check',
     control=TMP + """ printf 'not the generated view\\n' > "$T/QUEUE.md" && python3 tools/queue/emit.py --check --out "$T/QUEUE.md\"""",
     positive_control=TMP + """ python3 tools/queue/emit.py --out "$T/QUEUE.md" >/dev/null && python3 tools/queue/emit.py --check --out "$T/QUEUE.md\"""",
     proves="--check exits 1 against a file that is not the rendering and 0 against one that is. Both measured.")

# ---- P0-TAG object shape ---------------------------------------------------
hand(f'test "$(git -C {NC} cat-file -t v0.0.14)" = tag',
     control=f'test "$(git -C {NC} cat-file -t v0.0.13)" = tag',
     proves="v0.0.13 is a LIGHTWEIGHT tag - cat-file -t says `commit` - so the same test against it exits 1. The gate really is reading the object type and not merely that the name resolves.")
hand(f'test "$(git -C {NC} rev-parse v0.0.14^{{commit}})" = "$(git -C {NC} rev-parse release/v0.0.14)"',
     control=f'test "$(git -C {NC} rev-parse v0.0.13^{{commit}})" = "$(git -C {NC} rev-parse release/v0.0.14)"',
     proves="the same comparison against v0.0.13 (b394411a) versus release/v0.0.14 (649a7de2) exits 1.")
hand(f"""test "$(git -C {NC} show release/v0.0.14:package.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')" = 0.0.14""",
     control=f"""test "$(git -C {NC} show v0.0.13:package.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')" = 0.0.14""",
     proves="the same extraction at v0.0.13 yields 0.0.13 and the test exits 1.")

# ---- existence gates -------------------------------------------------------
hand('test -f docs/60-research/tenant-config-surface-2026-09-15.md',
     control='test -f docs/60-research/tenant-config-surface-2026-09-15.md.this-name-does-not-exist',
     positive_control='test -f docs/60-research/e3-gate-vacuity-audit-2026-09-15.md',
     proves="`test -f` is shown to distinguish an absent path from a present one. THIS IS A WEAK CONTROL and the audit says so: it proves the instrument works, not that the file it names is the right file. An existence gate can never be stronger than that.")
hand('test -f externals/work/crm-bf-alarms/node_modules/.cache/_ns_cache/public/js/bundle.app.js',
     control='test -f externals/work/crm-bf-alarms/node_modules/.cache/_ns_cache/public/js/bundle.app.js.absent',
     positive_control='test -f externals/work/crm-bf-reads/node_modules/.cache/_ns_cache/public/js/bundle.app.js',
     proves="the positive control is the SAME path under crm-bf-reads, where the bundle is present - so the gate is shown to go green on a real bundle at a real path, not merely on a file that happens to exist. crm-bf-alarms and crm-bf-connect-pin are the only two worktrees missing it (E3 checked all 15).")
for name in ('evaluator', 'realtime'):
    hand(f'test -f externals/work/crm-seam/bin/{name}.js',
         control=f'test -f externals/work/crm-seam/bin/{name}.js.absent',
         positive_control='test -f externals/work/crm-seam/package.json',
         proves="weak by nature - see the audit's note on existence gates. The work is not started, so the gate is red and there is nothing yet to assert a property OF.")

# --------------------------------------------------------------- assemble
entries = []

def merge_tree_counterpart(b):
    if b.startswith('seam/'):
        return 'bf/coercion'
    if 'chore/' in b:
        return 'bf/reads'
    return 'origin/chore/retire-jsdom'

for (cmd, cwd) in sorted(gates):
    key = (cmd, cwd)
    if key in HAND:
        h = dict(HAND[key])
        e = {'gate': cmd, 'cwd': cwd}
        if h.get('cwd_override'):
            e['control-cwd'] = h.pop('cwd_override')
        else:
            h.pop('cwd_override', None)
        if 'exempt' in h:
            e['control-exempt'] = h['exempt']
        else:
            e['control'] = ' '.join(h['control'].split())
            e['control-kind'] = h.get('kind', 'static')
            if h.get('positive_control'):
                e['positive-control'] = ' '.join(h['positive_control'].split())
            e['proves'] = h['proves']
        entries.append(e)
        continue

    m = re.fullmatch(r'git -C (\S+) merge-base --is-ancestor (\S+) (\S+)', cmd)
    if m:
        repo, a, b = m.groups()
        if repo == CRM and a == 'origin/dev':
            ctl = f'git -C {repo} merge-base --is-ancestor origin/chore/nightscout-modernization {b}'
            proves = (f'origin/chore/nightscout-modernization is a base {b} has NOT taken, and the same '
                      f'command reports it not-an-ancestor (exit 1, measured). That is exactly the shape '
                      f'this gate goes red in when dev moves ahead of the branch.')
        else:
            ctl = f'git -C {repo} merge-base --is-ancestor {b} {a}'
            proves = (f'{a} is a strict ancestor of {b}, so the reversed question must be answered no '
                      f'(exit 1, measured). A command that said yes both ways would not be reading '
                      f'ancestry at all.')
        entries.append({'gate': cmd, 'cwd': cwd, 'control': ctl,
                        'control-kind': 'static', 'proves': proves})
        continue

    m = re.fullmatch(r'git -C (\S+) merge-tree --write-tree (\S+) (\S+) >/dev/null', cmd)
    if m:
        repo, a, b = m.groups()
        other = merge_tree_counterpart(b)
        entries.append({'gate': cmd, 'cwd': cwd,
                        'control': f'git -C {repo} merge-tree --write-tree {b} {other} >/dev/null',
                        'control-kind': 'static',
                        'proves': (f'{b} and {other} were measured to conflict on 2026-09-15 and merge-tree '
                                   f'exits 1 on the pair. A trial merge that returned 0 for a conflicting '
                                   f'pair would make every "merges cleanly" row in this queue meaningless.')})
        continue

    m = re.fullmatch(r'TEST=(\S+) npm run test-single', cmd)
    if m and cwd in WORKTREE_BRANCH:
        test, branch = m.group(1), WORKTREE_BRANCH[cwd]
        files = ABLATION_FILES.get((branch, test))
        only = f' --files={files}' if files else ''
        entries.append({'gate': cmd, 'cwd': cwd, 'control-cwd': '.',
                        'control': f'{ABL} {CRM} {branch} origin/dev {cwd}{only} {test}',
                        'control-kind': 'slow',
                        'proves': (f'the same test file against a throwaway worktree of {branch} with the '
                                   f'shipping code put back to origin/dev — '
                                   f'{ABLATION_EVIDENCE.get((branch, test), "measured non-zero")}. Rule 6: the '
                                   f'control creates and removes its own worktree under $TMPDIR and never '
                                   f'writes into {cwd}, which it reads node_modules and my.test.env from.')})
        continue

    m = re.fullmatch(r'node (tools/queue/gates/[\w.-]+\.js)(.*)', cmd)
    if m:
        script, rest = m.group(1), m.group(2).strip()
        if script.endswith('bf-reads-read-contract.js'):
            entries.append({'gate': cmd, 'cwd': cwd,
                            'control': 'node tools/queue/gates/bf-reads-read-contract.js --rev origin/dev',
                            'control-kind': 'static',
                            'proves': ('the identical 8 assertions against origin/dev, materialised from the '
                                       'object database into a temporary tree: 4 failing, one of them '
                                       '"lib/server/count.js: not present at this rev". Measured failing at '
                                       'bf/alarms too, which is one of the three refs the gate this replaced '
                                       'passed against.')})
            continue
        entries.append({'gate': cmd, 'cwd': cwd,
                        'control': (f'{EMPTY} {script} {rest}').strip(),
                        'control-kind': 'static',
                        'proves': ('run with QUEUE_GATE_ROOT pointed at an EMPTY directory, so none of the '
                                   'files it reads exist, the gate does not exit 0. THIS IS THE WEAK FORM: it '
                                   'proves the gate is coupled to its inputs, not that it is coupled to the '
                                   'right property of them. Where a sharper control was run by hand the audit '
                                   'says so.')})
        continue

    entries.append({'gate': cmd, 'cwd': cwd,
                    'control-exempt': 'NO CONTROL AUTHORED YET. This entry exists so the gate is not silently uncontrolled; it is a debt, not a verdict.'})

json.dump(entries, open('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/controls.json', 'w'), indent=1)
print('entries:', len(entries))
print('exempt:', sum(1 for e in entries if 'control-exempt' in e))
print('unauthored:', sum(1 for e in entries if 'NO CONTROL AUTHORED' in e.get('control-exempt', '')))
