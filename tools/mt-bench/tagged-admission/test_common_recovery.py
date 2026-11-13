"""Constructed envelope tests backed by archived actual common helper ledger output.
No CLI producer or native acceptance is represented by these fixtures.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import tagged_admission as T
import tagged_capture as C
import test_tagged_capture as recording

FIXTURES=json.loads(Path(__file__).with_name('common_model_fixture.json').read_text())
def fixture(name='pair'):return copy.deepcopy(FIXTURES[name])
def seal(v):
    p=v['plan'];p['sha256']=T.sha({k:x for k,x in p.items() if k!='sha256'});v['expected']['planSha256']=p['sha256'];v['ledger']['planSha256']=p['sha256']
    for r in v['ledger']['controlLeases']:r['planSha256']=p['sha256']
def envelope(v,kind='controlled-connection-observation'):
    return {'version':2,'kind':kind,'visibility':'PG_STAT_AUTHENTICATED_ONLY','source':v['expected']['source'],'expected':{k:v['expected'][k] for k in ('source','imageId','project','workingDirectory')},'planSha256':v['plan']['sha256'],'ledger':v['ledger'],'hostMonotonic':{'startedNs':'1','finishedNs':'2'},**v['census']}

class CommonRecovery(unittest.TestCase):
    def test_helper_classes_and_zero_unknown_never_refund(self):
        for name in FIXTURES:
            v=fixture(name);before=copy.deepcopy(v);r=T.observe(**v)
            self.assertEqual(before,v);self.assertEqual(r['ledgerVersion'],3);self.assertEqual(r['nativeAcceptance'],'UNMEASURED')
            self.assertEqual(r['heldCredits']['control'],len(v['controlProcesses']));self.assertEqual(set(r['occupancy']['physical']['control']),set(T.CLASSES))
        self.assertEqual(T.observe(**fixture('two-unknown'))['heldCredits']['control'],2)
    def test_versions_and_mixed_tuple_refuse(self):
        for field,value in [('version',1),('version',True),('version','2')]:
            v=fixture();v['plan'][field]=value;seal(v)
            with self.assertRaises(ValueError):T.observe(**v)
        for version in (1,2,4,True,'3'):
            v=fixture();v['ledger']['version']=version
            with self.assertRaises(ValueError):T.observe(**v)
    def test_primitive_only_identity_digest_cid_name_project(self):
        for base in ('worker','control','container','principal'):
            for field in {'worker':('incarnation','nonce'),'control':('incarnation','nonce','intentSha256','class','planSha256'),'container':('cid','startedAt','project','imageId','service','workingDirectory'),'principal':('role','database','roleOid','databaseOid')}[base]:
                v=fixture();r=v['ledger']['controlLeases'][0]
                target=v['ledger']['slots']['api'][0] if base=='worker' else r['container'] if base=='container' else r['principal'] if base=='principal' else r
                target[field]=[target[field]]
                with self.subTest(base=base,field=field),self.assertRaises(ValueError):T.observe(**v)
    def test_duplicate_worker_arrays_do_not_evade_identity(self):
        v=fixture();r=v['ledger']['slots']['api'][0];r['incarnation']=[r['incarnation']];v['ledger']['slots']['api'].append(copy.deepcopy(r))
        with self.assertRaises(ValueError):T.observe(**v)
    def test_global_capacity_and_active_one(self):
        v=fixture();v['ledger']['controlLeases'][0]['state']='BOUND';v['ledger']['controlLeases'][0]['stopped']=None
        with self.assertRaisesRegex(ValueError,'COMMON_CAPACITY'):T.observe(**v)
        v=fixture('two-unknown');r=copy.deepcopy(v['ledger']['controlLeases'][0]);r.update(incarnation='e'*32,nonce='f'*32,tags=[T.tag('e'*32,T.CONTROL)]);v['ledger']['controlLeases'].append(r)
        with self.assertRaisesRegex(ValueError,'COMMON_CAPACITY'):T.observe(**v)
    def test_live_predecessor_and_terminal_setup(self):
        for mode in ('live','setup'):
            v=fixture();r=v['ledger']['controlLeases'][0]
            if mode=='live':r['stopped']=None
            else:
                r['class']='restore-commissioner';r['tags']=[T.tag(r['incarnation'],r['class'])];r['principal']=v['plan']['controlRecovery']['classes'][r['class']]['principal'];r['container']['service']=r['class'];r['stopped']['container']=r['container']
            with self.assertRaisesRegex(ValueError,'COMMON_PREDECESSOR'):T.observe(**v)
    def test_exact_tag_coverage_census_and_occupancy(self):
        for change in (lambda v:v['census']['tags'].pop(),lambda v:v['census']['tags'].append(v['census']['tags'][0]),lambda v:v['census']['tags'][0].update(applicationName='foreign'),lambda v:v['census']['tags'][0].update(count=True),lambda v:v['census']['occupancy'].update(heldControlCredits=0),lambda v:v['census']['occupancy']['physical']['control'].update(other=0)):
            v=fixture();change(v)
            with self.assertRaises(ValueError):T.observe(**v)
    def test_source_database_epoch_and_stopped_identity(self):
        for change in (lambda v:v['ledger']['controlLeases'][0].update(source={}),lambda v:v['ledger']['controlLeases'][0]['principal'].update(databaseOid='7'),lambda v:v['ledger']['controlLeases'][0]['stopped'].update(resourceEpoch=['other','epoch']),lambda v:v['ledger']['controlLeases'][0]['stopped'].update(noFutureDispatch=False),lambda v:v['ledger']['controlLeases'][0]['container'].update(project='foreign')):
            v=fixture();change(v)
            with self.assertRaises(ValueError):T.observe(**v)
    def test_held_unbound_unknown_and_closed_history(self):
        v=fixture('lifecycle-operator');r=v['ledger']['controlLeases'][0];r['state']='UNKNOWN';v['census']['occupancy']['activeControlExecutions']=0
        self.assertEqual(T.observe(**v)['heldCredits']['control'],1)
        v=fixture();r=v['ledger']['controlLeases'][0];r['state']='CLOSED';r['stopped']=None
        v['controlProcesses']=v['controlProcesses'][1:];v['census']['tags']=[t for t in v['census']['tags']if t['applicationName']not in r['tags']]
        v['census']['occupancy'].update(heldControlCredits=1)
        self.assertEqual(T.observe(**v)['controlHistory']['closed'],1)
    def test_both_declared_envelopes_and_metadata_refusals(self):
        v=fixture()
        for kind in ('controlled-connection-observation','controlled-native-stored-counts'):
            raw=envelope(v,kind);self.assertEqual(T.envelope(v['expected'],v['plan'],raw),v['census'])
            self.assertEqual(T.observe_envelope(v['expected'],v['plan'],raw,v['processes'],v['controlProcesses'])['heldCredits']['control'],2)
            bad=copy.deepcopy(raw);bad['occupancy']['heldControlCredits']=0
            with self.assertRaisesRegex(ValueError,'COMMON_OCCUPANCY'):T.observe_envelope(v['expected'],v['plan'],bad,v['processes'],v['controlProcesses'])
            for change in (lambda r:r.update(version=1),lambda r:r.update(version=True),lambda r:r.update(expected={}),lambda r:r['hostMonotonic'].update(startedNs=['1']),lambda r:r.update(kind='foreign')):
                r=copy.deepcopy(raw);change(r)
                with self.assertRaises(ValueError):T.envelope(v['expected'],v['plan'],r)
    def test_fixed_capture_inspects_both_classes_no_new_commands(self):
        # Existing recording transport, changed only to DECLARED envelope2.
        with tempfile.TemporaryDirectory() as d:
            v=fixture();spec,out,run,calls=recording.OperatorCapture().run_fixture(d,v)
            def producer(argv):
                response=run(argv)
                if argv[0]=='node':response.stdout=json.dumps(envelope(v)).encode()
                if argv[:2]==['docker','inspect']:
                    obj=json.loads(response.stdout)[0];cid=argv[-1]
                    for r in v['ledger']['controlLeases']:
                        if r['container'] and r['container']['cid']==cid:obj['Config']['Labels']['org.nightscout.operator.incarnation']=r['incarnation']
                    response.stdout=json.dumps([obj]).encode()
                return response
            r=C.capture(spec,out,producer)
            self.assertEqual(len(calls),5);self.assertEqual(r['heldCredits']['control'],2)
            self.assertEqual({r['processInstanceId']for r in r['controls']},{T.CONTROL,'realtime-recovery'})

if __name__=='__main__':unittest.main()
