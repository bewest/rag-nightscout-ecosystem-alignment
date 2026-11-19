#!/usr/bin/env python3
"""Run the canonical M7 adapter from one reusable configuration.

Preparation starts no services. Execution uses one finite independent cleanup
process and never retries a failed phase. Raw output and partial adapter results
stay in the private run directory.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter as a
import workload_inputs
import point_results
from contract import require
from auto_catalog import auto_catalog

TIERS = ('smoke', 'discovery', 'acceptance')
GENERATED_RECEIPT = 'configuration-receipt.json'
TO_COMPLETION = 'local-owned-to-completion'
STRUCTURED_OPTIONS = {'viewer-setup', 'driver-plan', 'opportunity-observation', 'drain-observation'}
SMOKE_DEFAULTS = {
    'tenants': 8, 'replicas': 1, 'load-seconds': 60, 'warmup-seconds': 5,
    'idle-seconds': 5, 'probe-every-ms': 10000, 'sockets-per-tenant': 1,
    'offered-rps': 2, 'completion-contract': 'evaluator-work-v2',
}


def tier_options(config):
    tier = config.get('tier')
    options = config['prepare']
    if tier is None:
        return options, {}
    defaults = {'profile': 'pgstream-sample',
                'run-purpose': 'acceptance' if tier == 'acceptance' else 'discovery'}
    if tier == 'smoke':
        defaults.update(SMOKE_DEFAULTS)
        if 'workload-mix' in options:
            del defaults['offered-rps']
    if tier != 'acceptance' and not {'receipt', 'freeze'} & options.keys():
        defaults['receipt'] = GENERATED_RECEIPT
    effective = {**defaults, **options}
    return effective, {key: value for key, value in defaults.items() if key not in options}


def tier_plan(config):
    from run_configuration import from_args, resolve
    _, argv = validate_config(config)
    parsed = a.parser().parse_args(['prepare', '--directory', '/tmp/m7-tier-plan', *argv])
    tier = config.get('tier', 'discovery')
    _, defaults = tier_options(config)
    if tier == 'acceptance':
        projection = {'configuration': from_args(parsed, a.instrument()['sha256'])}
    else:
        projection = resolve(config)
    effective = projection['configuration']
    return {
        'tier': tier, 'defaultsApplied': defaults,
        'authoredKeys': sorted(config['prepare']),
        'effective': effective,
        'execution': {**{key: config[key] for key in ('workSeconds', 'cleanupSeconds')},
                      'mode': TO_COMPLETION if config['workSeconds'] is None else 'fixed-window'},
        'sourceAdmission': ('frozen acceptance receipt' if tier == 'acceptance' else
                            'runner-materialized PENDING tuple' if parsed.freeze == GENERATED_RECEIPT
                            else 'supplied diagnostic receipt'),
        'effectiveLimits': {
            'workSeconds': {'value': config['workSeconds'], 'maximum': None if config['workSeconds'] is None else (workload_inputs.MAX_SECONDS if tier == 'discovery' else 86400),
                            'origin': 'authored' if config['workSeconds'] is not None else 'to-completion'},
            'cleanupSeconds': {'value': config['cleanupSeconds'], 'maximum': workload_inputs.MAX_SECONDS if tier == 'discovery' else 3600,
                               'origin': 'authored; a finite cleanup is always required'},
            'drainSeconds': {'value': effective.get('cadence', {}).get('drainSeconds'),
                             'origin': 'authored' if 'drainSeconds' in effective.get('cadence', {}) else 'run work deadline'}},
        'resourceOrigin': 'uncapped Compose services; host limits may apply',
        'coverage': {
            'clinical': 'selected write witnesses',
            'wholePopulationClinicalTails': 'UNMEASURED',
            'restore': 'separate frozen acceptance control',
        },
        'preflight': {
            'sourceAndImage': 'checked before fixture seed on tiered runs',
            'deploymentPrimer': 'stageSeconds limits time without durable tenant progress; the owner work cutoff still applies',
            'socketAndJwtSetup': 'viewerSetup selects connection progress and setupSeconds bounds ordinary driver JWT setup',
            'generatorDrain': 'drainSeconds selects collector drain; the clinical deadline is separate',
            'transportOrGeneratorChange': 'run a smoke point with the same source, image and instrument before seeding a larger discovery point',
            'runtime': 'owned readiness, driver export and completion reader checks',
        },
        'capacityAcceptance': 'NOT_GRANTED',
    }


def clean_source_preflight(parsed):
    if parsed.run_purpose != 'discovery':
        # An existing image is the run identity; its sources are not re-proved per run.
        a.image({'pair': {'core': parsed.core_commit, 'deploy': parsed.deploy_commit},
                 'image': parsed.image, 'imageId': parsed.image_id or parsed.image})
        return
    # Discovery builds image inputs from the selected commits (git archive);
    # the checkout's HEAD and working tree are not compared.
    for role in ('core', 'deploy'):
        a.commit(getattr(parsed, role + '_repo'), getattr(parsed, role + '_commit'))
    a.prepare_image_inputs(parsed)



CANDIDATE_OPTIONS = ('image', 'image-id', 'core-commit', 'deploy-commit')


def with_candidate(config, reference=None):
    """The candidate image is a run parameter, never a pinned tuple in the config.

    `--candidate` (or M7_CANDIDATE_IMAGE) names a local image reference. Its
    digest and its labelled core/deploy revisions replace whatever the config
    carried, and are recorded as the run's identity with the run configuration.
    """
    reference = reference or os.environ.get('M7_CANDIDATE_IMAGE')
    if not reference:
        return config, None
    spec = json.loads(a.command(['docker', 'image', 'inspect', reference]))[0]
    labels = (spec.get('Config') or {}).get('Labels') or {}
    candidate = {'reference': reference, 'imageId': spec['Id'], 'repoDigests': spec.get('RepoDigests') or [],
                 'core': labels.get('org.opencontainers.image.revision'),
                 'deploy': labels.get('org.nightscout.deploy.revision')}
    require(all(isinstance(candidate[k], str) and re.fullmatch(r'[0-9a-f]{40}', candidate[k]) for k in ('core', 'deploy')),
            'M7_CANDIDATE_LABELS')
    prepare = {k: v for k, v in config['prepare'].items() if k not in CANDIDATE_OPTIONS}
    prepare.update({'image': spec['Id'], 'image-id': spec['Id'],
                    'core-commit': candidate['core'], 'deploy-commit': candidate['deploy']})
    return {**config, 'prepare': prepare}, candidate


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.partial-' + str(os.getpid()))
    a.write(temp, value)
    os.replace(temp, path)


def code(error):
    value = str(error)
    return value if re.fullmatch(r'M7_[A-Z_]+(?::[A-Za-z0-9_.-]+)?', value) else 'M7_RUNNER_PHASE_FAILED'


def verify_helper(config):
    """Check the declared helper identity is well formed; the running instrument
    is recorded by the observation, not compared with a pin."""
    if 'helperInstrument' in config:
        expected = config['helperInstrument']
        require(isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected) is not None,
                'M7_RUNNER_HELPER_INSTRUMENT')
    else:
        # A recorded label, not a pin: any non-empty name identifies the helper.
        require(isinstance(config.get('helperHead'), str) and config['helperHead'] != '',
                'M7_RUNNER_HELPER_HEAD')


def load_config(path):
    return validate_config(a.document(path))


def validate_config(config):
    require(config.get('version') == 1, 'M7_RUNNER_CONFIG_VERSION')
    common = {'version', 'prepare', 'k6Image', 'workSeconds', 'cleanupSeconds'}
    keys = set(config) - {'tier', 'smokeBaseline'}
    require(keys in (common | {'helperHead'}, common | {'helperInstrument'}), 'M7_RUNNER_CONFIG_FIELDS')
    tier = config.get('tier')
    require('tier' not in config or tier in TIERS, 'M7_RUNNER_TIER')
    if 'smokeBaseline' in config:
        baseline = config['smokeBaseline']
        require(tier == 'smoke' and isinstance(baseline, str) and Path(baseline).is_absolute(),
                'M7_SMOKE_BASELINE_PATH')
    verify_helper(config)
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', config['k6Image']) is not None, 'M7_RUNNER_K6_PIN')
    work = config['workSeconds']
    local_to_completion = work is None and tier == 'discovery'
    require((local_to_completion or type(work) is int and 30 <= work <= (workload_inputs.MAX_SECONDS if tier == "discovery" else 86400))
            and type(config['cleanupSeconds']) is int and 30 <= config['cleanupSeconds'] <=
            (workload_inputs.MAX_SECONDS if tier == 'discovery' else 3600),
            'M7_RUNNER_FINITE_LIMIT')
    options = config['prepare']
    require(isinstance(options, dict) and 'directory' not in options and 'fixture-project' in options
            and 'backend-subnet' in options and 'edge-subnet' in options, 'M7_RUNNER_PREPARE_CONFIG')
    options, _ = tier_options(config)
    require(not {'receipt', 'freeze'} <= options.keys(), 'M7_RUNNER_RECEIPT_AMBIGUOUS')
    require(tier != 'acceptance' or bool({'receipt', 'freeze'} & options.keys()),
            'M7_FROZEN_ACCEPTANCE_REQUIRED')
    argv = []
    for key, value in options.items():
        if key in STRUCTURED_OPTIONS and isinstance(value, dict):
            value = json.dumps(value, sort_keys=True, allow_nan=False)
        require(re.fullmatch(r'[a-z][a-z0-9-]+', key) and isinstance(value, (str, int, float)) and not isinstance(value, bool), 'M7_RUNNER_PREPARE_OPTION')
        argv.extend(['--' + key, str(value)])
    # The adapter owns supported options and all source/profile admission.
    parsed = a.parser().parse_args(['prepare', '--directory', '/tmp/m7-runner-validation', *argv])
    purpose = 'acceptance' if tier == 'acceptance' else 'discovery'
    require(parsed.profile == 'pgstream-sample' and parsed.run_purpose == purpose, 'M7_RUNNER_TIER_PROFILE')
    if tier in ('smoke', 'discovery'):
        require(re.fullmatch(r'sha256:[a-f0-9]{64}', parsed.image_id or parsed.image) is not None,
                'M7_TIER_IMAGE_PIN')
        require(parsed.completion_contract is not None, 'M7_TIER_COMPLETION_CONTRACT')
    if tier == 'smoke':
        require(parsed.logical_polling_clients != 0, 'M7_SMOKE_CLIENT_WITNESS_REQUIRED')
    from run_configuration import validate_prepare
    validate_prepare(parsed)
    require(0 <= parsed.quiet_load <= (os.cpu_count() or 1), 'M7_QUIET_BOUND_INVALID')
    cadence = a.cadence_options(parsed)
    require(not local_to_completion or {'setupSeconds', 'drainSeconds'} <= cadence.keys(),
            'M7_RUNNER_TO_COMPLETION_PHASE_BUDGETS_REQUIRED')
    authored_windows = ('loadSeconds', 'setupSeconds', 'drainSeconds')
    require(local_to_completion or work > sum(cadence.get(key, 0) for key in authored_windows),
            'M7_RUNNER_WORK_WINDOW')
    return config, argv


def preflight_receipt(config, argv):
    # Validate receipt/config mirrors before creating output or arming a guard.
    parsed=a.parser().parse_args(['prepare','--directory','/tmp/m7-runner-validation',*argv])
    receipt=a.document(parsed.freeze)
    if 'workSeconds' in config and config['workSeconds'] is None:
        require(receipt.get('version') == 2 and receipt.get('executionScope') == 'LOCAL_OWNED_TO_COMPLETION',
                'M7_RUNNER_TO_COMPLETION_RECEIPT_REQUIRED')
    if config.get('tier') == 'acceptance':
        pair = {'core': parsed.core_commit, 'deploy': parsed.deploy_commit}
        require(receipt.get('imageId') == (parsed.image_id or parsed.image), 'M7_ACCEPTANCE_IMAGE_MISMATCH')
        a.receipt_scope({'pair': pair, 'profile': parsed.profile, 'runPurpose': 'acceptance'},
                        receipt, 'deploy')
    elif receipt.get('version')==2 or parsed.static_workers is not None:
        from run_configuration import from_args, validate_execution
        validate_execution(config,receipt)
        resolved=from_args(parsed,a.instrument()['sha256'])
        a.receipt_scope({**resolved,'instrument':{'sha256':resolved['instrument']},'runConfiguration':resolved},receipt,'deploy')


def materialize_tier_receipt(directory, config, argv):
    """Resolve the selected workload once for this new point or observation."""
    if config.get('tier') in ('smoke', 'discovery'):
        for option in ('--receipt', '--freeze'):
            if option not in argv:
                continue
            index = argv.index(option) + 1
            if argv[index] == GENERATED_RECEIPT:
                from run_configuration import resolve
                receipt = resolve(config)['diagnosticReceiptTemplate']
                receipt['status'] = 'AUTHORIZED_DIAGNOSTIC'
                path = directory / GENERATED_RECEIPT
                write(path, receipt)
                argv[index] = str(path)
            break


def prepare(config_file, directory, *, one_shot=False, candidate=None):
    config, selected = with_candidate(a.document(config_file), candidate)
    tier = config.get('tier')
    if tier is None:
        _, argv = validate_config(config)
        preflight_receipt(config, argv)
    root = Path(directory).resolve()
    require(not root.exists(), 'M7_RUNNER_OUTPUT_EXISTS')
    root.mkdir(mode=0o700, parents=True)
    write(root / 'config.json', config)
    if selected is not None:
        write(root / 'candidate.json', selected)
    entry_memory = point_results.available_memory()
    write(root / 'result.json', {'version': 1, 'memAvailableAtEntryBytes': entry_memory, 'status': 'PREPARING', 'phase': 'prepare', 'capacityAcceptance': 'NOT_GRANTED'})
    phase = 'configuration'
    try:
        if tier is not None:
            _, argv = validate_config(config)
            require(config['workSeconds'] is not None or one_shot, 'M7_RUNNER_TO_COMPLETION_REQUIRES_ONE_SHOT')
            parsed = a.parser().parse_args(['prepare', '--directory', str(root / 'fixture'), *argv])
            phase = 'source-input'
            clean_source_preflight(parsed)
            materialize_tier_receipt(root, config, argv)
            phase = 'receipt'
            preflight_receipt(config, argv)
        phase = 'prepare'
        arm_window(root, config)
        stage(root,'prepare',['prepare','--directory',str(root/'fixture'),*argv])
        phase = 'source-preflight'
        stage(root,'source-preflight',['source-preflight',str(root/'fixture')])
        write(root / 'result.json', {'version': 1, 'status': 'PREPARED', 'phase': 'prepare', 'runtimeStarted': False, 'configSha256': a.digest(root / 'config.json'), 'capacityAcceptance': 'NOT_GRANTED'})
    except BaseException as error:
        write(root / 'result.json', {'version': 1, 'status': 'FAILED', 'phase': phase,
                                     'code': code(error), 'runtimeStarted': False, 'memAvailableAtEntryBytes': entry_memory,
                                     'finishedAt': time.time(), 'capacityAcceptance': 'NOT_GRANTED'})
        if (root / 'execution.json').exists():
            try:
                cleanup(root, 'PREPARE_FAILURE')
            except BaseException as cleanup_error:
                write(root / 'cleanup-failure.json', {'code': code(cleanup_error)})
        point_results.publish_compose(root, a.document(root/'result.json'))
        auto_catalog(root, write)
        raise
    return root


@contextlib.contextmanager
def custody(root):
    with (root / 'cleanup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def stop_stage(file, owner):
    """Use the adapter's birth/group fence, then verify termination before cleanup."""
    job = a.document(file)
    # A prior TERM receipt is not proof that the same-birth process exited.
    a.stop_job(file, owner)
    proc = Path('/proc') / str(job['pid']) / 'stat'
    def alive():
        if not proc.exists():return False
        fields = proc.read_text().rsplit(')', 1)[1].split()
        return fields[19] == str(job['startTicks']) and fields[0] != 'Z'
    until = time.monotonic() + 10
    while alive() and time.monotonic() < until:time.sleep(.05)
    if alive():
        if job['group']:require(os.getpgid(job['pid']) == job['pid'], 'M7_HOST_JOB_GROUP_CHANGED')
        # Recheck the same birth immediately before escalation.
        require(alive(), 'M7_HOST_JOB_IDENTITY_CHANGED')
        if job['group']:os.killpg(job['pid'], signal.SIGKILL)
        else:os.kill(job['pid'], signal.SIGKILL)
        until = time.monotonic() + 2
        while alive() and time.monotonic() < until:time.sleep(.05)
    require(not alive(), 'M7_RUNNER_STAGE_STILL_LIVE')


