"""Actual Jsonnet constructor and exact selected edge readback; no native actors."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import kube_adapter as k
import edge_configuration as edge
import toolchain
from test_adapter import fixture
import test_toolchain as common


class EdgeConfiguration(unittest.TestCase):
    def test_common_intent_transports_only_kubernetes_selection(self):
        original=common.Toolchain().manifest();original['kubernetes']={'edge':{'workerProcesses':2,'workerConnections':8192}}
        selected=dict(coreCommit='1'*40,deployCommit='2'*40,localImageId='sha256:'+'6'*64,sourceAcceptance='PENDING')
        with patch.object(toolchain.frozen,'source',return_value=selected):
            local=toolchain.local(original,{'prepare':{}})
            self.assertNotIn('diagnostic-resource-allocation',local['prepare'])
            self.assertNotIn('diagnostic-resource-profile',local['prepare'])
            self.assertNotIn('edge',toolchain.legacy(original,'compose'))
            self.assertEqual(toolchain.legacy(original)['edge'],original['kubernetes']['edge'])
            with tempfile.TemporaryDirectory() as directory:
                out=Path(directory)/'projection'
                toolchain.project(original,{},'kubernetes',out)
                self.assertEqual(k.document(out/'binding-inputs.json'),{'edge':original['kubernetes']['edge']})
                self.assertEqual(k.document(out/'manifest.json')['edge'],original['kubernetes']['edge'])
                with patch.object(subprocess,'run'):
                    result=toolchain.project(original,{'prepare':{}},'compose',Path(directory)/'local')
                self.assertEqual(result['notApplicable'],['kubernetes.edge'])
        for value in ({'workerProcesses':True},{'workerProcesses':1025},{'workerConnections':0},{'workerConnections':2**53},{'worker_processes':2}):
            with self.assertRaisesRegex(ValueError,'EDGE_'):edge.selection(value)
        self.assertEqual(edge.selection({'workerProcesses':edge.NGINX_MAX_WORKERS}),{'workerProcesses':1024})
        self.assertIsNone(edge.selection({}))

    def test_inventory_hash_and_exact_configmap_readback_red_restored(self):
        c,inventory,render,client=fixture();selected={'workerProcesses':2,'workerConnections':8192}
        source='worker_processes auto;\nevents { worker_connections 1024; }\nhttp { # synthetic exact route bytes\n}\n'
        config={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'edge-nginx','namespace':c['namespace'],'labels':{c['ownerLabel']:c['runId']}},'data':{'nginx.conf':edge.project(source,selected)}}
        render.append(config);inventory['edgeConfiguration']=edge.record(selected)
        c['edgeConfiguration']=edge.check({'edge':selected},inventory,render,k.need)
        actual=copy.deepcopy(config);actual['metadata'].update(uid='edge-owned',resourceVersion='1');client.objects['ConfigMap/edge-nginx']=actual
        objects=k.validate(c,inventory,render)
        baseline=k.observe(c,objects,client)
        self.assertEqual(baseline['edgeConfiguration']['configurationSha256'],c['edgeConfiguration']['configurationSha256'])
        original=copy.deepcopy(actual['data'])
        for text,code in ((original['nginx.conf'].replace('8192','8193'),'EDGE_CONFIGMAP_CHANGED'),(original['nginx.conf']+'# changed route bytes\n','EDGE_CONFIGMAP_CHANGED'),('<redacted>','EDGE_CONFIGMAP_UNMEASURED')):
            actual['data']['nginx.conf']=text
            with self.assertRaisesRegex(k.Refused,code) as caught:k.observe(c,objects,client)
            if text=='<redacted>':self.assertEqual(caught.exception.verdict,'UNMEASURED')
            actual['data']=copy.deepcopy(original);k.observe(c,objects,client)
        bad=copy.deepcopy(inventory);bad['edgeConfiguration']['effective']['workerProcesses']=3
        with self.assertRaisesRegex(k.Refused,'EDGE_INVENTORY_CHANGED'):k.validate(c,bad,render)
        bad=copy.deepcopy(c);bad['edgeConfiguration']['configurationSha256']='f'*64
        with self.assertRaisesRegex(k.Refused,'EDGE_CONFIGURATION_CHANGED'):k.validate(bad,inventory,render)
        bad=copy.deepcopy(c);bad['edgeConfiguration']=None
        with self.assertRaisesRegex(k.Refused,'EDGE_CONFIGURATION_CHANGED'):k.validate(bad,inventory,render)
        actual['data']=None
        with self.assertRaisesRegex(k.Refused,'EDGE_CONFIGMAP_CHANGED'):k.observe(c,objects,client)
        actual['data']=copy.deepcopy(original);k.observe(c,objects,client)
        k.validate(c,inventory,render)
        print('RED_RESTORED selected edge inventory, config hash, exact native data and masked-data UNMEASURED')


class ActualBinding(unittest.TestCase):
    def setUp(self):
        source=os.environ.get('K8S_BINDING_SOURCE')
        if not source or not shutil.which('tk'):self.skipTest('K8S_BINDING_SOURCE and tk required')
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        revision=os.environ.get('K8S_BINDING_COMMIT','4d3efc3e9dbdf648cd97baed8237d48e36b4ea22')
        raw=subprocess.check_output(['git','-C',source,'archive',revision,'bindings/kubernetes'])
        with tarfile.open(fileobj=io.BytesIO(raw))as archive:archive.extractall(self.root,filter='data')
        subprocess.run(['git','apply','--directory=bindings/kubernetes',str(k.HERE/'binding-input.patch')],cwd=self.root,check=True)
        self.binding=self.root/'bindings/kubernetes';self.input=self.binding/'environments/synthetic/inputs.json';self.original=k.document(self.input)
        self.input.with_name('main.jsonnet').write_text("local ns=import 'ns/nightscout.libsonnet';local b=ns.new(import 'inputs.json');{render:b,inventory:b.inventory}")

    def render(self,selected=None,success=True):
        inputs=copy.deepcopy(self.original)
        if selected is not None:inputs['edge']={**inputs.get('edge',{}),**selected}
        self.input.write_text(json.dumps(inputs))
        actual=subprocess.run(['tk','eval','environments/synthetic'],cwd=self.binding,capture_output=True,text=True)
        if not success:
            self.assertNotEqual(actual.returncode,0);self.assertIn('EDGE_',actual.stderr);return actual.stderr
        self.assertEqual(actual.returncode,0,actual.stderr);return json.loads(actual.stdout)

    def text(self,value):return value['render']['edge']['config']['data']['nginx.conf']

    def checks(self,value):
        file=self.root/'render.json';file.write_text(json.dumps(value))
        script="const c=require(process.argv[1]),v=require(process.argv[2]);console.log(JSON.stringify(c.checks(c.manifests(v.render),v.inventory).filter(x=>['package-assets','edge-configuration'].includes(x.name))));"
        return json.loads(subprocess.check_output(['node','-e',script,self.binding/'check/invariants.js',file]))

    def test_real_constructor_selected_defaults_and_exact_source_checks(self):
        default=self.render();selected=self.render({'workerProcesses':2,'workerConnections':8192})
        self.assertEqual(self.text(default),(self.binding/'assets/nginx.conf').read_text())
        self.assertNotIn('edgeConfiguration',default['inventory'])
        self.assertEqual(self.text(selected),self.text(default).replace('worker_processes auto;','worker_processes 2;').replace('worker_connections 1024;','worker_connections 8192;'))
        self.assertEqual(selected['inventory']['edgeConfiguration'],edge.record({'workerProcesses':2,'workerConnections':8192}))
        self.assertTrue(all(not row['failures']for row in self.checks(selected)))
        for change in (lambda v:v['inventory']['edgeConfiguration']['effective'].update(workerConnections=8193),lambda v:v['render']['edge']['config']['data'].update({'nginx.conf':self.text(v)+'# source changed\n'})):
            bad=copy.deepcopy(selected);change(bad);self.assertTrue(any(row['failures']for row in self.checks(bad)))
            self.assertTrue(all(not row['failures']for row in self.checks(selected)))
        for key,value in (('workerProcesses',True),('workerProcesses',0),('workerProcesses',1025),('workerConnections',0),('workerConnections',1.5),('workerConnections',2**53),('worker_processes',2)):
            self.render({key:value},success=False)
        for value in ({'workerProcesses':1024},{'workerConnections':edge.MAX_EXACT_INTEGER}):
            current=self.render(value)
            self.assertTrue(all(not row['failures']for row in self.checks(current)))
        self.assertEqual(self.text(self.render()),self.text(default))

    def test_malformed_ambiguous_asset_controls_restore(self):
        asset=self.binding/'assets/nginx.conf';original=asset.read_text();selected={'workerProcesses':2,'workerConnections':8192}
        for text in (original+'worker_processes auto;\n',original.replace('worker_connections 1024;','worker_connections 2048;'),original.replace('worker_processes auto;','')):
            asset.write_text(text);self.render(selected,success=False);asset.write_text(original);self.render(selected)
        self.assertTrue(all(not row['failures']for row in self.checks(self.render(selected))))
        print('RED_RESTORED actual Jsonnet malformed/ambiguous source')


if __name__=='__main__':unittest.main()
