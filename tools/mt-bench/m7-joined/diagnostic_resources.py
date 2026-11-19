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
import hashlib
import os
import copy
import json
from pathlib import Path
import re
import shutil
from subprocess import TimeoutExpired
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
# Docker's quota, NanoCpus and memory-byte fields are signed int64 values.
# Authored service CPU uses integer quota/period, avoiding Compose CPUS float32.
NATIVE_INT64_MAX = (1 << 63) - 1
CPU_PERIOD = 100000
CPU_QUOTA_PER_MILLICPU = CPU_PERIOD // 1000
# Linux CFS MAX_BW=(1<<(64-BW_SHIFT))-1 with BW_SHIFT=20 bounds quota
# microseconds. At the minimum legal 1000us period, quota equals millicpus.
# https://github.com/torvalds/linux/blob/v6.18/kernel/sched/core.c
# https://github.com/torvalds/linux/blob/v6.18/kernel/sched/sched.h
MAX_CFS_QUOTA_US = (1 << (64 - 20)) - 1
MAX_ALLOCATION_MILLICPUS = MAX_CFS_QUOTA_US
MAX_DRIVER_MILLICPUS = NATIVE_INT64_MAX // 1000000
# runc v1.3.3's systemd conversion multiplies signed quota microseconds by
# 1,000,000 before division. Keep fresh ordinary periods within that carrier.
MAX_RUNC_SYSTEMD_QUOTA_US = NATIVE_INT64_MAX // 1000000
RUNC_SYSTEMD_VERSIONS = frozenset(('1.3.3', '1.3.3-0ubuntu1~24.04.3'))
# nginx's Unix process table has NGX_MAX_PROCESSES slots (workers and cache
# helpers share it; reload generations can coexist). This necessary maximum
# does not promise that every slot is free or that workers have started.
# https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process.h
# https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process_cycle.c
# The existing mounted source config retains worker_rlimit_nofile 65536;
# larger budgets need their own configured/read-back descriptor capability.
NGINX_MAX_WORKERS = 1024
EDGE_NOFILE = 65536


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
DISCOVERY_K6 = Limit(2000, 4096 * MIB)

HOST = MappingProxyType({'probe': (512, 1), 'generator': (256, 1), 'helper': (128, 2)})


class AllocationLimit(Limit):
    def __post_init__(self):
        need(type(self.cpu) is int and 1<=self.cpu<=MAX_ALLOCATION_MILLICPUS,'CPU_INVALID')
        need(type(self.memory) is int and MIB<=self.memory<=NATIVE_INT64_MAX,'MEMORY_INVALID')


