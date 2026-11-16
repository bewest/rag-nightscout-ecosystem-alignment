"""Strict calibration identities and an additive, SUT-local ingress overlay."""
import copy
import hashlib
import json
import re
import shlex
import subprocess
from protocol import prepared_cadence, need, private_ipv4, workload, discovery_mode

CORE = '5d305dd08f006b7956c5c9a647d5e541b307c9f1'
DEPLOY = '0dcde57e1dd3959e3420a6e1e4ff2ef65a40902d'
APP = 'sha256:544ab2001b46297aec069f32beacdc7a152711a521f83faea9630de38032472d'
POSTGRES = 'sha256:21e7e1665c3dd2fdd80ebd9ce6d36fb160d6a4129683b315b6492a71d87bfda7'
PRIMER_DEPLOY = 'df5362745a1b2d1b02b9186daedef3faccc14e58'
PRIMER_APP = 'sha256:153505ae2a2568cd8a081762506a6ca8d6c8eef3b7ad10529ca04c30993f8416'
REPAIRED_CORE = '7291af9b9cc48dbe58c488e892e7b34cf367c88e'
REPAIRED_APP = 'sha256:2a4e911fc9d4a06a4a25286c90d8d9fca835d873849eb6974c15bdb498d41ff8'
MINIMUM_CORE = '8aeefaefc88c79c3d548f7683d5651bec9cf5c01'
MINIMUM_APP = 'sha256:382e44696c4415e710698ee6135c499ae2d480d9f39a2fb85c59675fdd8d2150'
PERFORMANCE_CORE = 'd5ec3998986365034c3189485339ec12960ba3f7'
PERFORMANCE_DEPLOY = 'bf8327f4de096bb342a65ecb75ef7a356a21ffc9'
PERFORMANCE_APP = 'sha256:0775fcd95b0a1807b2de7345caa9547584265a3c1495af75d89fffe7350c49e2'
CADENCE = dict(warmupSeconds=10, idleSeconds=30, loadSeconds=310, accel=1,
               hotFactor=1, samplerIntervalSeconds=2, probeEveryMs=300000, restart=False, socketsPerTenant=2)

def qualified_source(pair, image):
    need((pair == {'core': CORE, 'deploy': DEPLOY} and image == APP) or
         (pair == {'core': CORE, 'deploy': PRIMER_DEPLOY} and image == PRIMER_APP) or
         (pair == {'core': REPAIRED_CORE, 'deploy': PRIMER_DEPLOY} and image == REPAIRED_APP) or
         (pair == {'core': MINIMUM_CORE, 'deploy': PRIMER_DEPLOY} and image == MINIMUM_APP) or
         (pair == {'core': PERFORMANCE_CORE, 'deploy': PERFORMANCE_DEPLOY} and image == PERFORMANCE_APP),
         'REMOTE_QUALIFIED_SOURCE_REQUIRED')

def performance_profile(value, selected):
    if value['pair']['core'] == PERFORMANCE_CORE and value.get('reportMode','strict')=='strict':
        need(value.get('tenants') == 1000 and selected['cadence'] == {**CADENCE, 'offeredRps': 180}
             and selected['primerConcurrency'] == 1 and 'componentCases' not in value,
             'REMOTE_PERFORMANCE_PROFILE')

def pins(b):
    # Discovery configuration is a request, not source qualification. The SUT
    # executes source/image/loader admission before ingress, export or runtime.
    if not discovery_mode(b):qualified_source(b['pair'], b['imageId'])
    performance_profile(b, workload(b))
    need(discovery_mode(b) or workload(b)['primerConcurrency'] == 1 or b['pair']['deploy'] in (PRIMER_DEPLOY, PERFORMANCE_DEPLOY),
         'REMOTE_PRIMER_CONCURRENCY_UNSUPPORTED_SOURCE')
    t = b['transport']
    need(isinstance(t, dict) and set(t) == {'interface', 'mac', 'approvedAddress', 'approvalReference'}, 'REMOTE_TRANSPORT_SHAPE')
    need(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,14}', t['interface']) and
         re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}', t['mac']) and
         t['approvedAddress'] == b['appAddress'] and private_ipv4(t['approvedAddress']) and
         isinstance(t['approvalReference'], str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}', t['approvalReference']),
         'REMOTE_PROVIDER_APPROVAL_REQUIRED')

