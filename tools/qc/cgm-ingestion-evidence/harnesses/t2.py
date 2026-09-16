p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read()
i=s.index('externals/nightscout-connect` at')
print(repr(s[i-10:i+330]))
