"""Opt-in finite diagnostic quotas. No subprocesses, discovery or persistence here.

The caller supplies the existing owned container census before actor effects and
keeps its existing identity, deadline, cleanup and source checks. Heap quotas are
V8 heap limits; host RSS/native memory is NOT bounded by this profile.
"""
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
import fcntl
import os
import copy
import json
from pathlib import Path
import re
import shutil
import threading
from types import MappingProxyType

NAME = 'local-diagnostic-4cpu-8g-v1'
EXTERNAL_NAME = 'local-diagnostic-external-pgstream-4cpu-8g-v1'
EVALUATOR250_NAME = 'local-diagnostic-external-pgstream-evaluator250-4cpu-8g-v1'
EVALUATOR250_MEMORY512_NAME = 'local-diagnostic-external-pgstream-evaluator250-memory512-4cpu-8448m-v1'
QUALIFICATION_NAME = 'local-qualification-external-pgstream-6cpu-10g-v1'
EXTERNAL_PROFILES = (EXTERNAL_NAME, EVALUATOR250_NAME, EVALUATOR250_MEMORY512_NAME, QUALIFICATION_NAME)
PROFILES = (NAME, *EXTERNAL_PROFILES)
PROFILE_KEY = 'x-nightscout-diagnostic-profile'
MIB = 1024 * 1024
MAX_CPU = 4000  # millicpus; integral accounting avoids float undercounts
MAX_MEMORY = 8192 * MIB
MAX_HEAP = 1024


def need(condition, code):
    if not condition:
        raise RuntimeError('M7_DIAGNOSTIC_RESOURCE_' + code)


@dataclass(frozen=True)
class Limit:
    cpu: int
    memory: int

    def __post_init__(self):
        need(type(self.cpu) is int and 1 <= self.cpu <= MAX_CPU, 'CPU_INVALID')
        need(type(self.memory) is int and MIB <= self.memory <= MAX_MEMORY, 'MEMORY_INVALID')

    @property
    def cpus(self):
        return format(Decimal(self.cpu) / 1000, 'f')


# Immutable per-role source maxima, not an application capacity recommendation.
LIMITS = MappingProxyType({
    role: Limit(cpu, mib * MIB) for role, cpu, mib in (
        ('postgres', 500, 1536), ('vault', 125, 256),
        ('bootstrap', 125, 256), ('admin', 125, 256),
        ('primer', 250, 512), ('api', 500, 1024),
        ('realtime', 500, 1024), ('evaluator', 250, 512),
        ('tenant-admin', 125, 256), ('ui', 125, 256),
        ('nginx', 125, 128), ('placement-operator', 125, 128),
        ('demo', 125, 256), ('feed-reader', 125, 256),
        ('k6', 500, 1024))})
HOST = MappingProxyType({'probe': (512, 1), 'generator': (256, 1), 'helper': (128, 2)})


def selection(name=None):
    need(name in (None, *PROFILES), 'SELECTION_INVALID')
    return name


def memory_ceiling(profile):
    selection(profile)
    if profile == QUALIFICATION_NAME: return 10240 * MIB
    return 8448 * MIB if profile == EVALUATOR250_MEMORY512_NAME else MAX_MEMORY


def cpu_ceiling(profile):
    selection(profile)
    return 6000 if profile == QUALIFICATION_NAME else MAX_CPU


def role_limit(role, profile=NAME):
    selection(profile)
    if profile == QUALIFICATION_NAME:
        selected = {'postgres': Limit(1000, 1536*MIB),
                    'vault': Limit(250, 512*MIB),
                    'evaluator': Limit(1000, 1024*MIB),
                    'pgstream': Limit(250, 256*MIB)}
        if role in selected: return selected[role]
    if profile in EXTERNAL_PROFILES and role in ('evaluator','pgstream'):
        return Limit(250 if profile in (EVALUATOR250_NAME,EVALUATOR250_MEMORY512_NAME) and role=='evaluator' else 125,
                     (512 if profile==EVALUATOR250_MEMORY512_NAME and role=='evaluator' else 256)*MIB)
    if role in LIMITS:
        return LIMITS[role]
    for kind in ('api', 'realtime', 'evaluator'):
        if re.fullmatch(kind + r'-(?:[2-9]|1[0-6])', role):
            return LIMITS[kind]
    need(False, 'UNKNOWN_ROLE')