def cleanup(root,reason):
    state=a.document(root/'execution.json') if (root/'execution.json').exists() else {}
    deadline = (time.time() + state['cleanupSeconds'] if state.get('mode') == TO_COMPLETION
                else state.get('cleanupAt'))
    with a.command_deadline(deadline):
        return _cleanup(root,reason)


def _cleanup(root, reason):
    with custody(root):
        if (root / 'cleanup.json').exists():
            return a.document(root / 'cleanup.json')
        job = root / 'stage-job.json'
        if job.exists():
            value = a.document(job)
            if not value.get('completed'):
                stop_stage(job, value['owner'])
        state=a.document(root/'execution.json') if (root/'execution.json').exists() else {}
        if (root/'session.json').exists():stop_session_collectors(root)
        fixture = root / 'fixture'
        if (fixture / 'owner.json').exists():
            d, m = a.load(fixture,resource_limits=False)
            with a.private_commands(root / 'cleanup-commands'):
                a.down(d, m)
        result = {'status': 'ABSENT', 'reason': reason, 'at': time.time()}
        write(root / 'cleanup.json', result)
        return result


def controller_identity(pid):
    fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'startTicks': int(fields[19])}, fields[0]


def controller_alive(expected):
    try:
        actual, state = controller_identity(expected['pid'])
    except (FileNotFoundError, ProcessLookupError):
        return False
    return actual == expected and state not in ('Z', 'X')


