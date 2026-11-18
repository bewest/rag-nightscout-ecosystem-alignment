"""Bounded controller-only phase protocol for an isolated external traffic host."""
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import select
import sys
import time

PROFILE = 'remote-pgstream-calibration-v1'
VERSION = 1
TRAFFIC_FILES = ('probe-accounting.cjs', 'package.json', 'package-lock.json', 'tenants.private.json', 'probe.js', 'workload.js', 'recovery.cjs')
MAX_MESSAGE = 65536
RESERVE = 540
KINDS = {'case-start', 'app-ready', 'client-primed', 'load-ready', 'load-start', 'load-complete',
         'restart-ready', 'restart-prepare', 'restart-armed', 'restart-done',
         'server-recovery-complete', 'client-complete', 'finish', 'cell-complete'}
FIELDS = {'version', 'profile', 'runId', 'cloudId', 'nonce', 'cell', 'tenants', 'appAddress',
          'generatorAddress', 'port', 'expiresAt', 'pair', 'imageId', 'k6Image', 'sourceSha256', 'transport'}

def need(ok, code):
    if not ok:
        raise RuntimeError(code)

def private_ipv4(value):
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return addr.version == 4 and any(addr in ipaddress.ip_network(cidr) for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))

SUPPORTED_COHORTS = (10, 1000, 3000, 5000, 10000)
NATIVE_PROFILE = 'external-service-native-v1'
NATIVE_DEPENDENCIES = {
    'tools/mt-bench/m7-joined/' + name for name in (
        'completed-oracle.cjs', 'native-observation.cjs', 'client-delivery.cjs',
        'evaluator_opportunities.py', 'evaluator_progress.py', 'evaluator_idle.py',
        'discovery_rest.py', 'discovery_counts.py', 'probe.py',
    )
} | {'tools/mt-bench/capacity/probe.js'}

def native_mode(value):
    return (value.get('helperDependencies') or {}).get('profile') == NATIVE_PROFILE

def source_admission(value):
    selected=value.get('nativeSourceAdmission')
    need(selected is None or selected=='diagnostic-build-v1','REMOTE_NATIVE_SOURCE_ADMISSION')
    need(selected is None or native_mode(value) and discovery_mode(value),'REMOTE_NATIVE_BUILD_DISCOVERY_ONLY')
    return 'PENDING' if selected is not None else 'PASS'

def static_selection(value):
    selected=value.get('staticTopology');services=(value.get('diagnosticResourceAllocation')or{}).get('services',{})
    if selected is None:
        need('socket-edge' not in services,'REMOTE_STATIC_SELECTION_REQUIRED')
        return None
    need(selected=={'kind':'static-hash-v1','workers':1} and type(selected.get('workers')) is int,
         'REMOTE_STATIC_K1_N1_ONLY')
    need(native_mode(value) and discovery_mode(value) and value.get('pgstreamTopology')=='external-service-v1'
         and isinstance(value.get('diagnosticResourceAllocation'),dict),'REMOTE_STATIC_NATIVE_SCOPE')
    need('socket-edge' in services
         and not any(re.fullmatch(r'(api|evaluator|realtime)-[0-9]+',name)for name in services),'REMOTE_STATIC_ALLOCATION')
    return selected

def native_project(value):
    return 'nsremote-' + value['nonce'][:12]

def native_networks(value):
    networks=value.get('fixtureNetworks')
    need(isinstance(networks,dict) and set(networks)=={'backend','edge'},'REMOTE_NATIVE_NETWORKS')
    admitted=[]
    for cidr in networks.values():
        need(isinstance(cidr,str) and cidr.endswith('.0/24') and private_ipv4(cidr[:-3]),'REMOTE_NATIVE_NETWORKS')
        subnet=ipaddress.ip_network(cidr)
        need(all(ipaddress.ip_address(value[key]) not in subnet for key in ('appAddress','generatorAddress')),'REMOTE_NATIVE_NETWORKS')
        admitted.append(subnet)
    need(admitted[0]!=admitted[1],'REMOTE_NATIVE_NETWORKS')
    return networks

