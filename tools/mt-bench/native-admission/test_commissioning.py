"""Focused host/model controls. An actual private prepared root is explicit input."""
import copy,json,os,sys,tempfile,time,unittest
from pathlib import Path
import commissioning as C,owned_process as O,preflight as P
from recording import RecordingHost
ROOT=os.environ.get('M7_NATIVE_TEST_PREPARED')
class Controls(unittest.TestCase):
    def test_status_and_owned_group(self):
        with tempfile.TemporaryDirectory()as d:
            r=O.run([sys.executable,'-c','raise SystemExit(7)'],{'PATH':os.environ['PATH']},Path(d)/'exit7',2)
            self.assertEqual(r['returnCode'],7);self.assertTrue(r['groupDrained']);self.assertIsNone(r['failure'])
    def test_exited_leader_does_not_leave_ignoring_descendant(self):
        with tempfile.TemporaryDirectory()as d:
            ready=Path(d)/'pid';code="import os,signal,time,pathlib;pid=os.fork();\nif pid==0:\n signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path("+repr(str(ready))+").write_text(str(os.getpid()));time.sleep(30)\nelse:\n while not pathlib.Path("+repr(str(ready))+").exists():time.sleep(.01)\n"
            r=O.run([sys.executable,'-c',code],{'PATH':os.environ['PATH']},Path(d)/'orphan',2)
            self.assertEqual(r['returnCode'],0);self.assertTrue(r['groupDrained']);pid=ready.read_text();stat=Path('/proc')/pid/'stat';self.assertTrue(not stat.exists()or stat.read_text().rsplit(') ',1)[1].split()[0]in('Z','X'))
    def test_timeout_after_closed_output_is_unknown_and_drained(self):
        with tempfile.TemporaryDirectory()as d:
            r=O.run([sys.executable,'-c','import os,time;os.close(1);os.close(2);time.sleep(30)'],{'PATH':os.environ['PATH']},Path(d)/'timeout',.1)
            self.assertEqual(r['failure'],'COMMAND_TIMEOUT');self.assertEqual(r['operationOutcome'],'UNKNOWN');self.assertTrue(r['groupDrained'])
    def test_output_is_physically_bounded(self):
        with tempfile.TemporaryDirectory()as d:
            r=O.run([sys.executable,'-c',"import os;os.write(1,b'x'*8388608)"],{'PATH':os.environ['PATH']},Path(d)/'output',2,65536)
            self.assertEqual(r['failure'],'COMMAND_OUTPUT_BOUND');self.assertLessEqual(r['bytes'],65536);self.assertTrue(r['groupDrained'])
    def test_foreign_address_port_project_and_capacity_refusals(self):
        plan={'backendSubnet':'10.250.224.0/24','edgeSubnet':'10.250.225.0/24','project':'synthetic-owned','port':35661,'maximumBackendEndpoints':15,'maximumEdgeEndpoints':1}
        self.assertEqual(P.assess(plan,[],[{'dst':'default'}],[],[])['allocation'],'NOT_PERFORMED')
        for networks,routes,ports,projects,code in [([{'IPAM':{'Config':[{'Subnet':'10.250.224.0/24'}]}}],[],[],[],'DOCKER_IPAM'),([],[{'dst':'10.0.0.0/8'}],[],[],'ROUTE_COLLISION'),([],[],[35661],[],'PORT_IN_USE'),([],[],[],['synthetic-owned'],'EXISTING_PROJECT'),([{'IPAM':{},'Labels':{'com.docker.compose.project':'synthetic-owned'}}],[],[],[],'EXISTING_PROJECT')]:
            with self.assertRaisesRegex(P.Refused,code):P.assess(plan,networks,routes,ports,projects)
        small={**plan,'backendSubnet':'10.250.224.0/29'}
        with self.assertRaisesRegex(P.Refused,'ROSTER_CAPACITY'):P.assess(small,[],[],[],[])
    def test_no_allocation_cleanup_never_searches_or_stops_foreign_resources(self):
        with tempfile.TemporaryDirectory()as d:
            h=C.Host.__new__(C.Host);h.out=Path(d);h.p={'project':'synthetic-owned'};h.images={};h.owned={};h.uncertain=False;h.skip_controller_cleanup=True;h.allocation_attempted=False;calls=[];h.command=lambda args,*a,**k:(calls.append(args)or '');h.cleanup_owned();self.assertEqual(calls,[]);self.assertEqual(json.loads((Path(d)/'finally-no-allocation.json').read_text())['cleanupEffects'],0)
    def test_cleanup_continues_after_foreign_row_and_accepts_exact_known_removed_cid(self):
        with tempfile.TemporaryDirectory()as d:
            h=C.Host.__new__(C.Host);h.out=Path(d);h.p={'project':'synthetic-owned'};h.images={};h.allocation_attempted=True;h.skip_controller_cleanup=True;h.uncertain=False
            removed='a'*64;foreign='b'*64;owned='c'*64;h.owned={removed:('api','old','image'),owned:('api','current','image')};calls=[]
            def command(args,*a,**kw):
                calls.append(args)
                if args[:3]==['docker','ps','-aq']:
                    return foreign+'\n'+owned+'\n'
                if args[:2]==['docker','inspect']:return json.dumps([{'Id':args[2],'Config':{'Labels':{'com.docker.compose.service':'api'}},'State':{'Running':False}}])
                if args[:2]==['docker','logs']:return ''
                raise RuntimeError('UNPLANNED_RECORDING_COMMAND')
            def inspect(cid,service):
                if cid==foreign:raise RuntimeError('CONTAINER_CUSTODY')
                self.assertEqual(cid,owned);return {'Id':cid,'State':{'Running':False},'Config':{'Labels':{'com.docker.compose.service':'api'}}}
            h.command=command;h.inspect=inspect
            with self.assertRaisesRegex(RuntimeError,'CLEANUP_UNCONFIRMED'):h.cleanup_owned()
            final=json.loads((Path(d)/'finally-stopped.private.json').read_text());self.assertEqual(len(final['knownAbsent']),1);self.assertEqual(final['knownAbsent'][0]['cid'],removed);self.assertEqual(final['rows'][0]['Id'],owned);self.assertTrue(any(x['stage']=='inspect'for x in final['errors']));self.assertFalse(any(x[:2]==['docker','stop']for x in calls))
    def test_bind_requires_exact_qualified_image_before_worker_start(self):
        with tempfile.TemporaryDirectory()as d:
            state=Path(d);(state/'connection-budget').mkdir();file=state/'connection-budget/custody.json'
            h=C.Host.__new__(C.Host);h.p={'state':d,'project':'synthetic-owned','base':'/synthetic/source','imageId':C.IMAGE,'source':{'coreCommit':C.CORE,'deployCommit':C.DEPLOY},'controllerCli':'/synthetic/controller.js'};calls=[];h.command=lambda args,*a,**k:(calls.append(args)or '{"state":"BOUND"}')
            expected={'project':h.p['project'],'workingDirectory':h.p['base'],'imageId':C.IMAGE,'source':h.p['source']};C.save(file,{'expected':expected});self.assertEqual(h.controller('bind')['state'],'BOUND')
            file.unlink();wrong={**expected,'imageId':'sha256:'+'e'*64};C.save(file,{'expected':wrong})
            with self.assertRaisesRegex(RuntimeError,'BOUND_CUSTODY_MISMATCH'):h.controller('bind')
            self.assertTrue(all(args[-1]=='bind'for args in calls),'no worker may start before bound image agrees')
    def test_actual_prepared_plan_recording_has_required_protocol_and_no_acceptance(self):
        self.assertIsNotNone(ROOT,'M7_NATIVE_TEST_PREPARED required: actual source/image-qualified private preparation')
        plan=C.prepare(ROOT)
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'recording';result=C.execute(plan,out,RecordingHost);self.assertEqual(result['dryRun'],'PASS');self.assertEqual(result['commissioning'],'NOT_RUN');self.assertEqual(result['nativeAcceptance'],'UNMEASURED')
            events=json.loads((out/'recording-events.private.json').read_text())['events'];bootstrap=next(i for i,e in enumerate(events)if e[0]=='compose'and'bootstrap'in e[1]);bind=events.index(['controller','bind',None]);start=events.index(['controller','start','admin']);self.assertLess(bootstrap,bind);self.assertLess(bind,start)
            stop=events.index(['controller','stop','api']);ack=events.index(['ack','api']);restart=events.index(['controller','start','api'],stop+1);self.assertLess(stop,ack);self.assertLess(ack,restart);self.assertEqual([e for e in events if e[0]=='capture'],[['capture','started'],['capture','restarted'],['capture','retired']])
            self.assertFalse(any(e[0]=='compose'and e[1][0]=='up'and any(x in C.ROLES for x in e[1])for e in events))
if __name__=='__main__':unittest.main()