def work_active(state):
    if state.get('mode') == TO_COMPLETION:
        return controller_alive(state['controller'])
    return time.time() < state.get('stopWorkAt', state['cleanupAt'])


def guard(root):
    state = a.document(root / 'execution.json')
    live_owner = state.get('mode') == TO_COMPLETION
    write(root / 'guard-ready.json', {'pid': os.getpid(), 'owner': state['owner'], 'cleanupAt': state['cleanupAt']})
    while work_active(state) and not (root / 'cleanup.json').exists():
        time.sleep(.2)
    if not (root / 'cleanup.json').exists():
        cleanup(root, 'CONTROLLER_EXITED' if live_owner else 'FINITE_DEADLINE')
        if live_owner:
            result = a.document(root / 'result.json')
            if result['status'] in ('PREPARING', 'PREPARED'):
                phase = a.document(root/'phase.json')['phase'] if (root/'phase.json').is_file() else 'guard'
                write(root/'result.json', {'version': 1, 'status': 'ABORTED', 'phase': phase,
                      'failure': {'code': 'M7_RUNNER_CONTROLLER_EXITED'}, 'finishedAt': time.time(),
                      'partial': partial(root), 'capacityAcceptance': 'NOT_GRANTED'})
                auto_catalog(root, write)
    write(root / 'guard-result.json', {'status': 'RETURNED', 'at': time.time()})


