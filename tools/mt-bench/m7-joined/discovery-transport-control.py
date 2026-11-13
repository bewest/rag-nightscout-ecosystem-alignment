#!/usr/bin/env python3
"""Actual source producer -> immutable transport validator; recording files only."""
import argparse
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
        cells=[original]
        for count in (750,1000):
            target=root/('cell-'+str(count));module.populate(target,count);other=adapter.document(target/'owner.json')
            other.update(owner='f'*32,hostIdentity=identity['hostIdentity'],imageId=identity['imageId'],runPurpose='discovery');adapter.write(target/'owner.json',other)
            produced=Record(adapter,target,other);produced.value['ownershipVerified']=True;produced.save();module.pilot.validate_discovery_cell(target,count,identity);cells.append(produced.value)
        aggregate=module.pilot.assemble(cells,identity);check_discovery(aggregate)
        print(json.dumps({'aggregateActualTransportAccepted':True,'kind':'recording-source-producer-transport-control','transportCommit':args.commit,'hashes':hashes,'partialProducerAccepted':True,'missingProfileRefused':True,'restored':True}))
if __name__=='__main__':main()