def cell_contract(m, b=None):
    bound=b or m.get('preparedExternalBinding') or m.get('externalBinding') or {'tenants':m.get('tenants')}
    exploratory=discovery_mode(bound)
    need(m.get('pgstreamTopology','colocated-v1')==bound.get('pgstreamTopology','colocated-v1') and m.get('diagnosticResources',{}).get('profile')==bound.get('diagnosticResourceProfile'),'REMOTE_TOPOLOGY_CELL_CHANGED')
    selected=workload(bound)
    if not exploratory:qualified_source(m.get('pair'),m.get('imageId'))
    performance_profile({**m,'reportMode':bound.get('reportMode','strict')},selected)
    if exploratory or m['pair']['core'] in (REPAIRED_CORE, MINIMUM_CORE, PERFORMANCE_CORE):
        need(m.get('completionContract') == 'evaluator-work-v2', 'REMOTE_REPAIRED_COMPLETION_V2_REQUIRED')
    if b is not None:
        need(m.get('tenants') == b['tenants'] and m.get('pair') == b['pair'] and m.get('imageId') == b['imageId'], 'REMOTE_CELL_BINDING_CHANGED')
    need(m.get('postgresImageId') == POSTGRES, 'REMOTE_QUALIFIED_SOURCE_REQUIRED')
    need(exploratory or selected['primerConcurrency'] == 1 or m['pair']['deploy'] in (PRIMER_DEPLOY,PERFORMANCE_DEPLOY), 'REMOTE_PRIMER_CONCURRENCY_UNSUPPORTED_SOURCE')
    need(m.get('profile') == 'pgstream-sample' and m.get('runPurpose') == 'discovery' and
         m.get('measurementMode', 'accepted') == 'accepted' and type(m.get('tenants')) is int and (1<=m['tenants']<=10000 if exploratory else m['tenants'] in (10, 1000, 3000, 5000, 10000)) and
         m.get('replicas') == 1 and m.get('cadence') == prepared_cadence(bound) and m.get('primerConcurrency', 1) == selected['primerConcurrency'], 'REMOTE_EXPLICIT_CADENCE_REQUIRED')

def local_nics():
    # This executes only on the SUT, never on the controller/load generator.
    return json.loads(subprocess.check_output(['ip', '-j', 'address', 'show'], timeout=10))

def owned_nic(b, nics):
    pins(b)
    t = b['transport']
    found = [n for n in nics if n.get('ifname') == t['interface'] and n.get('address') == t['mac'] and
             'UP' in n.get('flags', []) and any(a.get('family') == 'inet' and a.get('local') == b['appAddress']
                                             and a.get('scope') == 'global' for a in n.get('addr_info', []))]
    need(len(found) == 1, 'REMOTE_ADDRESS_NOT_ON_APPROVED_SUT_NIC')
    return {'interface': t['interface'], 'mac': t['mac'], 'address': b['appAddress']}

def firewall_rules(b):
    chain = 'NSPG' + b['nonce'][:12]
    selector = '-d '+b['appAddress']+'/32 -p tcp -m tcp --dport '+str(b['port'])
    return chain, ['-A PREROUTING '+selector+' -j '+chain,
                   '-A '+chain+' -i '+b['transport']['interface']+' -s '+b['generatorAddress']+'/32 -j ACCEPT', '-A '+chain+' -j DROP']

