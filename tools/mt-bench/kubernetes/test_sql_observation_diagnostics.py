import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import kube_adapter as k


class SqlObservationDiagnostics(unittest.TestCase):
    def run_bridge(self, failures):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            probe = root / 'probe.cjs'
            k.generate_probe(probe)
            source = probe.read_text()
            self.assertIn('performance.now()-e.sentMono<120000',source)
            bridge = source[source.index('const psqlAsync ='):source.index('const pct =')]
            harness = r'''
const fs=require('node:fs'),path=require('node:path');
const {performance}=require('node:perf_hooks');
const signalDir=process.argv[1],failures=JSON.parse(process.argv[2]),calls=[];
let next=0;
const execFile=(program,args,options,callback)=>({stdin:{end(sql){
  calls.push({program,args,options,sql});
  const chosen=failures[next++],err=chosen?Object.assign(new Error('unsafe message'),chosen):null;
  process.nextTick(()=>callback(err,'read-only-result\n',
    'postgres://user:DO_NOT_RETAIN_PASSWORD@private.invalid K8S_POD_NOT_READY'));
}}});
'''
            harness += bridge
            harness += r'''
(async()=>{
  const results=[];
  for(const failure of failures){
    try{results.push({stdout:await psqlAsync('SELECT 1;')});}
    catch(error){results.push({error:error.message});}
  }
  const file=path.join(signalDir,'sql-observation-failure.json');
  const diagnostic=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):null;
  console.log(JSON.stringify({results,calls,diagnostic}));
})().catch(error=>{console.error(error);process.exit(1)});
'''
            result = subprocess.run(['node', '-e', harness, str(root), json.dumps(failures)],
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

    def test_success_keeps_exact_sql_and_output_without_failure_record(self):
        value = self.run_bridge([None])
        self.assertEqual(value['results'], [{'stdout': 'read-only-result\n'}])
        self.assertIsNone(value['diagnostic'])
        self.assertEqual(value['calls'][0]['sql'], 'SELECT 1;')
        self.assertEqual(value['calls'][0]['options']['timeout'], 60000)
        self.assertEqual(value['calls'][0]['options']['maxBuffer'], 32 << 20)
        self.assertEqual(value['calls'][0]['args'][1], 'clinical-sql')

    def test_exit_retains_safe_reason_and_never_raw_stderr(self):
        value = self.run_bridge([{'code': 1, 'killed': False}])
        self.assertEqual(value['results'][0]['error'], 'M7_PROBE_SQL_OBSERVATION_UNAVAILABLE')
        diagnostic = value['diagnostic']
        self.assertEqual(diagnostic['reason'], 'CHILD_EXIT')
        self.assertEqual(diagnostic['exitCode'], 1)
        self.assertEqual(diagnostic['childReportedCodes'], ['K8S_POD_NOT_READY'])
        self.assertGreater(diagnostic['stderrBytes'], 0)
        self.assertNotIn('DO_NOT_RETAIN_PASSWORD', json.dumps(value))
        self.assertNotIn('private.invalid', json.dumps(diagnostic))

    def test_timeout_is_observation_failure_with_unchanged_limit(self):
        value = self.run_bridge([{'killed': True, 'signal': 'SIGTERM'}])
        self.assertEqual(value['diagnostic']['reason'], 'TIMEOUT')
        self.assertEqual(value['diagnostic']['timeoutMs'], 60000)
        self.assertEqual(value['results'][0]['error'], 'M7_PROBE_SQL_OBSERVATION_UNAVAILABLE')

    def test_buffer_refusal_is_retained_as_observation_failure(self):
        value = self.run_bridge([{'code': 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER'}])
        self.assertEqual(value['diagnostic']['reason'], 'OUTPUT_BOUND')
        self.assertEqual(value['results'][0]['error'], 'M7_PROBE_SQL_OBSERVATION_UNAVAILABLE')

    def test_first_failure_is_not_overwritten_by_a_later_failure(self):
        value = self.run_bridge([{'code': 1}, {'killed': True, 'signal': 'SIGTERM'}])
        self.assertEqual(value['diagnostic']['reason'], 'CHILD_EXIT')
        self.assertEqual(len(value['results']), 2)


if __name__ == '__main__':
    unittest.main()
