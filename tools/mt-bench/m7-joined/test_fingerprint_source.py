"""Fingerprint both supported source layouts and refuse dirty or missing code."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).parent
MODULE = HERE / 'fingerprint.cjs'
LEGACY = 'lib/server/tenant-app/rest-context.js'
SHARED = 'lib/server/tenant-app/shared-rest-context.js'


class FingerprintSource(unittest.TestCase):
    def test_source_layouts_keep_exact_blobs_and_dirty_checks(self):
        files = json.loads(subprocess.check_output(
            ['node', '-e', 'console.log(JSON.stringify(require(process.argv[1]).FILES))', str(MODULE.resolve())], text=True))
        settings = {'units': 'mg/dl', 'enable': ['bgnow'],
                    'thresholds': {key: 100 for key in ('bgHigh', 'bgTargetTop', 'bgTargetBottom', 'bgLow')}}
        for key in ('timeFormat', 'dayStart', 'dayEnd', 'alarmTimeagoWarnMins', 'alarmTimeagoUrgentMins', 'focusHours', 'heartbeat'):
            settings[key] = 1
        for key in ('nightMode', 'showSeconds', 'editMode', 'alarmUrgentHigh', 'alarmHigh', 'alarmLow', 'alarmUrgentLow',
                    'alarmTimeagoWarn', 'alarmTimeagoUrgent', 'alarmPumpBatteryLow', 'showClockDelta', 'showClockLastTime', 'authenticationPromptOnLoad'):
            settings[key] = False
        for key in ('alarmUrgentHighMins', 'alarmHighMins', 'alarmLowMins', 'alarmUrgentLowMins', 'alarmUrgentMins', 'alarmWarnMins'):
            settings[key] = []
        digests = []
        for route in (LEGACY, SHARED):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as temp:
                core = Path(temp)
                selected = [route if name == LEGACY else name for name in files]
                for name in selected:
                    file = core / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text('// source-bound fixture\n')
                (core / 'lib/server/tenant-app/environment.js').write_text(
                    'module.exports=()=>({settings:Object.assign(' + json.dumps(settings) +
                    ',{filteredSettings:x=>x}),extendedSettings:{devicestatus:{advanced:false,days:1}}});\n')
                (core / 'lib/tenant-registry/provision.js').write_text('// " (tenant_id, version, values) VALUES ($1, 1, \'{}\'::jsonb)"\n')
                (core / 'lib/tenant-registry/rules.js').write_text('exports.PURPOSES={a:1,b:2,c:3,d:4,e:5,f:6};\n')
                def git(*args):
                    return subprocess.check_output(['git', '-C', str(core), *args], text=True, stderr=subprocess.PIPE).strip()
                git('init', '-q')
                git('config', 'user.name', 'Synthetic fixture')
                git('config', 'user.email', 'fixture@example.invalid')
                git('add', '--', *selected)
                self.assertEqual(sorted(git('diff', '--cached', '--name-only').splitlines()), sorted(selected))
                git('commit', '-qm', 'Fingerprint source fixture', '--', *selected)
                commit = git('rev-parse', 'HEAD')
                seed = core / 'seed.json'
                seed.write_text(json.dumps({'version': 1, 'seed': [{'id': '11111111-1111-4111-8111-111111111111',
                    'hosts': ['synthetic.invalid'], 'issueRootSecret': True}]}))
                def run():
                    return subprocess.run(['node', str(MODULE.resolve()), str(core), commit, str(seed), '1'], text=True, capture_output=True)
                good = run()
                self.assertEqual(good.returncode, 0, good.stderr)
                value = json.loads(good.stdout)
                self.assertEqual(set(value['sourceBlobs']), set(selected))
                digests.append(value['sha256'])
                file = core / route
                original = file.read_bytes()
                file.write_bytes(original + b'// changed\n')
                changed = run()
                self.assertNotEqual(changed.returncode, 0)
                self.assertEqual(changed.stderr.strip(), 'M7_SETTINGS_SOURCE_DIRTY')
                file.write_bytes(original)
                self.assertEqual(run().returncode, 0)
                if route == SHARED:
                    git('rm', '--', SHARED)
                    self.assertEqual(git('diff', '--cached', '--name-only'), SHARED)
                    git('commit', '-qm', 'Remove supported REST context', '--', SHARED)
                    commit = git('rev-parse', 'HEAD')
                    missing = run()
                    self.assertEqual(missing.stderr.strip(), 'M7_SETTINGS_SOURCE_LAYOUT_UNREVIEWED')
                    self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(digests[0], digests[1], 'Layout identity must not alter the settings projection')