def verify_evaluator_cgroup(profile, cpu_max, memory_max, memory_swap_max):
    """Validate captured cgroup-v2 values; caller owns identity and capture I/O."""
    limit=role_limit('evaluator',profile)
    need(isinstance(cpu_max,str) and re.fullmatch(r'[1-9][0-9]* [1-9][0-9]*\n?',cpu_max) is not None,'EFFECTIVE_CPU_INVALID')
    quota,period=map(int,cpu_max.split())
    need(quota*1000==limit.cpu*period,'EFFECTIVE_CPU_CHANGED')
    need(str(memory_max).strip()==str(limit.memory),'EFFECTIVE_MEMORY_CHANGED')
    need(str(memory_swap_max).strip()=='0','EFFECTIVE_SWAP_CHANGED')
    return {'millicpus':limit.cpu,'memoryBytes':limit.memory,'swapBytes':0}


@dataclass(frozen=True)
class Plan:
    # (service, limit, concurrent count). Every selected role is reserved even
    # when idle, ops-only or used only during preparation. No stage subtraction.
    services: tuple
    profile: str = NAME

    def __post_init__(self):
        need(self.profile in PROFILES,'PROFILE_CHANGED')
        need(type(self.services) is tuple and bool(self.services), 'SERVICES_REQUIRED')
        need(len({r for r, _, _ in self.services}) == len(self.services), 'DUPLICATE_ROLE')
        for role, limit, count in self.services:
            need(isinstance(role, str) and role_limit(role,self.profile) == limit, 'LIMIT_CHANGED')
            need(type(count) is int and count == (2 if role in ('bootstrap', 'primer') else 1), 'MULTIPLICITY_CHANGED')
        cpu = sum(limit.cpu * count for _, limit, count in self.services) + LIMITS['k6'].cpu
        memory = sum(limit.memory * count for _, limit, count in self.services) + LIMITS['k6'].memory
        need(cpu <= cpu_ceiling(self.profile) and memory <= memory_ceiling(self.profile), 'AGGREGATE_EXCEEDED')
        need(sum(heap * count for heap, count in HOST.values()) <= MAX_HEAP, 'HOST_AGGREGATE_EXCEEDED')

    def record(self):
        return {'version': 1, 'profile': self.profile,
                'services': {r: {'millicpus': l.cpu, 'memoryBytes': l.memory, 'maximumConcurrent': n} for r, l, n in self.services},
                'standalone': {'k6': {'millicpus': LIMITS['k6'].cpu, 'memoryBytes': LIMITS['k6'].memory, 'maximumConcurrent': 1}},
                'host': {r: {'heapMiB': h, 'maximumConcurrent': n} for r, (h, n) in HOST.items()},
                'aggregate': {'millicpus': sum(l.cpu*n for _, l, n in self.services)+LIMITS['k6'].cpu,
                              'memoryBytes': sum(l.memory*n for _, l, n in self.services)+LIMITS['k6'].memory,
                              'heapMiB': sum(h*n for h, n in HOST.values())},
                'basis': 'ALL_SELECTED_SERVICES_PLUS_DECLARED_OVERLAPS_PLUS_STANDALONE_K6',
                'hostRss': 'SEPARATELY_OBSERVED_NOT_HEAP_BOUNDED'}


def plan(config):
    services = config.get('services', {})
    need(isinstance(services, dict) and bool(services), 'SERVICES_REQUIRED')
    need('k6' not in services, 'K6_COMPOSE_STANDALONE_AMBIGUOUS')
    profile=config.get(PROFILE_KEY,NAME);need(profile in PROFILES,'PROFILE_CHANGED')
    need(profile not in EXTERNAL_PROFILES or 'pgstream' in services and 'evaluator' in services,'EXTERNAL_ROSTER_REQUIRED')
    return Plan(tuple((r, role_limit(r,profile), 2 if r in ('bootstrap', 'primer') else 1) for r in sorted(services)),profile)


