"""Projections of the existing runner configuration; no execution or authority.

The adapter parser and cadence resolver own supported knobs. Transport overlays
carry paths/addresses and observed host inventory, never another workload.
"""
import copy
import hashlib
import ipaddress
import json
from contract import require


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_prepare(args):
    import adapter as a
    cadence = a.cadence_options(args)
    require(args.measurement_mode=='accepted','M7_CONFIG_DISCOVERY_MEASUREMENT_MODE')
    require(type(args.tenants) is int and 1 <= args.tenants <= 10000 and args.replicas == 1,
            'M7_CONFIG_SINGLE_API_TENANT_RANGE')
    a.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)
    a.primer_concurrency(args.primer_concurrency)
    a.jwt_setup_concurrency(args.jwt_setup_concurrency)
    a.fixture_project(args, '0'*32)
    networks = [ipaddress.ip_network(getattr(args, key), strict=True) for key in ('backend_subnet', 'edge_subnet')]
    private=[ipaddress.ip_network(c) for c in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    require(all(n.version==4 and any(n.subnet_of(p) for p in private) for n in networks) and not networks[0].overlaps(networks[1]),
            'M7_CONFIG_SUBNET_OVERLAP_OR_PUBLIC')
    selected = a.diagnostic_resources.selection(args.diagnostic_resource_profile)
    external = args.pgstream_topology == a.stream_topology.EXTERNAL
    require(not selected or external == (selected in a.diagnostic_resources.EXTERNAL_PROFILES),
            'M7_CONFIG_RESOURCE_TOPOLOGY')
    require(not selected or args.generator_dependencies, 'M7_DIAGNOSTIC_DEPENDENCIES_REQUIRED')
    return cadence


def from_args(args, instrument):
    import adapter as a
    # This is semantic input, independent of transport paths and observed limits.
    cadence = validate_prepare(args)
    profile = args.diagnostic_resource_profile
    resources = None if profile is None else {
        'profile': profile, 'millicpus': a.diagnostic_resources.cpu_ceiling(profile),
        'memoryBytes': a.diagnostic_resources.memory_ceiling(profile)}
    return {'version': 1, 'pair': {'core': args.core_commit, 'deploy': args.deploy_commit},
            'imageId': args.image_id or args.image, 'instrument': instrument,
            'postgresImageId': args.postgres_image, 'profile': args.profile,
            'runPurpose': args.run_purpose, 'tenants': args.tenants, 'replicas': args.replicas,
            'cadence': cadence, 'primerConcurrency': args.primer_concurrency,
            'jwtSetupConcurrency': args.jwt_setup_concurrency,
            'pgstreamTopology': args.pgstream_topology, 'resources': resources,
            'completionContract': args.completion_contract,
            'diagnostics':a.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)}


def from_manifest(m):
    import adapter as a
    profile = m.get('diagnosticResources', {}).get('profile')
    resources = None if profile is None else {'profile': profile,
        'millicpus': a.diagnostic_resources.cpu_ceiling(profile),
        'memoryBytes': a.diagnostic_resources.memory_ceiling(profile)}
    return {'version': 1, **{k: m.get(k) for k in ('pair','imageId','profile','runPurpose','tenants','replicas','cadence','completionContract')},
            'instrument': m['instrument']['sha256'], 'postgresImageId': m.get('postgresImageId'),
            'primerConcurrency': m.get('primerConcurrency',1), 'jwtSetupConcurrency': m.get('jwtSetupConcurrency',1),
            'pgstreamTopology': m.get('pgstreamTopology',a.stream_topology.COLOCATED), 'resources': resources,
            'diagnostics':m.get('diagnostics',a.profile_provenance.selection())}


def resolve(config, source_acceptance=None):
    import runner
    import adapter as a
    _, argv = runner.validate_config(config)
    args = a.parser().parse_args(['prepare','--directory','/tmp/m7-projection',*argv])
    resolved = from_args(args, a.instrument()['sha256'])
    limits={'tenants':resolved['tenants'],'apiReplicas':resolved['replicas'],'trafficSeconds':resolved['cadence']['loadSeconds']}
    acceptance=source_acceptance if source_acceptance is not None else {'status':'PENDING'}
    template={'version':2,'kind':'joined-diagnostic','status':'DRAFT','purpose':'BOUNDED_DISCOVERY',
              'pair':resolved['pair'],'imageId':resolved['imageId'],'instrument':resolved['instrument'],
              'sourceAcceptance':acceptance,'functionalAcceptanceAtAuthorization':acceptance.get('status'),
              'configurationSha256':sha(resolved),'limits':limits,
              'execution':{'workSeconds':config['workSeconds'],'cleanupSeconds':config['cleanupSeconds'],'k6Image':config['k6Image']}}
    from contract import discovery_authorization
    discovery_authorization({**resolved,'instrument':{'sha256':resolved['instrument']},'runConfiguration':resolved},template)
    return {'configuration': resolved, 'configurationSha256': sha(resolved), 'diagnosticReceiptTemplate':template,
            'receiptLimits': {'tenants': resolved['tenants'], 'apiReplicas': resolved['replicas'],
                              'trafficSeconds': resolved['cadence']['loadSeconds']},
            'workSeconds': config['workSeconds'], 'cleanupSeconds': config['cleanupSeconds'],
            'k6Image': config['k6Image']}


