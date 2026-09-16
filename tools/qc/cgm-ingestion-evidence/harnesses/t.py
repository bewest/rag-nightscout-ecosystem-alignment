p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read()
old = """against `externals/nightscout-connect` at cut 4's pinned commit `c962a13f`, and against the two retired
legacy packages `externals/share2nightscout-bridge` and
`externals/minimed-connect-to-nightscout`. Every number below says how it was measured. Claims
marked *(inference)* were reasoned from code I read but did not execute."""
print(repr(old[:60]))
print('count', s.count(old))