def discovery_mode(value):
    mode=value.get('reportMode','strict')
    need(mode in ('strict','discovery'),'REMOTE_REPORT_MODE')
    return mode=='discovery'

def workload(value):
    """Exact parameter binding; planning inventory is not measured headroom."""
    from transport import CADENCE
    exploratory=discovery_mode(value)
    selected = value.get('workload')
    need(not exploratory or selected is not None,'REMOTE_DISCOVERY_WORKLOAD_REQUIRED')
    if selected is None:
        need(value['tenants'] in (10, 1000), 'REMOTE_WORKLOAD_PLAN_REQUIRED')
        return dict(cadence=dict(CADENCE), primerConcurrency=1, resourcePlan=None)
    need(isinstance(selected, dict) and set(selected) in ({'cadence', 'primerConcurrency', 'resourcePlan'}, {'cadence', 'primerConcurrency', 'resourcePlan', 'jwtSetupConcurrency'}), 'REMOTE_WORKLOAD_SHAPE')
    cadence = selected['cadence']
    need(isinstance(cadence, dict) and set(CADENCE) <= set(cadence) and set(cadence)-set(CADENCE) <= ({'offeredRps','logicalPollingClients','restartDuringLoadAfterSeconds','workloadMix','workloadScale','driverShards'} if exploratory else {'offeredRps'}), 'REMOTE_CADENCE_SHAPE')
    for key, default in CADENCE.items():
        if exploratory and key in ('warmupSeconds','idleSeconds','loadSeconds','accel','hotFactor','samplerIntervalSeconds','probeEveryMs','socketsPerTenant'):
            maximum={'samplerIntervalSeconds':60,'socketsPerTenant':8}.get(key,10800 if key!='probeEveryMs' else 3600000)
            need(type(cadence[key]) is int and 1<=cadence[key]<=maximum,'REMOTE_DISCOVERY_CADENCE_RANGE')
        elif key == 'loadSeconds':
            need(type(cadence[key]) is int and 1 <= cadence[key] <= 3600, 'REMOTE_DURATION_RANGE')
        else:
            need(type(cadence[key]) is type(default) and cadence[key] == default, 'REMOTE_FIXED_WORKLOAD_CHANGED')
    need(sum(cadence[k] for k in ('warmupSeconds','idleSeconds','loadSeconds'))<=10800,'REMOTE_DURATION_RANGE')
    need(cadence['restart'] is False,'REMOTE_NO_RESTART')
    need('restartDuringLoadAfterSeconds' not in cadence,'REMOTE_DEMAND_RECOVERY_LOCAL_ONLY')
    if 'offeredRps' in cadence:
        rate = cadence['offeredRps']
        need(type(rate) in (int, float) and math.isfinite(rate) and 1 <= rate <= 10000, 'REMOTE_OFFERED_RATE_RANGE')
    if 'workloadMix' in cadence:
        need(exploratory and cadence['workloadMix']=='realistic-v1' and 'offeredRps' not in cadence
             and cadence['accel']==cadence['hotFactor']==1,'REMOTE_REALISTIC_MIX_CONFIGURATION')
    if 'workloadScale' in cadence:
        scale=cadence['workloadScale']
        need(cadence.get('workloadMix')=='realistic-v1' and type(scale) in (int,float) and math.isfinite(scale)
             and 0.25<=scale<=8,'REMOTE_WORKLOAD_SCALE_CONFIGURATION')
    if 'driverShards' in cadence:
        shards=cadence['driverShards']
        need(exploratory and type(shards) is int and 1<=shards<=16 and shards<=value['tenants'], 'REMOTE_DRIVER_SHARDS_RANGE')
        if shards>1:
            need(value.get('pgstreamTopology')=='external-service-v1' and isinstance(value.get('helperDependencies'),dict)
                 and not value.get('componentCases'), 'REMOTE_DRIVER_SHARDS_TOPOLOGY')
            if 'offeredRps' in cadence:
                smallest=value['tenants']//shards
                need(cadence['offeredRps']*smallest/(value['tenants']-1+cadence['hotFactor'])>=1,'REMOTE_DRIVER_SHARDS_RATE')
    jwt = selected.get('jwtSetupConcurrency', 1)
    need(type(jwt) is int and 1 <= jwt <= 64, 'REMOTE_JWT_SETUP_CONCURRENCY_RANGE')
    concurrency = selected['primerConcurrency']
    need(type(concurrency) is int and 1 <= concurrency <= 32, 'REMOTE_PRIMER_CONCURRENCY_RANGE')
    plan = selected['resourcePlan']
    need(isinstance(plan, dict) and set(plan) == {'reference', 'tenants', 'logicalPollingClients', 'hosts'}, 'REMOTE_RESOURCE_PLAN_SHAPE')
    need(isinstance(plan['reference'], str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}', plan['reference']) is not None and
         type(plan['tenants']) is int and plan['tenants'] == value['tenants'] and
         type(plan['logicalPollingClients']) is int and 0<=plan['logicalPollingClients']<=80000 and (exploratory or plan['logicalPollingClients']==cadence['socketsPerTenant']*value['tenants']), 'REMOTE_RESOURCE_PLAN_COHORT')
    if 'logicalPollingClients' in cadence:
        need(type(cadence['logicalPollingClients']) is int and cadence['logicalPollingClients']==plan['logicalPollingClients'],'REMOTE_VIEWER_MIRROR_CHANGED')
    hosts = plan['hosts']
    need(isinstance(hosts, dict) and set(hosts) == {'sut', 'driver'}, 'REMOTE_RESOURCE_PLAN_HOSTS')
    for host in hosts.values():
        need(isinstance(host, dict) and set(host) == {'providerId', 'cpuCores', 'ramBytes'} and
             isinstance(host['providerId'], str) and bool(host['providerId']) and len(host['providerId']) <= 160 and
             type(host['cpuCores']) in (int, float) and math.isfinite(host['cpuCores']) and host['cpuCores'] > 0 and
             type(host['ramBytes']) is int and host['ramBytes'] > 0, 'REMOTE_RESOURCE_PLAN_HOSTS')
    need(hosts['sut']['providerId'] != hosts['driver']['providerId'], 'REMOTE_RESOURCE_PLAN_DISTINCT_HOSTS')
    return selected