def remote_projection(config, overlay, source_acceptance=None):
    """Generate an existing discovery binding. No provisioning or permission grant."""
    import sys
    from pathlib import Path
    remote = Path(__file__).resolve().parent.parent/'remote-pgstream'
    previous=list(sys.path)
    try:
        sys.path.insert(0,str(remote))
        import protocol
        import transport
    finally:
        sys.path[:]=previous
    result = resolve(config,source_acceptance); r = result['configuration']
    require(r['postgresImageId']==transport.POSTGRES,'M7_CONFIG_REMOTE_POSTGRES_UNSUPPORTED')
    require(isinstance(overlay,dict) and set(overlay)=={'binding','hostInventory','resourceReference'}, 'M7_CONFIG_REMOTE_OVERLAY_FIELDS')
    b = copy.deepcopy(overlay['binding'])
    # Caller owns transport/authority; semantic mirrors are generated exclusively.
    require(not set(b).intersection({'tenants','pair','imageId','k6Image','workload','reportMode','pgstreamTopology','diagnosticResourceProfile'}),
            'M7_CONFIG_REMOTE_MIRROR_REFUSED')
    cadence = dict(r['cadence']); viewers = cadence.get('logicalPollingClients',r['tenants']*cadence['socketsPerTenant'])
    b.update(tenants=r['tenants'], pair=r['pair'], imageId=r['imageId'], reportMode='discovery',
             k6Image='grafana/k6@'+config['k6Image'], workload={
                 'cadence':cadence, 'primerConcurrency':r['primerConcurrency'], 'jwtSetupConcurrency':r['jwtSetupConcurrency'],
                 'resourcePlan':{'reference':overlay['resourceReference'], 'tenants':r['tenants'],
                                 'logicalPollingClients':viewers, 'hosts':overlay['hostInventory']}})
    if r['pgstreamTopology']!='colocated-v1':
        b.update(pgstreamTopology=r['pgstreamTopology'],diagnosticResourceProfile=r['resources']['profile'] if r['resources'] else None)
    protocol.binding(b)
    require(protocol.prepared_cadence(b)==r['cadence'], 'M7_CONFIG_REMOTE_CADENCE_DRIFT')
    return {**result, 'binding':b, 'remoteReceiptProjection':{
        'remoteProfile':b['profile'], 'remoteTransport':b['transport'], 'remoteExtensionSha256':b['sourceSha256'],
        'remoteReportMode':b['reportMode'], 'remoteWorkload':b['workload'],
        'remotePgstreamTopology':b.get('pgstreamTopology'), 'remoteDiagnosticResourceProfile':b.get('diagnosticResourceProfile'),
        'remoteHelperDependencies':b.get('helperDependencies'), 'completionContract':r['completionContract']}}


def validate_execution(config, receipt):
    if receipt.get('version')!=2:return
    expected={k:config[k] for k in ('workSeconds','cleanupSeconds','k6Image')}
    require(receipt.get('execution')==expected,'M7_DIAGNOSTIC_EXECUTION_MISMATCH')


def namespace_preflight(args):
    """Read the actual daemon immediately before preparation; never reserve it."""
    import adapter as a
    validate_prepare(args)
    require(args.fixture_project is not None,'M7_CONFIG_EXPLICIT_PROJECT_REQUIRED')
    a.unused_project_namespace(args.fixture_project)
    require(not a.resources({'project':args.fixture_project}),'M7_PROJECT_EXISTS')
    ids=a.command(['docker','network','ls','-q']).split()
    rows=json.loads(a.command(['docker','network','inspect',*ids])) if ids else []
    selected=[ipaddress.ip_network(getattr(args,k)) for k in ('backend_subnet','edge_subnet')]
    for row in rows:
        for entry in (row.get('IPAM',{}).get('Config') or []):
            if not entry.get('Subnet'):continue
            observed=ipaddress.ip_network(entry['Subnet'],strict=False)
            require(not any(observed.version==n.version and observed.overlaps(n) for n in selected),
                    'M7_CONFIG_LIVE_SUBNET_OVERLAP')
    return {'status':'PASS','scope':'namespace and CIDR readback only; no reservation'}