def partial(root):
    """References remain private; missing instruments are never invented zeros."""
    d = root / 'fixture'
    artifacts = {}
    for name in ('summary.json', 'runtime-readiness.json', 'deployment.json', 'deployment-stages.json', 'startup-primer-boundary.json', 'role-logs/manifest.json', 'load/probe.json', 'load/k6-summary.json'):
        file = d / name
        if file.is_file():
            artifacts[name] = {'sha256': a.digest(file), 'path': str(file)}
    unreadable = []
    def retained(name):
        file = d / name
        if not file.is_file():return {}
        try:
            value = a.document(file)
            if not isinstance(value, dict):raise ValueError('not an object')
            return value
        except (OSError, ValueError):
            unreadable.append(name)
            return {}
    phase = 'NOT_STARTED'
    summary = retained('load/k6-summary.json')
    metrics = summary.get('metrics') or {}
    if not isinstance(metrics, dict):metrics = {}
    attempts = metrics.get('scenario_request_attempts') or {}
    if not isinstance(attempts, dict):attempts = {}
    count = attempts.get('count', attempts.get('values', {}).get('count'))
    if metrics:
        phase = 'SCENARIO' if isinstance(count, (int, float)) and count > 0 else 'SETUP_ONLY' if count == 0 else 'UNMEASURED'
    events = []
    log = d / 'load/k6.log'
    if log.is_file():
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 65536))
            recent = stream.read(65536).decode(errors='replace')
        for line in recent.splitlines():
            match = re.search(r'msg="((?:[^"\\]|\\.)*)"', line)
            if not match:continue
            try:
                event = json.loads(json.loads('"' + match.group(1) + '"'))
                if event.get('event') in ('jwt-setup-start', 'jwt-setup-end', 'scenario-first-iteration', 'scenario-phase-end'):
                    events.append({k: event[k] for k in ('event', 'atMs', 'tenants', 'concurrency') if k in event})
            except (ValueError, TypeError):pass
    names = {event['event'] for event in events}
    if 'scenario-first-iteration' in names:phase = 'SCENARIO'
    elif 'jwt-setup-start' in names and 'jwt-setup-end' not in names:phase = 'JWT_SETUP_INCOMPLETE'
    native = retained('summary.json')
    probe = retained('load/probe.json')
    # Older partial runs may predate the final file-only reduction.
    observations = native.copy()
    if native.get('kind') == 'm7-joined-discovery-cell' and 'measurements' not in native and (d/'load').is_dir():
        import discovery
        for key, value in discovery.retained_results(a, d, retained('owner.json') or native, native).items():
            observations.setdefault(key, value)
    import outcome_gate
    gate = retained('load/outcome-gate.json')
    counts = native.get('oracleFindings') or native.get('oracle') or retained('load/oracle-findings.json')
    catchup = gate.get('components', {}).get('catchup') or {'verdict':'UNMEASURED'}
    measured = observations.get('measurements') or {}
    window = (measured.get('windows') or {}).get('load') or {}
    http = native.get('httpAccounting') or retained('load/http-accounting.json')
    if not http and metrics:
        import http_accounting
        try:
            http = http_accounting.assess(metrics)
        except (ValueError, TypeError, AttributeError):
            unreadable.append('load/k6-summary.json')
    clinical = outcome_gate.sampled_oracle(probe.get('completedOutput') or retained('load/clinical-witnesses-partial.json') or observations.get('completedOutput'))
    details = {'http': http or {'verdict':'UNMEASURED'}, 'rateOffer': native.get('rateOffer'),
               'storedWrites': outcome_gate.storage(counts), 'selectedClinical': clinical,
               'evaluatorProgress': observations.get('evaluatorProgress', {}).get('load') or
                                    native.get('strictChecks', {}).get('load', {'verdict':'UNMEASURED'}),
               'frames': observations.get('viewerFrames') or {'verdict':'UNMEASURED'}, 'catchup': catchup,
               'outcomeGate': gate.get('verdict', 'UNMEASURED'),
               'components': window or {'verdict':'UNMEASURED'}}
    if probe.get('viewerSetup'):
        details['viewerSetup'] = probe['viewerSetup']
    if probe.get('window'):
        details['frameCounts'] = {key: probe['window'].get(key) for key in ('expectedFrames', 'deliveredFrames')}
    if native.get('clinicalVerdict'):
        details['clinicalVerdict'] = native['clinicalVerdict']
    if counts.get('rows'):
        for key in ('accepted', 'stored', 'uncertain', 'probeStored'):
            values = [row.get(key) for row in counts['rows'] if isinstance(row, dict)]
            if len(values) == len(counts['rows']) and all(type(value) is int and value >= 0 for value in values):
                details['storedWrites'][key] = sum(values)
    return {'observations': details, 'artifacts': artifacts, 'trafficPhase': phase, 'scenarioAttempts': count,
            'workloadEvents': events, 'adapterStatus': native.get('status', 'UNMEASURED'),
            'processes': native.get('processes', {}), 'strictChecks': native.get('strictChecks', {}),
            'durableOutputObservation': probe.get('durableOutputObservation', {'status':'UNMEASURED'}),
            'unreadableArtifacts': unreadable, 'optionalMetrics': 'UNMEASURED unless present in retained artifacts'}