def overlay(config, selected):
    """Return a full JSON Compose document; never mutate source/default config."""
    if selected is None:
        return config
    selection(selected)
    result = copy.deepcopy(config)
    if selected in EXTERNAL_PROFILES:result[PROFILE_KEY]=selected
    need(result.get(PROFILE_KEY,NAME)==selected,'PROFILE_CHANGED')
    budget = plan(result)
    for role, limit, _ in budget.services:
        spec = result['services'][role]
        # Conflicting alternate resource knobs can change native enforcement.
        need(not any(k in spec for k in ('cpu_quota', 'cpu_period', 'cpu_count', 'cpu_percent', 'mem_reservation')),
             'ALTERNATE_LIMITS')
        need(not spec.get('deploy', {}).get('resources'), 'ALTERNATE_LIMITS')
        for key, value in (('cpus', float(limit.cpus)), ('mem_limit', limit.memory), ('memswap_limit', limit.memory)):
            need(key not in spec or str(spec[key]) == str(value), 'EXISTING_LIMIT_CONFLICT')
            spec[key] = value
    return result


def verify_config(config, budget):
    need(plan(config) == budget, 'PLAN_CHANGED')
    need(overlay(config, budget.profile) == config, 'CONFIG_LIMITS_CHANGED')


def standalone(argv, budget):
    """Apply native limits before the image, retaining all custody/image argv."""
    argv = list(argv)
    need(argv[:2] == ['docker', 'run'] and budget is not None, 'STANDALONE_SHAPE')
    # This seam only accepts the runner's already-qualified k6 oneoffs. Callers
    # must bind image/owner and exact argv using existing orchestration custody.
    need(argv[2:3] == ['--rm'], 'STANDALONE_SHAPE')
    limit = LIMITS['k6']
    flags = ['--cpus', limit.cpus, '--memory', str(limit.memory), '--memory-swap', str(limit.memory)]
    # Existing custody inserts attempt labels/cidfile after --rm. Accept the
    # exact selected flags once at their resulting position, without reordering
    # that actual argv or weakening duplicate/override refusal.
    indices = [i for i in range(3, len(argv)) if argv[i] == '--cpus']
    present = len(indices) == 1 and argv[indices[0]:indices[0]+6] == flags
    tail = argv[3:indices[0]] + argv[indices[0]+6:] if present else argv[3:]
    need(not any(str(a).split('=')[0] in ('--cpus', '--cpu-quota', '--cpu-period', '--memory', '-m', '--memory-swap') for a in tail), 'STANDALONE_LIMIT_OVERRIDE')
    return argv if present else argv[:3] + flags + tail


def node_argv(argv, env, role='helper'):
    argv = list(argv)
    need(argv and Path(str(argv[0])).name == 'node' and role in HOST, 'NODE_SHAPE')
    need(not (env or {}).get('NODE_OPTIONS'), 'NODE_OPTIONS_REFUSED')
    need(not any(str(x).startswith(('--max-old-space-size', '--max_old_space_size', '--max-heap-size', '--max_heap_size', '--max-semi-space-size', '--max_semi_space_size')) for x in argv[1:]), 'NODE_HEAP_OVERRIDE')
    return [argv[0], '--max-heap-size=' + str(HOST[role][0]), *argv[1:]]


