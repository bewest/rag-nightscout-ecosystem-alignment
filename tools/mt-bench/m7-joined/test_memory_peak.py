"""Lifetime cgroup peaks remain separate from raw counters and phase means."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import adapter as a
import reduce as r

class MemoryPeak(unittest.TestCase):
    def row(self,peak=200,identity='same'):
        return {'id':identity,'containerStartedAt':'2026-11-16T20:00:00.000000001Z','memoryObservation':{'status':'MEASURED','memoryPeakBytes':peak,'memoryEvents':{'oom':0,'oom_kill':0,'high':1},'birth':{'containerId':identity,'startedAt':'2026-11-16T20:00:00.000000001Z','source':'docker-inspect-state-started-at-v1','stableRead':True}}}
    def test_native_capture_separate_reads_missing_invalid_never_zero(self):
        with patch.object(a,'command',side_effect=['123\n','oom 0\noom_kill 0\n']) as command:
            value=a.memory_observation('exact-id')
        self.assertEqual(value['memoryPeakBytes'],123)
        self.assertEqual([c.args[0][2] for c in command.call_args_list],['exact-id','exact-id'])
        self.assertEqual([c.args[0][-1] for c in command.call_args_list],['/sys/fs/cgroup/memory.peak','/sys/fs/cgroup/memory.events'])
        for bad in ('','max','-1','NaN','123\n456'):
            with patch.object(a,'command',side_effect=[bad,'oom 0\n']):value=a.memory_observation('id')
            self.assertEqual(value['status'],'UNMEASURED');self.assertNotIn('memoryPeakBytes',value)
        with patch.object(a,'command',side_effect=RuntimeError('missing')):value=a.memory_observation('id')
        self.assertEqual(value['status'],'UNMEASURED');self.assertEqual(value['memoryEvents'],'UNMEASURED')
    def test_same_container_monotone_lifetime_scope_and_event_delta(self):
        first=self.row(200);last=self.row(300);last['memoryObservation']['memoryEvents']['oom_kill']=2
        value=r.memory_peak_observation(first,last)
        self.assertEqual(value['memoryPeakBytesAfter'],300);self.assertNotIn('memoryPeakBytesDelta',value)
        self.assertEqual(value['memoryEventsDelta']['oom_kill'],2)
        self.assertIn('not phase peak',value['scope']);self.assertIn('concurrent',value['scope'])
        for mutation,code in [(lambda x:x.update(id='other'),'CONTAINER_CHANGED'),(lambda x:x['memoryObservation'].update(memoryPeakBytes=199),'PEAK_RESET'),(lambda x:x['memoryObservation'].update(memoryPeakBytes=True),'PEAK_RESET'),(lambda x:x['memoryObservation']['memoryEvents'].update(high=0),'EVENTS_RESET')]:
            broken=copy.deepcopy(last);mutation(broken)
            with self.assertRaisesRegex(RuntimeError,code):r.memory_peak_observation(first,broken)
        self.assertEqual(r.memory_peak_observation(first,last)['memoryPeakBytesAfter'],300)
        self.assertEqual(r.memory_peak_observation({},last)['status'],'UNMEASURED')
    def test_phase_snapshot_raw_parser_and_exact_identity_unchanged(self):
        with tempfile.TemporaryDirectory() as scratch:
            d=Path(scratch);a.write(d/'owner.json',{});a.write(d/'frozen.compose.json',{'services':{}})
            raw='usage_usec 100\n1024\nanon 512\n'
            def command(argv):
                self.assertEqual(argv[2],'exact-id')
                return {'/sys/fs/cgroup/memory.stat':raw,'-eo':'unused','pid,comm,rss':'PID COMMAND RSS\n','/sys/fs/cgroup/memory.peak':'2048\n','/sys/fs/cgroup/memory.events':'oom 0\noom_kill 0\n'}[argv[-1]]
            with patch.object(a,'resources',return_value=[{'Id':'exact-id','Name':'owned','Config':{'Labels':{'com.docker.compose.service':'evaluator'}}}]),patch.object(a,'command',side_effect=command),patch.object(a,'psql',return_value=''):
                a.phase_snapshot(d,d,'before')
            role=a.document(d/'before-cgroups.json')['roles']['evaluator']
            self.assertEqual(role['cgroup'],raw);self.assertEqual(role['id'],'exact-id');self.assertEqual(role['memoryObservation']['memoryPeakBytes'],2048)
    def test_restart_lifetime_gap_and_forged_birth_refusal(self):
        first=self.row(500);last=self.row(100);last['containerStartedAt']='2026-11-16T21:00:00.000000001Z';last['memoryObservation']['birth']['startedAt']=last['containerStartedAt']
        value=r.memory_peak_observation(first,last)
        self.assertEqual(value['status'],'UNMEASURED');self.assertEqual(value['reason'],'container-lifetime-changed')
        self.assertEqual(value['memoryPeakBytesBeforeLifetime'],500);self.assertEqual(value['memoryPeakBytesAfterLifetime'],100);self.assertEqual(value['memoryEventsDelta'],'UNMEASURED')
        old=copy.deepcopy(first);del old['memoryObservation']['birth']
        self.assertEqual(r.memory_peak_observation(old,last)['reason'],'container-birth-unavailable')
        for field,value in [('containerId','forged'),('startedAt','forged'),('source','caller-asserted'),('stableRead',False)]:
            bad=copy.deepcopy(last);bad['memoryObservation']['birth'][field]=value
            with self.assertRaisesRegex(RuntimeError,'BIRTH_PROVENANCE'):r.memory_peak_observation(first,bad)
        older=copy.deepcopy(last);older['containerStartedAt']='2026-11-16T19:00:00Z';older['memoryObservation']['birth']['startedAt']=older['containerStartedAt']
        with self.assertRaisesRegex(RuntimeError,'BIRTH_REWIND'):r.memory_peak_observation(first,older)
        with self.assertRaisesRegex(RuntimeError,'PEAK_RESET'):r.memory_peak_observation(first,self.row(100))
    def test_capture_brackets_started_at_and_refuses_midread_restart(self):
        import json
        started='2026-11-16T20:00:00.000000001Z'
        for changed in (False,True):
            row={'Id':'id','State':{'StartedAt':'2026-11-16T21:00:00Z' if changed else started}}
            with patch.object(a,'command',side_effect=['123','oom 0',json.dumps(row)]):value=a.memory_observation('id',started)
            if changed:self.assertEqual(value['status'],'UNMEASURED');self.assertNotIn('birth',value)
            else:self.assertEqual(value['birth']['startedAt'],started)
    def test_omitted_identity_and_monotonicity_checks_are_detectable(self):
        first=self.row();broken=self.row(100,'foreign')
        def bad_reader(first,last):return {'memoryPeakBytesAfter':last['memoryObservation']['memoryPeakBytes']}
        self.assertEqual(bad_reader(first,broken)['memoryPeakBytesAfter'],100)
        with self.assertRaisesRegex(RuntimeError,'CONTAINER_CHANGED'):r.memory_peak_observation(first,broken)
        broken['id']='same';broken['memoryObservation']['birth']['containerId']='same'
        with self.assertRaisesRegex(RuntimeError,'PEAK_RESET'):r.memory_peak_observation(first,broken)
        self.assertEqual(r.memory_peak_observation(first,self.row(300))['status'],'MEASURED')

if __name__=='__main__':unittest.main()
