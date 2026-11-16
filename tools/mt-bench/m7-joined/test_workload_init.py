"""Execute main/VU initialization and payloads; threshold metadata is main-only."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter
from workload import generate

JS = r'''
const fs=require('node:fs'),vm=require('node:vm');
const [file,vu]=process.argv.slice(1),calls=[];
const tenants=Array.from({length:1000},(_,i)=>({id:'tenant-'+i,host:'tenant-'+i+'.invalid',token:'synthetic-'+i}));
const c={calls,__VU:Number(vu),__ENV:{BASE_URL:'http://synthetic.invalid',TENANTS_FILE:'unused',RUN_ID:'synthetic-init',RUN_START:'1800000000000',DURATION:'180',ACCEL:'1',HOT_FACTOR:'1',OFFERED_RPS:'60',SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'},
 console:{log(){}},sha256:()=>'',SharedArray:function(name,factory){return factory();},open:()=>JSON.stringify(tenants),exec:{scenario:{iterationInTest:1}},Counter:class{constructor(name){this.name=name}add(value,tags){calls.push({counter:this.name,value,tags})}},
 http:{expectedStatuses:()=>null,get:(url,params)=>{calls.push({method:'GET',url,params});return{status:200,body:JSON.stringify({token:'synthetic-jwt'})}},post:(url,body,params)=>{calls.push({method:'POST',url,body:JSON.parse(body),params});return{status:200}}}};
vm.createContext(c);let source=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
source+=`\nconst data=setup();for(const i of [1,999]){exec.scenario.iterationInTest=i;w_sgv();w_devicestatus();w_treatments_v3(data);r_sgv();r_devicestatus();r_treatments();r_status();}JSON.stringify({options,calls});`;
console.log(vm.runInContext(source,c,{timeout:5000}));
'''

class WorkloadInit(unittest.TestCase):
    def test_thresholds_stay_complete_in_main_without_per_vu_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'workload.js';generate(adapter.ROOT,path)
            source=path.read_text()
            def observe(vu):
                return json.loads(subprocess.check_output(['node','-e',JS,str(path),str(vu)],text=True,timeout=10))
            main=observe(0);vu=observe(1)
            self.assertEqual(len([k for k in main['options']['thresholds'] if k.startswith('writes_ok{tenant:')]),1000)
            self.assertEqual(len([k for k in main['options']['thresholds'] if k.startswith('writes_uncertain{tenant:')]),1000)
            self.assertEqual(vu['calls'],main['calls'])
            self.assertEqual({k:v for k,v in vu['options'].items() if k!='thresholds'}, {k:v for k,v in main['options'].items() if k!='thresholds'})
            def no_roster_metadata(value):
                self.assertFalse(any('{tenant:' in key for key in value['options']['thresholds']), 'PER_VU_ROSTER_METADATA')
            no_roster_metadata(vu)
            # Break the actual guard: detect per-VU metadata while main options
            # and emitted payloads remain equal. Restore and check again.
            guard="typeof __VU === 'undefined' || __VU === 0"
            self.assertEqual(source.count(guard),1)
            path.write_text(source.replace(guard,'true'))
            broken=observe(1)
            with self.assertRaisesRegex(AssertionError,'PER_VU_ROSTER_METADATA'):no_roster_metadata(broken)
            self.assertEqual(observe(0),main)
            self.assertEqual(broken['calls'],main['calls'])
            path.write_text(source);no_roster_metadata(observe(1))

if __name__=='__main__':unittest.main()
