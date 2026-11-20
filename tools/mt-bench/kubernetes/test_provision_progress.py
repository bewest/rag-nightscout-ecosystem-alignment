"""Drive the real suspended Job release and readiness waiter with a controlled clock."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import application_topology
import experiment
import lifecycle_config
from kube_adapter import frozen
from primer_progress import ProgressWindow
import producer_startup
import scheduling


def scope(**values):
    values.update(ProgressWindow=ProgressWindow, scheduling=scheduling, subprocess=subprocess)
    source = Path(__file__).with_name('lifecycle.py')
    names = {'install', 'ready'}
    body = [node for node in ast.parse(source.read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=body, type_ignores=[]), str(source), 'exec'), values)
    return values


class ProvisionProgress(unittest.TestCase):
    def test_authored_stall_window_reaches_job_init_and_preflight(self):
        intent = {'profile':{'phases':{'startupWindows':{'kubernetes':{'primerReadySeconds':4200}}}}}
        env = {'workDeadlineSeconds':7200, 'provisionDeadlineSeconds':600}
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            lib = package/'lib/ns/nightscout.libsonnet'
            lib.parent.mkdir(parents=True)
            lib.write_text("{}")
            experiment.bind_primer_stall(package, intent)
            self.assertIn("{ name: 'NS_PRIMER_STALL_SECONDS', value: '4200' }", lib.read_text())
        init = {'name':'primer', 'env':[]}
        job = {'kind':'Job', 'metadata':{'name':'primer'}, 'spec':{'template':{'spec':{
            'initContainers':[init], 'containers':[{'name':'done'}]}}}}
        with self.assertRaisesRegex(ValueError, 'PRIMER_STALL_WINDOW_CHANGED'):
            lifecycle_config.startup_preflight(intent,env,[job])
        init['env'].append({'name':'NS_PRIMER_STALL_SECONDS', 'value':'4200'})
        result = lifecycle_config.startup_preflight(intent,env,[job])
        self.assertEqual(result['selectedSeconds']['primerReadySeconds'],4200)

    def test_install_starts_only_the_claim_primer_and_patches_no_deadline(self):
        # 57e2c62785: Jobs are applied as authored; only the claim-mode primer, rendered
        # suspended, is started. No deadline or suspend patching of any other Job.
        for name, location, started in (('primer', 'claim', True), ('primer', 'controller', False),
                                        ('verification', 'claim', False)):
            with self.subTest(name=name, location=location):
                job = {'kind': 'Job', 'metadata': {'name': name, 'namespace': 'ns'},
                       'spec': {'activeDeadlineSeconds': 6, 'suspend': True}}
                created = []
                def create(obj):
                    created.append(obj)
                    return {'kind': obj['kind'], 'metadata': {'name': obj['metadata']['name'], 'uid': 'owned'}}
                env = scope(owned=lambda: None, uids=[], step=lambda _stage: None, put=lambda *_: None,
                            objects=lambda _stage: [copy.deepcopy(job)], create=create, ns='ns',
                            intent={'primerLocation': location})
                env['install'](name)
                self.assertEqual(created[0]['spec'], {'activeDeadlineSeconds': 6, 'suspend': not started})

    def test_running_role_and_platform_job_renew_only_on_forward_milestones(self):
        for name in ('pgstream','provision'):
            for wedged in (True,False):
                with self.subTest(name=name,wedged=wedged):
                    clock=SimpleNamespace(now=0)
                    clock.time=clock.monotonic=lambda:clock.now
                    clock.sleep=lambda n:setattr(clock,'now',clock.now+n)
                    records={}
                    def pods(_):
                        elapsed=min(clock.now,4) if wedged else clock.now
                        status={'conditions':[],'initContainerStatuses':[]}
                        if elapsed>=4:status['conditions'].append({'type':'PodScheduled','status':'True'})
                        if elapsed>=8:status['initContainerStatuses'].append({'state':{'terminated':{'exitCode':0}}})
                        if elapsed>=12:status['conditions'].append({'type':'Ready','status':'True'})
                        return [{'metadata':{'uid':'pod','name':name+'-xyz','labels':{'nightscout.org/run-id':'run'}},
                                 'spec':{'nodeName':'worker'} if elapsed>=4 else {},'status':status}]
                    target=scope(time=clock,work=24,phase_cutoff=None,rid='run',owned=lambda:None,
                        pods=pods,step=lambda *_:None,summary=lambda _:{'uid':'pod','containers':[]},
                        producer_startup=producer_startup,application_topology=application_topology,
                        intent={},frozen=frozen,put=lambda n,v:records.update({n:v}))
                    if wedged:
                        with self.assertRaisesRegex(RuntimeError,'READINESS_STALLED_'+name):
                            target['ready']('owned',name,6)
                        self.assertEqual(clock.now,10)
                    else:
                        self.assertIsNotNone(target['ready']('owned',name,6))
                        self.assertEqual(clock.now,12)
                    self.assertEqual(records['startup-window-'+name+'.json']['workUntilEpochSeconds'],24)

    def test_advancing_milestones_still_stop_at_the_work_window(self):
        clock = SimpleNamespace(now=0)
        clock.time = clock.monotonic = lambda: clock.now
        clock.sleep = lambda n: setattr(clock, 'now', clock.now + n)
        def pods(_):
            # A new milestone every 4 s; Ready would arrive at 12 s.
            status = {'conditions': [], 'initContainerStatuses': []}
            if clock.now >= 4: status['conditions'].append({'type': 'PodScheduled', 'status': 'True'})
            if clock.now >= 8: status['initContainerStatuses'].append({'state': {'terminated': {'exitCode': 0}}})
            if clock.now >= 12: status['conditions'].append({'type': 'Ready', 'status': 'True'})
            return [{'metadata': {'uid': 'pod', 'name': 'primer-xyz', 'labels': {'nightscout.org/run-id': 'run'}},
                     'spec': {'nodeName': 'worker'} if clock.now >= 4 else {}, 'status': status}]
        for work, ready in ((9, False), (24, True)):
            with self.subTest(work=work):
                clock.now = 0
                target = scope(time=clock, work=work, phase_cutoff=None, rid='run', owned=lambda: None,
                               pods=pods, step=lambda *_: None, summary=lambda _: {'uid': 'pod', 'containers': []},
                               producer_startup=producer_startup, application_topology=application_topology,
                               intent={}, frozen=frozen, put=lambda *_: None)
                if ready:
                    self.assertIsNotNone(target['ready']('owned', 'primer', 6))
                else:
                    with self.assertRaisesRegex(RuntimeError, 'READY_DEADLINE_primer'):
                        target['ready']('owned', 'primer', 6)
                    self.assertEqual(clock.now, 9)

    def test_sealed_reason_requires_initialized_and_sealed_in_returned_health(self):
        for health, expected in (({'initialized':True,'sealed':True},True),
                                 ({'data':{'initialized':True,'sealed':True}},True),
                                 ({'initialized':False,'sealed':True},False),
                                 ({'initialized':True,'sealed':False},False), ({},False)):
            self.assertEqual(producer_startup.vault_sealed(health),expected)