def optional_preflight(root, directory):
    """Optional cost counters qualify their own measurements, not discovery admission."""
    captures = list(directory.glob('setup-attempts/*/readability-realtime-costs.json'))
    value = {'status': 'NO-INSTRUMENT', 'reason': 'M7_REALTIME_COST_BOOKEND_UNAVAILABLE'}
    if captures:
        latest = max(captures, key=lambda p: p.stat().st_mtime)
        try:
            observed = a.document(latest)
            value = {'status': observed.get('status', 'NO-INSTRUMENT'),
                     'artifact': str(latest), 'sha256': a.digest(latest)}
        except (OSError, ValueError, AttributeError):
            value = {'status': 'NO-INSTRUMENT', 'reason': 'M7_REALTIME_COST_UNREADABLE'}
    result = {'realtimeCosts': value, 'scope': 'discovery observation only; no acceptance granted'}
    write(root / 'preflight-observations.json', result)
    return result


def launch_stage(root, output, args, state):
    command = [sys.executable, '-B', str(HERE / 'adapter.py'), *args]
    if state.get('mode') != TO_COMPLETION:
        child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        a.job_record(root / 'stage-job.json', child, state['owner'], group=True)
        return child
    # Hold the child before exec until its birth and process-group ownership
    # are journaled. Owner death before the handoff closes the write end.
    read_fd, write_fd = os.pipe()
    gate = '''
import os
import sys

with os.fdopen(int(sys.argv[1]), 'rb') as start:
    if start.read(1) != b'1':
        sys.exit(1)
os.execv(sys.argv[2], sys.argv[2:])
'''
    try:
        child = subprocess.Popen([sys.executable, '-B', '-c', gate, str(read_fd), *command],
                                 stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
                                 pass_fds=(read_fd,))
        identity, _ = controller_identity(child.pid)
        write(root / 'stage-job.json', {**identity, 'startTicks': str(identity['startTicks']),
              'owner': state['owner'], 'group': True, 'completed': False})
        os.write(write_fd, b'1')
        return child
    finally:
        os.close(read_fd)
        os.close(write_fd)


def stage(root, name, args):
    state = a.document(root / 'execution.json')
    with custody(root):
        require(work_active(state) and not (root / 'cleanup.json').exists(), 'M7_RUNNER_WORK_DEADLINE')
        write(root / 'phase.json', {'phase': name, 'startedAt': time.time()})
        with (root / (name + '.private.log')).open('xb') as output:
            child_args = [*args]
            deadline = state['stopWorkAt']
            if deadline is not None and child_args[:1] in (['deploy'],['preflight'],['run']):
                child_args += ['--work-deadline', str(deadline)]
            child = launch_stage(root, output, child_args, state)
    try:
        rc = child.wait(timeout=None if deadline is None else max(.1, deadline - time.time()))
        write(root / 'stage-job.json', {**a.document(root / 'stage-job.json'), 'completed': True, 'returncode': rc})
        write(root / (name + '-result.json'), {'phase': name, 'returncode': rc, 'endedAt': time.time()})
        require(rc == 0, 'M7_RUNNER_' + re.sub('[^A-Z0-9_]', '_', name.upper()) + '_FAILED')
    finally:
        if child.poll() is None:
            stop_stage(root / 'stage-job.json', state['owner'])
            child.wait(timeout=12)


def generated_control(root, d, m):
    """Execute the generated program with a deliberately absent required input.

    This is a real Node execution, before I/O; the normal run then exercises
    the same bytes with the canonical caller/environment.
    """
    argv=[m['generator']['tools']['node']['path'],str(d/'probe.js')]
    with (root/'generated-control.private.log').open('xb') as output:
        result=subprocess.run(argv,env=a.runtime_env({'M7_GENERATOR_ROOT':str(d/'dependencies')}),stdout=output,stderr=subprocess.STDOUT,timeout=10)
    text = (root / 'generated-control.private.log').read_text()
    require(result.returncode != 0 and 'ERR_INVALID_URL' in text, 'M7_RUNNER_GENERATED_CONTROL_VACUOUS')
    write(root / 'generated-control.json', {'status': 'EXPECTED_FAILURE', 'returncode': result.returncode,
        'symptom': 'ERR_INVALID_URL', 'probeSha256': a.digest(d / 'probe.js'),
        'break': 'required --base absent; generated bytes unchanged; failure occurs before network I/O'})


