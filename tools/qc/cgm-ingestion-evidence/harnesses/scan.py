import os,re,sys,json

def strip(src):
    # returns source with comments blanked (keep newlines) and string literals replaced by ""
    out=[]; i=0; n=len(src)
    state=None; quote=None
    while i<n:
        c=src[i]
        if state is None:
            if c=='/' and i+1<n and src[i+1]=='/':
                while i<n and src[i]!='\n': i+=1
                continue
            if c=='/' and i+1<n and src[i+1]=='*':
                i+=2
                while i+1<n and not (src[i]=='*' and src[i+1]=='/'): 
                    if src[i]=='\n': out.append('\n')
                    i+=1
                i+=2
                continue
            if c in '"\'`':
                quote=c; i+=1
                out.append('""' if c!='`' else '``')
                while i<n:
                    if src[i]=='\\': i+=2; continue
                    if src[i]==quote: i+=1; break
                    if src[i]=='\n': out.append('\n')
                    i+=1
                continue
            out.append(c); i+=1
        else:
            i+=1
    return ''.join(out)

CALL=re.compile(r'console\s*\.\s*(log|error|warn|debug|info|trace)\s*\(')
def sites(path):
    src=open(path,encoding='utf8',errors='replace').read()
    s=strip(src)
    res=[]
    for m in CALL.finditer(s):
        j=m.end(); depth=1
        while j<len(s) and depth>0:
            if s[j]=='(': depth+=1
            elif s[j]==')': depth-=1
            j+=1
        args=s[m.end():j-1]
        # dynamic = anything left after removing "" literals, `` , whitespace, commas, +
        r=args.replace('""','').replace('``','')
        r=re.sub(r'[\s,+]','',r)
        res.append((s[:m.start()].count('\n')+1, m.group(1), bool(r), args.strip()[:120]))
    return res

root=sys.argv[1]
tot=0; dyn=0; per={}
for dirpath,dirnames,files in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in ('node_modules','test','tests')]
    for f in files:
        if not f.endswith('.js'): continue
        p=os.path.join(dirpath,f)
        rel=os.path.relpath(p,root)
        if not (rel.startswith('lib'+os.sep) or rel=='index.js'): continue
        ss=sites(p)
        if ss:
            per[rel]=(len(ss),sum(1 for x in ss if x[2]))
        tot+=len(ss); dyn+=sum(1 for x in ss if x[2])
print(json.dumps({'total':tot,'dynamic':dyn,'per':per},indent=1,sort_keys=True))
