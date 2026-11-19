"""Opt-in native test Job declaration, census, budgets and exact owned stop.

Application resources and the workstation probe/controller remain unchanged.
The Job is declared suspended before entry and admitted before it can run.
"""
import copy
import json
from pathlib import Path
import re
import tempfile
import time

import kube_adapter as k
import native_load
import workload
import candidate

FIELD = 'nativeLoad'
JOB = 'Job/k6'
ACCOUNT = 'native-load-waiter'


def waiting_jobs(c):
    # In the split binding, primer readiness only proves client export is ready;
    # the independent verification Job must have completed as well.
    return ['provision', 'verification', 'primer:ready'] if candidate.verified_serving(c) else ['provision', 'primer:ready']


def has_mask(value):
    if isinstance(value, dict):
        return any(has_mask(row) for row in value.values())
    if isinstance(value, list):
        return any(has_mask(row) for row in value)
    return value == '<redacted>'


def exact_spec(c, client, observed, namespace_uid, *, cleanup=False):
    """Read only an owned native Job/Pod when the guard masks its references.

    This returns private bytes to the existing strict declaration checks; a
    masked Secret name or projected key is never accepted as matching evidence.
    No Secret data, list of private objects or unrelated workload is read.
    """
    if not has_mask(observed.get('spec', {})):
        return observed
    k.need(selected(c) is not None, 'NATIVE_LOAD_SELECTION')
    k.owned(c, observed)
    kind, name = observed['kind'], observed['metadata']['name']
    parent = None
    if kind == 'Pod':
        parent = k.controller(observed)
        k.need(parent.get('kind') == 'Job' and parent.get('name') == 'k6', 'NATIVE_LOAD_POD_CONTROLLER')
    else:
        k.need(kind == 'Job' and name == 'k6', 'NATIVE_LOAD_UNACCOUNTED_JOB')
    def namespace():
        native_load._identity(c, client.get('namespace', c['namespace'], cleanup), namespace_uid)
    namespace()
    raw = client.call(['get', kind, name, '-o', 'json'], read=False, cleanup=cleanup, output_limit=512*1024)
    try:
        actual = json.loads(raw)
    except (ValueError, TypeError):
        raise k.Refused('K8S_NATIVE_LOAD_SPEC_UNMEASURED', 'UNMEASURED') from None
    k.owned(c, actual)
    k.need(k.key(actual) == k.key(observed) and
           actual['metadata']['uid'] == observed['metadata']['uid'], 'NATIVE_LOAD_ACTOR_REPLACED')
    if parent is not None:
        k.need(k.controller(actual) == parent, 'NATIVE_LOAD_POD_CONTROLLER')
    k.need(not has_mask(actual.get('spec', {})), 'NATIVE_LOAD_SPEC_UNMEASURED', 'UNMEASURED')
    namespace()
    return actual


def selected(c):
    value = c.get(FIELD)
    if value is None:
        return None
    k.need(c.get('tier','discovery') == 'discovery' and isinstance(value,dict)
           and set(value) - {'inputCodec'} == {'version','mode','image','shellContract','resources','exporterResources',
                             'nodeName','deadlineSeconds','imagePullSecrets'}
           and value.get('version') == 1 and value.get('mode') == 'job-v1', 'NATIVE_LOAD_SELECTION')
    import native_input
    k.need(value.get('inputCodec', 'raw-v1') in native_input.CODECS, 'NATIVE_LOAD_INPUT_CODEC')
    k.need(isinstance(value['nodeName'],str) and k.NAME.fullmatch(value['nodeName'])
           and type(value['deadlineSeconds']) is int and value['deadlineSeconds'] > 1
           and isinstance(value['imagePullSecrets'],list)
           and all(isinstance(row,dict) and set(row)=={'name'} and k.NAME.fullmatch(row['name'])
                   for row in value['imagePullSecrets']), 'NATIVE_LOAD_PLACEMENT')
    k.need('driverPlan' in c['workload'], 'NATIVE_LOAD_CONFIGURED_DRIVER_REQUIRED')
    native_load.selection(c)
    window=c['workload']
    grace=max(row.get('gracefulStopSeconds',30) for row in window['driverPlan']['scenarios'].values())
    k.need(value['deadlineSeconds'] >= window.get('setupSeconds',310)+window['loadSeconds']+grace+5,
           'NATIVE_LOAD_JOB_WINDOW_TOO_SHORT')
    return value


