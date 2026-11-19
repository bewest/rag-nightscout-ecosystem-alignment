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
    names = {'release_job', 'ready', 'provisioned_count'}
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

    def test_release_uses_remaining_work_only_for_primer(self):
        for name, bound in (('primer', 24), ('verification', 6)):
            job = {'kind': 'Job', 'metadata': {'uid': 'owned'},
                   'spec': {'activeDeadlineSeconds': 6, 'suspend': True}}
            def patch(args):
                for op in json.loads(args[-1]):
                    parent, field = op['path'].lstrip('/').split('/')
                    if op['op'] == 'test':
                        self.assertEqual(job[parent][field], op['value'])
                    else:
                        self.assertEqual(op['op'], 'replace')
                        job[parent][field] = op['value']
                return json.dumps(job).encode()
            env = scope(owned=lambda: None, uids=[{'kind':'Job', 'name':name, 'uid':'owned'}],
                        get=lambda *_:copy.deepcopy(job), k=patch, ns='ns',
                        json=json, time=SimpleNamespace(time=lambda:15.2), work=40)
            env['release_job'](name)
            self.assertIs(job['spec']['suspend'], False)
            self.assertEqual(job['spec']['activeDeadlineSeconds'], bound)

    def attempt(self, *, wedged=False, work=32, probe_error=None):
        clock = SimpleNamespace(now=0)
        clock.time = clock.monotonic = lambda:clock.now
        clock.sleep = lambda seconds:setattr(clock, 'now', clock.now + seconds)
        records = {}
        uid = 'primer-job'
        job = {'metadata':{'uid':uid}, 'spec':{'activeDeadlineSeconds':work}}
        def sample(_):
            running = {'name':'primer', 'state':{'running':{}}, 'restartCount':0}
            done = {'name':'done', 'state':{'running':{}}, 'ready':True, 'restartCount':0}
            ready = clock.now >= 16 and not wedged
            return [{'metadata':{'uid':'one-pod','name':'primer-xyz','labels':{'nightscout.org/run-id':'run'},
                                 'ownerReferences':[{'controller':True,'uid':uid}]},
                     'status':{'initContainerStatuses':[running], 'containerStatuses':[done] if ready else [],
                               'conditions':[{'type':'Ready','status':'True' if ready else 'False'}]}}]
        def execpod(pod, container, args):
            self.assertEqual((pod['metadata']['uid'], container), ('one-pod', 'primer'))
            self.assertIn('provisioned.json', args[2])
            if probe_error:
                raise RuntimeError(probe_error)
            count = min(3, int(clock.now//4))
            return str(min(1, count) if wedged else count).encode()
        def summary(pod):
            init = pod['status']['initContainerStatuses']
            return {'uid':'one-pod', 'name':'primer-xyz', 'containers':init}
        env = scope(time=clock, work=work, phase_cutoff=None, e={'tenantCount':3}, split=True,
                    ns='ns', rid='run', json=json, subprocess=subprocess, execpod=execpod,
                    owned=lambda:None, pods=sample, summary=summary, step=lambda _:None,
                    producer_startup=producer_startup, application_topology=application_topology,
                    intent={}, frozen=frozen, put=lambda name, row:records.update({name:row}))
        return lambda:env['ready']('job-name=primer','primer',6,primer_job=job), clock, records

    def test_alive_unchanged_checkpoint_stalls_then_real_advances_outlast_former_cutoff(self):
        launch, clock, receipts = self.attempt(wedged=True)
        with self.assertRaisesRegex(RuntimeError, 'PRIMER_PROVISION_STALLED'):
            launch()
        self.assertEqual((clock.now, receipts['startup-window-primer.json']['completedTenants']), (10,1))
        launch, clock, receipts = self.attempt()
        self.assertEqual(launch()['metadata']['uid'], 'one-pod')
        self.assertEqual((clock.now, receipts['startup-window-primer.json']['completedTenants']), (16,3))

    def test_advancing_seed_still_stops_at_owner_boundary(self):
        launch, clock, receipts = self.attempt(work=9)
        with self.assertRaisesRegex(RuntimeError, 'READY_DEADLINE_primer'):
            launch()
        self.assertEqual((clock.now, receipts['startup-window-primer.json']['completedTenants']), (9,2))

    def test_unobservable_checkpoint_never_renews(self):
        launch, clock, _ = self.attempt(probe_error='PRIVATE_STEP_FAILED')
        with self.assertRaisesRegex(RuntimeError, 'PRIMER_PROVISION_PROGRESS_UNMEASURED'):
            launch()
        self.assertEqual(clock.now, 6)

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

    def test_sealed_reason_requires_initialized_and_sealed_in_returned_health(self):
        for health, expected in (({'initialized':True,'sealed':True},True),
                                 ({'data':{'initialized':True,'sealed':True}},True),
                                 ({'initialized':False,'sealed':True},False),
                                 ({'initialized':True,'sealed':False},False), ({},False)):
            self.assertEqual(producer_startup.vault_sealed(health),expected)

    def test_user_cancellation_interrupts_probe(self):
        launch, clock, _ = self.attempt(probe_error='CONTROLLER_SIGNAL_15')
        with self.assertRaisesRegex(RuntimeError, 'CONTROLLER_SIGNAL_15'):
            launch()
        self.assertEqual(clock.now, 0)
