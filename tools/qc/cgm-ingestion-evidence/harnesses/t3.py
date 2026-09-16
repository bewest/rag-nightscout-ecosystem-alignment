p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read()
old = """against `externals/nightscout-connect` at cut 4's pinned commit `c962a13f`, and against the two retired
legacy packages `externals/share2nightscout-bridge` and
`externals/minimed-connect-to-nightscout`. Every number below says how it was measured. Claims
marked *(inference)* were reasoned from code I read but did not execute."""
for n in range(20, len(old)+1, 20):
    if s.count(old[:n])==0:
        print('breaks at', n, repr(old[max(0,n-40):n]))
        break
else:
    print('all prefixes found; full count', s.count(old))