def jwt_setup_concurrency(b):
    return workload(b).get('jwtSetupConcurrency', 1)

def viewer_total(b):
    selected=workload(b)
    plan=selected['resourcePlan']
    return plan['logicalPollingClients'] if plan else selected['cadence']['socketsPerTenant']*b['tenants']

def prepared_cadence(b):
    cadence=dict(workload(b)['cadence'])
    if viewer_total(b)!=cadence['socketsPerTenant']*b['tenants']:
        cadence['logicalPollingClients']=viewer_total(b)
    return cadence



def resource_selection(value):
    named=value.get('diagnosticResourceProfile');explicit=value.get('diagnosticResourceAllocation')
    need(named is None or explicit is None,'REMOTE_RESOURCE_SELECTION_AMBIGUOUS')
    return explicit if explicit is not None else named


def allocation_boundary(value,hosts=None):
    """Transport admission; canonical SUT verifier independently binds native quotas."""
    need(isinstance(value,dict) and set(value)=={'version','services','driver','ceiling','edge'} and type(value['version']) is int and value['version']==1,'REMOTE_ALLOCATION_SHAPE')
    need(isinstance(value['services'],dict) and 1<=len(value['services'])<=32 and {'evaluator','pgstream','nginx'}<=set(value['services']),'REMOTE_ALLOCATION_ROSTER')
    for role in value['services']:
        need(isinstance(role,str) and re.fullmatch(r'(postgres|vault|bootstrap|admin|primer|api|realtime|evaluator|tenant-admin|ui|nginx|placement-operator|demo|feed-reader|pgstream|socket-edge|(?:api|realtime|evaluator)-(?:[2-9]|1[0-6]))',role),'REMOTE_ALLOCATION_ROLE')
    for limit in [*value['services'].values(),value['driver']]:
        need(isinstance(limit,dict) and set(limit)=={'millicpus','memoryBytes'} and type(limit['millicpus']) is int and 1<=limit['millicpus']<=64000 and type(limit['memoryBytes']) is int and 1048576<=limit['memoryBytes']<=128*1024*1048576,'REMOTE_ALLOCATION_LIMIT')
    ceiling=value['ceiling']
    need(isinstance(ceiling,dict) and set(ceiling)=={'millicpus','memoryBytes'} and type(ceiling['millicpus']) is int and 1<=ceiling['millicpus']<=64000 and type(ceiling['memoryBytes']) is int and 1048576<=ceiling['memoryBytes']<=128*1024*1048576,'REMOTE_ALLOCATION_CEILING')
    need(value['edge']=={'workerProcesses':1,'workerConnections':16384} and all(type(x) is int for x in value['edge'].values()),'REMOTE_ALLOCATION_EDGE')
    totals={key:sum(v[key]*(2 if role in ('bootstrap','primer') else 1) for role,v in value['services'].items()) for key in ('millicpus','memoryBytes')}
    need(all(totals[k]+value['driver'][k]<=ceiling[k] for k in totals),'REMOTE_ALLOCATION_AGGREGATE')
    if hosts is not None:
        need(all(totals[k]<=hosts['sut']['cpuCores']*1000 if k=='millicpus' else totals[k]<=hosts['sut']['ramBytes'] for k in totals) and value['driver']['millicpus']<=hosts['driver']['cpuCores']*1000 and value['driver']['memoryBytes']<=hosts['driver']['ramBytes'],'REMOTE_ALLOCATION_HOST_CAPACITY')
    return value


