"""Write-contract corpus measurements: explicit nulls (Task 1a) and natural keys (Task 2).
Aggregate output only; no identifiers. Usage: python3 -I analyze.py [--control]"""
import json,collections,re,sys,copy
from datetime import datetime
base='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/ns-data/'
SITES=[(c,f'patients/{c}/raw') for c in 'abcdefghijk']+[('L','live-recent-180-json/live-recent')]
CONTROL='--control' in sys.argv

def cls_treat(x):
    v=x.get('enteredBy')
    if v is None: return 'no-enteredBy'
    v=str(v)
    if v.startswith('loop://'): return 'Loop'
    if v=='Loop': return 'Loop (enteredBy=Loop)'
    if v.startswith('Loop (via remote'): return 'Loop (remote command)'
    if v=='Trio': return 'Trio'
    if v.startswith('openaps://AndroidAPS') or v=='AndroidAPS': return 'AndroidAPS'
    if v.startswith('openaps://'): return 'openaps'
    if v=='xDrip4iOS': return 'xDrip4iOS'
    if v.lower().startswith('xdrip'): return 'xDrip+'
    return 'other free-text'
def cls_ds(x):
    v=x.get('device')
    if v is None: return 'no-device'
    v=str(v)
    if v.startswith('loop://'): return 'Loop'
    if v=='Trio': return 'Trio'
    if v.startswith('openaps://AndroidAPS'): return 'AndroidAPS'
    if v.startswith('openaps://'): return 'openaps'
    if set(x)-{'_id','device','created_at','uploader','uploaderBattery','utcOffset','mills','srvModified','srvCreated','identifier'}==set() and 'uploader' in x:
        return 'uploader-only (phone-model device)'
    return 'other'
def cls_entry(x):
    v=x.get('device')
    if v is None: return 'no-device'
    v=str(v)
    if re.match(r'Dexcom G[67] ',v): return 'CGM manager (Dexcom <model> <tx>)'
    if v.startswith('com.dexcom.'): return 'Dexcom app bundle id'
    if 'trio' in v.lower(): return 'Trio bundle id'
    if v=='share2': return 'share2'
    if 'LibreLinkUp' in v: return 'LibreLinkUp'
    if v.startswith('xDrip-'): return 'xDrip+ ('+v.split('-',1)[1][:20]+')' if v in('xDrip-WebFollower',) else 'xDrip+'
    if v.startswith('redacted'): return 'redacted device'
    if v.startswith('loop://'): return 'Loop'
    if v.startswith('openaps://'): return 'openaps/AndroidAPS'
    return 'other'
def cls_profile(x):
    v=x.get('enteredBy')
    return 'enteredBy:'+cls_treat(x) if v is not None else 'no-enteredBy'
CLS={'treatments':cls_treat,'devicestatus':cls_ds,'entries':cls_entry,'profile':cls_profile}

def nullpaths(x):
    top=[];nested=[];deep=0
    for k,v in x.items():
        if v is None: top.append(k)
        elif isinstance(v,dict):
            for k2,v2 in v.items():
                if v2 is None: nested.append(k+'.'+k2)
    def anyd(o,d):
        if o is None: return d>=3
        if isinstance(o,dict): return any(anyd(v,d+1) for v in o.values())
        if isinstance(o,list): return any(anyd(v,d+1) for v in o)
        return False
    return top,nested,anyd(x,0)

def iso_ms(s):
    try:
        if isinstance(s,(int,float)): return None
        t=s.replace('Z','+00:00')
        return datetime.fromisoformat(t).timestamp()*1000
    except Exception: return None

VOLATILE={'_id','srvModified','srvCreated','identifier','mills','utcOffset'}

