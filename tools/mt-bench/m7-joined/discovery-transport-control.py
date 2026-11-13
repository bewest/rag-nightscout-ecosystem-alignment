#!/usr/bin/env python3
"""Actual source producer -> immutable transport validator; recording files only."""
import argparse
import ast
import types
from unittest.mock import patch
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import evaluator_idle
import evaluator_progress
import adapter
from discovery import Record,check_discovery

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repo',required=True);parser.add_argument('--commit',required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='m7-discovery-contract-') as temp:
        root=Path(temp);base=root/'tools/perf-cloud'
        paths=['pilot-ledger.py','tests/pilot-ledger.test.py','tests/fixtures/pilot-progress-policy-v2.json','tests/fixtures/pilot-idle-safety-policy-v1.json']
        hashes={}
        for name in paths:
            rel='tools/perf-cloud/'+name;raw=subprocess.check_output(['git','-C',args.repo,'show',args.commit+':'+rel]);file=base/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw);hashes[rel]=hashlib.sha256(raw).hexdigest()
        spec=importlib.util.spec_from_file_location('recording_transport_fixture',base/'tests/pilot-ledger.test.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.POLICY=evaluator_progress.POLICY;module.IDLE_POLICY=evaluator_idle.POLICY
        cell=root/'cell';module.populate(cell,500);owner=adapter.document(cell/'owner.json');identity=module.expected();identity['runPurpose']='discovery'
        owner.update(owner='f'*32,hostIdentity=identity['hostIdentity'],imageId=identity['imageId'],runPurpose='discovery');adapter.write(cell/'owner.json',owner)
        record=Record(adapter,cell,owner);record.value['ownershipVerified']=True;record.save();check_discovery(record.value)
        module.pilot.validate_discovery_cell(cell,500,identity)
        original=adapter.document(cell/'summary.json');broken={k:v for k,v in original.items() if k!='profileSelection'};adapter.write(cell/'summary.json',broken)
        try:module.pilot.validate_discovery_cell(cell,500,identity)
        except RuntimeError as error:assert 'PROFILE_SELECTION_SHAPE' in str(error)
        else:raise AssertionError('MISSING_DECLARED_PROFILE_FALSE_PASS')
        adapter.write(cell/'summary.json',original);module.pilot.validate_discovery_cell(cell,500,identity)
        # Execute the actual producer through its first ownership check only;
        # all product/Git/Docker operations are beyond this recording boundary.
        class PreparedCaptured(Exception):pass
        def capture(fn,purpose,target):
            args=types.SimpleNamespace(core_commit='a'*40,deploy_commit='b'*40,core_repo=str(root/'core'),deploy_repo=str(root/'deploy'),image='synthetic',tenants=500,replicas=1,quiet_load=3,freeze=str(root/'freeze'),profile='remote-pilot',run_purpose=purpose)
            with patch.object(adapter,'port',return_value=1234),patch.object(adapter,'inventory',return_value={}),patch.object(adapter,'host_identity',return_value=identity['hostIdentity']),patch.object(adapter,'resources',side_effect=PreparedCaptured):
                try:fn(args,target,{'sha256':identity['instrument']})
                except PreparedCaptured:pass
                else:raise AssertionError('PREPARE_RECORDING_BOUNDARY_NOT_REACHED')
            return adapter.document(target/'owner.json')
        adapter.write(root/'input/pilot-instrument.json',{'sha256':identity['instrument']})
        default_spec={'coreCommit':'a'*40,'deployCommit':'b'*40,'diagnostics':'off','diagnosticsIntervalMs':5000}
        adapter.write(root/'input/spec.json',default_spec)
        captured=capture(adapter.prepare_staged,'acceptance',cell);assert 'runPurpose' not in captured
        module.pilot.validate_prepared(root,cell,500)
        # Exact prior producer reproduces the mismatch; no source/worktree edits.
        old_source=subprocess.check_output(['git','-C',adapter.ROOT,'show','1591a3e8cfbff1eb462690843ce936abcb6fe218:tools/mt-bench/m7-joined/adapter.py'],text=True)
        node=next(n for n in ast.parse(old_source).body if isinstance(n,ast.FunctionDef) and n.name=='prepare_staged')
        old_tree=ast.Module(body=[node],type_ignores=[]);old_globals=adapter.__dict__
        exec(compile(old_tree,'<original159prepare>','exec'),old_globals)
        old_fn=old_globals['prepare_staged']
        # Restore the current function after extraction, including on failure.
        current_node=next(n for n in ast.parse((adapter.HERE/'adapter.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='prepare_staged')
        try:
            capture(old_fn,'acceptance',cell)
            try:module.pilot.validate_prepared(root,cell,500)
            except RuntimeError as error:assert 'PREPARE_PURPOSE_CHANGED' in str(error)
            else:raise AssertionError('DEFAULT_PURPOSE_MISMATCH_NOT_REPRODUCED')
        finally:exec(compile(ast.Module(body=[current_node],type_ignores=[]),'<restoredprepare>','exec'),old_globals)
        capture(adapter.prepare_staged,'acceptance',cell);module.pilot.validate_prepared(root,cell,500)
        adapter.write(root/'input/spec.json',{**default_spec,'runPurpose':'discovery'})
        capture(adapter.prepare_staged,'discovery',cell);module.pilot.validate_prepared(root,cell,500)
        adapter.write(cell/'owner.json',owner);adapter.write(cell/'summary.json',original)
        cells=[original]
        for count in (750,1000):
            target=root/('cell-'+str(count));module.populate(target,count);other=adapter.document(target/'owner.json')
            other.update(owner='f'*32,hostIdentity=identity['hostIdentity'],imageId=identity['imageId'],runPurpose='discovery');adapter.write(target/'owner.json',other)
            produced=Record(adapter,target,other);produced.value['ownershipVerified']=True;produced.save();module.pilot.validate_discovery_cell(target,count,identity);cells.append(produced.value)
        aggregate=module.pilot.assemble(cells,identity);check_discovery(aggregate)
        print(json.dumps({'defaultPreparedProducerAccepted':True,'oldDefaultPurposeMismatchRefused':True,'discoveryPreparedProducerAccepted':True,'aggregateActualTransportAccepted':True,'kind':'recording-source-producer-transport-control','transportCommit':args.commit,'hashes':hashes,'partialProducerAccepted':True,'missingProfileRefused':True,'restored':True}))
if __name__=='__main__':main()
