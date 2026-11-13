"""Explicit in-memory model only; never contacts Docker, SQL, HTTP or an app."""
import json,time
from pathlib import Path
class RecordingHost:
    def __init__(self,plan,output):
        self.p=plan;self.out=Path(output);self.out.mkdir(mode=0o700);self.events=[];self.n=0;self.bytes=0;self.uncertain=False;self.allocation_attempted=False;self.images={};self.rows={};self.deadline=time.monotonic()+900
    def command(self,args,**kw):
        self.events.append(['command',args]);self.n+=1
        if args==['docker','context','show']:return 'default\n'
        if args[:3]==['docker','network','ls']:return ''
        if args[:3]==['ip','-j','-4']:return '[{"dst":"127.0.0.0/8"},{"dst":"default"}]'
        if args[:3]==['docker','ps','-a']:return ''
        if args[:2]==['ss','-H']:return ''
        if args[:3]==['docker','image','inspect']:
            ref=args[3];image=ref if ref.startswith('sha256:')else 'sha256:'+'b'*64;return json.dumps([{'Id':image,'Os':'linux','Architecture':'amd64'}])
        raise RuntimeError('RECORDING_UNPLANNED_COMMAND')
    def compose(self,*args,**kw):
        self.events.append(['compose',list(args)])
        if args[:1]==('up',):assert args[-2:]==('postgres','vault')
        return ''
    def healthy(self,slot):self.events.append(['healthy',slot])
    def controller(self,operation,slot=None):
        self.events.append(['controller',operation,slot]);self.n+=1
        if operation=='start':assert self.rows.get(slot)!='ISSUED';self.rows[slot]='ISSUED'
        if operation=='stop':assert self.rows[slot]=='ISSUED';self.rows[slot]='RETIRED'
        return {'kind':'RECORDING_ONLY'}
    def capture(self,label):self.events.append(['capture',label])
    def ack(self,slot):assert self.rows[slot]=='RETIRED';self.events.append(['ack',slot])
    def explicit_health(self,slot):assert self.rows[slot]=='ISSUED';self.events.append(['health-existing-claim',slot])
    def cleanup_owned(self):
        self.events.append(['cleanup','allocation-attempted'if self.allocation_attempted else'NO_ALLOCATION_NO_EFFECTS']);assert all(x=='RETIRED'for x in self.rows.values());(self.out/'recording-events.private.json').write_text(json.dumps({'kind':'MODEL_ONLY_NO_NATIVE_EVIDENCE','events':self.events},indent=2)+'\n')
