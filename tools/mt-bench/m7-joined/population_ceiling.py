"""One optional deployment population ceiling; pages, caches and bytes are separate."""
import hashlib
import json
from pathlib import Path

import primer_options
import workload_inputs

FIELD = 'populationCeiling'
PROTOCOL_FIELD = 'populationCeilingProtocol'
PROTOCOL = 'population-ceiling-v1'
ENV = 'NS_DEMO_POPULATION_CEILING'
DEFAULT = 10000
MAX_SYNTHETIC_TENANTS = 0x100000000 - 0x30000000
SOURCE_PREFIX = 'bindings/compose/multitenant/'
SOURCE_FILES = ('population-ceiling.js', 'config.js', 'registry-plan.js', 'registry-bootstrap.js', 'prime.js', 'bootstrap.js')
DECLARATION = b"const PROTOCOL = 'population-ceiling-v1';"


def selection(value, tenants, need):
    if value is None:
        return None
    need(workload_inputs.tenants(value), 'POPULATION_CEILING_INVALID')
    need(workload_inputs.tenants(tenants) and tenants <= value, 'POPULATION_SEED_OVER_CEILING')
    need(tenants <= MAX_SYNTHETIC_TENANTS, 'POPULATION_SEED_UUID_UNREPRESENTABLE')
    return value


def from_profile(profile, need):
    population = profile.get('population', {})
    if 'maxTenants' not in population:
        return None
    need(population['maxTenants'] is not None, 'POPULATION_CEILING_INVALID')
    return selection(population.get('maxTenants'), population.get('provisionedTenants'), need)


def commissioning(tenants, options=None):
    """Fresh-seed chunk arithmetic, never a DATA completion observation."""
    chosen=dict(options or {})
    maximum=chosen.get('maxTenants',primer_options.DEFAULT_MAX_TENANTS)
    return {'scope':'READ_DERIVED_FRESH_SEED_CHUNK_BUDGET','freshSeedTenants':tenants,'selected':chosen,
            'representation':{'maximumWholeRegistryArrayTenants':workload_inputs.MAX_ARRAY_LENGTH,
                              'maximumFreshSyntheticSeedTenants':MAX_SYNTHETIC_TENANTS,
                              'seedBasis':'Eight-hex-digit UUID first component 0x30000000+index; no capacity claim'},
            'effective':{'concurrency':chosen.get('concurrency',primer_options.DEFAULT_CONCURRENCY),'maxTenants':maximum},
            'freshSeedWithinChunk':min(tenants,maximum),'freshSeedBeyondChunk':max(0,tenants-maximum),
            'coverage':'PARTIAL_CHUNK_BUDGET' if tenants>maximum else 'FULL_CHUNK_BUDGET',
            'actualDataResult':'UNMEASURED'}


def source_protocol(files):
    return PROTOCOL if DECLARATION in files.get('population-ceiling.js', b'').splitlines() else None


def source_hashes(files, need):
    need(set(files) == set(SOURCE_FILES) and source_protocol(files) == PROTOCOL, 'POPULATION_SOURCE_UNSUPPORTED')
    return {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}


def image_probe():
    return r"""
const fs=require('node:fs'),crypto=require('node:crypto');
const root='/opt/app/deploy/multitenant/',expected=JSON.parse(process.argv[1]),limit=Number(process.argv[2]);
for(const [name,hash] of Object.entries(expected))if(crypto.createHash('sha256').update(fs.readFileSync(root+name)).digest('hex')!==hash)throw Error('POPULATION_IMAGE_SOURCE_CHANGED');
const population=require(root+'population-ceiling');
process.env[population.ENV]=String(limit);process.env.NS_DEMO_TENANTS=String(Math.min(2,limit));
const plan=require(root+'config'),layout=plan.layout('population_probe');
const urls=Object.fromEntries(Object.keys(layout.roles).map(role=>[role,'postgres://'+role+':synthetic@postgres/nightscout_compose_test']));
const docs=plan.documents({layout,urls,tokens:[],publicKeys:[],managementKeys:[],vaultAddress:'https://vault:8200'});
const config={version:1,adminOrigin:'http://admin:1342',apiOrigin:'http://api:1337',ownerConsumer:'synthetic',seed:plan.tenantIds(),...docs.populationCeiling};
require(root+'prime').parseConfig(config);
let overSeedRefused=false,protocolRefused=false;
const oversized=new Proxy([],{get:(target,key)=>key==='length'?limit+1:Reflect.get(target,key)});
try{require(root+'prime').parseConfig({...config,seed:oversized});}catch(error){if(error.code==='PRIMER_CONFIG_INVALID')overSeedRefused=true;else throw error;}
try{require(root+'prime').parseConfig({...config,populationCeilingProtocol:'unsupported'});}catch(error){if(error.code==='POPULATION_CEILING_INVALID')protocolRefused=true;else throw error;}
if(!overSeedRefused||!protocolRefused)throw Error('POPULATION_IMAGE_SOURCE_IGNORED');
console.log(JSON.stringify({protocol:population.PROTOCOL,sourceFilesSha256:expected,populationCeiling:config.populationCeiling,
  seedCount:config.seed.length,overSeedRefused,protocolRefused,effective:{api:docs.configs.api.socketForwarding.maxTenants,evaluator:docs.configs.evaluator.maxTenants,realtime:docs.configs.realtime.maxTenants,primer:population.privateCeiling(config)}}));
"""