def service_cpu_settings(millicpus):
    """Exact Linux CFS quota/period; preserve 100ms for ordinary allocations.

    A 1s period gives 1..9millicpu the kernel's minimum 1ms quota. Very large
    allocations use a 1ms period before runc's signed quota*1e6 can overflow.
    This integer projection alone does not qualify a runtime's precision.
    Fresh preflight separately checks the observed systemd/runc conversion.
    """
    period=1000000 if millicpus<10 else 1000 if millicpus>MAX_RUNC_SYSTEMD_QUOTA_US//CPU_QUOTA_PER_MILLICPU else CPU_PERIOD
    return millicpus*(period//1000),period


def frozen_cpu_settings(millicpus, quota, period):
    """Validate the exact frozen pair without selecting a replacement period."""
    need(type(quota) is int and type(period) is int and 1000<=quota<=MAX_CFS_QUOTA_US
         and 1000<=period<=1000000 and quota*1000==millicpus*period, 'EXISTING_LIMIT_CONFLICT')
    return quota,period


def fresh_cpu_preflight(profile, read=None, *, roles=None, observation=None):
    """Check only a known observed runtime; plans and unknown runtimes stay unmeasured.

    The caller opts in at actual fresh prepare, before effects, and supplies its
    existing read-only command wrapper. No daemon access occurs without it.
    Upstream runc v1.3.3 vendor/opencontainers/cgroups/systemd/common.go:264-296
    rounds CPUQuotaPerSecUSec to 10,000us/sec, then writes the rounded quota.
    https://github.com/opencontainers/runc/blob/v1.3.3/vendor/github.com/opencontainers/cgroups/systemd/common.go
    """
    if not isinstance(profile,dict):return {'verdict':'NOT_APPLICABLE'}
    selection(profile)
    chosen=set(profile['services']) if roles is None else set(roles)
    need(chosen<=set(profile['services']),'CPU_EXECUTION_ROLES')
    result={'verdict':'UNMEASURED','runtimePrecision':'UNMEASURED','qualifiedRoles':[],
            'deferredRoles':sorted(profile['services']),
            'scope':'selected execution roles only; dormant roles and native readback remain unqualified'}
    runtime=(observation or {}).get('runtime')
    if runtime is None:
        if read is None:return result
        try:
            info=json.loads(read(['docker','info','--format',
                '{"CgroupDriver":{{json .CgroupDriver}},"CgroupVersion":{{json .CgroupVersion}},"DefaultRuntime":{{json .DefaultRuntime}},"ServerVersion":{{json .ServerVersion}}}']))
            components=json.loads(read(['docker','version','--format','{{json .Server.Components}}']))
            runtime={'cgroupDriver':info['CgroupDriver'],'cgroupVersion':info['CgroupVersion'],
                     'defaultRuntime':info['DefaultRuntime'],'engineVersion':info['ServerVersion'],
                     'runcVersion':next(row['Version'] for row in components if row['Name']=='runc')}
        except (RuntimeError,ValueError,KeyError,TypeError,StopIteration,OSError,TimeoutExpired):return result
    if not (isinstance(runtime,dict) and set(runtime)=={'cgroupDriver','cgroupVersion','defaultRuntime','engineVersion','runcVersion'}
            and all(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.~+-]{1,160}',value) for value in runtime.values())):return result
    result['runtime']=runtime
    if not (runtime['cgroupDriver']=='systemd' and runtime['cgroupVersion']=='2'
            and runtime['defaultRuntime']=='runc' and runtime['runcVersion'] in RUNC_SYSTEMD_VERSIONS):return result
    result['runtimePrecision']='runc-systemd-whole-percent-v1'
    for role in sorted(chosen):
        limit=profile['services'][role]
        cpu=limit['millicpus'];quota,period=service_cpu_settings(cpu)
        reason='WHOLE_PERCENT_CPU_REQUIRED' if cpu%10 else \
               'SIGNED_QUOTA_PRODUCT_OVERFLOW' if quota>MAX_RUNC_SYSTEMD_QUOTA_US else None
        if reason:
            error=RuntimeError('M7_DIAGNOSTIC_RESOURCE_CPU_UNREPRESENTABLE:services.'+role+'.millicpus')
            error.diagnostic={'field':'services.'+role+'.millicpus','millicpus':cpu,'runtime':runtime,
                              'quotaMicros':quota,'periodMicros':period,'reason':reason,
                              'exactMillicpuStep':10,'maximumConversionQuotaMicros':MAX_RUNC_SYSTEMD_QUOTA_US}
            raise error
    return {**result,'verdict':'PASS' if chosen else 'UNMEASURED',
            'qualifiedRoles':sorted(chosen),'deferredRoles':sorted(set(profile['services'])-chosen),
            'scope':'known runtime integer CPU representation for selected execution roles only; dormant roles, native admission/readback and host fit remain unqualified'}


def compose_actor_roles(args, config):
    """Use the existing argv authority, then select exact targets/dependencies."""
    import orchestration_binding as binding
    services=config['services'];values=list(map(str,args))
    action=binding._action(values,services)
    if action not in ('up','run','create','start','restart'):return []
    index=0;profiles=set()
    while values[index]=='--profile':profiles.add(values[index+1]);index+=2
    tail=values[index+1:]
    first=next((i for i,value in enumerate(tail) if value in services),len(tail))
    options=tail[:first]
    if action in ('up','run','create'):binding._options(action,options)
    if action=='run':
        need(first<len(tail),'COMPOSE_ROLE_REQUIRED');chosen={tail[first]}
    elif first<len(tail):
        need(all(value in services for value in tail[first:]),'COMPOSE_ROLE_REQUIRED');chosen=set(tail[first:])
    else:
        chosen={role for role,spec in services.items() if not spec.get('profiles') or profiles.intersection(spec['profiles'])}
    if '--no-deps' not in options:
        pending=list(chosen)
        while pending:
            dependencies=services[pending.pop()].get('depends_on',{})
            need(isinstance(dependencies,(dict,list)) and set(dependencies)<=set(services),'COMPOSE_DEPENDENCY_REQUIRED')
            for role in set(dependencies)-chosen:chosen.add(role);pending.append(role)
    return sorted(chosen)


def explicit_allocation(value):
    """One finite authored allocation, not a new named profile or permission grant."""
    need(isinstance(value,dict) and set(value) - {'ceiling'} == {'version','services','driver','edge'} and type(value['version']) is int and value['version']==1,'ALLOCATION_SHAPE')
    need(isinstance(value['services'],dict) and bool(value['services']),'ALLOCATION_ROSTER')
    for role,limit in value['services'].items():
        need(isinstance(role,str) and (role in LIMITS and role!='k6' or role in ('pgstream','socket-edge') or re.fullmatch(r'(api|realtime|evaluator)-(?:[2-9]|1[0-6])',role)),'UNKNOWN_ROLE')
        allocation_limit(limit,field='services.'+role)
    driver_limit(value)
    # Older selections include a whole-host planning estimate. Accept it as
    # metadata. Docker applies the selected per-container settings.
    if 'ceiling' in value:
        ceiling = value['ceiling']
        need(isinstance(ceiling, dict) and set(ceiling) == {'millicpus', 'memoryBytes'}
             and type(ceiling['millicpus']) is int and ceiling['millicpus'] >= 1
             and type(ceiling['memoryBytes']) is int and ceiling['memoryBytes'] >= MIB,
             'ALLOCATION_CEILING')
    edge=value['edge']
    need(isinstance(edge,dict) and set(edge)=={'workerProcesses','workerConnections'} and 'nginx' in value['services'] and type(edge['workerProcesses']) is int and 1<=edge['workerProcesses']<=NGINX_MAX_WORKERS and type(edge['workerConnections']) is int and edge['workerConnections']>=1,'ALLOCATION_EDGE')
    need(edge['workerConnections']<=EDGE_NOFILE,'ALLOCATION_EDGE_DESCRIPTOR_LIMIT:workerConnections exceeds retained worker_rlimit_nofile=65536; a larger configured/read-back descriptor budget is required')
    return value


def allocation_limit(value, *, driver=False, field='allocation'):
    need(isinstance(value,dict) and set(value)=={'millicpus','memoryBytes'},'ALLOCATION_LIMIT:'+field)
    try:limit=AllocationLimit(value['millicpus'],value['memoryBytes'])
    except RuntimeError as error:
        key='millicpus' if 'CPU_INVALID' in str(error) else 'memoryBytes'
        raise RuntimeError(str(error)+':'+field+'.'+key) from error
    need(not driver or limit.cpu<=MAX_DRIVER_MILLICPUS,'CPU_INVALID:'+field+'.millicpus exceeds standalone NanoCpus signed-int64 representation')
    return limit


def external_selection(value):
    return isinstance(value,dict) or value in EXTERNAL_PROFILES


def driver_memory_request(profile):
    return isinstance(profile, dict) and 'memoryReservationBytes' in profile['driver']


def driver_limit(profile):
    if not isinstance(profile, dict):
        return LIMITS['k6']
    driver = dict(profile['driver']) if isinstance(profile['driver'], dict) else profile['driver']
    if isinstance(driver, dict) and 'memoryReservationBytes' in driver:
        need('memoryBytes' not in driver, 'ALLOCATION_LIMIT:driver')
        driver['memoryBytes'] = driver.pop('memoryReservationBytes')
    return allocation_limit(driver, driver=True, field='driver')


def driver_record(profile):
    limit = driver_limit(profile)
    memory = 'memoryReservationBytes' if driver_memory_request(profile) else 'memoryBytes'
    return {'millicpus': limit.cpu, memory: limit.memory, 'maximumConcurrent': 1}


def standalone_flags(limit, request_only):
    cpu = ['--cpus', limit.cpus]
    if request_only:
        return cpu + ['--memory-reservation', str(limit.memory)]
    return cpu + ['--memory', str(limit.memory), '--memory-swap', str(limit.memory)]


def standalone_native(limit, request_only):
    native = {'NanoCpus': limit.cpu * 1000000}
    if request_only:
        return {**native, 'MemoryReservation': limit.memory, 'Memory': 0, 'MemorySwap': 0}
    return {**native, 'Memory': limit.memory, 'MemorySwap': limit.memory}


def selection(name=None):
    if isinstance(name,dict):return explicit_allocation(name)
    need(name in (None, *PROFILES), 'SELECTION_INVALID')
    return name


def memory_ceiling(profile):
    selection(profile)
    if isinstance(profile,dict):return profile['ceiling']['memoryBytes']
    if profile == QUALIFICATION_NAME: return 10240 * MIB
    return 8448 * MIB if profile == EVALUATOR250_MEMORY512_NAME else MAX_MEMORY


def cpu_ceiling(profile):
    selection(profile)
    return profile['ceiling']['millicpus'] if isinstance(profile,dict) else 6000 if profile == QUALIFICATION_NAME else MAX_CPU


def edge_worker_budget(profile):
    if profile is None:return None
    selection(profile)
    cpu=role_limit('nginx',profile).cpu
    if isinstance(profile,dict):return {**profile['edge'],'nginxMillicpus':cpu,'source':'explicit-resource-allocation-v1'}
    return {'workerProcesses':(cpu+999)//1000,'workerConnections':16384,'nginxMillicpus':cpu,'source':'diagnostic-resource-profile-v1'}


def role_limit(role, profile=NAME):
    selection(profile)
    if isinstance(profile,dict):
        need(role in profile['services'],'ALLOCATION_ROLE_MISSING')
        return allocation_limit(profile['services'][role])
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


def verify_evaluator_cgroup(profile, cpu_max, memory_max, memory_swap_max, *, expected_cpu=None):
    """Validate captured cgroup-v2 values; caller owns identity and capture I/O."""
    limit=role_limit('evaluator',profile)
    need(isinstance(cpu_max,str) and re.fullmatch(r'[1-9][0-9]* [1-9][0-9]*\n?',cpu_max) is not None,'EFFECTIVE_CPU_INVALID')
    quota,period=map(int,cpu_max.split())
    need(quota*1000==limit.cpu*period,'EFFECTIVE_CPU_CHANGED')
    if isinstance(profile,dict):
        expected=service_cpu_settings(limit.cpu) if expected_cpu is None else frozen_cpu_settings(limit.cpu,*expected_cpu)
        need((quota,period)==expected,'EFFECTIVE_CPU_PERIOD_CHANGED')
    need(str(memory_max).strip()==str(limit.memory),'EFFECTIVE_MEMORY_CHANGED')
    need(str(memory_swap_max).strip()=='0','EFFECTIVE_SWAP_CHANGED')
    return {'millicpus':limit.cpu,'memoryBytes':limit.memory,'swapBytes':0}


@dataclass(frozen=True)
class Plan:
    # (service, limit, concurrent count). Every selected role is reserved even
    # when idle, ops-only or used only during preparation. No stage subtraction.
    services: tuple
    profile: object = NAME  # Named selector or exact explicit allocation JSON.
    cpu_enforcement: tuple = ()  # (role, quota microseconds, period microseconds)

    def __post_init__(self):
        need(selection(self.profile) is not None,'PROFILE_CHANGED')
        need(type(self.services) is tuple and bool(self.services), 'SERVICES_REQUIRED')
        need(len({r for r, _, _ in self.services}) == len(self.services), 'DUPLICATE_ROLE')
        for role, limit, count in self.services:
            need(isinstance(role, str) and role_limit(role,self.profile) == limit, 'LIMIT_CHANGED')
            need(type(count) is int and count == (2 if role in ('bootstrap', 'primer') else 1), 'MULTIPLICITY_CHANGED')
        need(type(self.cpu_enforcement) is tuple and len({role for role,_,_ in self.cpu_enforcement})==len(self.cpu_enforcement),'CPU_ENFORCEMENT_CHANGED')
        for role,quota,period in self.cpu_enforcement:
            need(isinstance(self.profile,dict) and role in {r for r,_,_ in self.services},'CPU_ENFORCEMENT_CHANGED')
            frozen_cpu_settings(role_limit(role,self.profile).cpu,quota,period)
        if not isinstance(self.profile, dict):
            cpu = sum(limit.cpu * count for _, limit, count in self.services) + driver_limit(self.profile).cpu
            memory = sum(limit.memory * count for _, limit, count in self.services) + driver_limit(self.profile).memory
            need(cpu <= cpu_ceiling(self.profile) and memory <= memory_ceiling(self.profile), 'AGGREGATE_EXCEEDED')
        need(sum(heap * count for heap, count in HOST.values()) <= MAX_HEAP, 'HOST_AGGREGATE_EXCEEDED')

    def record(self):
        native={role:{'kind':'cfs-quota-period-v1','quotaMicros':quota,'periodMicros':period} for role,quota,period in self.cpu_enforcement}
        record = {'version': 1, 'profile': self.profile,
                'services': {r: {'millicpus': l.cpu, 'memoryBytes': l.memory, 'maximumConcurrent': n, **({'cpuEnforcement':native[r]} if r in native else {})} for r, l, n in self.services},
                'standalone': {'k6': driver_record(self.profile)},
                'host': {r: {'heapMiB': h, 'maximumConcurrent': n} for r, (h, n) in HOST.items()},
                'hostRss': 'SEPARATELY_OBSERVED_NOT_HEAP_BOUNDED'}
        if not isinstance(self.profile, dict):
            record['aggregate'] = {'millicpus': sum(l.cpu*n for _, l, n in self.services) + driver_limit(self.profile).cpu,
                                   'memoryBytes': sum(l.memory*n for _, l, n in self.services) + driver_limit(self.profile).memory,
                                   'heapMiB': sum(h*n for h, n in HOST.values())}
            record['basis'] = 'ALL_SELECTED_SERVICES_PLUS_DECLARED_OVERLAPS_PLUS_STANDALONE_K6'
        return record


def plan(config, *, freeze_cpu=True):
    services = config.get('services', {})
    need(isinstance(services, dict) and bool(services), 'SERVICES_REQUIRED')
    need('k6' not in services, 'K6_COMPOSE_STANDALONE_AMBIGUOUS')
    profile=config.get(PROFILE_KEY,NAME);need(selection(profile) is not None,'PROFILE_CHANGED')
    if isinstance(profile,dict):need(set(profile['services'])==set(services),'ALLOCATION_ROSTER_CHANGED')
    need(not external_selection(profile) or 'pgstream' in services and 'evaluator' in services,'EXTERNAL_ROSTER_REQUIRED')
    native=tuple((role,*frozen_cpu_settings(role_limit(role,profile).cpu,services[role].get('cpu_quota'),services[role].get('cpu_period'))) for role in sorted(services) if freeze_cpu and isinstance(profile,dict) and any(key in services[role] for key in ('cpu_quota','cpu_period')))
    return Plan(tuple((r, role_limit(r,profile), 2 if r in ('bootstrap', 'primer') else 1) for r in sorted(services)),profile,native)



COMPOSE_CPU_LIMITS = ('cpus', 'cpu_quota', 'cpu_period', 'cpu_count', 'cpu_percent')
COMPOSE_MEMORY_LIMITS = ('mem_limit', 'memswap_limit', 'mem_reservation')
NATIVE_CPU_LIMITS = ('NanoCpus', 'CpuQuota', 'CpuPeriod', 'CpuCount', 'CpuPercent')
NATIVE_MEMORY_LIMITS = ('Memory', 'MemorySwap', 'MemoryReservation')


def compose_limit_mode(config, selected):
    if selected is not None:
        return 'configured'
    for role, spec in config['services'].items():
        alternate = spec.get('deploy', {}).get('resources', {})
        need(not any(spec.get(key) for key in (*COMPOSE_CPU_LIMITS, *COMPOSE_MEMORY_LIMITS))
             and not any(alternate.get(kind, {}).get(key) for kind in ('limits', 'reservations')
                         for key in ('cpus', 'memory')),
             'IMPLICIT_SERVICE_LIMIT:' + role)
    return 'uncapped-services'


def uncapped_compose(config):
    """Project reference sizing out of the diagnostic runtime, preserving source files."""
    result = copy.deepcopy(config)
    removed = {}
    for role, spec in result['services'].items():
        fields = [key for key in (*COMPOSE_CPU_LIMITS, *COMPOSE_MEMORY_LIMITS) if key in spec]
        for key in fields:
            del spec[key]
        alternate = spec.get('deploy', {}).get('resources', {})
        for kind in ('limits', 'reservations'):
            block = alternate.get(kind, {})
            for key in ('cpus', 'memory'):
                if key in block:
                    del block[key]
                    fields.append('deploy.resources.' + kind + '.' + key)
        if fields:
            removed[role] = fields
    return result, removed


def uncapped_readback(rows, services):
    evidence = []
    for row in rows:
        role = row['Config']['Labels'].get('com.docker.compose.service')
        if role not in services:
            continue
        config = row['HostConfig']
        observed = {key: config.get(key) for key in (*NATIVE_CPU_LIMITS, *NATIVE_MEMORY_LIMITS)}
        need(all(type(value) is int and value == 0 for value in observed.values()),
             'UNEXPECTED_NATIVE_SERVICE_LIMIT:' + role)
        evidence.append({'role': role, 'containerId': row['Id'], 'limits': observed})
    need(bool(evidence), 'NATIVE_SERVICE_LIMITS_UNMEASURED')
    return evidence


def overlay(config, selected, *, applying=True):
    """Return a full JSON Compose document; never mutate source/default config."""
    if selected is None:
        return config
    selection(selected)
    result = copy.deepcopy(config)
    if external_selection(selected):result[PROFILE_KEY]=selected
    need(result.get(PROFILE_KEY,NAME)==selected,'PROFILE_CHANGED')
    budget = plan(result,freeze_cpu=not applying)
    for role, limit, _ in budget.services:
        spec = result['services'][role]
        # Entered explicit fixtures can retain their frozen legacy cpus field.
        # Fresh explicit services always use integer quota/period. Never accept
        # simultaneous CPU mechanisms or round the selected millicpu quantity.
        quota=isinstance(selected,dict) and (applying or 'cpus' not in spec)
        # Conflicting alternate resource knobs can change native enforcement.
        need(not any(k in spec for k in ('cpu_count', 'cpu_percent', 'cpu_rt_period', 'cpu_rt_runtime', 'mem_reservation'))
             and (quota or not any(k in spec for k in ('cpu_quota','cpu_period'))),
             'ALTERNATE_LIMITS')
        need(not spec.get('deploy', {}).get('resources'), 'ALTERNATE_LIMITS')
        if quota:
            need(not ('cpus' in spec and any(k in spec for k in ('cpu_quota','cpu_period'))),'ALTERNATE_LIMITS')
            if 'cpus' in spec:del spec['cpus']
            quota_value,period=service_cpu_settings(limit.cpu) if applying else frozen_cpu_settings(limit.cpu,spec.get('cpu_quota'),spec.get('cpu_period'))
            cpu_values=(('cpu_period',period),('cpu_quota',quota_value))
        else:cpu_values=(('cpus',float(limit.cpus)),)
        for key, value in (*cpu_values, ('mem_limit', limit.memory), ('memswap_limit', limit.memory)):
            same=key not in spec or str(spec[key])==str(value) or key=='cpus' and type(spec[key]) in (int,float) and spec[key]==value
            # An authored allocation replaces reference sizing during fresh
            # preparation. Readback validation never reapplies that override.
            need(same or applying and isinstance(selected,dict), 'EXISTING_LIMIT_CONFLICT')
            # Compose JSON preserves byte limits as strings and normalizes 1.0
            # CPU to integer 1. Preserve equivalent existing representations.
            if key not in spec or not same:spec[key] = value
    return result


def verify_config(config, budget):
    need(plan(config) == budget, 'PLAN_CHANGED')
    need(overlay(config, budget.profile, applying=False) == config, 'CONFIG_LIMITS_CHANGED')


def standalone_limit():
    return getattr(_ACTIVE, 'driver_limit', LIMITS['k6']) if _ACTIVE is not None else LIMITS['k6']


def discovery_driver_record(owner):
    if owner.get('runPurpose') != 'discovery' or owner.get('profile') != 'pgstream-sample' or 'diagnosticResources' not in owner:
        return None
    original=owner['diagnosticResources']
    if isinstance(original.get('profile'),dict):return None  # Keep the authored driver settings.
    return {'kind':'discovery-k6-allocation-v1','owner':owner['owner'],'pair':owner['pair'],
            'imageId':owner['imageId'],'instrument':owner['instrument']['sha256'],
            'serverProfile':original['profile'],'serverResourceRecordUnchanged':True,
            'replacesStandaloneReservation':original['standalone']['k6'],
            'k6':{'millicpus':DISCOVERY_K6.cpu,'memoryBytes':DISCOVERY_K6.memory,'maximumConcurrent':1},
            'effectiveAggregate':{**original['aggregate'],
                'millicpus':original['aggregate']['millicpus']-LIMITS['k6'].cpu+DISCOVERY_K6.cpu,
                'memoryBytes':original['aggregate']['memoryBytes']-LIMITS['k6'].memory+DISCOVERY_K6.memory},
            'scope':'prospective standalone load driver only; original runtime resource declaration unchanged; no backend capacity acceptance'}


@contextmanager
def discovery_driver(owner):
    record=discovery_driver_record(owner)
    if record is None:
        yield None
        return
    need(_ACTIVE is not None and _ACTIVE.budget is not None,'DRIVER_SELECTION_NOT_ACTIVE')
    need(_ACTIVE.budget.record()==owner['diagnosticResources'],'DRIVER_RUNTIME_RECORD_CHANGED')
    previous=_ACTIVE.driver_limit
    _ACTIVE.driver_limit=DISCOVERY_K6
    try:yield record
    finally:_ACTIVE.driver_limit=previous


def standalone(argv, budget):
    """Apply native limits before the image, retaining all custody/image argv."""
    argv = list(argv)
    need(argv[:2] == ['docker', 'run'] and budget is not None, 'STANDALONE_SHAPE')
    # This seam only accepts the runner's already-qualified k6 oneoffs. Callers
    # must bind image/owner and exact argv using existing orchestration custody.
    need(argv[2:3] == ['--rm'], 'STANDALONE_SHAPE')
    limit = standalone_limit()
    flags = standalone_flags(limit, driver_memory_request(budget.profile))
    # Existing custody inserts attempt labels/cidfile after --rm. Accept the
    # exact selected flags once at their resulting position, without reordering
    # that actual argv or weakening duplicate/override refusal.
    indices = [i for i in range(3, len(argv)) if argv[i] == '--cpus']
    present = len(indices) == 1 and argv[indices[0]:indices[0]+len(flags)] == flags
    tail = argv[3:indices[0]] + argv[indices[0]+len(flags):] if present else argv[3:]
    need(not any(str(a).split('=')[0] in ('--cpus', '--cpu-quota', '--cpu-period', '--memory', '-m', '--memory-swap', '--memory-reservation') for a in tail), 'STANDALONE_LIMIT_OVERRIDE')
    return argv if present else argv[:3] + flags + tail


def node_argv(argv, env, role='helper'):
    argv = list(argv)
    need(argv and Path(str(argv[0])).name == 'node' and role in HOST, 'NODE_SHAPE')
    need(not (env or {}).get('NODE_OPTIONS'), 'NODE_OPTIONS_REFUSED')
    need(not any(str(x).startswith(('--max-old-space-size', '--max_old_space_size', '--max-heap-size', '--max_heap_size', '--max-semi-space-size', '--max_semi_space_size')) for x in argv[1:]), 'NODE_HEAP_OVERRIDE')
    return [argv[0], '--max-heap-size=' + str(HOST[role][0]), *argv[1:]]


class Runtime:
    """One existing fixture driver process; callers retain cleanup ownership.

    The driver lock serializes calls for one fixture. Independent fixtures may
    overlap within their authored allocations; their measurements are contended.
    Container ownership
    and the sole finite runtime window remain with the existing orchestrator.
    The container census must be fresh, whole-project and identity-qualified by
    the existing caller. It is an admission read, not a new custody mechanism.
    """
    def __init__(self, config=None, record=None, observe=None, driver_scope=None):
        self.budget = plan(config) if config is not None else None
        if record is not None:
            # Older explicit allocations also recorded a descriptive sum.
            if isinstance(record.get('profile'), dict):
                record = {key: value for key, value in record.items() if key not in ('aggregate', 'basis')}
            need(self.budget is not None and record == self.budget.record(), 'RECORD_CHANGED')
            verify_config(config, self.budget)
        self.observe = observe
        self.quota_roles={role for role,spec in (config or {}).get('services',{}).items() if 'cpu_quota' in spec}
        self.driver_limit = driver_limit(self.budget.profile) if self.budget else LIMITS['k6']
        self.lock = threading.RLock()
        self.host = Counter()
        self.driver_fd = None
        self.driver_scope = driver_scope

    def acquire(self, lock_file=None):
        # One driver per fixture across CLI processes. A killed driver leaves its
        # nonempty heap-lease marker; a successor refuses until exact-owned
        # orphan cleanup is verified externally. Never expire a lease by time.
        from experiment_batch import child_lock, global_lock_path
        reserved = child_lock()
        need(not (reserved and lock_file), 'BATCH_LOCK_OVERRIDE')
        scope = self.driver_scope
        if scope is not None:
            need(Path(scope).is_absolute(), 'DRIVER_SCOPE_PATH')
            key = hashlib.sha256(str(Path(scope).resolve()).encode()).hexdigest()[:32]
            scoped = global_lock_path().with_name(global_lock_path().stem + '-' + key + '.lock')
        else:
            scoped = global_lock_path()  # legacy/batch callers keep their original custody
        path = Path(reserved or lock_file or scoped)
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
        self.driver_limit = driver_limit(self.budget.profile)
        verify_config(config, self.budget)
        self.quota_roles={role for role,spec in config['services'].items() if 'cpu_quota' in spec}
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
        allowances['k6'] = (self.driver_limit, 1)
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
            if role in self.quota_roles:
                quota,period=next((q,p) for r,q,p in self.budget.cpu_enforcement if r==role)
                cpu_matches=all(type(native.get(key)) is int for key in ('NanoCpus','CpuQuota','CpuPeriod')) and native['NanoCpus']==0 and native['CpuQuota']==quota and native['CpuPeriod']==period and all(native.get(key,0)==0 for key in ('CpuCount','CpuPercent','CpuRealtimePeriod','CpuRealtimeRuntime'))
            else:cpu_matches=native.get('NanoCpus')==limit.cpu*1000000
            expected = (standalone_native(limit, driver_memory_request(self.budget.profile)) if role == 'k6'
                        else {'Memory': limit.memory, 'MemorySwap': limit.memory})
            need(cpu_matches and all(native.get(key) == value for key, value in expected.items()),
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
        if not isinstance(self.budget.profile, dict):
            need(cpu <= cpu_ceiling(self.budget.profile)+self.driver_limit.cpu-driver_limit(self.budget.profile).cpu and memory <= memory_ceiling(self.budget.profile)+self.driver_limit.memory-driver_limit(self.budget.profile).memory, 'RUNTIME_AGGREGATE_EXCEEDED')
        return counts

    def compose(self, args, config, cpu_preflight=None):
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
        # Legacy NanoCpus records retain their existing admission path. New
        # quota actors, including later activation of a dormant role, must be
        # representable on the observed runtime before any actor command.
        if self.quota_roles:
            observation=fresh_cpu_preflight(self.budget.profile,roles=(),observation=cpu_preflight)
            if observation.get('runtimePrecision')=='runc-systemd-whole-percent-v1':
                roles=compose_actor_roles(args,config)
                fresh_cpu_preflight(self.budget.profile,roles=(set(roles)|set(current))&self.quota_roles,observation=observation)
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


def configure(selected=None, config=None, record=None, observe=None, driver_scope=None):
    global _ACTIVE
    selection(selected)
    need(_ACTIVE is None or not any(_ACTIVE.host.values()), 'ACTIVE_HOST_LEASES')
    if _ACTIVE is not None:
        _ACTIVE.close()
    _ACTIVE = None
    if selected is not None:
        candidate = Runtime(config, record, observe, driver_scope=driver_scope)
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


def before_compose(args, config, cpu_preflight=None):
    if _ACTIVE is not None:
        _ACTIVE.compose(args, config,cpu_preflight)


def selected_record(config, selected):
    if selected is None:
        return None
    need(_ACTIVE is not None, 'SELECTION_NOT_ACTIVE')
    return _ACTIVE.bind(config)
