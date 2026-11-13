from pathlib import Path
import json,subprocess,time
s=Path('<private-state>/clinical');owner=json.loads((s/'owner.json').read_text());id=owner['id']
row=json.loads(subprocess.check_output(['docker','inspect',id],text=True))[0]
assert row['Id']==id and row['Config']['Labels']['ns.api.final-clinical.owner']==owner['owner']
for _ in range(60):
 p=subprocess.run(['docker','exec',id,'pg_isready','-h','127.0.0.1','-U','postgres','-d','clinical_final'],capture_output=True)
 if p.returncode==0:break
 time.sleep(.25)
else:raise RuntimeError('OWN_FINAL_TCP_PG_NOT_READY')
facts={'id':id,'imageId':row['Image'],'image':owner['image'],'serverVersion':subprocess.check_output(['docker','exec',id,'psql','-U','postgres','-d','clinical_final','-Atc','SHOW server_version'],text=True).strip(),'owner':owner['owner'],'boundLoopback':row['NetworkSettings']['Ports']['5432/tcp'][0]['HostIp']=='127.0.0.1'}
(s/'pg-facts.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps(facts))
