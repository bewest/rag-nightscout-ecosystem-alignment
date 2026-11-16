"""Canonical role stage order with the sealed helper's guards retained."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
import adapter as a
from transport import cell_contract
from protocol import binding, discovery_mode, RESERVE

def deployment_plan(config, pgstream=False, primer_concurrency=1):
    a.require(pgstream, 'REMOTE_PGSTREAM_REQUIRED')
    plan = a.deployment_plan(config, pgstream=True, primer_concurrency_value=primer_concurrency)
    index = next(i for i, row in enumerate(plan) if row[0] == 'commission') + 1
    plan.insert(index, ('pool-initialize', 'compose', ['--profile', 'ops', 'run', '--rm', '--no-deps', 'primer', 'node', 'deploy/multitenant/evaluator-pool.js', 'initialize']))
    # Match the current canonical demo phase bounds and prohibit implicit pulls
    # or dependency starts; all infrastructure is started explicitly above.
    for name, scope, args in plan:
        if scope != 'compose':continue
        if '--no-deps' not in args:args.insert(args.index('-d')+1 if args[0]=='up' else args.index('--rm')+1,'--no-deps')
        if '--pull' not in args:args[args.index('--rm')+1:args.index('--rm')+1]=['--pull','never']
        if '--wait-timeout' in args:args[args.index('--wait-timeout')+1]='90' if name in ('infrastructure','admin-feed') else '900'
    return plan

def deploy(d, m):
    from host_binding import preflight
    preflight(d)
    raw=m.get('externalBinding') or m.get('preparedExternalBinding')
    b=binding(raw)
    with a.command_deadline(b['expiresAt']-RESERVE if discovery_mode(b) else None):
        return _deploy(d,m)

def _deploy(d, m):
    cell_contract(m)
    a.frozen(m, 'deploy')
    a.experiment_host(d, m, 'deploy-before')
    a.verify(d, m)
    m['imageId'] = a.image(m)
    if not m.get('generator'):
        a.setup_generator(d, m)
    else:
        a.verify_generator(d, m)
    m['generator']['servingImageId'] = m['imageId']
    a.write(d / 'generator-provenance.json', m['generator'])
    config = a.document(d / 'frozen.compose.json')
    a.pin_service_images(config, m['imageId'])
    if m.get('postgresImageId'):
        pg = a.json.loads(a.command(['docker', 'image', 'inspect', m['postgresImageId']]))[0]
        a.require(pg['Id'] == m['postgresImageId'] and config['services']['postgres']['image'] == pg['Id'], 'M7_POSTGRES_IMAGE_CHANGED')
    a.write(d / 'frozen.compose.json', config)
    m['composeSha256'] = a.digest(d / 'frozen.compose.json')
    a.write(d / 'owner.json', m)
    from host_binding import freeze,run_stage,existing,authorize
    freeze(d);m=a.document(d/'owner.json');config=a.document(d/'frozen.compose.json')
    stages = []
    for name, scope, args in deployment_plan(config, pgstream=m.get('profile') == 'pgstream-sample', primer_concurrency=m.get('primerConcurrency', 1)):
        before = a.time.monotonic()
        with (d / (name + '.log')).open('wb') as output:
            if scope == 'local':
                existing(d);authorize(d)
                a.command(['node', d / 'core/deploy/multitenant' / args[0], d / 'state'], file=output)
            else:
                run_stage(d,name,args,file=output,timeout=a.discovery_seconds(m,1800))
        stages.append({'name': name, 'seconds': a.time.monotonic() - before})
        a.write(d / 'deployment-stages.json', stages)
        if name == 'infrastructure':
            a.psql(d, 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements;')
        if name == 'prime' and m.get('primerConcurrency', 1) != 1:
            a.primer_counts(d, m)
        if name == 'bootstrap':
            fingerprint = a.json.loads(a.command(['node', a.HERE / 'fingerprint.cjs', d / 'core', m['pair']['core'], d / 'state/primer/config.json', str(m['tenants'])], phase='settings-fingerprint'))
            m['settingsFingerprint'] = fingerprint
            m['profileSelection'] = a.profile_provenance.identity(fingerprint, m['diagnostics'], config)
            a.profile_provenance.state_environment(d / 'state', config, m['diagnostics'])
            a.write(d / 'owner.json', m)
            layout = a.document(d / 'state/bootstrap/layout.json')
            a.require(all((layout.get('namespaces', {}).get(kind) == 'nsdemo_' + kind for kind in ('entries', 'devicestatus', 'treatments', 'clock', 'eval_checkpoint'))), 'M7_ORACLE_SCHEMA_CONTRACT_CHANGED')
            for name in a.service_roster(config):
                file = d / 'state' / name / 'env.json'
                if file.exists():
                    a.require(not a.document(file).get('MULTITENANT_REALTIME_PLACEMENT'), 'M7_SHARDED_RESTART_HELPER_REQUIRED')
    candidates = [file for file in (d / 'state/primer/tenants.json', d / 'state/ops/tenants.json') if file.exists()]
    a.require(candidates, 'M7_PRIMER_OUTPUT_MISSING')
    projections = [a.tenant_projection(a.document(file), m['tenants']) for file in candidates]
    a.require(all((value == projections[0] for value in projections)), 'M7_PRIMER_OUTPUT_CONFLICT')
    a.write(d / 'tenants.private.json', projections[0])
    a.profile_provenance.runtime_environment(a.resources(m), m['diagnostics'], config, pgstream=m.get('profile') == 'pgstream-sample')
    m['restartRoles'] = a.service_roster(config)
    a.write(d / 'owner.json', m)
    a.write(d / 'deployment.json', {'stages': stages, 'pair': m['pair'], 'imageId': m['imageId']})
