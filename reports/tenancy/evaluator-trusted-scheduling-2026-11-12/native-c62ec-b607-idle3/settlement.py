from pathlib import Path
import json,time
h=Path(__file__).parent;p=h/'startup-settlement.json';assert not p.exists();start=time.monotonic();row={'kind':'explicit-host-functional-startup-settlement','requestedSeconds':12,'startedAtMs':time.time_ns()//1000000,'notProductFix':True};time.sleep(12);row.update(endedAtMs=time.time_ns()//1000000,elapsedSeconds=time.monotonic()-start);p.write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row))
