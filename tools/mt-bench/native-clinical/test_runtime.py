"""Execute the actual orchestrator/finally against recording ports, never Docker."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import clinical as D,runtime as R
C=R.C
class RecordingHost(R.Host):
    records=[];fail_inspection=None;fail_controller=False
    def __init__(self,plan,out):
        super().__init__(plan,out);self.events=[];self.rows={};self.producerClosed=False;self.images['vault']=C.VAULT
        for index,slot in enumerate(plan['startOrder']+['postgres','vault']):
            cid=format(index+1,'064x');self.rows[cid]={'Id':cid,'Image':self.images.get(slot,plan['imageId']),'State':{'Running':True,'StartedAt':'birth-'+slot},'Config':{'Labels':{'com.docker.compose.project':plan['project'],'com.docker.compose.project.working_dir':plan['base'],'com.docker.compose.service':slot}}}
        self.owned={cid:(r['Config']['Labels']['com.docker.compose.service'],r['State']['StartedAt'],r['Image'])for cid,r in self.rows.items()}
        type(self).records.append(self)
    def command(self,args,*a,**kw):
        self.n+=1;self.events.append(tuple(args))
        if args[:3]==['docker','image','inspect']:return json.dumps([{'Id':args[3],'Os':'linux','Architecture':'amd64'}])
        if args[:2]==['docker','ps']:return '\n'.join(self.rows)
        if args[:2]==['docker','inspect']:
            if args[2]==self.fail_inspection:raise RuntimeError('RECORDING_INSPECTION_FAILURE')
            return json.dumps([self.rows[args[2]]])
        if args[:2]==['docker','logs']:return ''
        if args[:2]==['docker','stop']:self.rows[args[-1]]['State']['Running']=False;return args[-1]
        raise AssertionError(args)
    def compose(self,*args,**kw):
        self.events.append(('compose',*args))
        if args[:3]==('ps','-a','-q'):return next((cid for cid,r in self.rows.items()if r['Config']['Labels']['com.docker.compose.service']==args[-1]),'')
        return ''
    def controller(self,op,slot=None,**kw):
        self.events.append(('controller',op,slot))
        if self.fail_controller and op=='stop':raise RuntimeError('RECORDING_QUIESCE_UNKNOWN')
        if op=='stop':
            for row in self.rows.values():
                if row['Config']['Labels']['com.docker.compose.service']==slot:row['State']['Running']=False
        return {'state':{'bind':'BOUND','start':'STARTED','stop':'QUIESCED_RETIRED'}[op]}
    def ack(self,slot):self.events.append(('ack',slot))
    def healthy(self,slot):pass
    def health(self,slot):pass
    def plan_view(self):pass
    def start_producer(self):
        host=self
        class Producer:
            def phase(self,name,**kw):host.events.append(('producer',name));return {'primed':16,'provisioned':16}if name=='prime'else{'attempted':4608,'accepted':4608}
            def abort(self):host.events.append(('producer','abort'));host.producerClosed=True
        self.producer=Producer();return self.producer
    def wait_owned(self):raise RuntimeError('PRIMARY_ACQUISITION_FAILURE')

def plan():
    return {'root':'/model','topology':{},'runtimeReady':True,'hostDependencies':{'nodePath':'/model/cache'},'kind':'recording','scope':'recording only; native UNMEASURED','source':{},'imageId':'sha256:'+'a'*64,'maximumSeconds':1800,'maximumCommands':2048,'maximumOutputBytes':134217728,'cleanupReserveCommands':256,'cleanupReserveSeconds':180,'cleanupReserveOutputBytes':33554432,'selectedEnvironment':{},'project':'ns-admission-'+'b'*32,'nonce':'b'*32,'base':'/model/source/deploy/multitenant','startOrder':['admin','api','api-2'],'slots':['admin','api','api-2'],'config':{'fileDigests':{}},'state':'/model/state'}
class Runtime(unittest.TestCase):
    def setUp(self):RecordingHost.records=[];RecordingHost.fail_inspection=None;RecordingHost.fail_controller=False
    def test_actual_executor_repeated_events_primary_failure_producer_drain_and_cleanup(self):
        p=plan()
        with tempfile.TemporaryDirectory()as td,patch.object(D,'SOURCE_JOIN','REVIEWED_FINAL_SOURCE'),patch.object(D,'prepare',return_value=p),patch.object(D.DEP,'capture',return_value=p['hostDependencies']),patch.object(R,'Host',RecordingHost),patch.object(R.P,'read_host',return_value={'observedMonotonicNs':time.monotonic_ns()}),patch.object(D.Ports,'start',lambda self,slot:self.host.controller('start',slot)):
            result=R.execute(p,Path(td)/'run');h=RecordingHost.records[-1]
            self.assertEqual(result['error'],'PRIMARY_ACQUISITION_FAILURE');self.assertNotIn('cleanupError',result);self.assertEqual(result['nativeAcceptance'],'UNMEASURED')
            events=json.loads((h.out/'phase-events.private.json').read_text());self.assertGreater(len(events),4)
            abort=h.events.index(('producer','abort'));stops=[i for i,v in enumerate(h.events)if v[:2]==('controller','stop')];self.assertTrue(stops and all(i>abort for i in stops));self.assertTrue(all(not r['State']['Running']for r in h.rows.values()))
    def test_final_event_publication_failure_preserves_primary_and_still_cleans(self):
        p=plan();save=C.save
        def fail(file,value):
            if file.name=='phase-events-006.private.json':raise OSError('recording final event failure')
            return save(file,value)
        with tempfile.TemporaryDirectory()as td,patch.object(D,'SOURCE_JOIN','REVIEWED_FINAL_SOURCE'),patch.object(D,'prepare',return_value=p),patch.object(D.DEP,'capture',return_value=p['hostDependencies']),patch.object(R,'Host',RecordingHost),patch.object(R.P,'read_host',return_value={'observedMonotonicNs':time.monotonic_ns()}),patch.object(D.Ports,'start',lambda self,slot:self.host.controller('start',slot)),patch.object(C,'save',side_effect=fail):
            result=R.execute(p,Path(td)/'run');h=RecordingHost.records[-1]
            self.assertEqual(result['error'],'PRIMARY_ACQUISITION_FAILURE');self.assertIn('eventPublicationError',result);self.assertTrue(all(not row['State']['Running']for row in h.rows.values()))
    def test_cleanup_continues_after_bad_inspection_and_controller_failure(self):
        with tempfile.TemporaryDirectory()as td:
            h=RecordingHost(plan(),Path(td)/'run');h.allocation_attempted=True;h.fail_controller=True;h.fail_inspection=min(h.rows)
            with self.assertRaisesRegex(Exception,'CLEANUP_UNCONFIRMED'):h.cleanup_owned()
            final=json.loads((h.out/'finally-stopped.private.json').read_text());self.assertTrue(final['errors']);self.assertEqual(len(final['rows']),len(h.rows)-1);self.assertTrue(all(not r['State']['Running']for cid,r in h.rows.items()if cid!=h.fail_inspection))
    def test_removed_old_cid_is_absent_foreign_custody_is_never_stopped(self):
        with tempfile.TemporaryDirectory()as td:
            h=RecordingHost(plan(),Path(td)/'run');h.allocation_attempted=True;h.skip_controller_cleanup=True;old='f'*64;h.owned[old]=('api','old-birth',h.p['imageId']);cid=min(h.rows);h.rows[cid]['Config']['Labels']['com.docker.compose.project']='foreign'
            with self.assertRaisesRegex(Exception,'CLEANUP_UNCONFIRMED'):h.cleanup_owned()
            final=json.loads((h.out/'finally-stopped.private.json').read_text());self.assertEqual(final['knownAbsent'][0]['cid'],old);self.assertTrue(h.rows[cid]['State']['Running']);self.assertNotIn(('docker','stop','--time','10',cid),h.events)
    def test_cleanup_publication_failure_does_not_skip_effects(self):
        with tempfile.TemporaryDirectory()as td:
            h=RecordingHost(plan(),Path(td)/'run');h.allocation_attempted=True;save=C.save
            def fail(file,value):
                if file.name=='root-cleanup-spec.private.json':raise OSError('recording disk failure')
                return save(file,value)
            with patch.object(C,'save',side_effect=fail),self.assertRaisesRegex(Exception,'CLEANUP_UNCONFIRMED'):h.cleanup_owned()
            self.assertTrue(all(not r['State']['Running']for r in h.rows.values()))
    def test_repeated_progress_and_cold_ack_receipts_are_unique(self):
        with tempfile.TemporaryDirectory()as td:
            h=RecordingHost(plan(),Path(td)/'run');h.p['coldLimits']={'api':{'activeLimit':1,'pendingLimit':9}};h.p['ids']=[]
            def sample(**kw):h.rounds+=1;return {}
            h.sample=sample
            with patch.object(R.time,'sleep'),patch.object(R.EP,'assess',return_value={}),patch.object(R.EP,'pack',return_value={}):h.three('load');h.three('load')
            self.assertEqual(len(list(h.out.glob('load-successful-work-*.private.json'))),2)
            ack={'cleanShutdown':True,'unconfirmedCleanup':False,'cold':{'closed':True,'activeLimit':1,'pendingLimit':9,'queued':0,'delaying':0,'running':0,'observed':{'version':1,'peakActive':1,'peakQueued':1,'accepted':1,'started':1,'completed':1,**dict.fromkeys(('failed','duplicates','deferred','overloaded','schedulerRefused','cancelled','closeCancelled','closedRefused','invalidRefused'),0)}}}
            for generation in ('old','new'):
                def read(file):return {'slots':{'api':[{'incarnation':generation}]}}if file.name=='ledger.json'else ack
                with patch.object(C,'read',side_effect=read):h.stop_ack('api',cold=True)
            self.assertEqual(set(h.coldProofs),{'old','new'});self.assertEqual(len(list(h.out.glob('cold-high-water-api-*.private.json'))),2)
    def test_actual_producer_terminal_thread_requires_positive_group_custody(self):
        import threading
        from types import SimpleNamespace
        def producer(result,error=None):
            p=object.__new__(D.Producer);p.cancelled=threading.Event();p.result=result;p.error=error;p.thread=SimpleNamespace(join=lambda **kw:None,is_alive=lambda:False);return p
        for result,error in [(None,None),({'groupDrained':False,'failure':'GROUP_DRAIN_UNKNOWN'},None),({'groupDrained':True},OSError('receipt failure'))]:
            p=producer(result,error)
            with self.assertRaisesRegex(Exception,'PRODUCER_CLEANUP_UNKNOWN'):p.abort()
            with tempfile.TemporaryDirectory()as td:
                h=RecordingHost(plan(),Path(td)/'run');h.producer=p;h.allocation_attempted=True
                with self.assertRaisesRegex(Exception,'CLEANUP_UNCONFIRMED'):h.cleanup_owned()
                value=json.loads((h.out/'finally-stopped.private.json').read_text());self.assertTrue(value['uncertainHostEffect']);self.assertEqual(value['lateDaemonEffect'],'UNCONFIRMED');self.assertEqual(value['errors'][0]['stage'],'producer-cancel');self.assertTrue(all(not r['State']['Running']for r in h.rows.values()))
        p=producer({'groupDrained':True,'failure':'COMMAND_CANCELLED'});p.abort();self.assertTrue(p.cancelled.is_set())
    def test_producer_reservations_refuse_before_child_construction(self):
        for mode,code in [('commands','COMMAND_COUNT'),('bytes','PRODUCER_OUTPUT_RESERVATION')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as td:
                p=plan();p.update(maximumProducerOutputBytes=4194304,ids=[],runId='model');p['hostDependencies']['nodeVersion']='model'
                # These two fixed helper inputs are read before the reservation;
                # source hashes are stubbed without executing any source module.
                h=RecordingHost(p,Path(td)/'run');h.endpoints=lambda:{}
                if mode=='commands':h.n=p['maximumCommands']-p['cleanupReserveCommands']
                else:h.bytes=p['maximumOutputBytes']-p['cleanupReserveOutputBytes']-4194304+1
                with patch.object(C,'sha',return_value='model'),patch.object(D,'Producer',side_effect=AssertionError('NO_CHILD'))as constructor,self.assertRaisesRegex(Exception,code):R.Host.start_producer(h)
                constructor.assert_not_called()
    def test_ports_stop_requires_controller_then_actual_ack(self):
        with tempfile.TemporaryDirectory()as td:
            h=RecordingHost(plan(),Path(td)/'run');h.stop_ack('api');self.assertEqual(h.events[-2:],[('controller','stop','api'),('ack','api')])
if __name__=='__main__':unittest.main()