class Runtime:
    """One existing fixture driver process; callers retain cleanup ownership.

    The host driver lock serializes selected CLI processes. Container ownership
    and the sole finite runtime window remain with the existing orchestrator.
    The container census must be fresh, whole-project and identity-qualified by
    the existing caller. It is an admission read, not a new custody mechanism.
    """
    def __init__(self, config=None, record=None, observe=None):
        self.budget = plan(config) if config is not None else None
        if record is not None:
            need(self.budget is not None and record == self.budget.record(), 'RECORD_CHANGED')
            verify_config(config, self.budget)
        self.observe = observe
        self.lock = threading.RLock()
        self.host = Counter()
        self.driver_fd = None

    def acquire(self, lock_file=None):
        # One host-Node driver across CLI processes. A killed driver leaves its
        # nonempty heap-lease marker; a successor refuses until exact-owned
        # orphan cleanup is verified externally. Never expire a lease by time.
        from experiment_batch import child_lock, global_lock_path
        reserved = child_lock()
        need(not (reserved and lock_file), 'BATCH_LOCK_OVERRIDE')
        path = Path(reserved or lock_file or global_lock_path())
        need(path.is_absolute(), 'DRIVER_LOCK_PATH')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            stat = os.fstat(fd)
            need(stat.st_uid == os.getuid() and stat.st_nlink == 1 and stat.st_mode & 0o077 == 0, 'DRIVER_LOCK_INVALID')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                need(False, 'OTHER_DRIVER_ACTIVE')
            need(os.fstat(fd).st_size == 0, 'STALE_HOST_LEASES')
        except BaseException:
            os.close(fd)
            raise
        self.driver_fd = fd

    def _heap_marker(self):
        need(self.driver_fd is not None, 'DRIVER_LOCK_REQUIRED')
        value = json.dumps({'profile': self.budget.profile if self.budget else NAME, 'hostLeases': dict(self.host)}, sort_keys=True).encode() if any(self.host.values()) else b''
        os.lseek(self.driver_fd, 0, os.SEEK_SET)
        os.write(self.driver_fd, value)
        os.ftruncate(self.driver_fd, len(value))
        os.fsync(self.driver_fd)

    def close(self):
        need(not any(self.host.values()), 'ACTIVE_HOST_LEASES')
        if self.driver_fd is not None:
            os.close(self.driver_fd)
            self.driver_fd = None

    def bind(self, config):
        self.budget = plan(config)
        verify_config(config, self.budget)
        return self.budget.record()

    @contextmanager
    def host_lease(self, role):
        need(role in HOST, 'HOST_ROLE_UNKNOWN')
        with self.lock:
            need(self.host[role] < HOST[role][1], 'HOST_CONCURRENCY_EXCEEDED')
            self.host[role] += 1
            try:
                self._heap_marker()
            except BaseException:
                self.host[role] -= 1
                raise
        try:
            yield
        finally:
            with self.lock:
                self.host[role] -= 1
                self._heap_marker()

    def containers(self, additions=None):
        need(self.budget is not None and callable(self.observe), 'CENSUS_REQUIRED')
        allowances = {r: (l, n) for r, l, n in self.budget.services}
        allowances['k6'] = (LIMITS['k6'], 1)
        counts = Counter()
        cpu = memory = 0
        rows = self.observe()
        need(isinstance(rows, list), 'CENSUS_INVALID')
        for row in rows:
            # Include starting, paused and restarting containers; omit only
            # explicitly dead/exited/created (no active cgroup actor).
            state = row.get('State', {}).get('Status')
            need(state in ('running', 'paused', 'restarting', 'created', 'exited', 'dead'), 'STATE_UNKNOWN')
            if state in ('created', 'exited', 'dead'):
                continue
            role = row.get('Config', {}).get('Labels', {}).get('com.docker.compose.service')
            need(role in allowances, 'RUNTIME_ROLE_UNKNOWN')
            limit, _ = allowances[role]
            native = row.get('HostConfig', {})
            need(native.get('NanoCpus') == limit.cpu * 1000000 and native.get('Memory') == limit.memory and native.get('MemorySwap') == limit.memory,
                 'NATIVE_LIMITS_CHANGED')
            counts[role] += 1
        for role, count in (additions or {}).items():
            need(role in allowances and type(count) is int and count >= 0, 'ADMISSION_ROLE_UNKNOWN')
            counts[role] += count
        for role, count in counts.items():
            limit, maximum = allowances[role]
            need(count <= maximum, 'CONTAINER_CONCURRENCY_EXCEEDED')
            cpu += limit.cpu * count
            memory += limit.memory * count
        need(cpu <= MAX_CPU and memory <= memory_ceiling(self.budget.profile), 'RUNTIME_AGGREGATE_EXCEEDED')
        return counts

    def compose(self, args, config):
        # Teardown and read-only commands must remain available after a refusal.
        args = list(args)
        need(not any(x in ('build', 'pull') for x in args), 'BUILD_PULL_REFUSED')
        if not any(x in ('up', 'run', 'start', 'restart', 'create') for x in args):
            return
        verify_config(config, self.budget)
        # The existing binding remains the parser and authority for actual argv.
        args = list(args)
        action = next((x for x in args if x in ('up', 'run', 'start', 'restart', 'create')), None)
        if action is None:
            return
        current = self.containers()
        if action == 'run':
            index = args.index('run')
            role = next((x for x in args[index+1:] if x in config['services']), None)
            need(role is not None, 'COMPOSE_ROLE_REQUIRED')
            self.containers({role: 1})
        else:
            # Every role can coexist once. Unknown overrides/scale are refused
            # by existing binding and also refused here before an actor effect.
            need(not any(str(x).startswith(('--scale', '--force-recreate')) for x in args), 'RECREATE_SCALE_REFUSED')
            need(all(n <= (2 if r in ('bootstrap', 'primer') else 1) for r, n in current.items()), 'CONTAINER_CONCURRENCY_EXCEEDED')


