#!/usr/bin/env python3
"""Run only in an owned disposable core checkout. Every mutant restores exact bytes."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
NATIVE = ['node', str(HERE / 'native-run.cjs')]
MOCHA = ['node', 'node_modules/mocha/bin/mocha.js', '--reporter', 'dot']
CASES = {
 'strict-generation': ('lib/realtime-placement/index.js', 'expected.generation > owner.generation', 'expected.generation !== owner.generation', NATIVE + ['tests/realtime-sharding-native.integration.test.js', '--grep', 'SHARD_NATIVE_MOVE'], 'SHARD_NATIVE_HANDOFF synthetic B during unrelated target warm: REALTIME_HANDOFF_UNAVAILABLE'),
 'cohort-omission': ('lib/server/serve/operation-cohort.js', 'if (workers.length!==map.workers.size || new Set(workers).size!==workers.length || workers.some(worker=>!map.workers.has(worker)))', 'if (false)', MOCHA + ['tests/realtime-placement-cohort.test.js', '--grep', 'SHARD_COHORT_OMISSION'], 'Missing expected rejection'),
 'publication-pin': ('lib/realtime-placement/publish.js', "if (held?.held !== true) fail('REALTIME_PLACEMENT_MAINTENANCE_PINNED');", "if (false) fail('REALTIME_PLACEMENT_MAINTENANCE_PINNED');", NATIVE + ['tests/realtime-placement-publication.integration.test.js'], 'Missing expected rejection'),
 'alarm-envelope': ('lib/server/serve/evaluator-consumer-config.js', 'if (placement) envelope.placement', 'if (false) envelope.placement', MOCHA + ['tests/realtime-placement.test.js', '--grep', 'reserves the maximum placement'], 'Missing expected exception'),
 'registry-label': ('lib/server/internal-api/contracts/lifecycle-participant.json', '^registry:(?!public$|information_schema$|pg_)[a-z][a-z0-9_]{0,62}$', '^never-registry-label$', NATIVE + ['tests/realtime-sharding-native.integration.test.js', '--grep', 'SHARD_REGISTRY_STATUS'], 'SOCKET_IPC_UNAVAILABLE'),
}
for name in sys.argv[1:] or CASES:
 path, before, after, command, symptom = CASES[name]
 target = Path(path); original = target.read_bytes()
 try:
  text = original.decode(); assert before in text, (name, 'source mismatch')
  target.write_text(text.replace(before, after))
  result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  output = result.stdout.decode(errors='replace')
  print('CONTROL', name, 'exit', result.returncode, flush=True)
  print(output, flush=True)
  assert result.returncode != 0 and symptom in output, (name, 'control failed to demonstrate intended symptom')
 finally:
  target.write_bytes(original)
  assert target.read_bytes() == original
 print('RESTORED', name, flush=True)
