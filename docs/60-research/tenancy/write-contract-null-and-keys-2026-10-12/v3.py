import json,sys,hashlib,urllib.request,subprocess,time
port,db=sys.argv[1],sys.argv[2]; SECRET=open(sys.argv[3]).read().strip()
H={'api-secret':hashlib.sha1(SECRET.encode()).hexdigest(),'Content-Type':'application/json','Accept':'application/json'}
B=f'http://127.0.0.1:{port}'
def req(m,p,body=None,h=H):
    r=urllib.request.Request(B+p,data=None if body is None else json.dumps(body).encode(),method=m,headers=h)
    try:
        with urllib.request.urlopen(r,timeout=20) as x: return x.status,x.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()
s,b=req('POST','/api/v2/authorization/subjects',{'name':'wclab','roles':['admin']}); print('subject create',s)
s,b=req('GET','/api/v2/authorization/subjects'); tok=[x for x in json.loads(b) if x['name']=='wclab'][0]['accessToken']
s,b=req('GET','/api/v2/authorization/request/'+tok,h={'Accept':'application/json'}); jwt=json.loads(b)['token']
J={'Authorization':'Bearer '+jwt,'Content-Type':'application/json','Accept':'application/json'}
def mongo(col,q):
    js=f"EJSON.stringify(db.getSiblingDB('{db}').{col}.find({json.dumps(q)},{{_id:0}}).toArray(),{{relaxed:true}})"
    return json.loads(subprocess.run(['docker','exec','wcnull-mongo','mongosh','--quiet','--eval',js],capture_output=True,text=True).stdout)
ms=int(time.time()*1000)
for col,body in [('treatments',{'eventType':'Note','date':ms,'app':'wc-lab','device':'wc-lab-v3','notes':'n','labNull':None,'labNested':{'a':None},'carbs':None,'insulin':None}),
                 ('entries',{'type':'sgv','sgv':99,'date':ms,'app':'wc-lab','device':'wc-lab-v3','direction':None,'labNested':{'a':None}}),
                 ('devicestatus',{'date':ms,'app':'wc-lab','device':'wc-lab-v3','labNull':None,'pump':{'battery':None}})]:
    s,b=req('POST','/api/v3/'+col,body,h=J)
    d=mongo(col,{'device':'wc-lab-v3'})
    for x in d:
        nulls=sorted([k for k,v in x.items() if v is None]+[k+'.'+k2 for k,v in x.items() if isinstance(v,dict) for k2,v2 in v.items() if v2 is None])
        print(f'v3 POST {col} {s}: stored nulls={nulls}')
    if not d: print(f'v3 POST {col} {s}: NOT STORED {b[:100]}')
# v1 treatment duration/absolute null -> stored value
print('v1 duration/absolute stored as', mongo('treatments',{'enteredBy':'wc-lab-v1'})[0].get('duration'), mongo('treatments',{'enteredBy':'wc-lab-v1'})[0].get('absolute'))
