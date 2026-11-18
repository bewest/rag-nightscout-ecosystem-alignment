import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import adapter
import driver_vu_diagnostic as v
import workload


class DriverVuDiagnosticTests(unittest.TestCase):
    def test_selection_refuses_incomparable_scopes(self):
        args = SimpleNamespace(driver_vu_diagnostic='trace-v1', profile='pgstream-sample', run_purpose='discovery', replicas=1, tenants=1000)
        cadence = {'offeredRps':180, 'loadSeconds':310}
        self.assertEqual(v.selection(args,cadence), {'driverVuDiagnostic':'trace-v1'})
        for key, value in [('offeredRps',120),('loadSeconds',300),('driverShards',8),('workloadMix','realistic-v1'),('restartDuringLoadAfterSeconds',30)]:
            with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_DIAGNOSTIC_SCOPE'):
                v.selection(args, cadence | {key:value})
        args.node_observation='profile-v1'
        with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_DIAGNOSTIC_SCOPE'):v.selection(args,cadence)
        args.node_observation='off';args.driver_vu_diagnostic=None
        self.assertEqual(v.selection(args,cadence),{})

    def test_command_keeps_limits_and_refuses_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'k6').mkdir()
            a=SimpleNamespace(assert_owned=Mock());m={'runPurpose':'discovery','cadence':{'driverVuDiagnostic':'trace-v1'}}
            command=['docker','run','--cpus','4','--memory','8g','image','run','--quiet','--summary-export','/out/k6-summary.json','/scripts/workload.js']
            with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_DIAGNOSTIC_SCOPE'):v.select_command(a,d,m,command[:-1])
            self.assertFalse((d/'k6'/v.SCRIPT).exists())
            result=v.select_command(a,d,m,command)
            self.assertEqual(result[:6],command[:6]);self.assertIn('csv=/out/k6-scheduling.csv.gz',result)
            self.assertEqual((d/'k6'/v.SCRIPT).read_bytes(),Path(v.__file__).with_name(v.SCRIPT).read_bytes())
            a.assert_owned.assert_called_once_with(m)
            with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_WRAPPER_EXISTS'):v.select_command(a,d,m,command)
            with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_DIAGNOSTIC_SCOPE'):v.select_command(a,d,m | {'remoteTransport':True},command)
            self.assertEqual(v.select_command(a,d,{'cadence':{}},command),command)

    def test_real_workload_plan_keeps_schedule_and_exact_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'workload.js';workload.generate(adapter.ROOT,script)
            inspect = r"""
const fs=require('fs'),vm=require('vm');const [work,wrapper,mode]=process.argv.slice(1);
const context={__ENV:{ACCEL:'1',HOT_FACTOR:'1',DURATION:'310',OFFERED_RPS:'180',
 SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'},
 SharedArray:function(_,fn){return fn();},open:()=>JSON.stringify(Array.from({length:1000},(_,id)=>({id}))),Counter:class{}};
let text=fs.readFileSync(work,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
const base=vm.runInNewContext(text+'\noptions;',context);
const wrapperContext={base,__ENV:{M7_DRIVER_VU_DIAGNOSTIC:mode},workloadSetup:()=>({}),console:{log:()=>{}}};
text=fs.readFileSync(wrapper,'utf8').replace(/^import .*;$/gm,'').replace(/^export \{[\s\S]*?\} from .*;$/m,'').replace(/^export /gm,'');
console.log(JSON.stringify(vm.runInNewContext(text+'\n({plan,options});',wrapperContext)));
"""
            def plan(mode):return json.loads(subprocess.check_output(['node','-e',inspect,str(script),str(Path(v.__file__).with_name(v.SCRIPT)),mode],text=True))
            before,after,restored=map(plan,('trace-v1','preallocated-v1','trace-v1'))
            self.assertEqual(before,restored)
            self.assertEqual(before['plan']['aggregatePreallocatedVUs'],403)
            self.assertEqual(after['plan']['aggregatePreallocatedVUs'],620)
            self.assertEqual(sum(row['preAllocatedVUs'] for row in after['options']['scenarios'].values()),620)
            for shape, row in before['options']['scenarios'].items():
                actual=after['options']['scenarios'][shape]
                self.assertEqual({k:x for k,x in row.items() if k!='preAllocatedVUs'}, {k:x for k,x in actual.items() if k!='preAllocatedVUs'})
                self.assertGreaterEqual(actual['preAllocatedVUs'],row['preAllocatedVUs'])
                self.assertLessEqual(actual['preAllocatedVUs'],row['maxVUs'])
            bad=subprocess.run(['node','-e',inspect,str(script),str(Path(v.__file__).with_name(v.SCRIPT)),'unknown'],capture_output=True,text=True)
            self.assertNotEqual(bad.returncode,0);self.assertIn('M7_DRIVER_VU_MODE',bad.stderr)

    def test_parser_and_cadence_use_existing_contract(self):
        a=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',replicas=1,tenants=1000,
                          offered_rps=180,load_seconds=310,driver_vu_diagnostic='preallocated-v1')
        self.assertEqual(adapter.cadence_options(a)['driverVuDiagnostic'],'preallocated-v1')
        a.tenants=10000
        with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_DIAGNOSTIC_SCOPE'):adapter.cadence_options(a)


if __name__=='__main__':unittest.main()
