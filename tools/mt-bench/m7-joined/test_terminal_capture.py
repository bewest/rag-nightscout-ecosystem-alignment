import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import adapter as a

class Terminal(unittest.TestCase):
    def row(self):
        return dict(Id='a'*64,Image='sha256:'+'b'*64,RestartCount=3,
            Config=dict(Labels={a.OWNER:'1'*32,'com.docker.compose.project':'owned','com.docker.compose.service':'evaluator'},Env=['DO_NOT_RETAIN=secret']),
            State=dict(Status='exited',Running=False,Pid=0,ExitCode=7,OOMKilled=True,StartedAt='2026-11-18T00:00:00Z',FinishedAt='2026-11-18T00:00:05Z'),HostConfig=dict(Memory=1024**3,NanoCpus=1000000000))
    def test_terminal_state_survives_without_cgroup_and_wrong_source_refuses(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp);m=dict(project='owned',owner='1'*32);row=self.row()
            a.write(d/'frozen.compose.json',{'services':{'evaluator':{'image':row['Image']}}})
            with patch.object(a,'assert_owned'),patch.object(a,'resources',return_value=[row]),patch.object(a,'command',return_value=json.dumps(row)):
                v=a.terminal_snapshot(d,m)
                self.assertEqual(v['containers'][0]['state']['ExitCode'],7)
                self.assertTrue(v['containers'][0]['state']['OOMKilled'])
                self.assertEqual(v['containers'][0]['restartCount'],3)
                self.assertEqual(v['containers'][0]['cgroup']['status'],'UNMEASURED')
                self.assertNotIn('DO_NOT_RETAIN',(d/'terminal-before-cleanup.json').read_text())
                bad=copy.deepcopy(row);bad['Image']='sha256:'+'c'*64
                with patch.object(a,'resources',return_value=[bad]):
                    with self.assertRaisesRegex(RuntimeError,'TERMINAL_IMAGE_CHANGED'):a.terminal_snapshot(d,m,'wrong-image.json')
                self.assertEqual(a.terminal_snapshot(d,m,'restored.json')['containers'][0]['state']['ExitCode'],7)
                print('RED_RESTORED M7_TERMINAL_IMAGE_CHANGED; exited/OOM/restart retained')
    def test_missing_owner_never_reads_private_cgroup(self):
        with TemporaryDirectory() as tmp:
            with patch.object(a,'assert_owned',side_effect=RuntimeError('M7_RESOURCE_NOT_OWNED')),patch.object(a,'resources') as read:
                with self.assertRaisesRegex(RuntimeError,'RESOURCE_NOT_OWNED'):a.terminal_snapshot(Path(tmp),{})
                read.assert_not_called()
                print('RED_RESTORED M7_RESOURCE_NOT_OWNED before resource reads')

if __name__=='__main__':unittest.main()
