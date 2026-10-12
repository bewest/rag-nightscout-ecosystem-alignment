"""Task 1(c): do explicit nulls survive a v1/v3 create? Reads stored docs straight from MongoDB.
usage: python3 -I repro.py <port> <dbname> <label>"""
import json,sys,hashlib,urllib.request,subprocess,time,datetime
port,db,label=sys.argv[1],sys.argv[2],sys.argv[3]
SECRET=open(sys.argv[4]).read().strip()
H={'api-secret':hashlib.sha1(SECRET.encode()).hexdigest(),'Content-Type':'application/json','Accept':'application/json'}
B=f'http://127.0.0.1:{port}'
def req(m,p,body=None,h=None):
    r=urllib.request.Request(B+p,data=None if body is None else json.dumps(body).encode(),method=m,headers=h or H)
    try:
        with urllib.request.urlopen(r,timeout=20) as x: return x.status,x.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()
def mongo(col,q):
    js=f"EJSON.stringify(db.getSiblingDB('{db}').{col}.find({json.dumps(q)},{{_id:0}}).toArray(),{{relaxed:true}})"
    out=subprocess.run(['docker','exec','wcnull-mongo','mongosh','--quiet','--eval',js],capture_output=True,text=True).stdout
    return json.loads(out)
now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
iso=lambda d:d.isoformat().replace('+00:00','.000Z')
ms=int(now.timestamp()*1000)
print('#',label,'mongo',subprocess.run(['docker','exec','wcnull-mongo','mongosh','--quiet','--eval','db.version()'],capture_output=True,text=True).stdout.strip())
def show(name,col,q):
    docs=mongo(col,q)
    for d in docs:
        nulls=sorted([k for k,v in d.items() if v is None]+[k+'.'+k2 for k,v in d.items() if isinstance(v,dict) for k2,v2 in v.items() if v2 is None])
        print(f'{name}: stored nulls={nulls} stored keys={sorted(d)}')
    if not docs: print(f'{name}: NOT STORED')
# 1 v1 treatment with explicit nulls
t={'eventType':'Note','created_at':iso(now),'enteredBy':'wc-lab-v1','notes':'n','reason':None,'labNull':None,'labNested':{'a':None,'b':1},
   'carbs':None,'insulin':None,'duration':None,'absolute':None,'targetTop':None}
print('v1 POST treatments', req('POST','/api/v1/treatments',[t])[0]); show('  v1 treatment','treatments',{'enteredBy':'wc-lab-v1'})
# control: same shape without nulls, and the v1 GET rendering of carbs/insulin
t2={'eventType':'Note','created_at':iso(now+datetime.timedelta(seconds=1)),'enteredBy':'wc-lab-v1-nonull','notes':'n'}
print('v1 POST treatments (control, no nulls)', req('POST','/api/v1/treatments',[t2])[0]); show('  v1 treatment control','treatments',{'enteredBy':'wc-lab-v1-nonull'})
s,b=req('GET','/api/v1/treatments.json?find[enteredBy]=wc-lab-v1-nonull')
g=json.loads(b) if s==200 else []
print('  v1 GET of control: status',s,'carbs' in (g[0] if g else {}), 'value', (g[0].get('carbs','ABSENT') if g else None), 'insulin', (g[0].get('insulin','ABSENT') if g else None))
# 2 entries
e={'type':'sgv','sgv':101,'date':ms,'dateString':iso(now),'device':'wc-lab-v1','direction':None,'noise':None,'labNested':{'a':None}}
print('v1 POST entries', req('POST','/api/v1/entries',[e])[0]); show('  v1 entry','entries',{'device':'wc-lab-v1'})
# 3 devicestatus
d={'device':'wc-lab://v1','created_at':iso(now),'labNull':None,'pump':{'battery':None,'reservoir':10},'uploader':{'battery':None}}
print('v1 POST devicestatus', req('POST','/api/v1/devicestatus',[d])[0]); show('  v1 devicestatus','devicestatus',{'device':'wc-lab://v1'})
# 4 profile
p={'defaultProfile':'Default','startDate':iso(now),'created_at':iso(now),'enteredBy':'wc-lab-v1','labNull':None,'store':{'Default':{'units':'mg/dl','timezone':'UTC','dia':5,'carbratio':[{'time':'00:00','value':10}],'sens':[{'time':'00:00','value':50}],'basal':[{'time':'00:00','value':1}],'target_low':[{'time':'00:00','value':100}],'target_high':[{'time':'00:00','value':110}]}},'mills':None}
print('v1 POST profile', req('POST','/api/v1/profile',p)[0]); show('  v1 profile','profile',{'enteredBy':'wc-lab-v1'})
# 5 v3 treatment
t3={'eventType':'Note','date':ms+5000,'app':'wc-lab','device':'wc-lab-v3','enteredBy':'wc-lab-v3','notes':'n','labNull':None,'labNested':{'a':None},'carbs':None,'insulin':None}
s,b=req('POST','/api/v3/treatments',t3); print('v3 POST treatments',s,b[:120].replace(SECRET,'***')); show('  v3 treatment','treatments',{'enteredBy':'wc-lab-v3'})
# 6 v1 re-send: stored reason 'x', re-send with reason null (today's re-send = replace)
t4={'eventType':'Temp Target','created_at':iso(now+datetime.timedelta(seconds=7)),'enteredBy':'wc-lab-resend','reason':'x','duration':30,'targetTop':110,'targetBottom':100,'syncIdentifier':'wc-lab-sync-1'}
req('POST','/api/v1/treatments',[t4]); show('  re-send step 1 (reason set)','treatments',{'enteredBy':'wc-lab-resend'})
t5=dict(t4); t5['reason']=None
req('POST','/api/v1/treatments',[t5]); show('  re-send step 2 (reason null)','treatments',{'enteredBy':'wc-lab-resend'})
