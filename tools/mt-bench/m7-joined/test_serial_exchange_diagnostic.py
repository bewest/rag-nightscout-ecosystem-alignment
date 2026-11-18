import argparse,copy,hashlib,importlib.util,json,subprocess,sys,tempfile,unittest,types,contextlib
from pathlib import Path
from unittest.mock import patch
import adapter as a
import probe
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SELECTION={'tenants':64,'phaseSeconds':120,'requestSeconds':60}
class SerialDiagnostic(unittest.TestCase):
 def test_actual_cli_and_receipt_scope(self):
  args=a.parser().parse_args(['prepare','--directory','/synthetic','--core-repo','/synthetic-core','--core-commit','a'*40,'--deploy-repo','/synthetic-deploy','--deploy-commit','b'*40,'--image','sha256:'+'c'*64,'--receipt','/synthetic-receipt','--profile','pgstream-sample','--run-purpose','discovery','--tenants','3000','--replicas','1','--serial-exchange-diagnostic'])
  self.assertEqual(a.serial_exchange_selection(args),SELECTION)
  m={'tenants':3000,'serialExchangeDiagnostic':SELECTION,'profile':'pgstream-sample','runPurpose':'discovery','tenants':3000};r={'status':'AUTHORIZED_DIAGNOSTIC','serialExchangeDiagnostic':SELECTION}
  a.serial_exchange_receipt(m,r)
  for value in ({'status':'AUTHORIZED_DIAGNOSTIC'}, {'status':'FROZEN','serialExchangeDiagnostic':SELECTION}, {'status':'AUTHORIZED_DIAGNOSTIC','serialExchangeDiagnostic':{**SELECTION,'tenants':63}}):
   with self.assertRaises(RuntimeError):a.serial_exchange_receipt(m,value)
  args.tenants=1000
  with self.assertRaises(RuntimeError):a.serial_exchange_selection(args)
  args.serial_exchange_diagnostic=False;self.assertIsNone(a.serial_exchange_selection(args));a.serial_exchange_receipt({}, {})
 def test_default_generated_probe_matches_explicit_disabled_diagnostic(self):
  # Durable-lag instrumentation legitimately changed the generated default after
  # the old serial-feature parent. The supported default contract is the current
  # ordinary generator with the opt-in diagnostic disabled, including its helpers.
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);(d/'default').mkdir();(d/'disabled').mkdir()
   first=probe.generate(ROOT,d/'default/probe.js');second=probe.generate(ROOT,d/'disabled/probe.js',serial_exchange=False)
   self.assertEqual(first,second);self.assertEqual((d/'default/probe.js').read_bytes(),(d/'disabled/probe.js').read_bytes())
   self.assertFalse((d/'default/serial-exchange-pair.cjs').exists())
   self.assertNotIn("require('./serial-exchange-pair.cjs')",(d/'default/probe.js').read_text())
   self.assertIn('durable-lag.cjs',first['recoveryHelpers'])
 def test_diagnostic_runner_uses_existing_job_sampler_and_safe_result_path(self):
  import discovery
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);(d/'completion-source.json').write_text('{}');(d/'owner.json').write_text('{}');(d/'tenants.private.json').write_text('[]');(d/'serial-exchange-pair.cjs').write_text('synthetic actor')
   m={'tenants':3000,'serialExchangeDiagnostic':SELECTION,'owner':'a'*32,'pair':{'core':'b'*40,'deploy':'c'*40},'imageId':'sha256:'+'d'*64,'instrument':{'sha256':'e'*64},'port':53001,'project':'synthetic','generator':{'tools':{'node':{'path':'/synthetic/node','sha256':'f'*64}}},'cadence':{'loadSeconds':310,'probeEveryMs':300000},'restartRoles':['api']}
   record=types.SimpleNamespace(value={'processes':{},'strictChecks':{}},save=Mock())
   process=types.SimpleNamespace(pid=12345,poll=lambda:None,wait=Mock(return_value=0))
   def spawn(argv,**kwargs):
    self.assertEqual(argv[0],'/synthetic/node');self.assertIn('--serialExchangeBinding',argv);self.assertEqual(argv[argv.index('--per')+1],'2');self.assertEqual(argv[argv.index('--open')+1],'5');self.assertEqual(argv[argv.index('--restart')+1],'0')
    b=json.loads(Path(argv[argv.index('--serialExchangeBinding')+1]).read_text());self.assertEqual(b['selection'],SELECTION)
    output=Path(argv[argv.index('--out')+1]);output.write_text(json.dumps({'diagnosticOnly':True,'serialExchangeDiagnostic':{'before':{'status':'COMPLETED_64'},'after':{'status':'HTTP_REFUSED'}},'prime':{'primed':6000}}))
    return process
   fake=types.SimpleNamespace(SERIAL_EXCHANGE_DIAGNOSTIC=SELECTION,frozen=Mock(),verify=Mock(),image=Mock(),verify_generator=Mock(),assert_owned=Mock(),document=a.document,digest=a.digest,write=a.write,runtime_env=lambda x:x,sys=sys,progress_services=lambda d:['evaluator'],progress_attribution=lambda m:{},diagnostic_resources=types.SimpleNamespace(popen=lambda launcher,argv,**kwargs:launcher(argv,**kwargs)),subprocess=types.SimpleNamespace(Popen=spawn,STDOUT=-2),sampling=lambda *x:contextlib.nullcontext(),phase_snapshot=Mock(),job_record=Mock(),loadgen_process=lambda *x:contextlib.nullcontext(),stop_job=Mock())
   discovery.serial_exchange_diagnostic(fake,d,m,record)
   self.assertEqual(record.value['serialExchangeDiagnostic']['after']['status'],'HTTP_REFUSED');self.assertEqual(record.value['serialExchangeDiagnostic']['ordinaryTraffic'],'NOT_RUN');fake.stop_job.assert_called_once_with(d/'load/probe-job.json',m['owner']);self.assertFalse((d/'load/.window').exists());self.assertFalse((d/'load/k6-summary.json').exists())
 def test_selected_discovery_branches_after_idle_and_never_calls_ordinary_load(self):
  import discovery
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);(d/'deploy-before-host.json').write_text('{}');events=[]
   m={'profile':'pgstream-sample','serialExchangeDiagnostic':SELECTION,'generator':{},'cadence':{'warmupSeconds':10,'idleSeconds':30}}
   class Record:
    def __init__(self,*args):self.value={'hardFailures':[],'processes':{},'strictChecks':{}}
    def save(self):pass
    def observe(self,name,fn):events.append(name);return fn()
    def failure(self,*args):raise AssertionError('unexpected failure')
   fake=types.SimpleNamespace(frozen=Mock(),quiet=Mock(),verify=Mock(),image=Mock(),verify_generator=Mock(),readiness=Mock(),command=lambda *args: '[{"Id":"synthetic-k6"}]',write=a.write,sample_preflight=lambda *args:({},{}),psql=Mock(),phase_snapshot=Mock(),time=types.SimpleNamespace(sleep=lambda *args:None),enabled_idle=Mock(),diagnostic_resources=types.SimpleNamespace(discovery_driver=Mock(side_effect=lambda m:contextlib.nullcontext())))
   with patch.object(discovery,'Record',Record),patch.object(discovery,'serial_exchange_diagnostic',side_effect=lambda *args:events.append('paired')),patch.object(discovery,'discovery_load',side_effect=AssertionError('ordinary load released')),patch.object(discovery,'check_discovery',return_value=True):
    result=discovery.run_discovery(fake,d,m,'synthetic-k6')
   fake.diagnostic_resources.discovery_driver.assert_called_once_with(m)
   self.assertEqual(events,['readiness','idle','paired']);self.assertEqual(result['status'],'PARTIAL');self.assertTrue(result['diagnosticOnly']);self.assertEqual(result['ordinaryTraffic'],'NOT_RUN');self.assertFalse(result['measurements']['complete'])
 def run_generated(self,mode,broken=False):
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);target=d/'probe.js';probe.generate(ROOT,target,serial_exchange=True)
   (d/'tenants.json').write_text(json.dumps([{'id':'synthetic-'+str(i),'host':'tenant-'+str(i)+'.synthetic','token':'SYNTHETIC_SECRET_'+str(i)}for i in range(3000)]))
   if broken:
    s=target.read_text();anchor="  out.serialExchangeDiagnostic.after=await serialExchange.phase('after');";self.assertEqual(s.count(anchor),1);s=s.replace(anchor,"  fs.writeFileSync(args.signal, String(Date.now()));\n"+anchor);target.write_text(s)
   result=subprocess.run(['node',str(HERE/'test-serial-probe-vm.cjs'),str(target),str(d),mode],capture_output=True,text=True)
   return result
 def test_generated_probe_before_stock_after_close_and_refusal_paths(self):
  for mode in ('positive','stock-retry','refuse-before','refuse-after','throw-before','throw-after','throw-close'):
   with self.subTest(mode=mode):
    result=self.run_generated(mode);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_release_before_after_control_goes_red(self):
  result=self.run_generated('positive',broken=True);self.assertNotEqual(result.returncode,0);self.assertIn('diagnostic released .window',result.stderr)

if __name__=='__main__':unittest.main()
