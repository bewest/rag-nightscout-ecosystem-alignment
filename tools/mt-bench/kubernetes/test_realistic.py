"""Released generator options and normal adapter/profile selectors with controls."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_adapter import k, execute as e, fixture
import workload_runtime as w
from workloads import profile as profiles

JS = r'''
const fs=require('fs'),vm=require('vm');const [script,n,env]=process.argv.slice(1);
const context={__ENV:JSON.parse(env),SharedArray:function(_,fn){return fn();},open:()=>JSON.stringify(Array.from({length:Number(n)},(_,id)=>({id}))),Counter:class{}};
const source=fs.readFileSync(script,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
console.log(JSON.stringify(vm.runInNewContext(source+'\noptions.scenarios;',context)));
'''

class Realistic(unittest.TestCase):
    def settings(self, **changes):
        return dict(loadSeconds=1800,workloadMix='realistic-v1',workloadScale=1,logicalPollingClients=50,probeEveryMs=300000,**changes)

    def test_actual_generated_options_match_profiles_at_all_populations_and_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'workload.js';k.workload.generate(k.ROOT,path)
            for n in (500,1000,3000):
                for scale in (1,2):
                    settings=self.settings();settings['workloadScale']=scale
                    env=w.environment(settings,dict(ACCEL='1',HOT_FACTOR='1',DURATION='1800',SHAPES=','.join(w.SHAPES)),k.need)
                    self.assertNotIn('OFFERED_RPS',env)
                    options=json.loads(subprocess.check_output(['node','-e',JS,str(path),str(n),json.dumps(env)]))
                    cycles,rates=w.rates(settings,n)
                    self.assertEqual(set(options),set(w.SHAPES))
                    for shape,row in options.items():
                        self.assertEqual(row['duration'],'1800s')
                        self.assertEqual(row['timeUnit'],str(cycles[shape])+'ms')
                        self.assertAlmostEqual(row['rate']*1000/cycles[shape],rates[shape])
                    self.assertAlmostEqual(sum(rates.values()),n/72*scale)
                    # Exercise the released JS guard too, independently of Python.
                    env['OFFERED_RPS']='18'
                    broken=subprocess.run(['node','-e',JS,str(path),str(n),json.dumps(env)],capture_output=True,text=True)
                    self.assertNotEqual(broken.returncode,0)
                    self.assertIn('M7_REALISTIC_MIX_CONFIGURATION',broken.stderr)
                    del env['OFFERED_RPS']
                    subprocess.run(['node','-e',JS,str(path),str(n),json.dumps(env)],check=True,stdout=subprocess.DEVNULL)
            print('RED_RESTORED M7_REALISTIC_MIX_CONFIGURATION actual released generator')

    def test_sparse_zero_full_and_environment_selector_controls(self):
        settings=self.settings()
        for viewers in (0,1,50,500,1000):
            settings['logicalPollingClients']=viewers
            w.validate(settings,k.need)
            assigned=k.viewer_plan.counts({'tenants':500,'cadence':settings},[{'id':str(i)} for i in range(500)])
            self.assertEqual(sum(assigned.values()),viewers)
            if viewers<500:self.assertEqual(sum(n>0 for n in assigned.values()),viewers)
        for change,code in (({'offeredRps':18},'REALISTIC_MIX_CONFIGURATION'),({'workloadScale':True},'WORKLOAD_SCALE_CONFIGURATION'),({'workloadScale':float('nan')},'WORKLOAD_SCALE_CONFIGURATION'),({'hotFactor':2},'REALISTIC_MIX_CONFIGURATION')):
            with self.assertRaisesRegex(k.Refused,code):w.validate({**settings,**change},k.need)
            w.validate(settings,k.need)
        for key,value in [('OFFERED_RPS','18'),('M7_WORKLOAD_SCALE','2'),('M7_WORKLOAD_MIX','unknown')]:
            with self.assertRaisesRegex(k.Refused,'WORKLOAD_ENVIRONMENT_CONFLICT'):w.environment(settings,{key:value},k.need)
            w.environment(settings,{},k.need)
        old=dict(loadSeconds=330,offeredRps=18,logicalPollingClients=500,probeEveryMs=300000)
        self.assertEqual(w.environment(old,{},k.need),{'OFFERED_RPS':'18','DRIVER_HEADROOM':'2.0'})
        print('RED_RESTORED K8S_WORKLOAD_ENVIRONMENT_CONFLICT; sparse/zero/full assignments')

    def test_normal_prepare_rejects_override_before_output_or_actor(self):
        c,inv,render,_=fixture();c['tenants']=2;c['workload']={**self.settings(), 'offeredRps':18}
        with self.assertRaisesRegex(k.Refused,'REALISTIC_MIX_CONFIGURATION'):k.validate(c,inv,render)
        del c['workload']['offeredRps'];k.validate(c,inv,render)
        print('RED_RESTORED K8S_REALISTIC_MIX_CONFIGURATION prepare validation')

    def test_bind_replaces_prior_rate_without_leaking_it_and_keeps_marker(self):
        from test_adapter import iso
        import time
        p=profiles.read(profiles.HERE/'small.json');p['workload']=self.settings();p['population'].update(provisionedTenants=500,ordinaryRosterTenants=500);p['phases']['workSeconds']=2400
        c=dict(tenants=500,pins=dict(pair={key:p['referencePins'][key] for key in ('core','deploy')},bindingCommit=p['referencePins']['bindingCommit']),
               driver=dict(resources=dict(millicpus=1000,memoryBytes=1073741824)),observer=dict(resources=dict(millicpus=200,memoryBytes=268435456)),
               workload=dict(offeredRps=18,pointId='realistic-500'),deadlines=dict(workUntil=iso(time.time()+3000),cleanupUntil=iso(time.time()+3600)))
        bound=profiles.bind(p,c)
        self.assertNotIn('offeredRps',bound['workload'])
        self.assertEqual(bound['workload']['pointId'],'realistic-500')
        self.assertEqual(c['workload']['offeredRps'],18)
        self.assertAlmostEqual(sum(profiles.describe(p)['shapeRequestsPerSecond'].values()),500/72)

    def test_legacy_access_setup_does_not_create_a_load_phase(self):
        profile = profiles.read(profiles.HERE/'small.json')
        profile['phases']['accessSetupSeconds'] = 18000
        self.assertNotIn('accessSetupSeconds', profiles.describe(profile)['effectivePhaseWindows'])

if __name__=='__main__':unittest.main()
