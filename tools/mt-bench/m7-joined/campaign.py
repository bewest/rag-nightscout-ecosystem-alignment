#!/usr/bin/env python3
"""Explicit same-source capacity ladders; never skip a failed functional gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
from contract import COUNTS, REPLICAS, PILOT_COUNTS, require, campaign_check, pilot_check, host_identity, measurement_request, measurement_output, unaccepted_check, receipt_scope


def failure_class(code):
    if code.startswith(('M7_ORACLE_','M7_CONTROL_','M7_FUNCTIONAL_')):return 'functional-block'
    if code.startswith(('M7_IMAGE_','M7_SOURCE_','M7_OWN_','M7_INSTRUMENT_','M7_RESOURCE_','M7_FOREIGN_','M7_HOST_','M7_FROZEN_','M7_GENERATOR_')):return 'attribution-or-host-block'
    return 'diagnosis-required'


def authorize_profile(profile, master, root, receipt_file):
    require(not master.get('functionalBlock'),'M7_GLOBAL_FUNCTIONAL_BLOCK')
    if profile==1:return
    previous=REPLICAS[REPLICAS.index(profile)-1]
    prior_path=root/('profile-'+str(previous)+'.json')
    require(prior_path.is_file(),'M7_FIRST_PROFILE_REQUIRED')
    prior=adapter.document(prior_path)
    if prior.get('status')=='PASS':return
    require(prior.get('failureClass')=='diagnosis-required','M7_PRIOR_PROFILE_BLOCKED')
    require(receipt_file is not None,'M7_PRIOR_PROFILE_NEEDS_DIAGNOSIS')
    receipt=adapter.document(receipt_file)
    require(receipt.get('kind')=='measured-profile-ceiling' and receipt.get('classification')=='performance'
            and receipt.get('pair')==master['pair'] and receipt.get('instrument')==master['instrument']
            and receipt.get('hostIdentity')==master['hostIdentity']
            and receipt.get('profileArtifactSha256')==adapter.digest(prior_path)
            and re.fullmatch(r'[0-9a-f]{64}',receipt.get('diagnosisEvidenceSha256','')),'M7_PROFILE_CEILING_RECEIPT_INVALID')


def ladder(args, profile, root, master):
    require(not master.get("functionalBlock"),"M7_GLOBAL_FUNCTIONAL_BLOCK")
    tools=adapter.generator_tools()
    master.setdefault("generatorTools",tools)
    require(master["generatorTools"]==tools,"M7_GENERATOR_TOOL_CHANGED")
    adapter.write(root/"campaign.json",master)
    pilot=args.mode=="pilot"
    if not pilot:authorize_profile(profile,master,root,args.ceiling_receipt)
    label="remote-pilot" if pilot else str(profile)
    require(not (root/('profile-'+label+'.json')).exists(),'M7_PROFILE_ALREADY_RECORDED')
    result={**measurement_output(master,aggregate=True,complete=False),'profile':profile,'pair':master['pair'],'instrument':master['instrument'],'hostIdentity':master['hostIdentity'],'status':'RUNNING','cells':[]}
    for tenants in (PILOT_COUNTS if pilot else COUNTS):
        folder=root/('n'+str(tenants)+'-a'+str(profile))
        options=SimpleNamespace(**{**vars(args),"profile":"remote-pilot" if pilot else "capacity","directory":str(folder),"tenants":tenants,"replicas":profile})
        error=None
        try:
            adapter.prepare(options);d,m=adapter.load(folder);adapter.deploy(d,m);adapter.run(d,m,args.k6_image)
            cell=adapter.document(folder/'summary.json')
            require(cell.get('hostIdentity')==master['hostIdentity'],'M7_HOST_IDENTITY_CHANGED')
            master.setdefault('imageId',cell['imageId']);require(master['imageId']==cell['imageId'],'M7_IMAGE_ID_CHANGED')
            from profile_provenance import check_identity
            chosen=check_identity(cell.get('profileSelection'))
            master.setdefault('profileSelection',chosen)
            require(master['profileSelection']==chosen,'M7_PROFILE_SELECTION_MISMATCH')
            result['profileSelection']=chosen
            result['cells'].append(cell);master['cells'].append(cell)
        except Exception as caught:
            error=caught
        finally:
            if (folder/'owner.json').exists():
                try:
                    d,m=adapter.load(folder);adapter.down(d,m)
                except Exception as cleanup:
                    error=cleanup  # Ownership cleanup refusal itself blocks progression.
        if error:
            text=str(error);code=text if text.startswith('M7_') else 'M7_PROFILE_DIAGNOSIS_REQUIRED'
            result.update(**measurement_output(master,aggregate=True,complete=False),status='FAIL',failedTenants=tenants,error=code,failureClass=failure_class(code))
            if result['failureClass']=='functional-block':master['functionalBlock']=True
            if master.get('measurementMode')=='unaccepted':
                if (folder/'summary.json').is_file():
                    partial=adapter.document(folder/'summary.json')
                    if partial not in result['cells']:result['cells'].append(partial);master['cells'].append(partial)
                master.update(measurement_output(master,aggregate=True,complete=False),verdict='FAIL',failedTenants=tenants,error=code)
            adapter.write(root/('profile-'+label+'.json'),result);adapter.write(root/'campaign.json',master)
            raise error
        adapter.write(root/'campaign.json',master)
    result.update(measurement_output(master,aggregate=True),verdict='PASS');result['status']='PASS';adapter.write(root/('profile-'+label+'.json'),result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('all','ladder','pilot'))
    for name in ('work','core-repo','core-commit','deploy-repo','deploy-commit','image','freeze','k6-image'):p.add_argument('--'+name,required=True)
    p.add_argument('--quiet-load',type=float,default=3);p.add_argument('--replicas',type=int,choices=REPLICAS);p.add_argument('--ceiling-receipt')
    p.add_argument('--diagnostics',choices=('off','on'),default='off');p.add_argument('--diagnostics-interval-ms',type=int,default=5000)
    p.add_argument('--measurement-mode',choices=('accepted','unaccepted'),default='accepted');p.add_argument('--run-id');p.add_argument('--image-id');p.add_argument('--maximum-run-minutes',type=int,default=180)
    args=p.parse_args();root=Path(args.work).resolve()
    require(args.mode in ('all','pilot') or args.replicas in REPLICAS,'M7_LADDER_PROFILE_REQUIRED')
    instrument=adapter.instrument()['sha256']
    pair={'core':args.core_commit,'deploy':args.deploy_commit}
    if args.measurement_mode=='unaccepted':
        require(args.mode=='pilot','M7_UNACCEPTED_PROFILE_LIMIT')
        candidate={'measurementMode':'unaccepted','profile':'remote-pilot','tenants':500,'replicas':args.replicas or 1,'pair':pair,'instrument':{'sha256':instrument},'imageId':args.image_id,'runId':args.run_id,'maximumRunMinutes':args.maximum_run_minutes,'diagnostics':adapter.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)}
        receipt_scope(candidate,adapter.document(args.freeze),'run')
    host=adapter.inventory('none');identity=host_identity(host)
    chosen=adapter.profile_provenance.selection(args.diagnostics,args.diagnostics_interval_ms)
    kind='m7-joined-unaccepted-measurement' if args.measurement_mode=='unaccepted' else 'm7-joined-remote-pilot' if args.mode=='pilot' else 'm7-joined-capacity'
    if root.exists():
        require((root/'campaign.json').is_file(),'M7_CAMPAIGN_DIRECTORY_NOT_OWNED')
        master=adapter.document(root/'campaign.json')
        require(master.get('directory')==str(root) and master.get('kind')==kind and master.get('pair')==pair and master.get('instrument')==instrument
                and master.get('hostIdentity')==identity and master.get('diagnostics')==chosen and master.get('measurementMode','accepted')==args.measurement_mode
                and (args.measurement_mode!='unaccepted' or master.get('runId')==args.run_id and master.get('imageId')==args.image_id),'M7_CAMPAIGN_IDENTITY_CHANGED')
    else:
        root.mkdir(mode=0o700,parents=True)
        master={'version':1,'kind':kind,'directory':str(root),'pair':pair,'instrument':instrument,'hostIdentity':identity,'diagnostics':chosen,'cells':[]}
        if args.measurement_mode=='unaccepted':master.update(measurement_output(candidate,aggregate=True,complete=False),imageId=args.image_id)
        adapter.write(root/'campaign.json',master)
    selected=args.replicas or 1
    if args.mode=='pilot':
        master.setdefault('profileReplicas',selected)
        require(master['profileReplicas']==selected,'M7_PILOT_REPLICAS_CHANGED')
    profiles=REPLICAS if args.mode=='all' else (selected,) if args.mode=='pilot' else (args.replicas,)
    for profile in profiles:ladder(args,profile,root,master)
    if args.mode=='all':campaign_check(master);print('M7_CAMPAIGN_COMPLETE')
    elif args.mode=='pilot':
        if args.measurement_mode=='unaccepted':master.update(measurement_output(master,aggregate=True),verdict='PASS');unaccepted_check(master);adapter.write(root/'campaign.json',master);print('M7_UNACCEPTED_COLLECTION_COMPLETE_NOT_ACCEPTANCE')
        else:pilot_check(master);print('M7_REMOTE_PILOT_COMPLETE')
    else:print('M7_REPLICA_LADDER_COMPLETE:'+str(args.replicas))

if __name__=='__main__':
    try:main()
    except Exception as error:
        text=str(error)
        print(text if text.startswith('M7_') else 'M7_CAMPAIGN_REFUSED',file=sys.stderr);sys.exit(1)
