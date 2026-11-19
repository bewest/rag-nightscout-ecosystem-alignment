"""Materialize one standard discovery point using the selected deploy binding."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

import experiment
import frozen
import kube_adapter as k
import lifecycle_config as lc
import native_join


def prepare(template_case, package, profile_path, output, binding=None, core=None, taint=None):
    output = output.resolve()
    inputs = (template_case, package, binding or package/'binding')
    k.need(all(not output.is_relative_to(path.resolve()) for path in inputs),
           'STANDARD_OUTPUT_INSIDE_SOURCE')
    try:
        output.mkdir(parents=True,exist_ok=False,mode=0o700)
    except FileExistsError:
        raise k.Refused('K8S_STANDARD_CASE_EXISTS','UNMEASURED') from None
    try:
        return _materialize(template_case,package,profile_path,output,binding,core,taint)
    except Exception as error:
        failed = output.with_name(output.name+'.failed-'+str(time.time_ns()))
        output.rename(failed)
        report = experiment.failure(error)
        if not report['code'].startswith(('K8S_', 'M7_')):
            report.update(code='K8S_STANDARD_PREPARATION_FAILED', cause=type(error).__name__)
            if isinstance(error, FileNotFoundError):
                report['missing'] = str(error.filename)
            if isinstance(error, subprocess.CalledProcessError):
                report.update(program=Path(error.cmd[0]).name, returncode=error.returncode)
        report.update(stage='offline preparation', liveActors=0)
        k.write(failed/'prepare-error.json',report)
        raise k.Refused(report['code'], report['verdict']) from error


def _materialize(template_case, package, profile_path, output, binding, core, taint):
    template_case = template_case.resolve()
    package = package.resolve()
    binding = (binding or package/'binding').resolve()
    output = output.resolve()
    run_id = output.name
    namespace = 'ns-synth-' + run_id
    k.need(re.fullmatch(r'[a-z0-9][a-z0-9-]*[a-z0-9]', run_id) and len(namespace) <= 63,
           'STANDARD_CASE_NAME')
    profile = k.document(profile_path)
    profile['name'] = run_id
    control = k.document(template_case/'lifecycle-input.json')
    core = (core or Path(control['coreRepository'])).resolve()
    prior = k.document(template_case/'intent.json')
    run = k.document(template_case/'native-run-template.json')
    binding_inputs = k.document(template_case/'binding-inputs.json')
    env = k.document(template_case/'environment.json')
    k.need(run['storageMode'] == 'disposable' and binding_inputs['storage']['mode'] == 'disposable',
           'STANDARD_CASE_DISPOSABLE_STORAGE')
    selection = run.pop('nativeLoad')
    resources = k.document(binding/'bindings/kubernetes/lib/ns/typical-requests.json')
    selection.pop('nodeName', None)
    selection.pop('tolerations', None)
    selection['resources'] = {'requests': resources['k6']}
    selection['exporterResources'] = {'requests': resources['artifact-exporter']}
    selection['waiterResources'] = {'requests': resources['wait-for-jobs']}
    placement = {}
    if taint:
        key, equal, value = taint.partition('=')
        k.need(equal and key and value, 'STANDARD_RESERVED_WORKER_TAINT')
        placement = {'tolerations':[{'key':key,'value':value,'operator':'Equal','effect':'NoSchedule'}]}
        selection.update(placement)
    phases = profile['phases']
    traffic = profile['workload']
    grace = max(v.get('gracefulStopSeconds', 30) for v in traffic['driverPlan']['scenarios'].values())
    selection['deadlineSeconds'] = max(selection['deadlineSeconds'], traffic.get('setupSeconds',310) + traffic['loadSeconds'] + grace + 5)
    delivery = k.document(package/'runner-image-delivery.json')
    intent = {key: value for key, value in prior.items() if key not in ('nativeLoad','profile')}
    intent.update(profile=profile, bindingCommit=k.document(binding/'binding.json')['bindingCommit'],
                  postgresImageId=delivery['postgresImageId'], sourceReceipt=lc.ref(package/'source-receipt.json'),
                  buildReceipt=lc.ref(package/'build-receipt.json'))
    source = frozen.source(intent)
    core_head = subprocess.check_output(['git', '-C', core, 'rev-parse', 'HEAD'],text=True).strip()
    k.need(core_head == source['coreCommit'] == delivery['sourceCommit'] and
           source['deployCommit'] == delivery['imageDeployCommit'] and
           source['localImageId'] == delivery['appImageId'], 'STANDARD_CASE_SOURCE')
    # Carry forward only the platform setup allowance, independently of the selected load duration.
    setup_allowance = env['workDeadlineSeconds'] - prior['profile']['phases']['workSeconds']
    outer = phases['workSeconds'] + setup_allowance
    tenants = profile['population']['provisionedTenants']
    images = {name:delivery[name] for name in ('app','postgres')}
    binding_inputs.pop('resources', None)
    binding_inputs.update(runId=run_id, namespace=namespace, tenantCount=tenants, images=images,
                          placement=placement, placementByWorkload={}, provisionDeadlineSeconds=outer,
                          sourceCommit=source['coreCommit'], imageDeployCommit=source['deployCommit'],
                          bindingIdentity=intent['bindingCommit'],resourceAccounting='requests-v1')
    k.write(output/'binding-inputs.json',binding_inputs)
    bundled = Path(control['toolsDirectory'])/'jsonnet-0.21.0/jsonnet'
    jsonnet = str(bundled) if bundled.is_file() else shutil.which('jsonnet')
    k.need(jsonnet, 'STANDARD_JSONNET_REQUIRED')
    for name,suffix in [('render',''),('inventory','.inventory')]:
        data = subprocess.check_output([jsonnet,'-J',binding/'bindings/kubernetes/lib','--ext-code-file',
             'INPUT='+str(output/'binding-inputs.json'),'-e','(import "ns/nightscout.libsonnet").new(std.extVar("INPUT"))'+suffix],timeout=30)
        k.write(output/(name+'.json'),json.loads(data))
    rendered = k.document(output/'render.json')
    inventory = k.document(output/'inventory.json')
    objects = k.manifests(rendered)
    totals = dict.fromkeys(('millicpus','memoryBytes','ephemeralBytes'),0)
    for obj in objects:
        if obj['kind'] in k.WORKLOADS:
            amount = k.resource_budget.pod_budget(k.template(obj)['spec'],'requests-v1',k.need)
            count = obj['spec'].get('replicas',obj['spec'].get('parallelism',1))
            for dimension in totals:
                totals[dimension] += amount[dimension] * count
    # This wire format also serves older callers. Populate it from this render and
    # the controller's configured host scope. Historical envelope values are unused.
    profile['proposedEnvelope'] = {
        'clusterLimits': {'millicpus':totals['millicpus'], 'memoryBytes':totals['memoryBytes'],
                          'ephemeralStorageBytes':totals['ephemeralBytes']},
        'nativeLimits':control['nativeLimits'],
    }
    stages = {name:[] for name in lc.stages_for(inventory)}
    prior_stages = {k.key(obj):stage for stage in stages for obj in
                    k.document(template_case/'stages'/(stage+'.json'))['items'] if obj['kind'] in k.WORKLOADS}
    for obj in k.manifests(rendered):
        stage = {'Namespace':'namespace','ClusterRoleBinding':'cluster-trust'}.get(obj['kind'],'foundation')
        if obj['kind'] in k.WORKLOADS:
            stage = prior_stages[k.key(obj)]
        stages[stage].append(obj)
    (output/'stages').mkdir()
    for stage,items in stages.items():
        k.write(output/'stages'/(stage+'.json'),{'apiVersion':'v1','kind':'List','items':items})

    k.write(output/'intent.json',intent)
    env.update(namespace=namespace,runId=run_id,images=images,tenantCount=tenants,sourceCommit=source['coreCommit'],
               imageDeployCommit=source['deployCommit'],provisionDeadlineSeconds=outer,workDeadlineSeconds=outer,
               cleanupDeadlineSeconds=outer+phases['cleanupSeconds'],resourceAccounting='requests-v1')
    k.write(output/'environment.json',env)
    now = datetime.now(timezone.utc)
    run['driver']['coreRepository'] = str(core)
    run.update(runId=run_id,namespace=namespace,tenants=tenants,workload=traffic,resourceAccounting='requests-v1',
               tenantsFile=str(output/'runtime/packet/primer/tenants.json'), deadlines={kind:(now+timedelta(seconds=env[seconds])).isoformat().replace('+00:00','Z')
               for kind,seconds in [('workUntil','workDeadlineSeconds'),('cleanupUntil','cleanupDeadlineSeconds')]})
    k.write(output/'native-run-template.json', run)
    k.write(output/'preflight.json',{'offline':'PASS','commissioning':'PREFLIGHT_ONLY',
        'trialEnvelope':{'placementMode':'scheduler','resourceAccounting':'requests-v1'},'experiment':{'runId':run_id,
        'namespace':namespace,'renderSha256':k.digest(output/'render.json'),'experimentSha256':k.digest(output/'intent.json')}})
    selected_control = {key:control[key] for key in ('version','toolsDirectory','k6','readonlyGuard','observerScript','pullSecretCommand') if key in control}
    selected_control.update(caseDirectory=str(output),bindingDirectory=str(binding),instrumentDirectory=str(k.ROOT),
                            schedulerPlacement=True,coreRepository=str(core),runTemplate=lc.ref(output/'native-run-template.json'),
                            delivery=lc.ref(package/'runner-image-delivery.json'),nativeLimits=control['nativeLimits'],
                            primerConcurrency=phases.get('primerOptions',{}).get('concurrency',control['primerConcurrency']))
    k.write(output/'lifecycle-input.json',selected_control)
    native_join.prepare_case(output,selection)
    instance = {'config':str(output/'native-run-template.json'),'render':str(output/'render.json'),
                'inventory':str(output/'inventory.json'),'bindingReceipt':lc.ref(binding/'binding.json'),
                'delivery':selected_control['delivery']}
    experiment.prepare(output/'intent.json',instance,output/'offline-final',await_primer=True)
    return experiment.launch(output/'lifecycle-input.json', True)
