#!/usr/bin/env python3
"""Explicit bounded matrix: one API first, then 2/4, same frozen source pair."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
from contract import COUNTS, REPLICAS, require, campaign_check


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('work','core-repo','core-commit','deploy-repo','deploy-commit','image','freeze','k6-image'):p.add_argument('--'+name,required=True)
    p.add_argument('--quiet-load',type=float,default=3)
    args=p.parse_args();root=Path(args.work).resolve();require(not root.exists(),'M7_CAMPAIGN_DIRECTORY_EXISTS');root.mkdir(mode=0o700,parents=True)
    summary={'version':1,'kind':'m7-joined-capacity','pair':{'core':args.core_commit,'deploy':args.deploy_commit},'instrument':adapter.instrument()['sha256'],'cells':[]}
    # Source remains identical across counts and replicas. Each cell owns a new
    # project/worktree/port/state and stops growth on any refused correctness gate.
    for replicas in REPLICAS:
        for tenants in COUNTS:
            folder=root/('n'+str(tenants)+'-a'+str(replicas))
            options=SimpleNamespace(**vars(args),directory=str(folder),tenants=tenants,replicas=replicas)
            try:
                adapter.prepare(options);d,m=adapter.load(folder);adapter.deploy(d,m);adapter.run(d,m,args.k6_image)
                cell=adapter.document(folder/'summary.json');summary.setdefault('imageId',cell['imageId']);summary['cells'].append(cell);adapter.write(root/'campaign.json',summary)
            except Exception:
                adapter.write(root/'campaign.json',summary)
                raise
            finally:
                if (folder/'owner.json').exists():
                    d,m=adapter.load(folder)
                    # Down verifies ownership; never force cleanup of mismatches.
                    adapter.down(d,m)
    campaign_check(summary);adapter.write(root/'campaign.json',summary);print('M7_CAMPAIGN_COMPLETE')

if __name__=='__main__':
    try:main()
    except Exception as error:
        text=str(error)
        print(text if text.startswith('M7_') else 'M7_CAMPAIGN_REFUSED',file=sys.stderr);sys.exit(1)
