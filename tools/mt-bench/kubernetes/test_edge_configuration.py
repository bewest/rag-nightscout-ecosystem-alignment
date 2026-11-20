"""Exact selected edge readback; no native actors."""
import copy
import json
from pathlib import Path
import subprocess
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


if __name__=='__main__':unittest.main()
