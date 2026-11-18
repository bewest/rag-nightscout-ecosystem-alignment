"""Check the full diagnostic render using its selected source and binding receipt."""
import argparse
import copy
import json
from pathlib import Path
import unittest

import frozen


def objects(value):
    if isinstance(value, dict) and 'apiVersion' in value and 'kind' in value:
        yield value
    else:
        for row in (value.values() if isinstance(value,dict) else value):
            yield from objects(row)


def controls(manifest, render, inventory, receipt):
    docs = list(objects(render))
    def one(rows, kind, name):
        return next(o for o in rows if (o['kind'],o['metadata']['name']) == (kind,name))
    def state(rows):
        job = one(rows,'Job','provision')
        config = one(rows,'ConfigMap','bootstrap-diagnostic')
        spec = job['spec']['template']['spec']
        boot = next(c for c in spec['initContainers'] if c['name']=='bootstrap')
        mount = next(m for m in boot['volumeMounts'] if m['name']==frozen.HELPER_MAP)
        return config,job,boot,mount
    def check(m, current):
        frozen.check_bootstrap_render(m, current)
    def refused(action, code):
        with unittest.TestCase().assertRaisesRegex(frozen.Refused,'^K8S_EXPERIMENT_'+code+'$'):
            action()
        return code
    selected=frozen.source(manifest)
    assert selected['sourceAcceptance']=='PENDING'
    assert selected['imageSourceAcceptance']==inventory['candidateContract']['imageSourceAcceptance']
    assert selected['runtimeBootstrapHelper']==inventory['candidateContract']['runtimeBootstrapHelper']
    check(manifest,docs)
    results=[]
    for key, value, code in [('deployCommit','a'*40,'BOOTSTRAP_HELPER_UNSUPPORTED'),('sha256','b'*64,'BOOTSTRAP_HELPER_UNSUPPORTED')]:
        changed=copy.deepcopy(manifest);changed['bootstrapHelper'][key]=value
        results.append(refused(lambda: check(changed, docs),code))
    for mut,code in (
        (lambda cm,j,b,m: cm['data'].update({'bootstrap.js':'different'}), 'BOOTSTRAP_HELPER_CHANGED'),
        (lambda cm,j,b,m: cm.update(immutable=False), 'BOOTSTRAP_HELPER_CHANGED'),
        (lambda cm,j,b,m: cm['data'].update({'extra':'extra'}), 'BOOTSTRAP_HELPER_CHANGED'),
        (lambda cm,j,b,m: cm['metadata']['labels'].update({'nightscout.org/run-id':'other'}), 'BOOTSTRAP_HELPER_OWNERSHIP'),
        (lambda cm,j,b,m: j['metadata']['annotations'].update({'nightscout.org/instance-acceptance':'PASS'}), 'BOOTSTRAP_HELPER_ANNOTATIONS'),
        (lambda cm,j,b,m: m.update(readOnly=False), 'BOOTSTRAP_HELPER_MOUNT'),
        (lambda cm,j,b,m: m.update(mountPath='/tmp/other'), 'BOOTSTRAP_HELPER_MOUNT'),
        (lambda cm,j,b,m: b.update(command=['node','elsewhere.js']), 'BOOTSTRAP_HELPER_MOUNT'),
        (lambda cm,j,b,m: j['spec']['template']['spec']['containers'][0]['volumeMounts'].append(m), 'BOOTSTRAP_HELPER_MOUNT'),
    ):
        changed=copy.deepcopy(docs);mut(*state(changed))
        results.append(refused(lambda: check(manifest,changed),code))
        check(manifest,docs)
    results.append(refused(lambda:check({},docs),'BOOTSTRAP_HELPER_CONFIGMAP'))
    script=one(docs,'ConfigMap','provision-scripts')['data']['source-contract.json']
    frozen.rendered_contract(manifest,script,receipt)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('manifest','render','inventory','binding_receipt'):
        parser.add_argument(field,type=Path)
    args=parser.parse_args()
    load=lambda p:json.loads(p.read_bytes())
    binding=dict(path=str(args.binding_receipt.resolve()),sha256=frozen.digest(args.binding_receipt.read_bytes()))
    result=controls(load(args.manifest),load(args.render),load(args.inventory),binding)
    print(json.dumps({'restored':'PASS','refusals':result},indent=2))