def topology(value):
    selected='pgstreamTopology' in value or 'diagnosticResourceProfile' in value or 'diagnosticResourceAllocation' in value or 'helperDependencies' in value
    if not selected:return None
    selection=resource_selection(value)
    need(discovery_mode(value) and value.get('pgstreamTopology')=='external-service-v1' and (isinstance(selection,dict) or selection in ('local-diagnostic-external-pgstream-4cpu-8g-v1','local-qualification-external-pgstream-6cpu-10g-v1')),'REMOTE_EXPLICIT_TOPOLOGY')
    if isinstance(selection,dict):allocation_boundary(selection,workload(value)['resourcePlan']['hosts'])
    deps=value.get('helperDependencies')
    need(isinstance(deps,dict) and set(deps)=={'version','profile','files'} and type(deps['version']) is int and deps['version']==1 and deps['profile'] in ('external-service-v1','external-service-batch-v1',NATIVE_PROFILE),'REMOTE_TOPOLOGY_DEPENDENCIES')
    names={'tools/mt-bench/m7-joined/stream_topology.py','tools/mt-bench/m7-joined/diagnostic_resources.py'}
    if deps['profile'] in ('external-service-batch-v1',NATIVE_PROFILE):names.add('tools/mt-bench/m7-joined/experiment_batch.py')
    if workload(value)['cadence'].get('driverShards',1)>1:
        names.update({'tools/mt-bench/m7-joined/driver_shards.py','tools/mt-bench/m7-joined/contract.py'})
    if value.get('staticTopology') is not None:
        names.update({'tools/mt-bench/m7-joined/static_topology.py','tools/mt-bench/m7-joined/role_instances.py'})
    if value.get('commissioningSlotWalMiB')is not None:
        names.update({'tools/mt-bench/m7-joined/commissioning_wal.py','tools/mt-bench/m7-joined/contract.py'})
    if native_mode(value):
        need(isinstance(selection,dict) and not value.get('componentCases') and viewer_total(value)>0,'REMOTE_NATIVE_PROFILE')
        names.update(NATIVE_DEPENDENCIES)
    need(isinstance(deps['files'],dict) and set(deps['files'])==names and all(isinstance(h,str) and re.fullmatch('[a-f0-9]{64}',h) for h in deps['files'].values()),'REMOTE_TOPOLOGY_DEPENDENCIES')
    return deps


