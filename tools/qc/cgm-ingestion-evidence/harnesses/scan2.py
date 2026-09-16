import re,os
W='trees'
def strip(s):
    out=[];i=0;n=len(s)
    st=None
    while i<n:
        c=s[i]
        if st is None:
            if c=='/' and i+1<n and s[i+1]=='/':
                j=s.find('\n',i); j=n if j<0 else j
                out.append(' '*(j-i)); i=j; continue
            if c=='/' and i+1<n and s[i+1]=='*':
                j=s.find('*/',i+2); j=n if j<0 else j+2
                out.append(re.sub(r'[^\n]',' ',s[i:j])); i=j; continue
            if c in '"\'`': st=c; out.append(c); i+=1; continue
            out.append(c); i+=1
        else:
            if c=='\\': out.append(s[i:i+2]); i+=2; continue
            if c==st: st=None
            out.append(c); i+=1
    return ''.join(out)
pat=re.compile(r'console\.(log|error|warn|debug|info)\s*\(')
def args_of(s,i):
    d=0
    for j in range(i,len(s)):
        if s[j]=='(':d+=1
        elif s[j]==')':
            d-=1
            if d==0:return s[i+1:j]
    return s[i:i+200]
def dynamic(a):
    r=re.sub(r'"(\\.|[^"\\])*"','',a); r=re.sub(r"'(\\.|[^'\\])*'",'',r); r=re.sub(r'`(\\.|[^`\\])*`','',r)
    return bool(re.sub(r'[\s,+]','',r))
res={}
for tree in sorted(os.listdir(W)):
    tot=0;sites=[]
    for root,ds,fs in os.walk(os.path.join(W,tree)):
        ds[:]=[d for d in ds if d not in ('node_modules','test','tests')]
        for f in sorted(fs):
            if not f.endswith('.js'): continue
            p=os.path.join(root,f); rel=os.path.relpath(p,os.path.join(W,tree))
            if not (rel.startswith('lib/') or rel=='index.js'): continue
            raw=open(p,encoding='utf8',errors='replace').read()
            s=strip(raw)
            for m in pat.finditer(s):
                tot+=1
                a=args_of(s,m.end()-1)
                if dynamic(a):
                    ln=s[:m.start()].count('\n')+1
                    sites.append((rel,ln,' '.join(args_of(raw,raw.find('(',m.start())).split())[:100]))
    res[tree]=(tot,sites)
print('tree                 live_console  live_with_dynamic_arg')
for t,(tot,sites) in res.items(): print(f'{t:<20} {tot:>12} {len(sites):>22}')
print()
for t,(tot,sites) in res.items():
    print(f'######## {t}: {len(sites)} LIVE dynamic sites ########')
    for rel,ln,a in sites: print(f'  {rel}:{ln}  {a}')
    print()
