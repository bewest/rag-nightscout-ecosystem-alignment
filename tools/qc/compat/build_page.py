# build_page.py: the page datasets of the 16.0.0 write-compatibility page, from the comparison's
# outputs (tools/qc/compat/build.py --all) and the group metadata.
#
#   python3 tools/qc/compat/build_page.py --data DIR --groups GROUPS.yaml --out DIR
#
# --data holds summary.json, diff-cells.json and clients.json. Writes headline.json, groups.json,
# heat.json, families.json, triage.json, clients.json and cells.json (minified) into --out.
import argparse, json, collections, os, sys
import yaml

ap = argparse.ArgumentParser()
ap.add_argument('--data', required=True)
ap.add_argument('--groups', required=True)
ap.add_argument('--out', required=True)
A = ap.parse_args()
S = lambda f: os.path.join(A.data, f)
s=json.load(open(S('summary.json'))); d=json.load(open(S('diff-cells.json'))); cl=json.load(open(S('clients.json')))
GM = yaml.safe_load(open(A.groups))['groups']
_need = sorted({r['group'] for r in d} - {g for g, m in GM.items() if m.get('name')})
if _need: sys.exit('build_page: groups with cells but no name/meaning/verdict in %s: %s' % (A.groups, ', '.join(_need)))
META = {g: (m['name'], m.get('meaning', ''), m.get('consequence', ''), m['verdict'], m.get('basis', '')) for g, m in GM.items() if m.get('name')}
SEVERITY = {g: m['severity'] for g, m in GM.items() if 'severity' in m}
def origin(r):
    a,b=r['in_v1509_to_dev'],r['in_dev_to_8879']
    return 'both' if a and b else ('dev' if a else '8879')
def guard(g):
    if g.startswith('decided-not-built'): return 'Setting decided, not built'
    if g.startswith('WRITE_'): return g
    if g == 'fixed on current dev': return 'Fixed on current dev'
    if 'strict' in g: return 'Revert only (strict refuses)'
    return 'Revert only'
def fam(form):
    for p in ('idfmt','idf','batch','tt'):
        if form.startswith(p+'-') or form==p: return {'idfmt':'Identifier format','idf':'Identifier matching','batch':'Batches','tt':'Temporary Target'}[p]
    return 'Earlier forms'
EFF_RANK={'new-record':1,'stays-deleted':2,'field-dropped':3,'refused':4,'field-kept':5,'duplicate-avoided':6,'other':7,'reply-only':8,'no-visible-change':9}
EFF_LABEL={'new-record':'New record stored','stays-deleted':'Stays deleted','field-dropped':'Value not stored','refused':'Refused','field-kept':'Field kept','duplicate-avoided':'Duplicate avoided','other':'Other','reply-only':'Reply only','no-visible-change':'No visible change'}
by=collections.defaultdict(list)
for r in d: by[r['group']].append(r)
groups=[]
for g,rows in by.items():
    m=META[g]
    effs=collections.Counter(r['data_effect'] for r in rows)
    combos={(r['collection'],r['re_send_path'] if r.get('re_send_path') else r['resend_path']) for r in rows}
    cg=[c for c in cl if c['group']==g]
    groups.append({'group':g,'name':m[0],'meaning':m[1],'consequence':m[2],'verdict':m[3],'basis':m[4],
      'cells':len(rows),'on_dev':sum(1 for r in rows if origin(r)=='dev'),'by_8879':sum(1 for r in rows if origin(r)=='8879'),'both':sum(1 for r in rows if origin(r)=='both'),
      'combos':len(combos),'collections':len({r['collection'] for r in rows}),
      'worst_effect':EFF_LABEL[min(effs,key=lambda e:EFF_RANK[e])],
      'guard':collections.Counter(guard(r['guard']) for r in rows).most_common(1)[0][0],
      'clients':len({c['client'] for c in cg}),
      'clients_read':len({c['client'] for c in cg if c['tier'].startswith('read')}),
      'clients_measured':len({c['client'] for c in cg if c['tier'].startswith('measured')})})
