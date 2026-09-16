import sys
sys.path.insert(0,'/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad')
def key_shipped(d):
    k={}; sel=False
    for f in ['insulin','carbs','percent','absolute','duration']:
        v=d.get(f)
        if v: k[f]=v; sel=True
    if d.get('NSCLIENT_ID'): k['NSCLIENT_ID']=d['NSCLIENT_ID']; sel=True
    if not sel: k['eventType']=d.get('eventType')
    return tuple(sorted(k.items()))
def key_presence(d):
    k={}; sel=False
    for f in ['insulin','carbs','percent','absolute','duration']:
        if f in d and d[f] is not None: k[f]=d[f]; sel=True
    if d.get('NSCLIENT_ID'): k['NSCLIENT_ID']=d['NSCLIENT_ID']; sel=True
    if not sel: k['eventType']=d.get('eventType')
    return tuple(sorted(k.items()))

cases = [
 ("zero-temp vs untyped temp, same duration",
   {'eventType':'Temp Basal','absolute':0,'duration':30},
   {'eventType':'Temp Basal','duration':30}),
 ("zero bolus vs carb-only entry",
   {'eventType':'Bolus','insulin':0,'carbs':12},
   {'eventType':'Bolus','carbs':12}),
 ("two identical zero temps (control, must agree)",
   {'eventType':'Temp Basal','absolute':0,'duration':30},
   {'eventType':'Temp Basal','absolute':0,'duration':30}),
 ("distinct absolutes (control, must agree = no match)",
   {'eventType':'Temp Basal','absolute':0,'duration':30},
   {'eventType':'Temp Basal','absolute':1.5,'duration':30}),
]
print(f"{'case':46s} {'shipped':>9s} {'presence':>9s}  {'verdict'}")
for name,a,b in cases:
    s = key_shipped(a)==key_shipped(b)
    p = key_presence(a)==key_presence(b)
    v = "DIVERGES" if s!=p else "agree"
    print(f"{name:46s} {str(s):>9s} {str(p):>9s}  {v}")