def probe_image(command, image, files, value, need):
    hashes = source_hashes(files, need)
    result = primer_options.probe_constructor(command, image, image_probe(), [json.dumps(hashes), str(value)], need)
    expected = {'protocol': PROTOCOL, 'sourceFilesSha256': hashes, FIELD: value,
                'seedCount': min(2, value), 'overSeedRefused':True, 'protocolRefused':True,
                'effective': {role: value for role in ('api', 'evaluator', 'realtime', 'primer')}}
    need(isinstance(result,dict) and type(result.get(FIELD)) is int and type(result.get('seedCount')) is int and
         result.get('overSeedRefused') is True and result.get('protocolRefused') is True and
         all(type(result.get('effective',{}).get(role)) is int for role in ('api','evaluator','realtime','primer')) and
         result == expected, 'POPULATION_IMAGE_SOURCE_CHANGED')
    return result


def verify_image(directory, manifest, need):
    value = manifest.get(FIELD)
    if value is None:
        return
    reference=manifest.get('imageInputPreflight', {})
    proof = reference.get('populationSource', {})
    try:
        files = {name: (Path(directory)/'core/deploy/multitenant'/name).read_bytes() for name in SOURCE_FILES}
    except OSError:
        need(False,'POPULATION_IMAGE_SOURCE_CHANGED')
    need(reference.get('appImageId')==manifest.get('imageId') and
         proof.get(FIELD) == value and proof.get('protocol') == PROTOCOL and
         proof.get('overSeedRefused') is True and proof.get('protocolRefused') is True and
         proof.get('sourceFilesSha256') == source_hashes(files, need) and
         proof.get('effective') == {role: value for role in ('api', 'evaluator', 'realtime', 'primer')},
         'POPULATION_IMAGE_SOURCE_CHANGED')


def project_compose(config, value, need, *, verify=False):
    if value is None:
        return
    environment = config['services']['bootstrap'].setdefault('environment', {})
    need(ENV not in environment or environment[ENV] == str(value), 'POPULATION_CONFIGURATION_CHANGED')
    if verify:
        need(environment.get(ENV) == str(value), 'POPULATION_CONFIGURATION_CHANGED')
    else:
        environment[ENV] = str(value)


def effective_documents(documents, value, tenants, need):
    """Read existing generated/private JSON; never retain credential values."""
    primer = documents['primer']
    need(type(primer.get(FIELD)) is int and primer.get(FIELD) == value and primer.get(PROTOCOL_FIELD) == PROTOCOL and
         isinstance(primer.get('seed'), list) and len(primer['seed']) == tenants <= value,
         'POPULATION_PRIMER_CHANGED')
    result = {'primer': value}
    for role, config in documents.items():
        if role == 'primer':
            continue
        base = next((base for base in ('api', 'evaluator', 'realtime') if role == base or role.startswith(base+'-')), role)
        if base not in ('api', 'evaluator', 'realtime'):
            continue
        effective = config.get('socketForwarding', {}).get('maxTenants') if base == 'api' else config.get('maxTenants')
        need(type(effective) is int and effective == value, 'POPULATION_ROLE_CHANGED')
        result[role] = effective
    need(all(any(role == base or role.startswith(base+'-') for role in result) for base in ('api', 'evaluator', 'realtime')), 'POPULATION_ROLE_MISSING')
    return result


def local_readback(directory, manifest, need):
    value = manifest.get(FIELD)
    if value is None:
        return None
    state = Path(directory)/'state'
    paths = {'primer': state/'primer/config.json'}
    config = json.loads((Path(directory)/'frozen.compose.json').read_bytes())
    for role, spec in config['services'].items():
        if isinstance(spec.get('command'), list) and spec['command'][-1:] and spec['command'][-1] in ('api', 'evaluator', 'realtime'):
            paths[role] = state/role/'config.json'
    documents = {role: json.loads(path.read_bytes()) for role, path in paths.items()}
    effective = effective_documents(documents, value, manifest['tenants'], need)
    return {FIELD: value, PROTOCOL_FIELD: PROTOCOL, 'effective': effective,
            'configurationSha256': {role: hashlib.sha256(path.read_bytes()).hexdigest() for role, path in paths.items()}}