def guard_alive(root):
    job=a.document(root/'guard-job.json')
    stat=Path('/proc')/str(job['pid'])/'stat'
    if not stat.exists():return False
    fields=stat.read_text().rsplit(')',1)[1].split()
    require(fields[19]==str(job['startTicks']),'M7_RUNNER_GUARD_BIRTH_CHANGED')
    return fields[0]!='Z'


def arm_window(root,config):
    require(not (root/'execution.json').exists(),'M7_RUNNER_WINDOW_EXISTS')
    start=time.time()
    work = config['workSeconds']
    cleanup_seconds = config['cleanupSeconds']
    initial = point_results.read(root/'result.json')
    entry_memory = initial['memAvailableAtEntryBytes'] if 'memAvailableAtEntryBytes' in initial else point_results.available_memory()
    state = {'owner': uuid.uuid4().hex, 'startedAt': start, 'startedMonoNs': time.monotonic_ns(),
             'memAvailableAtEntryBytes': entry_memory,
             'stopWorkAt': start + work if work is not None else None,
             'cleanupAt': start + work + cleanup_seconds if work is not None else None,
             'configSha256': a.digest(root/'config.json'), 'includesPreparation': True}
    if work is None:
        state.update(mode=TO_COMPLETION, controller=controller_identity(os.getpid())[0],
                     cleanupSeconds=cleanup_seconds)
    write(root/'execution.json',state)
    with (root/'guard.private.log').open('xb') as output:
        guardian=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'_guard',str(root)],stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    a.job_record(root/'guard-job.json',guardian,state['owner'],group=True)
    deadline=time.monotonic()+5
    while not (root/'guard-ready.json').exists() and guardian.poll() is None and time.monotonic()<deadline:time.sleep(.05)
    require((root/'guard-ready.json').exists() and guardian.poll() is None,'M7_RUNNER_GUARD_NOT_READY')
    return state


def execution_window(root,config):
    state=a.document(root/'execution.json')
    require(state.get('includesPreparation') is True and state['configSha256']==a.digest(root/'config.json'), 'M7_RUNNER_WINDOW_CHANGED')
    work = config['workSeconds']
    if work is None:
        require(state.get('mode') == TO_COMPLETION and state.get('stopWorkAt') is None
                and state.get('cleanupAt') is None and state.get('cleanupSeconds') == config['cleanupSeconds']
                and state.get('controller') == controller_identity(os.getpid())[0],
                'M7_RUNNER_TO_COMPLETION_CONTROLLER_CHANGED')
    else:
        require(state['stopWorkAt'] == state['startedAt'] + work
                and state['cleanupAt'] == state['stopWorkAt'] + config['cleanupSeconds'],
                'M7_RUNNER_WINDOW_CHANGED')
    require(work_active(state) and not (root/'cleanup.json').exists(),'M7_RUNNER_WORK_DEADLINE')
    require(guard_alive(root) and a.document(root/'guard-ready.json')['owner']==state['owner'],'M7_RUNNER_GUARD_NOT_READY')
    return state


def execute(directory, rehearsal=False):
    root = Path(directory).resolve()
    config, _ = load_config(root / 'config.json')
    require(a.document(root / 'result.json')['status'] == 'PREPARED' and not (root / 'deploy-result.json').exists(), 'M7_RUNNER_ALREADY_EXECUTED')
    d, m = a.load(root / 'fixture',resource_limits=False)
    state=execution_window(root,config)
    failure = None
    try:
        if rehearsal:
            generated_control(root, d, m)
        stage(root, 'deploy', ['deploy', str(d)])
        stage(root, 'preflight', ['preflight', str(d), '--k6-image', config['k6Image']])
        # Essential source/runtime/instrument checks stay in adapter preflight.
        optional_preflight(root, d)
        stage(root, 'run', ['run', str(d), '--k6-image', config['k6Image']])
        if config.get('tier') == 'smoke':
            from tier_smoke import assess
            assess(root, config.get('smokeBaseline'))
    except BaseException as error:
        failure = {'code': code(error), 'errorType': type(error).__name__}
    finally:
        phase = a.document(root / 'phase.json')['phase'] if (root / 'phase.json').exists() else 'guard'
        try:
            cleanup(root, 'POINT_FINISHED' if failure is None else 'PHASE_FAILURE')
        except BaseException as error:
            write(root / 'cleanup-failure.json', {'code': code(error), 'errorType': type(error).__name__})
            failure = {**(failure or {}), 'cleanupCode': code(error)}
        until=time.monotonic()+10
        while guard_alive(root) and time.monotonic()<until:time.sleep(.05)
        if guard_alive(root):failure={**(failure or {}),'guardCode':'M7_RUNNER_GUARD_PENDING'}
        result = {'version': 1, 'status': ('COMPLETED' if partial(root)['adapterStatus'] == 'MEASURED' else 'COMPLETED_PARTIAL') if failure is None else 'FAILED_PARTIAL', 'phase': phase, 'failure': failure, 'partial': partial(root), 'cleanup': a.document(root / 'cleanup.json') if (root / 'cleanup.json').exists() else {'status': 'UNMEASURED'}, 'capacityAcceptance': 'NOT_GRANTED', 'finishedAt': time.time()}
        if 'startedMonoNs' in state:
            result['elapsedSeconds'] = (time.monotonic_ns() - state['startedMonoNs']) / 1e9
        point_results.publish_compose(root, result)
        auto_catalog(root, write)
    require(failure is None, 'M7_RUNNER_POINT_INCOMPLETE')
    return result




# Reuse is opt-in and starts its own finite window; an entered point is never adopted.
SESSION_VARIABLE_OPTIONS = frozenset(('freeze', 'receipt', 'warmup-seconds', 'idle-seconds',
    'load-seconds', 'offered-rps', 'hot-factor', 'probe-every-ms', 'sockets-per-tenant',
    'logical-polling-clients', 'viewer-setup', 'workload-mix', 'workload-scale', 'sampler-interval', 'quiet-load', 'jwt-setup-concurrency',
    'evaluator-catchup', 'evaluator-opportunities', 'opportunity-observation', 'restart-during-load-after-seconds', 'driver-shards', 'driver-headroom', 'driver-plan'))
