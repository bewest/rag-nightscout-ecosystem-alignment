"""Projections of the existing runner configuration; no execution or authority.

The adapter parser and cadence resolver own supported knobs. Transport overlays
carry paths/addresses and observed host inventory, never another workload.
"""
import copy
import hashlib
import ipaddress
import json
import commissioning_wal
import workload_inputs
from contract import require, REPLICAS, discovery_api_replicas


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_prepare(args):
    import adapter as a
    cadence = a.cadence_options(args)
    a.node_observation.option(args)
    a.api_warm_cause.option(args)
    static = a.static_topology.option(args)
    commissioning_wal.option(args)
    a.stream_topology.ack_option(args)
    a.preload_convergence.option(args)
    require(args.measurement_mode=='accepted','M7_CONFIG_DISCOVERY_MEASUREMENT_MODE')
    require(workload_inputs.tenants(args.tenants) and (args.run_purpose=='discovery' or args.tenants<=10000)
            and (discovery_api_replicas(args.replicas) if args.run_purpose=='discovery'
                 else type(args.replicas) is int and args.replicas in REPLICAS)
            and (args.replicas == 1 or static),
            'M7_CONFIG_SINGLE_API_TENANT_RANGE')
    a.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)
    a.primer_concurrency(args.primer_concurrency)
    a.jwt_setup_concurrency(args.jwt_setup_concurrency, args.run_purpose=='discovery')
    a.fixture_project(args, '0'*32)
    networks = [ipaddress.ip_network(getattr(args, key), strict=True) for key in ('backend_subnet', 'edge_subnet')]
    private=[ipaddress.ip_network(c) for c in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    require(all(n.version==4 and any(n.subnet_of(p) for p in private) for n in networks) and not networks[0].overlaps(networks[1]),
            'M7_CONFIG_SUBNET_OVERLAP_OR_PUBLIC')
    selected = a.selected_resources_profile(args)
    external = args.pgstream_topology == a.stream_topology.EXTERNAL
    require(not selected or external == a.diagnostic_resources.external_selection(selected),
            'M7_CONFIG_RESOURCE_TOPOLOGY')
    require(not selected or args.generator_dependencies, 'M7_DIAGNOSTIC_DEPENDENCIES_REQUIRED')
    return cadence


def from_args(args, instrument):
    import adapter as a
    # This is semantic input, independent of transport paths and observed limits.
    cadence = validate_prepare(args)
    profile = a.selected_resources_profile(args)
    resources = None if profile is None else {
        'profile': profile, 'millicpus': a.diagnostic_resources.cpu_ceiling(profile),
        'memoryBytes': a.diagnostic_resources.memory_ceiling(profile)}
    return {**commissioning_wal.option(args), **a.stream_topology.ack_option(args), **a.preload_convergence.option(args), **({'tenantReadiness':args.tenant_readiness} if getattr(args,'tenant_readiness',None) else {}), **a.static_topology.option(args), **a.node_observation.option(args), **a.api_warm_cause.option(args), **({'apiCauseObservation':'on'} if getattr(args,'api_cause_observation','off')=='on' else {}),'version': 1, 'pair': {'core': args.core_commit, 'deploy': args.deploy_commit},
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
    node = m.get('nodeObservation')
    warm = m.get('apiWarmCause')
    return {**({'staticBuildReceiptSha256': m['staticBuildReceiptSha256']} if m.get('staticBuildReceiptSha256') else {}),
            **commissioning_wal.from_manifest(m), **a.stream_topology.ack_selection(m), **a.preload_convergence.selection(m), **({'tenantReadiness':m['tenantReadiness']} if m.get('tenantReadiness') else {}), **({'staticTopology':m['staticTopology']} if m.get('staticTopology') else {}),**({'nodeObservationMode':node['mode']} if node else {}),
            **({'apiWarmCauseMode':warm['mode']} if warm else {}),
            **({'apiCauseObservation':'on'} if m.get('apiCause') else {}),'version': 1, **{k: m.get(k) for k in ('pair','imageId','profile','runPurpose','tenants','replicas','cadence','completionContract')},
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
    limits={'tenants':resolved['tenants'],'apiReplicas':resolved['replicas'],'trafficSeconds':resolved['cadence']['loadSeconds'],**({'staticWorkers':resolved['staticTopology']['workers']} if resolved.get('staticTopology') else {})}
    acceptance=source_acceptance if source_acceptance is not None else {'status':'PENDING'}
    template={'version':2,'kind':'joined-diagnostic','status':'DRAFT','purpose':'BOUNDED_DISCOVERY',
              'pair':resolved['pair'],'imageId':resolved['imageId'],'instrument':resolved['instrument'],
              'sourceAcceptance':acceptance,'functionalAcceptanceAtAuthorization':acceptance.get('status'),
              'configurationSha256':sha(resolved),'limits':limits,
              'execution':{'workSeconds':config['workSeconds'],'cleanupSeconds':config['cleanupSeconds'],'k6Image':config['k6Image']}}
    if config['workSeconds'] is None:
        template['executionScope'] = 'LOCAL_OWNED_TO_COMPLETION'
    from contract import discovery_authorization
    discovery_authorization({**resolved,'instrument':{'sha256':resolved['instrument']},'runConfiguration':resolved},template)
    return {'configuration': resolved, 'configurationSha256': sha(resolved), 'diagnosticReceiptTemplate':template,
            'receiptLimits': limits,
            'workSeconds': config['workSeconds'], 'cleanupSeconds': config['cleanupSeconds'],
            'k6Image': config['k6Image']}


def remote_projection(config, overlay, source_acceptance=None):
    """Generate an existing discovery binding. No provisioning or permission grant."""
    import sys
    from pathlib import Path
    import adapter as a
    remote = Path(__file__).resolve().parent.parent/'remote-pgstream'
    previous=list(sys.path)
    try:
        sys.path.insert(0,str(remote))
        import protocol
        import transport
    finally:
        sys.path[:]=previous
    require(config['workSeconds'] is not None, 'M7_REMOTE_TO_COMPLETION_UNSUPPORTED')
    result = resolve(config,source_acceptance); r = result['configuration']
    if r.get('staticTopology'):
        require(r['staticTopology']=={'kind':'static-hash-v1','workers':1} and r['replicas']==1 and isinstance((r.get('resources')or{}).get('profile'),dict),'M7_STATIC_REMOTE_K1_N1_ONLY')
    require(not (r.get('nodeObservationMode') or r.get('apiWarmCauseMode') or r['cadence'].get('driverVuDiagnostic')),
            'M7_LOCAL_OBSERVER_LOCAL_ONLY')
    require(r['postgresImageId']==transport.POSTGRES,'M7_CONFIG_REMOTE_POSTGRES_UNSUPPORTED')
    require(isinstance(overlay,dict) and set(overlay)=={'binding','hostInventory','resourceReference'}, 'M7_CONFIG_REMOTE_OVERLAY_FIELDS')
    b = copy.deepcopy(overlay['binding'])
    # Caller owns transport/authority; semantic mirrors are generated exclusively.
    require(not set(b).intersection({'tenants','pair','imageId','k6Image','workload','reportMode','pgstreamTopology','diagnosticResourceProfile','diagnosticResourceAllocation','staticTopology','commissioningSlotWalMiB','tenantReadiness'}),
            'M7_CONFIG_REMOTE_MIRROR_REFUSED')
    cadence = dict(r['cadence'])
    require(not {'setupSeconds','drainSeconds','drainObservation'} & cadence.keys(),
            'M7_REMOTE_PHASE_WINDOWS_UNSUPPORTED')
    viewers = cadence.get('logicalPollingClients',r['tenants']*cadence['socketsPerTenant'])
    b.update(tenants=r['tenants'], pair=r['pair'], imageId=r['imageId'], reportMode='discovery',
             k6Image='grafana/k6@'+config['k6Image'], workload={
                 'cadence':cadence, 'primerConcurrency':r['primerConcurrency'], 'jwtSetupConcurrency':r['jwtSetupConcurrency'],
                 'resourcePlan':{'reference':overlay['resourceReference'], 'tenants':r['tenants'],
                                 'logicalPollingClients':viewers, 'hosts':overlay['hostInventory']}})
    if r['pgstreamTopology']!='colocated-v1':
        selected=r['resources']['profile'] if r['resources'] else None
        b.update(pgstreamTopology=r['pgstreamTopology'],**({'diagnosticResourceAllocation':selected} if isinstance(selected,dict) else {'diagnosticResourceProfile':selected}))
    if cadence.get('driverShards',1)>1:
        require(b.get('pgstreamTopology')=='external-service-v1' and isinstance(b.get('helperDependencies'),dict),
                'M7_CONFIG_REMOTE_SHARDS_TOPOLOGY')
        files=b['helperDependencies']['files']
        for name in ('tools/mt-bench/m7-joined/driver_shards.py','tools/mt-bench/m7-joined/contract.py'):
            expected=a.digest(a.ROOT/name)
            require(name not in files or files[name]==expected,'M7_CONFIG_REMOTE_SHARD_DEPENDENCY_CHANGED')
            files[name]=expected
    if r.get('staticTopology'):b['staticTopology']=r['staticTopology']
    for key in ('commissioningSlotWalMiB','tenantReadiness'):
        if key in r:b[key]=r[key]
    if commissioning_wal.remote_selection(b):
        files=b['helperDependencies']['files']
        for name in ('commissioning_wal.py','contract.py'):
            path='tools/mt-bench/m7-joined/'+name
            require(path not in files or files[path]==a.digest(a.ROOT/path),'M7_REMOTE_STARTUP_DEPENDENCY_CHANGED')
            files[path]=a.digest(a.ROOT/path)
    protocol.binding(b)
    require(protocol.prepared_cadence(b)==r['cadence'], 'M7_CONFIG_REMOTE_CADENCE_DRIFT')
    return {**result, 'binding':b, 'remoteReceiptProjection':{
        'remoteProfile':b['profile'], 'remoteTransport':b['transport'], 'remoteExtensionSha256':b['sourceSha256'],
        'remoteReportMode':b['reportMode'], 'remoteWorkload':b['workload'],
        'remotePgstreamTopology':b.get('pgstreamTopology'), 'remoteDiagnosticResourceProfile':b.get('diagnosticResourceProfile'),
        'remoteDiagnosticResourceAllocation':b.get('diagnosticResourceAllocation'),
        'remoteHelperDependencies':b.get('helperDependencies'), 'completionContract':r['completionContract'],
        **({'remoteNativeSourceAdmission':b['nativeSourceAdmission']} if b.get('nativeSourceAdmission') else {}),
        **({'remoteStaticTopology':b['staticTopology']} if b.get('staticTopology') else {}),
        **({'remoteCommissioningSlotWalMiB':b['commissioningSlotWalMiB'],'remoteTenantReadiness':b['tenantReadiness']}if b.get('commissioningSlotWalMiB')is not None else {})}}


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