def firewall_check(b, saved=None):
    # raw/PREROUTING filters the original destination before Docker DNAT;
    # INPUT-only or post-DNAT port rules would not protect this publication.
    if saved is None:
        saved = subprocess.check_output(['sudo', '-n', 'iptables-save', '-t', 'raw'], text=True, timeout=10)
    chain, expected = firewall_rules(b)
    code = 'REMOTE_GENERATOR_ONLY_FIREWALL_REQUIRED'
    try:
        rows = [shlex.split(line) for line in saved.splitlines() if line.startswith('-A ')]
    except ValueError:
        need(False, code)
    def predicates(row):
        need(len(row) >= 4 and row[0] == '-A' and len(row[2:]) % 2 == 0, code)
        result = {}
        for option, value in zip(row[2::2], row[3::2]):
            need(option in ('-d', '-p', '-m', '--dport', '-j', '-s', '-i') and
                 option not in result and value != '!' and not value.startswith('-'), code)
            result[option] = value
        return row[1], result
    # Only argument order is immaterial. Rule order, exact predicates and the
    # single leading jump remain obligations; no unknown or duplicate option.
    first = [row for row in rows if row[:2] == ['-A', 'PREROUTING']][:1]
    owned = [row for row in rows if row[:2] == ['-A', chain]]
    references = sum(any(row[i] in ('-j', '-g') and row[i+1] == chain
                         for i in range(len(row)-1)) for row in rows)
    need(len(first) == 1 and len(owned) == 2 and references == 1, code)
    need([predicates(row) for row in [first[0], *owned]] ==
         [predicates(shlex.split(row)) for row in expected], code)
    return {'table': 'raw', 'rules': expected, 'sha256': hashlib.sha256(saved.encode()).hexdigest()}

def overlay(config, b, nics, firewall):
    nic = owned_nic(b, nics)
    need(firewall.get('rules') == firewall_rules(b)[1], 'REMOTE_GENERATOR_ONLY_FIREWALL_REQUIRED')
    before = copy.deepcopy(config)
    published = [(name, port) for name, service in before['services'].items() for port in service.get('ports', [])]
    need(len(published) == 1 and published[0][0] == 'nginx', 'REMOTE_EDGE_ROSTER')
    port = published[0][1]
    need(port.get('host_ip') == '127.0.0.1' and int(port['published']) == b['port'] and
         int(port['target']) == 8080 and port.get('protocol', 'tcp') == 'tcp', 'REMOTE_LOOPBACK_REQUIRED')
    after = copy.deepcopy(before)
    private = copy.deepcopy(port); private['host_ip'] = b['appAddress']
    after['services']['nginx']['ports'].append(private)
    digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return after, {'profile': 'remote-pgstream-calibration-v1', 'beforeSha256': digest(before),
                   'afterSha256': digest(after), 'patch': [{'op': 'add', 'path': '/services/nginx/ports/1', 'value': private}],
                   'providerNic': nic, 'approvalReference': b['transport']['approvalReference'], 'firewall': firewall}


def verify_overlay(config, b, evidence):
    published = [(name, port) for name, service in config['services'].items() for port in service.get('ports', [])]
    need(len(published) == 2 and all(name == 'nginx' for name, port in published), 'REMOTE_EDGE_ROSTER')
    ports = [port for _, port in published]
    need([port.get('host_ip') for port in ports] == ['127.0.0.1', b['appAddress']] and
         all(int(port['published']) == b['port'] and int(port['target']) == 8080 and port.get('protocol', 'tcp') == 'tcp' for port in ports),
         'REMOTE_DUAL_BIND_REQUIRED')
    digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    need(evidence.get('afterSha256') == digest(config), 'REMOTE_OVERLAY_HASH_CHANGED')
    original = copy.deepcopy(config); original['services']['nginx']['ports'].pop()
    need(evidence.get('beforeSha256') == digest(original) and evidence.get('approvalReference') == b['transport']['approvalReference'], 'REMOTE_OVERLAY_BASE_CHANGED')
