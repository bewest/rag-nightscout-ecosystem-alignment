"""Recording-only actual spawned-process exit capture, with no Docker/application."""
import pathlib,shutil,subprocess,sys,json,os
os.umask(0o077);here=pathlib.Path(__file__).parent;base=pathlib.Path('/tmp/ns-api-native-9db-supervisor-test-20261112');base.mkdir(mode=0o700)
for code in [0,7]:
 root=base/str(code);root.mkdir();shutil.copyfile(here/'run-once.py',root/'run-once.py');(root/'strict-time.spec.private.json').write_text('{}\n');(root/'capture.py').write_text('print("RECORDING_ONLY");raise SystemExit('+str(code)+')\n')
 child=subprocess.run([sys.executable,str(root/'run-once.py')],capture_output=True,text=True);record=json.loads((root/'process-result.private.json').read_bytes());assert child.returncode==record['returnCode']==code
 original=(root/'process-result.private.json').read_bytes();again=subprocess.run([sys.executable,str(root/'run-once.py')],capture_output=True,text=True);assert again.returncode!=0 and original==(root/'process-result.private.json').read_bytes()
print('RECORDING_ONLY: supervisor retains actual spawned exit0 and7; exact-once refuses both repeated launches. No native capture.')