SESSION_PREPARE_ONLY = frozenset(('fixture-project', 'fixture-snapshot', 'backend-subnet', 'edge-subnet', 'commissioning-slot-wal-mib', 'tenant-readiness',
    'generator-dependencies', 'generator-dependency-receipt',
    'generator-dependency-receipt-sha256', 'generator-dependency-preparation',
    'generator-dependency-preparation-sha256', 'generator-dependency-preparation-head'))


def session_start(config_file, directory):
    root = prepare(config_file, directory)
    config = a.document(root/'config.json')
    try:
        stage(root, 'deploy', ['deploy', str(root/'fixture')])
        d, m = a.load(root/'fixture', resource_limits=False)
        require(not m.get('attached'), 'M7_SESSION_ORIGINAL_OWNER_REQUIRED')
        (root/'observations').mkdir(mode=0o700)
        state = a.document(root/'execution.json')
        value = {'version':1, 'owner':state['owner'], 'startedAt':state['startedAt'],
            'stopWorkAt':state['stopWorkAt'], 'cleanupAt':state['cleanupAt'],
            'runtimeOwnerSha256':a.digest(d/'owner.json'), 'runtimeOwner':m['owner'],
            'cleanupRunner':str(Path(__file__).resolve())}
        with custody(root):
            execution_window(root,config)
            write(root/'session.json', value)
        write(root/'result.json', {'version':1, 'status':'SESSION_OPEN', 'capacityAcceptance':'NOT_GRANTED'})
        return value
    except BaseException:
        cleanup(root, 'SESSION_START_FAILURE')
        raise


def session_access(root, owner):
    session = a.document(root/'session.json')
    require(session['owner'] == owner, 'M7_SESSION_OWNER_REQUIRED')
    # The original config/helper is immutable, but a later collector may have its own pin.
    state = execution_window(root, a.document(root/'config.json'))
    require(all(state[k] == session[k] for k in ('owner','startedAt','stopWorkAt','cleanupAt')),
            'M7_SESSION_WINDOW_CHANGED')
    d = root/'fixture'
    require(a.digest(d/'owner.json') == session['runtimeOwnerSha256'], 'M7_SESSION_RUNTIME_CHANGED')
    m = a.document(d/'owner.json')
    require(not m.get('attached') and m['owner'] == session['runtimeOwner'], 'M7_SESSION_RUNTIME_CHANGED')
    return session, d, m


@contextlib.contextmanager
def session_observation_lock(root):
    # Serial observations share one fixture and the original guard-visible stage record.
    with (root/'observation.lock').open('a') as lock:
        try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('M7_SESSION_OBSERVATION_ACTIVE')
        yield


def session_observe(directory, owner, name, config_file, history_file=None):
    root = Path(directory).resolve()
    require(re.fullmatch(r'[a-z][a-z0-9-]{0,47}', name) is not None, 'M7_SESSION_OBSERVATION_NAME')
    with session_observation_lock(root):
        session, d, m = session_access(root, owner)
        config, prepared_argv = load_config(config_file)
        original = a.document(root/'config.json')
        require(config['k6Image'] == original['k6Image'], 'M7_SESSION_RUNTIME_CONFIG_CHANGED')
        stable = lambda options:{k:v for k,v in options.items() if k not in SESSION_VARIABLE_OPTIONS}
        require(stable(config['prepare']) == stable(original['prepare']), 'M7_SESSION_RUNTIME_CONFIG_CHANGED')
        ob = root/'observations'/name
        require(not ob.exists(), 'M7_SESSION_OBSERVATION_EXISTS')
        ob.mkdir(mode=0o700)
        entry_memory = point_results.available_memory()
        write(ob/'config.json',config)
        reuse = {'runtime': 'REUSED'}
        if history_file is not None:
            reuse['declared'] = a.document(history_file)
        write(ob/'history.json', reuse)
        failure = None
        try:
            with a.command_deadline(session['stopWorkAt']):
                a.verify(d,m);a.image(m)
                write(ob/'runtime-before.json',a.resources(m))
            materialize_tier_receipt(ob, config, prepared_argv)
            argv = ['attach','--directory',str(ob/'fixture')]
            # Reuse the validated tier defaults and JSON serialization for the
            # attached observer just as for a newly prepared fixture.
            for flag, value in zip(prepared_argv[::2], prepared_argv[1::2]):
                if flag[2:] not in SESSION_PREPARE_ONLY:
                    argv.extend([flag, value])
            for key,value in {'project':m['project'],'source-root':d/'core','state':d/'state',
                    'dependencies-root':d/'dependencies','env-file':d/'env',
                    'compose':d/'frozen.compose.json','runtime-owner':d/'owner.json'}.items():
                argv.extend(['--'+key,str(value)])
            stage(root,name+'-attach',argv)
            stage(root,name+'-preflight',['preflight',str(ob/'fixture'),'--k6-image',config['k6Image']])
            optional_preflight(ob,ob/'fixture')
            stage(root,name+'-run',['run',str(ob/'fixture'),'--k6-image',config['k6Image']])
        except BaseException as error:
            failure = {'code':code(error),'errorType':type(error).__name__}
        finally:
            try:
                with custody(root), a.command_deadline(session['stopWorkAt']):
                    stop_session_collectors(root, only=ob)
            except BaseException as error:
                failure = {**(failure or {}),'collectorCleanupCode':code(error)}
            result = {'version':1,'status':'FAILED_PARTIAL' if failure else
                    ('OBSERVED' if partial(ob)['adapterStatus']=='MEASURED' else 'OBSERVED_PARTIAL'),
                'failure':failure,'partial':partial(ob),'finishedAt':time.time(),
                'cleanupOwner':session['owner'],'stopWorkAt':session['stopWorkAt'],
                'capacityAcceptance':'NOT_GRANTED','runtime':'REUSED',
                'writeEffects':'UNCERTAIN after failure; inspect originals before another scenario' if failure else 'Retained; never reset'}
            result['memAvailableAtEntryBytes'] = entry_memory
            point_results.publish_compose(ob, result, cleanup={'status':'DEFERRED_TO_SESSION_CLOSE'})
            auto_catalog(ob, write)
            if failure and failure.get('errorType') in ('KeyboardInterrupt','SystemExit'):
                session_close(root,session['owner'])
        require(failure is None,'M7_SESSION_OBSERVATION_INCOMPLETE')
        return result


