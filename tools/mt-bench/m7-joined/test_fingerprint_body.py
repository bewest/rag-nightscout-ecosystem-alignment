"""Retain only the existing status body; discarded-body mock follows k6."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter
from workload import generate
import profile_provenance as profile

class FingerprintBody(unittest.TestCase):
    def test_status_text_override_old_null_red_wrong_and_malformed_still_refuse(self):
        with tempfile.TemporaryDirectory(prefix='m7-fingerprint-body-') as temp:
            root=Path(temp);status=root/'status.json';tenants=root/'tenants.json';work=root/'workload.js'
            tenants.write_text(json.dumps([{'id':'11111111-1111-4111-8111-111111111111','host':'synthetic.invalid','token':'synthetic-only'}]));generate(adapter.ROOT,work)
            value={'status':'ok','settings':{'units':'mg/dl','enable':['bgnow'],'thresholds':{k:100 for k in ('bgHigh','bgTargetTop','bgTargetBottom','bgLow')}},'extendedSettings':{'devicestatus':{'advanced':False,'days':1}}}
            for key in ('timeFormat','dayStart','dayEnd','alarmTimeagoWarnMins','alarmTimeagoUrgentMins','focusHours','heartbeat'):value['settings'][key]=1
            for key in ('nightMode','showSeconds','editMode','alarmUrgentHigh','alarmHigh','alarmLow','alarmUrgentLow','alarmTimeagoWarn','alarmTimeagoUrgent','alarmPumpBatteryLow','showClockDelta','showClockLastTime','authenticationPromptOnLoad'):value['settings'][key]=False
            for key in ('alarmUrgentHighMins','alarmHighMins','alarmLowMins','alarmUrgentLowMins','alarmUrgentMins','alarmWarnMins'):value['settings'][key]=[]
            status.write_text(json.dumps(value));script="const f=require(process.argv[1]),fs=require('fs'),c=require('crypto');process.stdout.write(c.createHash('sha256').update(f.projection(JSON.parse(fs.readFileSync(process.argv[2])))).digest('hex'));"
            digest=subprocess.check_output(['node','-e',script,str(adapter.HERE/'fingerprint.cjs'),str(status)],text=True)
            def calls():return json.loads(subprocess.check_output(['node',str(adapter.HERE/'workload-shapes.cjs'),str(work),str(tenants)],env={**os.environ,'M7_FIXTURE_STATUS':str(status),'M7_FIXTURE_FINGERPRINT':digest},text=True,timeout=5))
            def assessment(rows):return profile.fingerprint_check({r['counter']:{'count':r['value']} for r in rows if 'counter' in r})
            good=calls();self.assertEqual(assessment(good)['verdict'],'PASS')
            gets=[row for row in good if row.get('method')=='GET' and '/authorization/request/' not in row['url']]
            self.assertEqual(len([row for row in gets if '/status.json' in row['url']]),1)
            self.assertTrue(all(row['options'].get('responseType')==('text' if '/status.json' in row['url'] else None) for row in gets))
            original=work.read_text();anchor="get(t, '/api/v1/status.json', 'GET v1 status', 'text')";self.assertEqual(original.count(anchor),1)
            try:
                work.write_text(original.replace(anchor,"get(t, '/api/v1/status.json', 'GET v1 status')"));old=assessment(calls());self.assertEqual(old['verdict'],'FAIL');self.assertEqual(old['invalid'],1);self.assertEqual(old['observations'],0)
            finally:work.write_text(original)
            self.assertEqual(assessment(calls())['verdict'],'PASS')
            status.write_text('{');self.assertEqual(assessment(calls())['invalid'],1)
            value['settings']['enable']=['delta'];status.write_text(json.dumps(value));wrong=assessment(calls());self.assertEqual(wrong['verdict'],'FAIL');self.assertEqual(wrong['mismatch'],1)

if __name__=='__main__':unittest.main()