# One selection per fixture-driving process. Default calls preserve old behavior.
# Shared between threads so asynchronous launch cannot silently lose a ContextVar.
_ACTIVE = None


def configure(selected=None, config=None, record=None, observe=None):
    global _ACTIVE
    selection(selected)
    need(_ACTIVE is None or not any(_ACTIVE.host.values()), 'ACTIVE_HOST_LEASES')
    if _ACTIVE is not None:
        _ACTIVE.close()
    _ACTIVE = None
    if selected is not None:
        candidate = Runtime(config, record, observe)
        candidate.acquire()
        _ACTIVE = candidate
    return _ACTIVE


@contextmanager
def command(argv, env, host_role='helper'):
    if _ACTIVE is None:
        yield argv, env
        return
    argv = list(argv)
    need(argv[:2] not in (['docker', 'build'], ['docker', 'pull']), 'BUILD_PULL_REFUSED')
    if argv and Path(str(argv[0])).name in ('npm', 'npm-cli.js', 'npx', 'npx-cli.js'):
        need(argv[1:] in (['--version'], ['-v']), 'INSTALL_OR_NPM_ACTOR_REFUSED')
        executable = shutil.which('node')
        need(executable is not None, 'NODE_MISSING')
        argv = [str(Path(executable).resolve()), *argv]
    if argv and Path(str(argv[0])).name == 'node':
        argv = node_argv(argv, env, host_role)
        with _ACTIVE.host_lease(host_role):
            yield argv, env
    elif argv[:2] == ['docker', 'run']:
        argv = standalone(argv, _ACTIVE.budget)
        _ACTIVE.containers({'k6': 1})
        yield argv, env
    else:
        yield argv, env


def popen(launcher, argv, *, env, host_role='probe', **kwargs):
    if _ACTIVE is None:
        return launcher(argv, env=env, **kwargs)
    argv = node_argv(argv, env, host_role)
    lease = _ACTIVE.host_lease(host_role)
    lease.__enter__()
    try:
        process = launcher(argv, env=env, **kwargs)
    except BaseException:
        lease.__exit__(None, None, None)
        raise
    return _NodeProcess(process, lease)


class _NodeProcess:
    def __init__(self, process, lease):
        self._process, self._lease = process, lease

    def __getattr__(self, name):
        return getattr(self._process, name)

    def _release(self):
        if self._lease is not None:
            self._lease.__exit__(None, None, None)
            self._lease = None

    def poll(self):
        result = self._process.poll()
        if result is not None:
            self._release()
        return result

    def wait(self, *args, **kwargs):
        result = self._process.wait(*args, **kwargs)
        self._release()
        return result


def bounded_standalone(argv):
    if _ACTIVE is None:
        return argv
    result = standalone(argv, _ACTIVE.budget)
    _ACTIVE.containers({'k6': 1})
    return result


def before_compose(args, config):
    if _ACTIVE is not None:
        _ACTIVE.compose(args, config)


def selected_record(config, selected):
    if selected is None:
        return None
    need(_ACTIVE is not None, 'SELECTION_NOT_ACTIVE')
    return _ACTIVE.bind(config)