def base_job(c):
    s = selected(c)
    labels = {c['ownerLabel']:c['runId'], 'app.kubernetes.io/name':'nightscout',
              'app.kubernetes.io/part-of':'nightscout-multitenant','app.kubernetes.io/component':'load'}
    hardened = {'runAsUser':1000,'runAsGroup':1000,'runAsNonRoot':True,
                'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}}
    waiter = {'name':'wait-for-jobs','image':c['pins']['appImage'],'imagePullPolicy':'IfNotPresent',
              'command':['node','-e',(k.HERE/'native-wait-jobs.cjs').read_text(),*waiting_jobs(c)],
              'env':[{'name':'NS_WAIT_DEADLINE_SECONDS','value':str(s['deadlineSeconds'])}],
              'resources':copy.deepcopy(s['exporterResources']), 'securityContext':hardened,
              'volumeMounts':[{'name':'kube-api','mountPath':'/var/run/secrets/kubernetes.io/serviceaccount','readOnly':True}]}
    return {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'k6','namespace':c['namespace'],'labels':labels},
            'spec':{'backoffLimit':0,'parallelism':1,'completions':1,'podReplacementPolicy':'Failed',
                    'activeDeadlineSeconds':s['deadlineSeconds'],
                    'template':{'metadata':{'labels':labels},'spec':{
                        'restartPolicy':'Never','automountServiceAccountToken':False,'enableServiceLinks':False,
                        'terminationGracePeriodSeconds':5,
                        'serviceAccountName':ACCOUNT,'imagePullSecrets':copy.deepcopy(s['imagePullSecrets']),
                        'nodeSelector':{'kubernetes.io/hostname':s['nodeName']},
                        'securityContext':{'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}},
                        'initContainers':[waiter], 'containers':[{'name':'k6','image':s['image'],
                            'imagePullPolicy':'IfNotPresent','args':['run','/inputs/workload.js'],
                            'resources':copy.deepcopy(s['resources']),'securityContext':hardened,
                            'env':[{'name':'BASE_URL','value':'http://edge:'+str(c.get('nativeLoadEdgePort',8080))}],
                            'volumeMounts':[{'name':'inputs','mountPath':'/inputs','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]}],
                        'volumes':[{'name':'inputs','secret':{'secretName':'ns-k6-inputs','defaultMode':292}},
                            {'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}},
                            {'name':'kube-api','projected':{'defaultMode':292,'sources':[
                                {'serviceAccountToken':{'path':'token','expirationSeconds':3600}},
                                {'configMap':{'name':'kube-root-ca.crt','items':[{'key':'ca.crt','path':'ca.crt'}]}},
                                {'downwardAPI':{'items':[{'path':'namespace','fieldRef':{'fieldPath':'metadata.namespace'}}]}}]}}]}}}}


def declarations(c):
    s = selected(c)
    if s is None:
        return []
    with tempfile.TemporaryDirectory() as scratch:
        path=Path(scratch)/'workload.js';workload.generate(k.ROOT,path)
        job,_,_=native_load.package(c,base_job(c),path.read_bytes(),[], planning=True,
             runid=stage_runid(c),seconds=s['deadlineSeconds'],run_start_ms=1,setup_seconds=1,
             exporter_resources=s['exporterResources'],shell_contract=s['shellContract'],
             input_codec=s.get('inputCodec','raw-v1'))
    job['spec']['suspend']=True
    meta={'namespace':c['namespace'],'labels':{c['ownerLabel']:c['runId']}}
    return [job,
        {'apiVersion':'v1','kind':'ServiceAccount','metadata':dict(meta,name=ACCOUNT),'automountServiceAccountToken':False},
        {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'Role','metadata':dict(meta,name=ACCOUNT),
         'rules':[{'apiGroups':['batch'],'resources':['jobs'],
                   'resourceNames':[name.split(':')[0] for name in waiting_jobs(c)],'verbs':['get']}]},
        {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'RoleBinding','metadata':dict(meta,name=ACCOUNT),
         'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':ACCOUNT},
         'subjects':[{'kind':'ServiceAccount','name':ACCOUNT,'namespace':c['namespace']}]}]


def stage_runid(c):
    import execute
    return execute.stage_runid(c,'load')


def validate(c, inventory, objects):
    s=selected(c)
    k.need(inventory.get(FIELD)==s,'NATIVE_LOAD_INVENTORY_CHANGED')
    if s is None:
        k.need(JOB not in objects,'NATIVE_LOAD_UNACCOUNTED_JOB')
        return
    for expected in declarations(c):
        k.need(objects.get(k.key(expected))==expected,'NATIVE_LOAD_DECLARATION_CHANGED:'+k.key(expected))
    totals={name:0 for name in ('millicpus','memoryBytes','ephemeralBytes')}; count=0
    for obj in objects.values():
        if obj['kind'] in k.WORKLOADS:
            count+=1
            amount=k.resource_budget.pod_budget(k.template(obj)['spec'],'requests-v1',k.need)
            for name in totals:totals[name]+=amount[name]
    quotas=[obj for obj in objects.values() if obj['kind']=='ResourceQuota']
    k.need(len(quotas)==1,'NATIVE_LOAD_QUOTA_REQUIRED')
    hard=quotas[0]['spec']['hard']
    k.need(k.resource_budget.quantity(hard.get('requests.cpu',0),True,k.need)>=totals['millicpus']
           and k.resource_budget.quantity(hard.get('requests.memory',0),False,k.need)>=totals['memoryBytes']
           and int(hard.get('pods',0))>=count,'NATIVE_LOAD_UNACCOUNTED_QUOTA')


def reserve(c, objects):
    s=selected(c)
    if s is None:return None
    return s['nodeName'],k.resource_budget.pod_budget(k.template(objects[JOB])['spec'],k.resource_accounting(c),k.need)


def test_pod(c, parent, pod, controller_uid=None):
    """An exact declared Job is the only dynamic test actor admitted by census."""
    k.need(selected(c) is not None and k.key(parent)==JOB,'NATIVE_LOAD_UNACCOUNTED_JOB')
    k.owned(c,pod)
    k.need(k.subset(k.template(parent)['metadata']['labels'],pod['metadata'].get('labels',{})),
           'NATIVE_LOAD_POD_LABELS_CHANGED')
    wanted=k.template(parent)['spec']; actual,_=k.admission_projection(wanted,pod['spec'])
    k.need(k.subset(wanted,actual),'NATIVE_LOAD_POD_CHANGED')
    k.need(not pod['spec'].get('nodeName') or pod['spec']['nodeName']==c[FIELD]['nodeName'],
           'NATIVE_LOAD_PLACEMENT_CHANGED')
    states=pod.get('status',{}).get('containerStatuses',[])+pod.get('status',{}).get('initContainerStatuses',[])
    k.need(all(row.get('restartCount',0)==0 for row in states),'NATIVE_LOAD_ACTOR_RESTARTED')
    custody=Path(c.get('nativeLoadCustodyFile','/missing-native-custody'))
    if custody.is_file():
        value=k.document(custody)
        parent_uid=controller_uid or parent['metadata'].get('uid')
        k.need(value.get('jobUid',parent_uid)==parent_uid
               and value.get('podUid',pod['metadata']['uid'])==pod['metadata']['uid'], 'NATIVE_LOAD_ACTOR_REPLACED')
        actual={row['name']:row.get('containerID') for row in states}
        k.need(all(actual.get(name)==identity for name,identity in value.get('actorContainers',{}).items()),
               'NATIVE_LOAD_ACTOR_REPLACED')
    return {**k.meta(pod),'workload':JOB,'nodeName':pod['spec'].get('nodeName'),
            'phase':pod.get('status',{}).get('phase'),'states':states}


class Kube:
    """Use the existing pinned/guarded adapter client, including binary exec."""
    def __init__(self,c,client):self.c,self.client,self.namespace_uid=c,client,None
    def call(self,args,*,data=None,timeout=20,namespace=None,cleanup=False):
        k.need(namespace in (None,self.c['namespace']),'NATIVE_LOAD_NAMESPACE_CHANGED')
        raw=data.encode() if isinstance(data,str) else data
        maximum=max(32*1024**2,self.c['workload']['driverPlan'].get('maxTraceBytes',64*1024**2))
        return self.client.call(args,data=raw,read=args[0] in ('get','logs','top'),cleanup=cleanup,
                                output_limit=maximum,timeout=timeout)
    def json(self,args,**kw):
        value=json.loads(self.call([*args,'-o','json'],**kw))
        if args[:2] == ['get','namespace']:
            self.namespace_uid=native_load._identity(self.c,value,self.namespace_uid)
        elif args[:2] in (['get','job'], ['get','pods']):
            if self.namespace_uid is None:
                self.namespace_uid=native_load._identity(self.c,self.client.get('namespace',self.c['namespace'],kw.get('cleanup',False)))
            if 'items' in value:
                value=dict(value,items=[exact_spec(self.c,self.client,row,self.namespace_uid,cleanup=kw.get('cleanup',False)) for row in value['items']])
            else:
                value=exact_spec(self.c,self.client,value,self.namespace_uid,cleanup=kw.get('cleanup',False))
        return value


def cancel(kube,c,receipt,out,*,clock=time):
    """Atomic UID-tested suspension stops owned Pods; observe writer closure."""
    path=Path(out)/'native-cancel.json'
    if path.exists():
        k.need(k.document(path).get('writersStopped') is True,'NATIVE_LOAD_CANCEL_UNMEASURED','UNMEASURED')
        return k.document(path)
    uid=receipt['jobUid']; ns=c['namespace']
    until=clock.monotonic()+min(30,k.deadline(c,cleanup=True))
    def budget():
        left=min(until-clock.monotonic(),k.deadline(c,cleanup=True))
        k.need(left>0,'NATIVE_LOAD_CANCEL_UNMEASURED','UNMEASURED')
        return min(5,left)
    native_load._identity(c,kube.json(['get','namespace',ns],cleanup=True,timeout=budget()),receipt['namespaceUid'])
    job=kube.json(['get','job','k6'],namespace=ns,cleanup=True,timeout=budget());k.owned(c,job)
    k.need(job['metadata']['uid']==uid,'NATIVE_LOAD_ACTOR_REPLACED')
    patch=[{'op':'test','path':'/metadata/uid','value':uid},
           {'op':'add','path':'/spec/suspend','value':True}]
    kube.call(['patch','job','k6','--type=json','-p',json.dumps(patch)],namespace=ns,cleanup=True,timeout=budget())
    value={'jobUid':uid,'namespaceUid':receipt['namespaceUid'],'writersStopped':False,
           'mechanism':'atomic UID-tested Job suspension; no restart or mutation replay'}
    k.write(path,value)
    while clock.monotonic()<until:
        job=kube.json(['get','job','k6'],namespace=ns,cleanup=True,timeout=budget())
        k.need(job['metadata']['uid']==uid and job['spec'].get('suspend') is True,'NATIVE_LOAD_ACTOR_REPLACED')
        rows=kube.json(['get','pods','-l','job-name=k6'],namespace=ns,cleanup=True,timeout=budget())['items']
        k.need(len(rows)<=1,'NATIVE_LOAD_POD_CENSUS')
        stopped=True
        for pod in rows:
            k.owned(c,pod);ref=k.controller(pod)
            k.need(ref.get('uid')==uid and ref.get('kind')=='Job','NATIVE_LOAD_POD_CONTROLLER')
            k.need('podUid' not in receipt or receipt['podUid']==pod['metadata']['uid'],'NATIVE_LOAD_ACTOR_REPLACED')
            states={row['name']:row for row in pod.get('status',{}).get('containerStatuses',[])}
            stopped=stopped and ('terminated' in states.get('k6',{}).get('state',{}))
        if stopped:
            native_load._identity(c,kube.json(['get','namespace',ns],cleanup=True,timeout=budget()),receipt['namespaceUid'])
            value['writersStopped']=True;k.write(path,value);return value
        clock.sleep(min(.2,budget()))
    raise k.Refused('K8S_NATIVE_LOAD_CANCEL_UNMEASURED','UNMEASURED')


def run(d,out,c,objects,client,tenants,*,runid,setup,failures):
    s=selected(c);baseline=k.active_baseline(d)
    k.need(JOB in objects and JOB in baseline['objects'],'NATIVE_LOAD_UNACCOUNTED_JOB')
    k.need(c.get('nativeLoadCustodyFile')==str(out/'native-load.json'),'NATIVE_LOAD_CUSTODY_PATH')
    return native_load.run(Kube(c,client),c,base_job(c),(d/'workload.js').read_bytes(),tenants,out,
        predeclared={'uid':baseline['objects'][JOB]['uid']},failures=failures,runid=runid,
        seconds=s['deadlineSeconds'],run_start_ms=int(time.time()*1000),setup_seconds=setup,
        exporter_resources=s['exporterResources'],shell_contract=s['shellContract'],
        input_codec=s.get('inputCodec','raw-v1'))


def prepare_case(case, selection):
    """Offline opt-in for a fresh, uncaptured existing prepared case.

    Append only the declared test Job/RBAC, adjust its exact quota/envelope,
    and invalidate old preparation status. No cluster/image/source operation.
    The normal lifecycle capture and fresh scheduler fit remain mandatory.
    """
    import experiment
    import frozen
    import application_topology
    case=Path(case).resolve()
    k.need(case.is_absolute() and case.is_dir() and not (case/'runtime').exists(),
           'NATIVE_LOAD_FRESH_CASE_REQUIRED')
    control=k.document(case/'lifecycle-input.json')
    k.need(Path(control['caseDirectory']).resolve()==case,'NATIVE_LOAD_CASE_DIRECTORY_CHANGED')
    k.need('inputs' not in control,'NATIVE_LOAD_ALREADY_CAPTURED')
    from lifecycle_config import helper_directory
    k.need(helper_directory(control) == k.HERE, 'INSTRUMENT_DIRECTORY_MISMATCH')
    manifest=k.document(case/'intent.json');template=frozen.read_ref(control['runTemplate'])
    inventory=k.document(case/'inventory.json');render=k.document(case/'render.json')
    k.need(not any(value.get(FIELD) for value in (manifest,template,inventory)), 'NATIVE_LOAD_ALREADY_DECLARED')
    delivery=frozen.read_ref(control['delivery']);source=frozen.source(manifest)
    preparing=copy.deepcopy(template)
    preparing['pins']={'appImage':delivery['app'],'appImageId':delivery['appImageId'],
                   'pair':{'core':source['coreCommit'],'deploy':source['deployCommit']},
                   'bindingCommit':manifest['bindingCommit'],'instrument':k.instrument()['sha256']}
    if 'verification' in inventory.get('workloads', {}):
        # Match normal experiment.prepare's protocol selection, without copying
        # mutable candidate receipts into the run template. Full pins are bound
        # and checked by the normal preparer before entry.
        preparing['pins']['candidate']={'verificationJob':'verification'}
    c=experiment.profile.bind(experiment.workload(manifest),preparing)
    c.update(tier=manifest.get('tier','discovery'),nativeLoad=selection,
             applicationTopology=application_topology.selection(manifest,k.need))
    # Freeze the private DATA channel on new cases. Existing packets retain
    # the codec and Job template their original instrument declared.
    import native_input
    requested_codec = selection.get('inputCodec')
    k.need(requested_codec is None or requested_codec in native_input.CODECS, 'NATIVE_LOAD_INPUT_CODEC')
    selection = dict(selection, inputCodec=native_input.PRIVATE)
    c[FIELD] = selection
    extra=declarations(c);declared={k.key(obj):obj for obj in extra}
    before=k.manifests(render)
    k.need(not (set(declared)&{k.key(obj) for obj in before}), 'NATIVE_LOAD_RESOURCE_EXISTS')
    quota,= [obj for obj in before if obj['kind']=='ResourceQuota']
    request=k.resource_budget.pod_budget(k.template(declared[JOB])['spec'],'requests-v1',k.need)
    hard=quota['spec']['hard']
    hard['requests.cpu']=str(k.resource_budget.quantity(hard['requests.cpu'],True,k.need)+request['millicpus'])+'m'
    hard['requests.memory']=str(k.resource_budget.quantity(hard['requests.memory'],False,k.need)+request['memoryBytes'])
    hard['pods']=str(int(hard['pods'])+1)
    # Mutate the quota object in the original render; every application workload
    # stays byte-for-byte unchanged. New resources live only in foundation.
    render['nativeLoadResources']=extra
    inventory[FIELD]=copy.deepcopy(selection);manifest[FIELD]=copy.deepcopy(selection);template[FIELD]=copy.deepcopy(selection)
    for name,value in request.items():
        field='ephemeralStorageBytes' if name=='ephemeralBytes' else name
        k.need(field in manifest['profile']['proposedEnvelope']['clusterLimits'],'NATIVE_LOAD_ENVELOPE_DIMENSION')
        manifest['profile']['proposedEnvelope']['clusterLimits'][field]+=value
    foundation=k.document(case/'stages/foundation.json');foundation['items']+=extra
    for obj in foundation['items']:
        if obj['kind']=='ResourceQuota' and obj['metadata']['name']==quota['metadata']['name']:
            obj['spec']=copy.deepcopy(quota['spec'])
    objects={k.key(obj):obj for obj in k.manifests(render)}
    validate(c,inventory,objects);application_topology.validate(c,inventory,objects,k.need)
    with tempfile.TemporaryDirectory() as scratch:
        scratch=Path(scratch);k.write(scratch/'render.json',render);k.write(scratch/'inventory.json',inventory)
        checks=experiment.render_checks({'render':str(scratch/'render.json'),'inventory':str(scratch/'inventory.json'),
                                        'bindingReceipt':{'path':str(Path(control['bindingDirectory'])/'binding.json'),
                                                          'sha256':k.digest(Path(control['bindingDirectory'])/'binding.json')}})
    for name,value in [('render.json',render),('inventory.json',inventory),('intent.json',manifest),
                       ('native-run-template.json',template),('stages/foundation.json',foundation)]:k.write(case/name,value)
    control['runTemplate']={'path':str(case/'native-run-template.json'),'sha256':k.digest(case/'native-run-template.json')}
    k.write(case/'lifecycle-input.json',control)
    pre=k.document(case/'preflight.json')
    pre['experiment'].update(experimentSha256=k.digest(case/'intent.json'),renderSha256=k.digest(case/'render.json'))
    pre['nativeLoad']={'selection':selection,'requestedInputCodec':requested_codec,'reservedPodRequests':request,'nodeName':selection['nodeName'],
                       'liveFit':'UNMEASURED_REQUIRED_AT_ENTRY','jobSha256':k.hashed(declared[JOB])}
    k.write(case/'preflight.json',pre)
    result={'configuration':'STRUCTURAL_PASS','nativeLoad':pre['nativeLoad'],'checks':checks,
            'sourceAcceptance':source['sourceAcceptance'],'capacityAcceptance':'NOT_GRANTED',
            'next':'Fresh lifecycle capture and current scheduler fit; no actor created'}
    k.write(case/'pre-entry-prepare.json',result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Append native test actors to a fresh prepared case; no cluster actions')
    parser.add_argument('case',type=Path);parser.add_argument('selection',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare_case(args.case,k.document(args.selection)),indent=2))
