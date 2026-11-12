#!/usr/bin/env python3
"""Bounded public derivatives from saved G bytes; no runtime, network or repair."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--assessment',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--core-repo',type=Path,required=True);p.add_argument('--harness-repo',type=Path,required=True);a=p.parse_args()
def load(f):return json.loads(f.read_text())
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as s:
  for block in iter(lambda:s.read(1048576),b''):h.update(block)
 return h.hexdigest()
def write(n,v):(a.out/n).write_text(json.dumps(v,indent=2)+'\n')
parents=load(a.assessment/'manifest.json')
for name,digest in parents.items():assert sha(a.assessment/name)==digest
v=load(a.assessment/'assessment.json')
for name,digest in v['rawEvidenceSha256'].items():
 f=Path(name);assert not f.is_absolute() and '..' not in f.parts
 assert sha(a.run/f)==digest,name
pins=v['sourcePins'];assert pins=={'coreCommit':'761e8f19373c4fbbd6fc888b51b35c9b2eb677a1','deployCommit':'31565abe437ea84214aa0068f75de1246c06e45e','alignmentCommit':'502b46b05bc9a581d2c371f18f7e0e71852f0578','instrumentCommit':'7209cb29020543a82412cd69d2751ca939cf4318'}
for name,digest in v['readDerivedSourceSha256'].items():
 data=subprocess.check_output(['git','-C',str(a.core_repo),'show',pins['coreCommit']+':'+name]);assert hashlib.sha256(data).hexdigest()==digest
worker_source=subprocess.check_output(['git','-C',str(a.harness_repo),'show',pins['instrumentCommit']+':tools/perf-cloud/core-acceptance.py']);assert hashlib.sha256(worker_source).hexdigest()==v['capturedSourceProvenance']['workerSha256']
umask_lines=[i+1 for i,line in enumerate(worker_source.decode().splitlines()) if 'umask(0o077)' in line];assert umask_lines==[277]
raw=a.run/'decoded/work/core-acceptance';worker=load(raw/'result.json');commands={row['id']:row for row in load(raw/'commands.json')};assert worker['status']=='failed' and worker['sourceAcceptance']=='COORDINATOR_REVIEW_REQUIRED';assert worker['source']=={k:pins[k] for k in ('coreCommit','deployCommit','alignmentCommit')}
tiers=['unit','dom','dependency','core','harness','integration','stress','browser'];assert worker['completedTests']==tiers
clean=lambda s:re.sub(r'\x1b\[[0-9;]*m','',s)
stages={}
for tier in tiers+['enabled-corpus']:
 lines=clean((raw/'logs'/(tier+'.stdout.log')).read_text()).splitlines();counts={}
 for key in ['passing','pending','failing']:
  hits=[(i+1,int(m[1])) for i,line in enumerate(lines) if (m:=re.match(r'^\s*(\d+) '+key+r'\b',line))]
  counts[key]=hits[-1][1] if hits else 0
 assert counts==v['stages'][tier]['mochaCounts'];cmd=commands[tier]
 assert cmd['returnCode']==v['stages'][tier]['commandReturnCode'] and cmd['status']==v['stages'][tier]['commandStatus']
 stages[tier]={'counts':counts,'recordedCommandStatus':cmd['status'],'recordedReturnCode':cmd['returnCode']}
assert all(stages[t]['recordedReturnCode']==0 for t in tiers);assert stages['enabled-corpus']['recordedReturnCode']==1
inventory=subprocess.check_output(['git','-C',str(a.core_repo),'show',pins['coreCommit']+':scripts/test-multitenant.js']);section=re.search(rb'const INVENTORY = \[([\s\S]*?)\n\];',inventory);assert section;selected=[name.decode() for name in re.findall(rb"\{ file: '([^']+)'",section[1])]
corpus=load(raw/'corpus.json');assert selected==corpus['suites'];assert corpus['suites']==v['enabledCorpus']['selectedSuiteFiles'] and len(set(corpus['suites']))==86
assert corpus['result']=={'status':1,'signal':None,'passing':838,'pending':1,'failing':1}
summary={'kind':'sanitized-core-g-completed-failure','outcome':'FAILED','acceptance':'NOT_ACCEPTED','capacity':'NOT_ASSESSED','source':pins,'workerStatus':worker['status'],'workerSourceAcceptance':worker['sourceAcceptance'],'completedTiers':tiers,'stages':stages,'ordinaryTierTotals':{key:sum(stages[t]['counts'][key] for t in tiers) for key in ['passing','pending','failing']},'enabledCorpus':{'selectedSuites':86,'matchesExactSourceInventory':v['enabledCorpus']['matchesExactSourceUnfilteredInventory'],'actualExecutedFileLedger':'NOT_SEPARATELY_RECORDED','counts':corpus['result'],'startedAt':corpus['startedAt'],'finishedAt':corpus['finishedAt']},'processAttribution':'Only recorded outer stage command exits are reported; no independent child CLI exit ledger is inferred.'}
write('summary.json',summary)
failure=v['enabledCorpus']['failure'];lines=clean((raw/'logs/enabled-corpus.stdout.log').read_text()).splitlines();excerpt=[]
for row in failure['capturedLogTail']:
 text=row['text'];line=row['line']
 if not text.strip():continue
 assert 1<=line<=len(lines)
 assert text.strip() in lines[line-1] or lines[line-1].strip().endswith(text.strip())
 assert len(text)<=300 and not re.search(r'https?://|/home/|/opt/|postgres(?:ql)?://|bearer\s|password\s*[:=]|token\s*[:=]',text,re.I)
 excerpt.append({'line':line,'text':text})
write('failure-and-pending.json',{'kind':'bounded-captured-log-derivative','logSha256':v['rawEvidenceSha256']['decoded/work/core-acceptance/logs/enabled-corpus.stdout.log'],'excerpt':excerpt,'case':failure['case'],'source':failure['source'],'capturedAssertion':{'message':failure['assertion'],'comparedActual':0,'comparedExpected':64},'childProcessExitLedger':'NOT_SEPARATELY_RECORDED','originalFileMode':'UNMEASURED','mechanismGrade':'READ_DERIVED','mechanism':failure['readDerivedHypothesis'],'enabledPending':v['enabledCorpus']['pending'],'ordinaryPendingCounts':{t:stages[t]['counts']['pending'] for t in tiers}})
cleanup=v['cleanup'];assert worker['ownMongoCleanupVerified'] is True and worker['fixtureResiduals']==[] and worker['fixtureVolumeResiduals']==[]
assert corpus['remaining']==[] and all(r['verifiedAbsent'] for r in corpus['removed'])
cloud=load(a.run/'final-cloud-inventory.json');filtered={k:cloud[k] for k in ['verifiedAt','remainingDroplets','remainingFirewalls','remainingRunTags']};assert filtered==cleanup['independentProviderInventory']
write('cleanup.json',{'kind':'sanitized-captured-cleanup','workerOwnedMongoCleanupVerified':worker['ownMongoCleanupVerified'],'fixtureResiduals':worker['fixtureResiduals'],'fixtureVolumeResiduals':worker['fixtureVolumeResiduals'],'corpusOwnedCreatedCount':len(corpus['created']),'corpusOwnedRemoved':cleanup['corpusOwnedRemoved'],'corpusRemaining':corpus['remaining'],'controller':cleanup['controller'],'watchdog':cleanup['watchdog'],'savedProviderInventory':filtered,'inventoryObservation':'Read from retained parent capture; no reviewer provider query.','parentObservedEphemeralKeyFilesPresent':cleanup['ephemeralKeyFilesPresent'],'keyObservation':'Parent filesystem observation reported in hash-bound assessment; not independently re-observed.','capturedComputeEstimate':v['cost']})
write('provenance.json',{'kind':'public-derivative-provenance','sourcePins':pins,'capturedSource':v['capturedSourceProvenance'],'capturedKernel':v['capturedKernel'],'rawPrivateOriginalsSha256':v['rawEvidenceSha256'],'readDerivedSourceSha256':v['readDerivedSourceSha256'],'verifiedCommittedWorker':{'path':'tools/perf-cloud/core-acceptance.py','sha256':hashlib.sha256(worker_source).hexdigest(),'umaskLines':umask_lines,'scope':'Committed bytes match captured worker hash; not an original target-file mode observation.'},'parentAssessmentSha256':parents,'publicationScope':'Public derivatives only; raw private spec/environment/logs/container/provider inventory are not published.','reviewerActions':'Read and hash saved artifacts only; no cloud, Docker, runtime, tests or repair.'})
print(json.dumps({'outcome':summary['outcome'],'ordinaryTierTotals':summary['ordinaryTierTotals'],'corpus':corpus['result'],'source':pins}))
