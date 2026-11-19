import copy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import kube_adapter as k
import population_ceiling as p
import toolchain
import frozen
import test_toolchain


class PopulationCeiling(unittest.TestCase):
    def test_common_intent_projects_once_and_render_ignores_or_conflicts_refuse(self):
        manifest=test_toolchain.Toolchain().manifest();manifest['profile']['population']['maxTenants']=10001
        selected=dict(coreCommit='1'*40,deployCommit='2'*40,localImageId='sha256:'+'6'*64,sourceAcceptance='PENDING')
        with patch.object(toolchain.frozen,'source',return_value=selected):
            self.assertEqual(toolchain.local(manifest,{'prepare':{}})['prepare']['population-ceiling'],10001)
            manifest['local']['prepare']['population-ceiling']=10001
            with self.assertRaisesRegex(ValueError,'DUPLICATE_LOCAL_FACT'):toolchain.local(manifest,{'prepare':{}})
        job={'kind':'Job','spec':{'template':{'spec':{'initContainers':[{'name':'bootstrap','env':[{'name':p.ENV,'value':'10001'}]}]}}}}
        p.check_render(manifest,{p.FIELD:10001},[job],k.need)
        for inventory,render in [({},[job]),({p.FIELD:10001},[]),({p.FIELD:10001},[job,job])]:
            with self.assertRaisesRegex(k.Refused,'POPULATION_RENDER_CHANGED'):p.check_render(manifest,inventory,render,k.need)
        p.check_render(manifest,{p.FIELD:10001},[job],k.need)

    def test_actual_mounted_projection_binds_each_owned_container_then_mutations_refuse(self):
        config={p.FIELD:5,'tenants':2}
        pods={role:{'name':role,'uid':'pod-'+role,'workload':'Job/primer' if role=='primer' else 'StatefulSet/cohort',
                    'containers':{'done' if role=='primer' else role:{'ready':True,'containerID':'container-'+role}}}
              for role in ('api','evaluator','realtime','primer')}
        baseline={'pods':pods};calls=[]
        def selected(c,observation,role):return role,role
        def call(argv,read):
            self.assertFalse(read);calls.append(argv)
            role=argv[-1]
            return json.dumps({'effective':5,'sha256':'a'*64,
                **({'protocol':p.PROTOCOL,'seedCount':2} if role=='primer' else {})}).encode()
        with patch.object(k,'selected_pod',side_effect=selected):
            receipt=p.capture(k,config,baseline,SimpleNamespace(call=call))
            p.verify_capture(k,config,baseline,receipt)
            self.assertEqual(len(calls),4)
            for role in receipt['roles']:
                wrong=copy.deepcopy(receipt);wrong['roles'][role]['effective']=10000
                with self.assertRaisesRegex(k.Refused,'POPULATION_READBACK_(OWNER|CHANGED)'):
                    p.verify_capture(k,config,baseline,wrong)
                wrong=copy.deepcopy(receipt);wrong['roles'][role]['containerId']='foreign'
                with self.assertRaisesRegex(k.Refused,'POPULATION_READBACK_OWNER'):
                    p.verify_capture(k,config,baseline,wrong)
            p.verify_capture(k,config,baseline,receipt)


if __name__=='__main__':unittest.main()
