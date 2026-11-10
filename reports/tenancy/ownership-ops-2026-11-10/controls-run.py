import subprocess, sys, json, os
W='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-single-provision-20261110'
OUT=os.path.dirname(os.path.abspath(__file__))
M=[
 ('C1-email-key-without-issuer','lib/human-session/mongo.js',
  "const emailPrincipalId = (tenant, issuer, email) => hash([tenant, issuer, 'verified-email', email]);",
  "const emailPrincipalId = (tenant, issuer, email) => hash([tenant, 'verified-email', email]);",
  'same verified email from a second issuer'),
 ('C2-email-without-verified-check','lib/human-session/mongo.js',
  "const email = identity.emailVerified === true ? normalEmail(identity.email) : null;",
  "const email = normalEmail(identity.email);",
  'unverified email at the listed issuer'),
 ('C3-permission-snapshot-reintroduced','lib/human-session/mongo.js',
  "const groups = await roles.forSubject(bound.subject);",
  "const groups = Array.isArray(bound.permissionGroups) ? bound.permissionGroups : await roles.forSubject(bound.subject);",
  'next request'),
 ('C4-unlisted-gets-a-binding','lib/human-session/mongo.js',
  "principal.id === emailPrincipalId(tenant, identity.issuer, email)) || null;",
  "principal.id === emailPrincipalId(tenant, identity.issuer, email)) || principals[0] || null;",
  'fallback readable'),
 ('C5-config-exclusivity-removed','lib/human-session/private-setting.js',
  "  if (present(inline) && present(file)) refuse('Set ' + name + ' or ' + name + '_FILE, not both');\n",
  "",
  'together refuse at load'),
 ('C6-fallback-session-share-removed','lib/human-session/mongo.js',
  "while (next.sessions.filter(existing => existing.fallback === true).length >= MAX_FALLBACK_SESSIONS) {",
  "while (false && next.sessions.filter(existing => existing.fallback === true).length >= MAX_FALLBACK_SESSIONS) {",
  'bounded share of sessions'),
]
# C3 also needs provision to write the copy, as the pre-lane store kept one.
EXTRA={'C3-permission-snapshot-reintroduced':('lib/human-session/provision.js',
  "purposes: item.management ? ['data', 'management'] : ['data'], source: 'list' };",
  "purposes: item.management ? ['data', 'management'] : ['data'], source: 'list',\n        permissionGroups: item.roles.map(role => authorization.roles.find(value => value.name === role).permissions.slice()) };")}
def mocha(grep):
  cmd=['node','bin/with-env.js','./my.test.env','node_modules/mocha/bin/mocha.js','--timeout','5000','--require','./tests/hooks.js','--exit','tests/human-session-provision.test.js']
  if grep: cmd+=['--grep',grep]
  r=subprocess.run(cmd,cwd=W,capture_output=True,text=True)
  lines=[l for l in r.stdout.splitlines() if 'passing' in l or 'failing' in l]
  fails=[]
  out=r.stdout.splitlines()
  for i,l in enumerate(out):
    if l.strip().startswith(('AssertionError','Error:','AssertionError [ERR_ASSERTION]')): fails.append(l.strip()[:220])
  return r.returncode,' '.join(x.strip() for x in lines),fails,r.stdout
res=[]
which=sys.argv[1:] or [m[0] for m in M]
for name,f,old,new,grep in M:
  if name not in which: continue
  edits=[(f,old,new)]+([EXTRA[name]] if name in EXTRA else [])
  for ef,eo,en in edits:
    p=os.path.join(W,ef); s=open(p).read(); assert s.count(eo)==1,(name,ef); open(p,'w').write(s.replace(eo,en))
  code,summary,fails,stdout=mocha(grep)
  open(os.path.join(OUT,name+'.red.log'),'w').write(stdout)
  subprocess.run(['git','checkout','--']+sorted(set(e[0] for e in edits)),cwd=W,check=True)
  dirty=subprocess.run(['git','status','--porcelain','lib'],cwd=W,capture_output=True,text=True).stdout.strip()
  code2,summary2,_,stdout2=mocha(grep)
  open(os.path.join(OUT,name+'.green.log'),'w').write(stdout2)
  res.append({'control':name,'grep':grep,'mutant':{'exit':code,'summary':summary,'symptom':fails[:2]},'restored':{'exit':code2,'summary':summary2},'tree_clean_after_restore':dirty==''})
print(json.dumps(res,indent=1))
json.dump(res,open(os.path.join(OUT,'controls.json'),'w'),indent=1)