READBACK = r"""const fs=require('node:fs'),crypto=require('node:crypto'),role=process.argv[1];
if(!['api','evaluator','realtime','primer'].includes(role))throw Error('POPULATION_ROLE_INVALID');
const raw=fs.readFileSync(role==='primer'?'/run/ns-primer/config.json':'/run/ns-config/config.json'),c=JSON.parse(raw);
console.log(JSON.stringify({sha256:crypto.createHash('sha256').update(raw).digest('hex'),
  effective:role==='api'?c.socketForwarding?.maxTenants:role==='primer'?c.populationCeiling:c.maxTenants,
  ...(role==='primer'?{protocol:c.populationCeilingProtocol,seedCount:c.seed?.length}:{})}));"""


def capture(k, c, observation, client):
    value = c.get(FIELD)
    if value is None:
        return None
    result = {FIELD: value, PROTOCOL_FIELD: PROTOCOL, 'roles': {}}
    for role in ('api', 'evaluator', 'realtime', 'primer'):
        if role == 'primer':
            pods = [p for p in observation['pods'].values() if p['workload'] == 'Job/primer' and p['containers'].get('done', {}).get('ready')]
            k.need(len(pods) == 1, 'POPULATION_READBACK_OWNER')
            pod = pods[0]; name, container = pod['name'], 'done'
        else:
            name, container = k.selected_pod(c, observation, role)
            pod = observation['pods'][name]
        raw = client.call(['exec', name, '-c', container, '--', 'node', '-e', READBACK, role], read=False)
        k.need(len(raw) <= 1024, 'POPULATION_READBACK_CHANGED')
        try:observed = json.loads(raw)
        except ValueError:k.need(False,'POPULATION_READBACK_CHANGED')
        k.need(isinstance(observed,dict) and set(observed)==({'effective','sha256','protocol','seedCount'} if role=='primer' else {'effective','sha256'}),
               'POPULATION_READBACK_CHANGED')
        k.need(type(observed.get('effective')) is int and observed.get('effective') == value and isinstance(observed.get('sha256'), str) and
               k.HEX.fullmatch(observed['sha256']), 'POPULATION_READBACK_CHANGED')
        if role == 'primer':
            k.need(observed.get('protocol') == PROTOCOL and observed.get('seedCount') == c['tenants'] <= value,
                   'POPULATION_READBACK_CHANGED')
        result['roles'][role] = {**observed, 'podUid': pod['uid'], 'containerId': pod['containers'][container]['containerID']}
    return result


def verify_capture(k, c, baseline, receipt):
    value = c.get(FIELD)
    if value is None:
        k.need(receipt is None, 'POPULATION_READBACK_CHANGED')
        return
    k.need(isinstance(receipt, dict) and receipt.get(FIELD) == value and receipt.get(PROTOCOL_FIELD) == PROTOCOL and
           set(receipt.get('roles', {})) == {'api', 'evaluator', 'realtime', 'primer'}, 'POPULATION_READBACK_CHANGED')
    for role, row in receipt['roles'].items():
        k.need(isinstance(row,dict),'POPULATION_READBACK_CHANGED')
        if role == 'primer':
            pods = [p for p in baseline['pods'].values() if p['workload'] == 'Job/primer']
            k.need(len(pods) == 1, 'POPULATION_READBACK_OWNER')
            pod, container = pods[0], 'done'
            k.need(row.get('protocol') == PROTOCOL and row.get('seedCount') == c['tenants'], 'POPULATION_READBACK_CHANGED')
        else:
            name, container = k.selected_pod(c, baseline, role)
            pod = baseline['pods'][name]
        k.need(type(row.get('effective')) is int and row.get('effective') == value and isinstance(row.get('sha256'),str) and k.HEX.fullmatch(row['sha256']) and
               row.get('podUid') == pod['uid'] and row.get('containerId') == pod['containers'][container]['containerID'],
               'POPULATION_READBACK_OWNER')


def check_render(manifest, inventory, objects, need):
    value=from_profile(manifest['profile'],need)
    need(inventory.get(FIELD)==value,'POPULATION_RENDER_CHANGED')
    found=[]
    values=objects.values() if isinstance(objects,dict) else objects
    for obj in values:
        for container in obj.get('spec',{}).get('template',{}).get('spec',{}).get('initContainers',[]):
            if container.get('name')=='bootstrap':
                found.extend(row.get('value') for row in container.get('env',[]) if row.get('name')==ENV)
    need(found==([] if value is None else [str(value)]),'POPULATION_RENDER_CHANGED')