def topology_dependencies(value,root):
    deps=topology(value)
    if deps is None:return
    import ast
    root=Path(root).resolve()
    for name,expected in deps['files'].items():
        file=root/name
        need(file.is_file() and not file.is_symlink() and file.resolve()==file and hashlib.sha256(file.read_bytes()).hexdigest()==expected,'REMOTE_TOPOLOGY_DEPENDENCY_BYTES')
    source=ast.parse((root/'tools/mt-bench/m7-joined/diagnostic_resources.py').read_text())
    uses_batch=any((isinstance(n,ast.ImportFrom) and n.module=='experiment_batch') or (isinstance(n,ast.Import) and any(a.name=='experiment_batch' for a in n.names)) for n in ast.walk(source))
    need(uses_batch==(deps['profile'] in ('external-service-batch-v1',NATIVE_PROFILE)),'REMOTE_TOPOLOGY_DEPENDENCY_PROFILE')


def binding(value, now=None):
    now = time.time() if now is None else now
    need(isinstance(value, dict) and FIELDS <= set(value) and set(value)-FIELDS <= {'workload','componentCases','reportMode','pgstreamTopology','diagnosticResourceProfile','diagnosticResourceAllocation','helperDependencies','fixtureNetworks','nativeSourceAdmission','staticTopology','commissioningSlotWalMiB','tenantReadiness'}, 'EXTERNAL_BINDING_SHAPE')
    if 'componentCases' in value:
        from component_cases import plan
        plan(value['componentCases'],value['tenants'])
    need(value['version'] == VERSION and type(value['version']) is int and value['profile'] == PROFILE, 'EXTERNAL_PROFILE')
    need(re.fullmatch(r'[a-z][a-z0-9-]{2,39}', value['runId']) is not None
         and re.fullmatch(re.escape(value['runId']) + r'-[a-f0-9]{12}', value['cloudId']) is not None
         and re.fullmatch(r'[a-f0-9]{32}', value['nonce']) is not None, 'EXTERNAL_RUN_BINDING')
    need(type(value['cell']) is int and value['cell'] == 1
         and type(value['tenants']) is int and (1<=value['tenants']<=10000 if discovery_mode(value) else value['tenants'] in SUPPORTED_COHORTS), 'EXTERNAL_CELL')
    workload(value)
    topology(value)
    source_admission(value);static_selection(value)
    from commissioning_wal import remote_selection
    remote_selection(value)
    need(private_ipv4(value['appAddress']) and private_ipv4(value['generatorAddress'])
         and value['appAddress'] != value['generatorAddress'] and type(value['port']) is int
         and 1024 <= value['port'] <= 65535, 'EXTERNAL_PRIVATE_INGRESS')
    if native_mode(value):native_networks(value)
    else:need('fixtureNetworks' not in value,'REMOTE_NATIVE_NETWORKS')
    need(type(value['expiresAt']) in (int, float) and now + RESERVE < value['expiresAt'] <= now + 10800, 'EXTERNAL_DEADLINE')
    need(set(value['pair']) == {'core', 'deploy'} and all(re.fullmatch('[a-f0-9]{40}', x) for x in value['pair'].values())
         and re.fullmatch('sha256:[a-f0-9]{64}', value['imageId'])
         and re.fullmatch('grafana/k6@sha256:[a-f0-9]{64}', value['k6Image'])
         and re.fullmatch('[a-f0-9]{64}', value['sourceSha256']), 'EXTERNAL_SOURCE_BINDING')
    from transport import pins
    pins(value)
    return value