order={'Defect':0,'Decided':1,'Bug fix':2,'No value change':3}
groups.sort(key=lambda x:(order[x['verdict']],-x['cells']))
# heat: group x collection x resend path
heat=collections.Counter((r['group'],r['collection'],r['resend_path']) for r in d)
heat=[{'group':g,'name':META[g][0],'collection':c,'path':p,'cells':n} for (g,c,p),n in sorted(heat.items())]
# families
famc=collections.Counter((fam(r['form']),origin(r)) for r in d)
fams=[{'family':f,'origin':o,'cells':n} for (f,o),n in famc.items()]
# cells drill-down (trimmed)
def brief(x,k): return (x or {}).get(k,'')
origin_labels=s.get('origin_labels',{'8879':'#8879 only','dev':'already on dev','both':'dev, then #8879'})
cells=[{'cell':r['cell'],'group':r['group'],'collection':r['collection'],'seed':r['seed_path'],'resend':r['resend_path'],'form':r['form'],'family':fam(r['form']),
  'origin':origin_labels[origin(r)],'effect':EFF_LABEL[r['data_effect']],
  'store_before':brief(r['before'],'store'),'store_after':brief(r['after'],'store'),'reply_before':brief(r['before'],'st'),'reply_after':brief(r['after'],'st'),
  'cause':r['cause'][:140],'guard':guard(r['guard'])} for r in d]
# triage: group x collection x path with clients
tri=collections.defaultdict(lambda:{'cells':0,'effects':collections.Counter()})
for r in d:
    k=(r['group'],r['collection'],r['resend_path']); tri[k]['cells']+=1; tri[k]['effects'][r['data_effect']]+=1
cidx=collections.defaultdict(list)
for c in cl: cidx[(c['group'],c['collection'],c['path'])].append(c)
TIER={'measured':0,'read':1,'assumed':2}
triage=[]
for (g,c,p),v in tri.items():
    w=min(v['effects'],key=lambda e:EFF_RANK[e]); cs=cidx.get((g,c,p),[])
    names=sorted({x['client'].split(' (')[0] for x in cs})
    tiers=sorted({x['tier'].split(' ')[0].split(',')[0] for x in cs},key=lambda t:TIER.get(t,3))
    sev=10-EFF_RANK[w]
    if META[g][3]=='Bug fix' or w=='duplicate-avoided': sev=min(sev,3)
    if g in SEVERITY: sev=SEVERITY[g]
    triage.append({'key':f'{g}|{c}|{p}','group':g,'name':META[g][0],'verdict':META[g][3],'collection':c,'path':p,'cells':v['cells'],'effect':EFF_LABEL[w],
      'severity':sev,'clients':', '.join(names) or 'none found','n_clients':len(names),'evidence':tiers[0] if tiers else 'no client','score':round(sev*(len(names) if names else 0.5),1)})
triage.sort(key=lambda x:(-x['score'],-x['cells']))
clientsm=[{'client':x['client'].split(' (')[0],'group':x['group'],'name':META[x['group']][0],'collection':x['collection'],'path':x['path'],'tier':x['tier'].split(' ')[0].split(',')[0],'source':x.get('source','')[:160],'consequence':(x.get('consequence') or '')[:200]} for x in cl]
t=s['totals']; sp=s['split']
headline=[{'metric':'cells','value':t['cells_per_tree']},{'metric':'differ','value':len(d)},{'metric':'on_dev','value':sp['v1509_to_dev_only']},{'metric':'by_8879','value':sp['dev_to_8879_only']},{'metric':'both','value':sp['both']},{'metric':'unexplained','value':len(s['unexplained'])},{'metric':'defect_cells','value':len(by['n'])},{'metric':'format_cells','value':len(by['f'])},{'metric':'origin_labels','value':s.get('origin_labels',{'8879':'#8879 only','dev':'already on dev','both':'dev, then #8879'})}]
out={'groups':groups,'heat':heat,'families':fams,'cells':cells,'triage':triage,'clients':clientsm,'headline':headline}
for k,v in out.items():
    json.dump(v,open(os.path.join(A.out,k+'.json'),'w'),separators=(',',':'))
    print(k,len(v),len(json.dumps(v,separators=(',',':'))))
