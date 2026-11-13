#!/usr/bin/env python3
"""Explicit in-memory semantic ablations; no source edits or runtime admission."""
import importlib.util,sys,types,unittest
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here))
mode=sys.argv[1]
if mode=='image':
 file=here/'contract.py';target=' and receipt.get("imageId")==manifest["imageId"]';name='contract';test='test_unknown_claims_wrong_tuple_image_run_hash_limits_refuse'
elif mode=='accepted-gate':
 file=here.parents[1]/'queue/gates/m7_joined_receipt.py';target="    need(not unaccepted_measurement(cell),'M7_UNACCEPTED_MEASUREMENT_NOT_ACCEPTANCE')\n";name='m7_joined_receipt';test='test_real_receipt_gate_rejects_unaccepted_cell_even_when_otherwise_valid'
else:raise ValueError('NAMED_CONTROL_REQUIRED')
raw=file.read_text();assert raw.count(target)==1,'CONTROL_SOURCE_CHANGED'
m=types.ModuleType(name);m.__file__=str(file);sys.modules[name]=m;exec(compile(raw.replace(target,''),str(file),'exec'),m.__dict__)
s=importlib.util.spec_from_file_location('selected_controls',here/'test_unaccepted.py');tests=importlib.util.module_from_spec(s);s.loader.exec_module(tests)
r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([tests.Unaccepted(test)]))
raise SystemExit(0 if r.wasSuccessful() else 1)
