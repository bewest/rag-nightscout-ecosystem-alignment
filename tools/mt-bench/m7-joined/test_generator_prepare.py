"""Actual supported-helper prepare/generate path; external effects are file seams."""
import contextlib
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
from test_offered_rps import JS as OFFERED_PROGRAM


def prepare_fixture(target, concurrency=1, overlay_kind="directory"):
    """Keep adapter.prepare/staged/workload/probe real; isolate external effects."""
    target=Path(target)
    args=a.parser().parse_args(['prepare','--directory',str(target),'--core-repo','/tmp/synthetic-core','--core-commit','a'*40,'--deploy-repo','/tmp/synthetic-deploy','--deploy-commit','b'*40,'--image','synthetic','--freeze','/tmp/synthetic-freeze','--tenants','6','--replicas','1','--jwt-setup-concurrency',str(concurrency)])
    contract={'version':2,'operations':{'inspectEvaluator':{'response':{'properties':{'tenants':{'items':{'properties':{'dueAt':{},'dueReason':{},'jobs':{}},'required':['dueAt','dueReason','jobs']}}}}}}}
    def git(repo,*argv):
        if argv[0]=='show':return json.dumps(contract)
        if argv[:3]==('worktree','add','--detach'):
            overlay=target/'core/deploy/multitenant';overlay.parent.mkdir(parents=True)
            if overlay_kind=='directory':overlay.mkdir()
            elif overlay_kind=='symlink':overlay.symlink_to(target.parent/'peer')
            elif overlay_kind=='file':overlay.write_text('peer')
            return ''
        raise AssertionError(('unexpected git effect',argv))
    def command(argv,**kwargs):
        argv=[str(x) for x in argv]
        if argv[0]=='git' and 'archive' in argv:return b''
        overlay=target/'core/deploy/multitenant'
        if argv[0]=='tar':
            for file in ('commission-restore.js','publish-primer.js','compose.yaml'):(overlay/file).write_text('synthetic\n')
            return b''
        if argv[0]=='node' and argv[1].endswith('/prepare.js'):
            (target/'state').mkdir();(overlay/'.env').write_text('SYNTHETIC=1\n');return ''
        if argv[:2]==['docker','compose'] and argv[-3:]==['config','--format','json']:
            roles=('postgres','vault','admin','primer','api','realtime','evaluator','tenant-admin','ui','nginx','feed-reader')
            return json.dumps({'services':{role:{'command':['postgres'] if role=='postgres' else ['synthetic']} for role in roles}})
        raise AssertionError(('unexpected command effect',argv))
    with contextlib.ExitStack() as stack:
        for name,value in {'commit':lambda *args:None,'git':git,'command':command,'instrument':lambda:{'sha256':'f'*64},'inventory':lambda *args:{},'host_identity':lambda value:'synthetic','resources':lambda m:[],'port':lambda:12345,'setup_generator':lambda *args:None}.items():
            stack.enter_context(patch.object(a,name,side_effect=value))
        # Pure contract isolates machine UID policy, not a running service.
        stack.enter_context(patch.object(a.os,'getuid',return_value=1000));stack.enter_context(patch.object(a.os,'getgid',return_value=1000))
        with patch('builtins.print'):a.prepare(args)
    return json.loads((target/'owner.json').read_text())


class GeneratorPreparation(unittest.TestCase):
    def test_retired_core_overlay_absent_succeeds_but_link_and_file_refuse(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);peer=root/'peer';peer.mkdir();(peer/'sentinel').write_text('preserve')
            m=prepare_fixture(root/'absent',overlay_kind='absent');self.assertTrue(m['prepared'])
            self.assertTrue((root/'absent/core/deploy/multitenant/commission-restore.js').is_file())
            for kind in ('symlink','file'):
                with self.assertRaisesRegex(RuntimeError,'M7_DEPLOY_OVERLAY_PATH_REFUSED'):prepare_fixture(root/kind,overlay_kind=kind)
                self.assertEqual((peer/'sentinel').read_text(),'preserve')

    def test_first_prepare_reaches_actual_rich_generation_serial_and_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            for value in (1,16):
                target=Path(temp)/('selection-'+str(value));m=prepare_fixture(target,value)
                self.assertTrue(m['prepared']);self.assertEqual(m['jwtSetupConcurrency'],value)
                source=(target/'k6/workload.js').read_text()
                for retained in ('ARRIVAL_CYCLE_MS','M7_OFFERED_RPS_RANGE','scenario_request_attempts','scenario_http_responses','scenario_transport_failures','M7_SETUP_REFUSAL','requestOrdinal:tenantIndex+1','startedAtMs','finishedAtMs','settings_fingerprint_observed','SharedArray','exchangeResponse(responses[j], offset + j, exchangeStartedAtMs)'):
                    self.assertIn(retained,source)
                # Execute the emitted schedule; per-scenario cadence no longer
                # has one literal ARRIVAL_CYCLE_MS expression for every mix.
                generated=target/'k6/workload.js'
                def observe():
                    return json.loads(subprocess.check_output(['node','-e',OFFERED_PROGRAM,str(generated),'6','120','200'],text=True))
                def assert_clock(value):
                    period=float(value['options']['scenarios']['w_sgv']['timeUnit'][:-2])
                    self.assertEqual(value['calls'][0][0]['date'],1800000000000+period,'GENERATED_ARRIVAL_CLOCK')
                assert_clock(observe())
                anchor='const stamp = () => '
                self.assertEqual(source.count(anchor),1)
                generated.write_text(source.replace(anchor,anchor+'0 && '))
                with self.assertRaisesRegex(AssertionError,'GENERATED_ARRIVAL_CLOCK'):assert_clock(observe())
                generated.write_text(source);assert_clock(observe())
                self.assertEqual(m['workload']['adaptedSha256'],a.digest(target/'k6/workload.js'))


if __name__=='__main__':unittest.main()
