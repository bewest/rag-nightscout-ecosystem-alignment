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
    a.stream_topology.options(args)
    static = a.static_topology.option(args)
    commissioning_wal.option(args)
    a.stream_topology.ack_option(args)
    require(args.measurement_mode=='accepted','M7_CONFIG_DISCOVERY_MEASUREMENT_MODE')
    require(workload_inputs.tenants(args.tenants)
            and (discovery_api_replicas(args.replicas) if args.run_purpose=='discovery'
                 else type(args.replicas) is int and args.replicas in REPLICAS)
            and (args.replicas == 1 or static),
            'M7_CONFIG_SINGLE_API_TENANT_RANGE')
    a.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)
    a.prepare_primer_options(args)
    a.jwt_setup_concurrency(args.jwt_setup_concurrency, args.run_purpose=='discovery')
    a.fixture_project(args, '0'*32)
    networks = [ipaddress.ip_network(getattr(args, key), strict=True) for key in ('backend_subnet', 'edge_subnet')]
    private=[ipaddress.ip_network(c) for c in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    require(all(n.version==4 and any(n.subnet_of(p) for p in private) for n in networks) and not networks[0].overlaps(networks[1]),
            'M7_CONFIG_SUBNET_OVERLAP_OR_PUBLIC')
    return cadence


def from_args(args, instrument):
    import adapter as a
    # This is semantic input, independent of transport paths and observed limits.
    cadence = validate_prepare(args)
    return {**commissioning_wal.option(args), **a.stream_topology.ack_option(args), **({'tenantReadiness':args.tenant_readiness} if getattr(args,'tenant_readiness',None) else {}), **a.static_topology.option(args), **({'apiCauseObservation':'on'} if getattr(args,'api_cause_observation','off')=='on' else {}),'version': 1, 'pair': {'core': args.core_commit, 'deploy': args.deploy_commit},
            'imageId': args.image_id or args.image, 'instrument': instrument,
            'postgresImageId': args.postgres_image, 'profile': args.profile,
            'runPurpose': args.run_purpose, 'tenants': args.tenants, 'replicas': args.replicas,
            'cadence': cadence, 'primerConcurrency': args.primer_concurrency,
            **({'primerMaxTenants': args.primer_max_tenants} if getattr(args,'primer_max_tenants',None) is not None else {}),
            'jwtSetupConcurrency': args.jwt_setup_concurrency,
            **a.stream_topology.options(args, include_default=True),
            'completionContract': args.completion_contract,
            'diagnostics':a.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)}


def from_manifest(m):
    import adapter as a
    return {**commissioning_wal.from_manifest(m), **a.stream_topology.ack_selection(m), **({'tenantReadiness':m['tenantReadiness']} if m.get('tenantReadiness') else {}), **({'staticTopology':m['staticTopology']} if m.get('staticTopology') else {}),
            **({'apiCauseObservation':'on'} if m.get('apiCause') else {}),'version': 1, **{k: m.get(k) for k in ('pair','imageId','profile','runPurpose','tenants','replicas','cadence','completionContract')},
            'instrument': m['instrument']['sha256'], 'postgresImageId': m.get('postgresImageId'),
            'primerConcurrency': m.get('primerConcurrency',1), 'jwtSetupConcurrency': m.get('jwtSetupConcurrency',1),
            **({'primerMaxTenants':m['primerMaxTenants']} if 'primerMaxTenants' in m else {}),
            **({'inputTransport': a.stream_topology.WRITER} if a.stream_topology.selection(m) == a.stream_topology.WRITER
               else {'pgstreamTopology': a.stream_topology.selection(m)}),
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
    authored=resolved['cadence'].get('startupWindows',{})
    return {'configuration': resolved, 'configurationSha256': sha(resolved), 'diagnosticReceiptTemplate':template,
            'receiptLimits': limits,
            'startupWindows':{key:{'seconds':authored.get(key,value), 'origin':'authored' if key in authored else 'reference'}
                              for key,value in workload_inputs.COMPOSE_STARTUP_DEFAULTS.items()},
            'workSeconds': config['workSeconds'], 'cleanupSeconds': config['cleanupSeconds'],
            'k6Image': config['k6Image']}


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