def source_identity(directory):
    paths = sorted(p for p in Path(directory).iterdir() if p.suffix in ('.py', '.cjs') and not p.name.startswith('test_'))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return {'version': 1, 'profile': PROFILE, 'files': hashes, 'trafficFiles': sorted(TRAFFIC_FILES),
            'sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}

def write(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def validate_message(value, b, node, sequence, kind):
    need(isinstance(value, dict) and set(value) == {'version', 'runId', 'nonce', 'cell', 'node', 'sequence', 'kind', 'payload'}, 'EXTERNAL_MESSAGE_SHAPE')
    need(value['version'] == 1 and type(value['version']) is int and value['runId'] == b['runId']
         and value['nonce'] == b['nonce'] and value['cell'] == b['cell'] and type(value['cell']) is int
         and value['node'] == node and value['sequence'] == sequence and type(value['sequence']) is int,
         'EXTERNAL_MESSAGE_BINDING')
    need(value['kind'] == kind and kind in KINDS and isinstance(value['payload'], dict), 'EXTERNAL_MESSAGE_ORDER')
    return value['payload']

def work_seconds(b, legacy, now=None):
    # Binding admission owns the finite maximum; recompute its original remainder.
    remaining=b['expiresAt']-(time.time() if now is None else now)-RESERVE
    need(math.isfinite(remaining) and remaining>0,'EXTERNAL_DEADLINE')
    return remaining if discovery_mode(b) else min(legacy,remaining)

class Channel:
    def __init__(self, b, node, incoming=None, outgoing=None, clock=time.time):
        self.binding = binding(b, clock())
        need(node in ('app-0', 'generator-0'), 'EXTERNAL_NODE')
        self.node, self.read_sequence, self.write_sequence = node, 0, 0
        self.incoming, self.outgoing, self.clock = incoming or sys.stdin, outgoing or sys.stdout, clock
        self.buffer = b''

    def send(self, kind, payload=None):
        need(kind in KINDS, 'EXTERNAL_MESSAGE_KIND')
        self.write_sequence += 1
        row = {'version': 1, 'runId': self.binding['runId'], 'nonce': self.binding['nonce'],
               'cell': self.binding['cell'], 'node': self.node, 'sequence': self.write_sequence,
               'kind': kind, 'payload': payload or {}}
        encoded = json.dumps(row, separators=(',', ':'))
        need(len(encoded.encode()) <= MAX_MESSAGE, 'EXTERNAL_MESSAGE_BOUND')
        self.outgoing.write(encoded + '\n')
        self.outgoing.flush()

    def receive(self, kind, maximum=1800):
        remaining = min(maximum, self.binding['expiresAt'] - self.clock() - RESERVE)
        need(remaining > 0, 'EXTERNAL_DEADLINE')
        deadline = time.monotonic() + remaining
        while b'\n' not in self.buffer:
            need(len(self.buffer) < MAX_MESSAGE, 'EXTERNAL_MESSAGE_BOUND')
            left = deadline - time.monotonic()
            need(left > 0, 'EXTERNAL_HANDSHAKE_TIMEOUT')
            ready, _, _ = select.select([self.incoming], [], [], left)
            need(bool(ready), 'EXTERNAL_HANDSHAKE_TIMEOUT')
            data = os.read(self.incoming.fileno(), min(4096, MAX_MESSAGE - len(self.buffer)))
            need(bool(data), 'EXTERNAL_HANDSHAKE_LOST_OR_OVERSIZE')
            self.buffer += data
        raw, self.buffer = self.buffer.split(b'\n', 1)
        need(len(raw) + 1 <= MAX_MESSAGE, 'EXTERNAL_MESSAGE_BOUND')
        self.read_sequence += 1
        return validate_message(json.loads(raw), self.binding, 'controller', self.read_sequence, kind)

# k6 summary-export 1.3.0 raw Rate and the pre-existing wrapped model schema.
# The selected immutable k6 image is qualified separately before traffic.
def k6_metric(metrics, key, field='count'):
    row=metrics.get(key)
    need(isinstance(row,dict),'EXTERNAL_METRIC_MISSING')
    if field=='rate':
        if set(row)=={'value','passes','fails'}:
            value,passes,fails=row['value'],row['passes'],row['fails']
            need(type(passes)is int and passes>=0 and type(fails)is int and fails>=0,'EXTERNAL_METRIC_INVALID')
            need(type(value)in(int,float)and math.isfinite(value)and 0<=value<=1,'EXTERNAL_METRIC_INVALID')
            total=passes+fails
            need(abs(value-(passes/total if total else 0))<=1e-12,'EXTERNAL_METRIC_INVALID')
            return value
        need(set(row)=={'values'}and isinstance(row['values'],dict)and set(row['values'])=={'rate'},'EXTERNAL_METRIC_INVALID')
        value=row['values']['rate']
        need(type(value)in(int,float)and math.isfinite(value)and 0<=value<=1,'EXTERNAL_METRIC_INVALID')
        return value
    need(field=='count','EXTERNAL_METRIC_INVALID')
    if set(row)=={'values'}:
        values=row['values']
        need(isinstance(values,dict)and set(values)<= {'count','rate'}and 'count'in values,'EXTERNAL_METRIC_INVALID')
    else:
        values=row
        need(set(values)<= {'count','rate','thresholds'}and 'count'in values,'EXTERNAL_METRIC_INVALID')
        if 'thresholds'in values:
            need(isinstance(values['thresholds'],dict)and all(isinstance(k,str)and type(v)is bool for k,v in values['thresholds'].items()),'EXTERNAL_METRIC_INVALID')
    value=values['count']
    need(type(value)is int and value>=0,'EXTERNAL_METRIC_INVALID')
    if 'rate'in values:
        rate=values['rate']
        need(type(rate)in(int,float)and math.isfinite(rate)and rate>=0 and(value!=0 or rate==0),'EXTERNAL_METRIC_INVALID')
    return value

def traffic_verdict(probe, metrics, tenants, clients=None):
    clients=2*tenants if clients is None else clients
    def from_value(key, field='count'):
        return k6_metric(metrics,key,field)
    need(probe.get('prime', {}).get('primed') == clients, 'EXTERNAL_PRIME_FAILED')
    window, restart = probe.get('window', {}), probe.get('restart', {})
    need(window.get('deliveredFrames') == window.get('expectedFrames') and type(window.get('expectedFrames')) is int
         and window['expectedFrames'] >= 0 and window.get('writes', {}).get('failed') == 0, 'EXTERNAL_FRAMES_OR_WRITES_FAILED')
    need(not restart and window.get('sockets') == clients and window.get('connectedAtEnd') == clients, 'REMOTE_NO_RESTART_OR_SOCKET_COUNT')
    need(from_value('writes_refused') == 0 and from_value('responses_refused') == 0 and from_value('http_req_failed', 'rate') == 0
         and from_value('dropped_iterations') == 0, 'EXTERNAL_HTTP_FAILED')
    need(window.get('writeToEvaluationMs') == {'measurement': 'UNMEASURED', 'reason': 'Per-write SQL latency observer NOT_RUN; strict progress remains app-side; no cross-host latency inferred'}, 'EXTERNAL_SQL_LATENCY_SCOPE')
    return True


def server_verdict(oracle, recovered, measurements, generator, b):
    need(oracle.get('verdict') == 'GREEN' and type(oracle.get('uncertain')) is int and oracle['uncertain'] == 0, 'EXTERNAL_ORACLE_FAILED')
    need(recovered == {'measurement': 'NOT_RUN', 'reason': 'noRestart diagnostic profile'}, 'REMOTE_NO_RESTART')
    need(measurements.get('complete') is True, 'EXTERNAL_SERVER_METRICS_MISSING')
    need(generator.get('complete') is True and generator.get('runId') == b['runId'] and generator.get('nonce') == b['nonce']
         and generator.get('samples') and all(type(row.get('cpuUsec')) is int and type(row.get('rssBytes')) is int
         and type(row.get('networkBytes')) is int for row in generator['samples']), 'EXTERNAL_GENERATOR_METRICS_MISSING')
    return True
