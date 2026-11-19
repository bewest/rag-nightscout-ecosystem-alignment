"""Local pipe framing diagnosis: fragmentation is valid; EOF/bounds stay fail-closed."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import io,json,os,threading,time,unittest
from unittest.mock import patch
import protocol
from test_contract import selected

class ChannelFraming(unittest.TestCase):
 def channel(self):
  b=selected();b['expiresAt']=time.time()+10000
  reader,writer=os.pipe();stream=os.fdopen(reader,'rb',buffering=0);self.addCleanup(stream.close)
  return protocol.Channel(b,'app-0',incoming=stream,outgoing=io.StringIO()),writer,b
 def frame(self,b,sequence=1):return json.dumps({'version':1,'runId':b['runId'],'nonce':b['nonce'],'cell':b['cell'],'node':'controller','sequence':sequence,'kind':'load-start','payload':{'synthetic':'split-\u00e9'}}).encode()+b'\n'
 def test_fragmented_read_and_coalesced_successor_preserve_exact_messages(self):
  channel,writer,b=self.channel();first=self.frame(b);second=self.frame(b,2)
  def send():
   try:
    for part in (first[:1],first[1:5],first[5:-1],first[-1:]+second):os.write(writer,part);time.sleep(.002)
   finally:os.close(writer)
  thread=threading.Thread(target=send);thread.start()
  try:self.assertEqual(channel.receive('load-start',2),{'synthetic':'split-\u00e9'});self.assertEqual(channel.receive('load-start',2),{'synthetic':'split-\u00e9'})
  finally:thread.join(2);self.assertFalse(thread.is_alive())
 def test_closed_controller_pipe_reproduces_exact_eof_code(self):
  channel,writer,b=self.channel();os.close(writer)
  with self.assertRaisesRegex(RuntimeError,'EXTERNAL_HANDSHAKE_LOST_OR_OVERSIZE'):channel.receive('load-start',1)
 def test_incomplete_oversized_line_is_a_bound_refusal(self):
  channel,writer,b=self.channel()
  def send():
   try:
    try:os.write(writer,b'x'*protocol.MAX_MESSAGE)
    except BrokenPipeError:pass
   finally:os.close(writer)
  thread=threading.Thread(target=send);thread.start()
  try:
   with self.assertRaisesRegex(RuntimeError,'EXTERNAL_MESSAGE_BOUND'):channel.receive('load-start',2)
  finally:thread.join(2);self.assertFalse(thread.is_alive())
if __name__=='__main__':unittest.main()
