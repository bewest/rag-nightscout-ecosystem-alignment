"""Bounded oneoff flags stay inside existing source/owner/epoch authority."""
import copy
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import adapter
import diagnostic_resources as r
import discovery
import orchestration_binding as b
import test_orchestration_binding as fixtures


# These actor-free controls exercise real flock on their own scratch lock.
# Production admission and the active proof's global driver lock stay untouched.
def setUpModule():
    global _unit_directory, _unit_lock_patch
    _unit_directory=tempfile.TemporaryDirectory(prefix='m7-oneoff-unit-')
    _unit_lock_patch=patch('experiment_batch.global_lock_path',return_value=Path(_unit_directory.name)/'heap.lock')
    _unit_lock_patch.start()


def tearDownModule():
    r.configure()
    _unit_lock_patch.stop()
    _unit_directory.cleanup()


class DiagnosticOneoffs(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.Tests('test_oneoff_wrong_image_owner_project_attempt_options_before_effect')
        self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.binding,self.d,self.scope,self.argv=self.fixture.oneoff()
        self.root=Path(self.scope['directory'])
        self.addCleanup(r.configure)

    def meta(self,argv):
        self.assertEqual(argv[:3],['docker','image','inspect'])
        return json.dumps([{'Id':self.scope['imageId'],'Config':{'Entrypoint':['k6'],'Env':[]}}])

    def selected(self):
        config=r.overlay({'services':{'api':{}}},r.NAME)
        budget=r.plan(config)
        owner=b.load(self.root/'owner.json');owner['diagnosticResources']=budget.record()
        (self.root/'owner.json').write_text(json.dumps(owner))
        (self.root/'frozen.compose.json').write_text(json.dumps(config))
        r.configure(r.NAME,config,budget.record(),observe=lambda:[])
        return adapter.bounded_k6_argv(self.argv)

    def test_selected_limits_required_and_native_readback_detects_missing_quota(self):
        argv=self.selected()
        with self.assertRaisesRegex(RuntimeError,'RESOURCE_LIMITS_CHANGED'):
            b._oneoff_intent(self.binding,'k6-version',self.argv,self.scope,self.meta,self.root/'cid')
        intent=b._oneoff_intent(self.binding,'k6-version',argv,self.scope,self.meta,self.root/'cid')
        layout=intent['layout']
        row={'Id':'e'*64,'Image':self.scope['imageId'],'Config':{'Image':self.scope['imageId'],'Cmd':['version'],'Entrypoint':['k6'],'Env':[],'User':'','Labels':layout['labels']},'HostConfig':{'NetworkMode':'none','Tmpfs':{},'Privileged':False,**layout['resourceLimits']},'Mounts':[]}
        b.qualify_oneoff(self.binding,row,intent)
        for field in ('NanoCpus','Memory','MemorySwap'):
            broken=copy.deepcopy(row);broken['HostConfig'][field]=0
            with self.assertRaisesRegex(RuntimeError,'RESOURCE_LIMITS_CHANGED'):
                b.qualify_oneoff(self.binding,broken,intent)
        owner=b.load(self.root/'owner.json');owner['diagnosticResources']['aggregate']['millicpus']=0
        (self.root/'owner.json').write_text(json.dumps(owner))
        with self.assertRaisesRegex(RuntimeError,'RESOURCE_RECORD_CHANGED'):
            b._oneoff_intent(self.binding,'k6-version',argv,self.scope,self.meta,self.root/'cid')

    def test_prospective_discovery_driver_preserves_runtime_and_native_guards(self):
        self.selected()
        owner=b.load(self.root/'owner.json')
        owner.update(runPurpose='discovery',profile='pgstream-sample',pair={'core':'a'*40,'deploy':'b'*40},
                     imageId=self.scope['imageId'],instrument={'sha256':'c'*64})
        (self.root/'owner.json').write_text(json.dumps(owner))
        original=copy.deepcopy(owner['diagnosticResources'])
        with r.discovery_driver(owner) as record:
            (self.root/'loadgen-resource-allocation.json').write_text(json.dumps(record))
            argv=adapter.bounded_k6_argv(self.argv)
            self.assertEqual(argv[3:9],['--cpus','2','--memory',str(4096*r.MIB),'--memory-swap',str(4096*r.MIB)])
            intent=b._oneoff_intent(self.binding,'k6-version',argv,self.scope,self.meta,self.root/'cid')
            self.assertEqual(owner['diagnosticResources'],original)
            limits=intent['layout']['resourceLimits']
            row={'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':'k6'}},'HostConfig':limits}
            r._ACTIVE.observe=lambda:[row]
            self.assertEqual(r._ACTIVE.containers()['k6'],1)
            row['HostConfig']['Memory']=1024*r.MIB
            with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):r._ACTIVE.containers()
            row['HostConfig']['Memory']=4096*r.MIB
            for field,value in [('owner','d'*32),('k6',{'millicpus':4000,'memoryBytes':4096*r.MIB,'maximumConcurrent':1})]:
                changed=copy.deepcopy(record);changed[field]=value
                (self.root/'loadgen-resource-allocation.json').write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError,'DRIVER_ALLOCATION_CHANGED'):
                    b._oneoff_intent(self.binding,'k6-version',argv,self.scope,self.meta,self.root/'cid')
            (self.root/'loadgen-resource-allocation.json').write_text(json.dumps(record))
            b._oneoff_intent(self.binding,'k6-version',argv,self.scope,self.meta,self.root/'cid')
        self.assertEqual(r.standalone_limit(),r.LIMITS['k6'])
        self.assertIsNone(r.discovery_driver_record({**owner,'runPurpose':'acceptance'}))

    def test_checked_custody_labels_do_not_break_resource_command_guard(self):
        argv=self.selected();effects=[]
        def runner(args):
            if args[:3]==['docker','image','inspect']:return self.meta(args)
            if args[:2]==['docker','run']:
                with r.command(args,{}) as (actual,env):
                    self.assertEqual(actual[3:9],argv[3:9]);self.assertIn('--cidfile',actual)
                    self.assertIn(b.ATTEMPT+'='+self.binding['attempt'],actual);effects.append(actual)
                return ''
            return self.d(args)
        b.checked_oneoff(self.binding,'k6-version',argv,self.scope,runner,lambda:True,self.fixture.f.journal)
        self.assertEqual(len(effects),1)

    def test_actual_generator_jwt_option_is_bound_to_recorded_selection(self):
        m={'project':self.binding['project'],'owner':self.scope['owner'],'port':12345,'settingsFingerprint':{'sha256':'f'*64},'cadence':{'loadSeconds':2},'jwtSetupConcurrency':16}
        owner=b.load(self.root/'owner.json');owner['jwtSetupConcurrency']=16
        (self.root/'owner.json').write_text(json.dumps(owner))
        argv=discovery.k6_command(adapter,self.root,m,self.scope['imageId'],'synthetic')
        b._oneoff_intent(self.binding,'k6-load',argv,self.scope,self.meta,self.root/'cid')
        for replacement in ('JWT_SETUP_CONCURRENCY=1','JWT_SETUP_CONCURRENCY=65'):
            broken=[replacement if x=='JWT_SETUP_CONCURRENCY=16' else x for x in argv]
            with self.assertRaisesRegex(RuntimeError,'JWT_SETUP_CHANGED'):
                b._oneoff_intent(self.binding,'k6-load',broken,self.scope,self.meta,self.root/'cid')
        legacy=list(argv);i=legacy.index('JWT_SETUP_CONCURRENCY=16');del legacy[i-1:i+1]
        with self.assertRaisesRegex(RuntimeError,'JWT_SETUP_CHANGED'):
            b._oneoff_intent(self.binding,'k6-load',legacy,self.scope,self.meta,self.root/'cid')
        owner.pop('jwtSetupConcurrency');(self.root/'owner.json').write_text(json.dumps(owner))
        b._oneoff_intent(self.binding,'k6-load',legacy,self.scope,self.meta,self.root/'cid')

    def test_remaining_setup_clock_is_bound_to_authored_window_and_owner(self):
        import phase_windows
        m={'project':self.binding['project'],'owner':self.scope['owner'],'port':12345,
           'settingsFingerprint':{'sha256':'f'*64},'cadence':{'loadSeconds':2,'setupSeconds':900}}
        owner=b.load(self.root/'owner.json');owner['cadence']=m['cadence']
        (self.root/'owner.json').write_text(json.dumps(owner))
        window=phase_windows.start(m,0,1000000)
        (self.root/'load').mkdir(exist_ok=True)
        (self.root/'load/phase-windows.json').write_text(json.dumps(window))
        base=discovery.k6_command(adapter,self.root,m,self.scope['imageId'],'synthetic')
        argv=phase_windows.k6_setup(base,self.scope['imageId'],750,window['setupUntilUnixMs'])
        b._oneoff_intent(self.binding,'k6-load',argv,self.scope,self.meta,self.root/'cid')
        for replacement in ('M7_SETUP_SECONDS=901','M7_SETUP_SECONDS=0','M7_SETUP_UNTIL_MS=99999999'):
            key=replacement.split('=')[0]
            broken=[replacement if x.startswith(key+'=') else x for x in argv]
            with self.assertRaisesRegex(RuntimeError,'SETUP_WINDOW_CHANGED'):
                b._oneoff_intent(self.binding,'k6-load',broken,self.scope,self.meta,self.root/'cid')
        with self.assertRaisesRegex(RuntimeError,'SETUP_WINDOW_CHANGED'):
            b._oneoff_intent(self.binding,'k6-load',base,self.scope,self.meta,self.root/'cid')
        window['owner']='foreign';(self.root/'load/phase-windows.json').write_text(json.dumps(window))
        with self.assertRaisesRegex(RuntimeError,'SETUP_WINDOW_CHANGED'):
            b._oneoff_intent(self.binding,'k6-load',argv,self.scope,self.meta,self.root/'cid')


if __name__=='__main__':unittest.main()
