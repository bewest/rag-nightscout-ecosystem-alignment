import sys, re, os
sys.path.insert(0, 'tools/queue')
import manifest

CRM = 'externals/cgm-remote-monitor-official'
NC = 'externals/nightscout-connect'
ABL = 'tools/queue/gates/ablate.sh'
EMPTY = 'tools/queue/gates/empty-root-control.sh'

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
# ablations proven by hand on 2026-09-15; --files= where a whole-branch revert
# would only prove a module could not be require()d.
ABLATION_FILES = {
    ('bf/coercion', 'query'): 'lib/server/query.js',
    ('bf/food', 'boluscalc.quickpick'): 'lib/client/boluscalc.js',
}
ABLATION_EVIDENCE = {
    ('bf/alarms', 'insulinage'): '3 passing / 2 failing',
    ('bf/alarms', 'plugins'): '5 passing / 8 failing',
    ('bf/alarms', 'api.alexa'): 'cannot run: no mongod on port 27034',
    ('bf/alarms', 'api.googlehome'): 'cannot run: no mongod on port 27034',
    ('bf/auth', 'authdelay'): '2 passing / 9 failing',
    ('bf/auth', 'authsubjects'): '1 passing / 7 failing',
    ('bf/coercion', 'query'): '24 passing / 4 failing',
    ('bf/food', 'boluscalc.quickpick'): '6 passing / 5 failing',
    ('bf/food', 'api.food.quickpicks'): '1 passing / 2 failing',
    ('bf/merge', 'receiveddata.merge'): '10 passing / 2 failing',
    ('bf/parms', 'browser-utils.queryparms'): '1 passing / 5 failing',
    ('bf/parms', 'language'): '16 passing / 1 failing',
    ('bf/reads', 'api.count-parameter'): 'not yet run (needs MongoDB)',
}

entries = []


def add(cmd, cwd, **kw):
    e = {'gate': cmd, 'cwd': cwd}
    e.update(kw)
    entries.append(e)


def merge_tree_counterpart(a, b):
    # A counterpart measured to conflict with `b` on 2026-09-15.
    if b.startswith('seam/'):
        return 'bf/coercion'
    if 'chore/' in b:
        return 'bf/reads'
    return 'origin/chore/retire-jsdom'


for (cmd, cwd) in sorted(gates):
    ids = ','.join(sorted(set(gates[(cmd, cwd)])))

    m = re.fullmatch(r'git -C (\S+) merge-base --is-ancestor (\S+) (\S+)', cmd)
    if m:
        repo, a, b = m.groups()
        if repo == CRM and a == 'origin/dev':
            ctl = f'git -C {repo} merge-base --is-ancestor origin/chore/nightscout-modernization {b}'
            proves = (f'origin/chore/nightscout-modernization is a base {b} has NOT taken, and the '
                      f'same command reports it as not-an-ancestor (exit 1). That is the shape this '
                      f'gate goes red in when dev moves ahead of the branch.')
        else:
            ctl = f'git -C {repo} merge-base --is-ancestor {b} {a}'
            proves = (f'{a} is a strict ancestor of {b}, so the reversed question must be answered no. '
                      f'A command that said yes both ways would not be reading ancestry at all.')
        add(cmd, cwd, control=ctl, proves=proves, **{'control-kind': 'static'})
        continue

    m = re.fullmatch(r'git -C (\S+) merge-tree --write-tree (\S+) (\S+) >/dev/null', cmd)
    if m:
        repo, a, b = m.groups()
        other = merge_tree_counterpart(a, b)
        ctl = f'git -C {repo} merge-tree --write-tree {b} {other} >/dev/null'
        add(cmd, cwd, control=ctl, **{'control-kind': 'static'},
            proves=(f'{b} and {other} were measured to conflict on 2026-09-15, and merge-tree exits 1 '
                    f'on them. A trial merge that returned 0 for a conflicting pair would make every '
                    f'"merges cleanly" row in this queue meaningless.'))
        continue

    m = re.fullmatch(r'TEST=(\S+) npm run test-single', cmd)
    if m and cwd in WORKTREE_BRANCH:
        test = m.group(1)
        branch = WORKTREE_BRANCH[cwd]
        files = ABLATION_FILES.get((branch, test))
        only = f' --files={files}' if files else ''
        ctl = f'{ABL} {CRM} {branch} origin/dev {cwd}{only} {test}'
        ev = ABLATION_EVIDENCE.get((branch, test), 'measured non-zero')
        add(cmd, '.', control=ctl, **{'control-kind': 'slow'},
            proves=(f'the same test file run against a throwaway worktree of {branch} with the '
                    f'shipping code put back to origin/dev: {ev}. The worktree is created and removed '
                    f'by the control; rule 6 — it never touches {cwd}, which it reads node_modules '
                    f'and my.test.env from.'))
        continue

    m = re.fullmatch(r'node (tools/queue/gates/[\w.-]+\.js)(.*)', cmd)
    if m:
        script, rest = m.group(1), m.group(2).strip()
        if script.endswith('bf-reads-read-contract.js'):
            add(cmd, cwd, control='node tools/queue/gates/bf-reads-read-contract.js --rev origin/dev',
                **{'control-kind': 'static'},
                positive_placeholder=None,
                proves=('the identical 8 assertions run against origin/dev materialised from the object '
                        'database: 4 failing, including "lib/server/count.js: not present at this rev". '
                        'Also measured failing at bf/alarms, which is one of the three refs the old '
                        'P0-E gate passed against.'))
            continue
        add(cmd, cwd, control=f'{EMPTY} {script} {rest}'.strip(), **{'control-kind': 'static'},
            proves=('the gate is run with QUEUE_GATE_ROOT pointed at an EMPTY directory, so none of the '
                    'files it reads exist, and it does not exit 0. This proves the gate is coupled to '
                    'its inputs; it does NOT prove it is coupled to the right PROPERTY of them, and '
                    'where a sharper control exists it is named in the audit.'))
        continue

    add(cmd, cwd, **{'control-exempt': 'PLACEHOLDER — author a control'})

print('generated', len(entries), 'entries')
import json
json.dump(entries, open('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/controls.json', 'w'), indent=1)
todo = [e for e in entries if 'control-exempt' in e]
print('needing hand authorship:', len(todo))
for e in todo:
    print('  [%s] %s' % (e['cwd'], e['gate']))
