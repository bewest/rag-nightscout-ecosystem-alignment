"""SUT-only entry point. No actor is started by importing this module."""
raise ImportError('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app
import producer
from protocol import prepared_cadence, binding, need, workload, discovery_mode, topology_dependencies, jwt_setup_concurrency, native_mode, native_project, source_admission, static_selection
from transport import POSTGRES, REPAIRED_CORE, MINIMUM_CORE, PERFORMANCE_CORE

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'deploy', 'export', 'session', 'down'))
    parser.add_argument('--binding', required=True)
    parser.add_argument('--cell', required=True)
    parser.add_argument('--run-config', help='Existing runner config; derive prepare argv instead of authoring mirrors')
    args, remaining = parser.parse_known_args()
    raw = json.loads(Path(args.binding).read_text())
    if args.action == 'down':
        need(not remaining, 'REMOTE_UNEXPECTED_ARGUMENT')
        return app.cleanup(args.cell, raw)
    b = binding(raw)
    selected = workload(b)
    # Strict binding admits only qualified presets. Discovery binding is an
    # unverified request; canonical prepare and app.load execute its admission.
    if args.action == 'prepare':
        if b.get('workload') is not None:
            need(time.time() + selected['cadence']['loadSeconds'] + 540 < b['expiresAt'], 'REMOTE_DURATION_OUTSIDE_ENVELOPE')
        if args.run_config:
            need(not remaining,'REMOTE_CONFIG_MIRROR_REFUSED')
            import runner
            run_config, remaining=runner.load_config(args.run_config)
        prep = app.a.parser().parse_args(['prepare', '--directory', args.cell, *remaining])
        need({'core': prep.core_commit, 'deploy': prep.deploy_commit} == b['pair'] and prep.image == b['imageId'] and
             prep.postgres_image == POSTGRES and prep.tenants == b['tenants'] and prep.replicas == 1 and
             prep.profile == 'pgstream-sample' and prep.run_purpose == 'discovery' and
             prep.measurement_mode == 'accepted' and app.a.cadence_options(prep) == prepared_cadence(b) and
             prep.primer_concurrency == selected['primerConcurrency'] and
             prep.jwt_setup_concurrency == jwt_setup_concurrency(b) and
             prep.pgstream_topology == b.get('pgstreamTopology','colocated-v1') and
             app.a.selected_resources_profile(prep) == b.get('diagnosticResourceAllocation',b.get('diagnosticResourceProfile')),
             'REMOTE_PREPARE_PROFILE_REQUIRED')
        if discovery_mode(b) or b['pair']['core'] in (REPAIRED_CORE, MINIMUM_CORE, PERFORMANCE_CORE):
            need(prep.completion_contract == 'evaluator-work-v2', 'REMOTE_REPAIRED_COMPLETION_V2_REQUIRED')
        # Validate the genuine authorization before even preparing source/state.
        receipt = app.a.document(prep.freeze)
        if native_mode(b):
            need(receipt.get('version') == 2 and receipt.get('functionalAcceptanceAtAuthorization') == source_admission(b)
                 and prep.fixture_project == native_project(b) and prep.evaluator_opportunities == 'received-input-v1',
                 'REMOTE_NATIVE_PREPARE_AUTHORIZATION')
            need(receipt.get('remoteNativeSourceAdmission')==b.get('nativeSourceAdmission'),'REMOTE_NATIVE_SOURCE_ADMISSION_RECEIPT')
            if source_admission(b)=='PENDING':need(receipt.get('sourceAcceptance')=={'status':'PENDING'},'REMOTE_NATIVE_PENDING_TRUTH')
            need(b['fixtureNetworks']=={'backend':prep.backend_subnet,'edge':prep.edge_subnet}
                 and receipt.get('remoteFixtureNetworks')==b['fixtureNetworks'],'REMOTE_NATIVE_NETWORKS')
        from commissioning_wal import remote_selection
        startup=remote_selection(b)
        need(app.a.commissioning_wal.option(prep).get('commissioningSlotWalMiB')==startup.get('commissioningSlotWalMiB') and
             prep.tenant_readiness==startup.get('tenantReadiness') and
             receipt.get('remoteCommissioningSlotWalMiB')==startup.get('commissioningSlotWalMiB') and
             receipt.get('remoteTenantReadiness')==startup.get('tenantReadiness'),'REMOTE_STARTUP_PREPARE_MIRROR')
        need(app.a.static_topology.option(prep).get('staticTopology')==static_selection(b) and receipt.get('remoteStaticTopology')==b.get('staticTopology'),'REMOTE_STATIC_PREPARE_MIRROR')
        if b.get('staticTopology'):need(receipt.get('limits',{}).get('staticWorkers')==1 and receipt['limits'].get('apiReplicas')==1,'REMOTE_STATIC_RECEIPT')
        if args.run_config:
            from run_configuration import validate_execution
            validate_execution(run_config,receipt)
        need(receipt.get('remoteReportMode','strict') == b.get('reportMode','strict') and receipt.get('status') == 'AUTHORIZED_DIAGNOSTIC' and receipt.get('remoteProfile') == b['profile'] and
             receipt.get('remoteTransport') == b['transport'] and receipt.get('remoteExtensionSha256') == b['sourceSha256'] and
             receipt.get('remotePgstreamTopology') == b.get('pgstreamTopology') and receipt.get('remoteDiagnosticResourceProfile') == b.get('diagnosticResourceProfile') and receipt.get('remoteDiagnosticResourceAllocation') == b.get('diagnosticResourceAllocation') and receipt.get('remoteHelperDependencies') == b.get('helperDependencies') and
             receipt.get('remoteWorkload') == b.get('workload') and receipt.get('remoteComponentCases') == b.get('componentCases') and
             receipt.get('completionContract') == prep.completion_contract and prep.completion_contract in ('evaluator-work-v1', 'evaluator-work-v2'),
             'REMOTE_EXTENSION_AUTHORIZATION_REQUIRED')
        topology_dependencies(b,Path(__file__).resolve().parents[3])
        app.a.prepare(prep)
        app.record_prepared_binding(args.cell, b)
    else:
        need(not remaining, 'REMOTE_UNEXPECTED_ARGUMENT')
        d, m, b = app.load(args.cell, b)
        if args.action == 'deploy':
            app.ingress(args.cell, b)
            d, m, b = app.load(args.cell, b)
            producer.deploy(d, m)
        elif args.action == 'export':
            print(json.dumps(app.export_traffic(args.cell, b), sort_keys=True))
        elif args.action == 'session':
            app.session(args.cell, b)
        else:
            app.a.down(d, m)

if __name__ == '__main__':
    main()