def stop_session_collectors(root, only=None):
    # A collector owns its jobs and oneoffs, never the fixture. This also runs
    # from the ORIGINAL guard after killing the active adapter process group.
    for ob in ([only] if only else sorted((root/'observations').glob('*'))):
        d = ob/'fixture'
        if not (d/'owner.json').is_file():continue
        m = a.document(d/'owner.json')
        require(m.get('attached') is True and m.get('project') == a.document(root/'fixture/owner.json')['project'],
                'M7_SESSION_COLLECTOR_OWNER_CHANGED')
        for file in list(d.glob('*/sampler-job.json'))+list(d.glob('*/probe-job.json'))+list(d.glob('*/diagnostic-job.json')):
            stop_stage(file,m['owner'])
        for row in a.resources(m):
            if row['Config']['Labels'].get(a.OWNER) == m['owner']:
                a.owned(row,m['owner'])
                a.command(['docker','rm','--force','--volumes',row['Id']])


def session_close(directory, owner):
    root = Path(directory).resolve()
    require(a.document(root/'session.json')['owner'] == owner, 'M7_SESSION_OWNER_REQUIRED')
    # Always call the original immutable runner for original-instrument cleanup.
    original = a.document(root/'session.json')['cleanupRunner']
    return subprocess.run([sys.executable,'-B',original,'down',str(root)],check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('identity')
    project=sub.add_parser('project');project.add_argument('config');project.add_argument('--source-acceptance')
    candidate_help = 'Candidate image reference (default $M7_CANDIDATE_IMAGE); sets image, image-id and the labelled core/deploy commits'
    project.add_argument('--candidate', help=candidate_help)
    for mode in ('prepare', 'run'):
        prep = sub.add_parser(mode)
        prep.add_argument('config')
        prep.add_argument('directory')
        prep.add_argument('--candidate', help=candidate_help)
        if mode == 'run':
            prep.add_argument('--standard-case', action='store_true',
                              help='Create a fresh case with result.json, cleanup.json and raw/')
    plan = sub.add_parser('plan')
    plan.add_argument('config')
    plan.add_argument('--candidate', help=candidate_help)
    for name in ('execute', 'rehearse', 'result', 'down', '_guard'):
        sub.add_parser(name).add_argument('directory')
    start = sub.add_parser('session-start');start.add_argument('config');start.add_argument('directory')
    observe = sub.add_parser('session-observe');observe.add_argument('directory');observe.add_argument('--owner',required=True)
    observe.add_argument('--name',required=True);observe.add_argument('--config',required=True);observe.add_argument('--history', help='Optional legacy observation metadata')
    close = sub.add_parser('session-close');close.add_argument('directory');close.add_argument('--owner',required=True)
    args = parser.parse_args()
    if args.action in ('prepare', 'execute', 'rehearse', 'run', 'session-start', 'session-observe'):
        def interrupted(signum, frame):raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM,interrupted)
    if args.action == 'session-start':return print(json.dumps(session_start(args.config,args.directory),indent=2))
    if args.action == 'session-observe':return session_observe(args.directory,args.owner,args.name,args.config,args.history)
    if args.action == 'session-close':return session_close(args.directory,args.owner)
    if args.action == 'project':
        import run_configuration as rc
        config,_=with_candidate(a.document(args.config),args.candidate)
        acceptance=a.document(args.source_acceptance) if args.source_acceptance else None
        value=rc.resolve(config,acceptance)
        return print(json.dumps(value,indent=2))
    if args.action == 'identity':
        identity = a.instrument()
        return print(json.dumps({'helperHead': identity['commit'], 'helperInstrument': identity['sha256']}, indent=2))
    if args.action == 'plan':
        return print(json.dumps(tier_plan(with_candidate(a.document(args.config), args.candidate)[0]), indent=2))
    if args.action in ('prepare', 'run'):
        directory = Path(args.directory).resolve()
        if not getattr(args, 'standard_case', False):
            root = prepare(args.config, directory, one_shot=args.action == 'run', candidate=args.candidate)
            return execute(root) if args.action == 'run' else root
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        raw = directory / 'raw'
        try:
            return execute(prepare(args.config, raw, one_shot=True, candidate=args.candidate))
        except BaseException as error:
            if not raw.exists():
                raw.mkdir(mode=0o700)
            result = point_results.read(raw/'result.json')
            if not result or result.get('status') in ('PREPARING', 'PREPARED'):
                write(raw/'result.json', {**result, 'version': 1, 'status': 'FAILED_PARTIAL',
                      'code': code(error), 'capacityAcceptance': 'NOT_GRANTED'})
            raise
        finally:
            result = point_results.read(raw/'result.json')
            result = point_results.publish_compose(raw, result)
            write(directory/'result.json', {**result, 'rawDirectory': 'raw'})
            write(directory/'cleanup.json', result['cleanup'])
    root = Path(args.directory).resolve()
    if args.action in ('execute', 'rehearse'):return execute(root, args.action == 'rehearse')
    if args.action == '_guard':return guard(root)
    if args.action == 'down':return cleanup(root, 'EXPLICIT_CLEANUP')
    print(json.dumps({**a.document(root / 'result.json'), 'partial': partial(root)}, indent=2))


if __name__ == '__main__':
    os.umask(0o077)
    try:main()
    except Exception as error:
        print(code(error), file=sys.stderr)
        sys.exit(1)