def run(load):
    R={'nulls':collections.Counter(),'nulldocs':collections.Counter(),'docs':collections.Counter(),'deepdocs':collections.Counter(),
       'dsgroups':collections.Counter(),'entdiff':collections.Counter()}
    for site,path in SITES:
        for col in ['treatments','entries','devicestatus','profile']:
            docs=load(path,col)
            if col=='profile' and isinstance(docs,dict): docs=[docs]
            for x in docs:
                c=CLS[col](x)
                R['docs'][(col,c)]+=1
                top,nested,deep=nullpaths(x)
                if top or nested: R['nulldocs'][(col,c)]+=1
                if deep: R['deepdocs'][(col,c)]+=1
                for f in top+nested: R['nulls'][(col,c,f)]+=1
            if col=='devicestatus':
                g=collections.defaultdict(list); gi=collections.defaultdict(list)
                for x in docs:
                    g[(x.get('created_at'),x.get('device'))].append(x)
                    gi[(iso_ms(x.get('created_at')),x.get('device'))].append(x)
                for label,G in (('string',g),('instant',gi)):
                    for k,v in G.items():
                        if len(v)<2: continue
                        c=CLS[col](v[0])
                        bodies={json.dumps({a:b for a,b in d.items() if a not in VOLATILE},sort_keys=True) for d in v}
                        kind='identical bodies (retry duplicate)' if len(bodies)==1 else 'distinct bodies'
                        R['dsgroups'][(label,c,kind,'groups')]+=1
                        R['dsgroups'][(label,c,kind,'docs')]+=len(v)
            if col=='entries':
                for x in docs:
                    c=CLS[col](x)
                    d=x.get('date'); st=x.get('sysTime')
                    if st is None: b='no sysTime'
                    elif not isinstance(d,(int,float)): b='date not numeric'
                    else:
                        m=iso_ms(st)
                        if m is None: b='sysTime unparseable'
                        else:
                            diff=abs(d-m)
                            b=('same instant (exact ms)' if diff==0 else 'differ <1 s' if diff<1000 else 'differ 1-60 s' if diff<60000 else 'differ >=60 s')
                    R['entdiff'][(c,b)]+=1
            del docs
    return R

def load_file(path,col):
    return json.load(open(base+path+'/'+col+'.json'))

def dump(R,out):
    for name in ['docs','nulldocs','deepdocs']:
        out.write(f'## {name}\n')
        for k,v in sorted(R[name].items()): out.write(f'{v}\t{k[0]}\t{k[1]}\n')
    out.write('## nulls (collection, client, field path)\n')
    for k,v in sorted(R['nulls'].items()): out.write(f'{v}\t'+'\t'.join(k)+'\n')
    out.write('## devicestatus (created_at,device) groups with >1 doc\n')
    for k,v in sorted(R['dsgroups'].items()): out.write(f'{v}\t'+'\t'.join(k)+'\n')
    out.write('## entries date vs sysTime\n')
    for k,v in sorted(R['entdiff'].items()): out.write(f'{v}\t'+'\t'.join(k)+'\n')

if __name__=='__main__':
    if not CONTROL:
        R=run(load_file); dump(R,sys.stdout)
    else:
        # Plant: in site a, one Loop treatment gets notes=None and a nested pump.x=None (devicestatus);
        # one devicestatus duplicated with a changed body and one with an identical body;
        # one entry gets sysTime shifted +5 min.
        def load_planted(path,col):
            d=load_file(path,col)
            if path.endswith('/a/raw'):
                if col=='treatments':
                    t=copy.deepcopy(d[0]); t['plantedNull']=None; d.append(t)
                if col=='devicestatus':
                    t=copy.deepcopy(d[0]); t['pump']=dict(t.get('pump') or {}); t['pump']['plantedNested']=None; t['_id']='x1'; d.append(t)
                    t2=copy.deepcopy(d[1]); t2['_id']='x2'; d.append(t2)  # identical retry
                    t3=copy.deepcopy(d[2]); t3['_id']='x3'; t3['loop']=dict(t3.get('loop') or {}); t3['loop']['plantedDistinct']=1; d.append(t3)
                if col=='entries':
                    t=copy.deepcopy(d[0]); t['_id']='e1'; t['sysTime']=datetime.utcfromtimestamp((t['date']+300000)/1000).isoformat()+'Z'; d.append(t)
            return d
        R0=run(load_file); R1=run(load_planted)
        for name in R0:
            for k in set(R0[name])|set(R1[name]):
                if R0[name][k]!=R1[name][k]: print('CONTROL DELTA',name,k,R0[name][k],'->',R1[name][k])
