import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import kube_adapter as k
import primer
import primer_storage as storage


class PrimerStorage(unittest.TestCase):
    def test_large_raw_config_fails_and_same_gzip_bytes_restore(self):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            contract = root/'contract.json'
            source = root/'primer'
            source.mkdir()
            raw = b'{"synthetic":"'+b'x'*storage.SECRET_LIMIT+b'"}\n'
            config = source/'config.json'
            config.write_bytes(raw)
            (source/'expected-verification.json').write_text('{}\n')
            selected = {'stateMiB':32, 'secretCodec':'raw-v1'}
            contract.write_text(json.dumps({storage.FIELD:selected}))
            with self.assertRaisesRegex(ValueError,'SECRET_TOO_LARGE'):
                storage.publish(contract,source)
            self.assertEqual(config.read_bytes(),raw)
            selected['secretCodec']='gzip-v1'
            contract.write_text(json.dumps({storage.FIELD:selected}))
            receipt = storage.publish(contract,source)
            self.assertLess(receipt['secretBytes'],storage.SECRET_LIMIT)
            self.assertFalse(config.exists())
            script = Path(storage.__file__).with_name('primer_config_unpack.cjs').read_text()
            script += '\nrestorePrimerConfig(process.argv[1],process.argv[2],33554432);'
            output = root/'restored'
            output.mkdir()
            command = ['node','-e',script,str(source),str(output)]
            subprocess.run(command,check=True,capture_output=True)
            restored = output/'config.json'
            self.assertEqual(restored.read_bytes(),raw)
            self.assertEqual(restored.stat().st_mode & 0o777,0o400)
            restored.unlink()
            meta = source/'config.digest.json'
            value = json.loads(meta.read_bytes())
            value['sha256']='0'*64
            meta.write_text(json.dumps(value))
            refusal=subprocess.run(command,capture_output=True)
            self.assertIn(b'K8S_PRIMER_STORAGE_CONFIG_CHANGED',refusal.stderr)
            self.assertFalse(restored.exists())

    def test_render_binds_primer_mount_and_memory_budget(self):
        def actor(name):
            return {'name':name,'volumeMounts':[{'name':'config-primer','mountPath':'/run/ns-primer','subPath':'d'}],
                    'resources':{'requests':{'memory':'224Mi'}}}
        pod={'volumes':[{'name':'config-primer','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}}],
             'initContainers':[actor('primer')],'containers':[actor('done')]}
        job={'kind':'Job','metadata':{'name':'primer'},'spec':{'template':{'spec':pod}}}
        selected={storage.FIELD:{'stateMiB':32,'secretCodec':'raw-v1'}}
        storage.check_render(selected,[job])
        pod['volumes'][0]['emptyDir']['sizeLimit']='1Mi'
        with self.assertRaisesRegex(ValueError,'RENDER_CHANGED'):storage.check_render(selected,[job])
        pod['volumes'][0]['emptyDir']['sizeLimit']='32768Ki'
        storage.check_render(selected,[job])
        pod['containers'][0]['resources']['requests']['memory']='16Mi'
        with self.assertRaisesRegex(ValueError,'EXCEEDS_ACTOR_MEMORY_REQUEST'):storage.check_render(selected,[job])

    def test_mounted_readback_requires_expected_bytes_and_volume(self):
        receipt = {'configBytes':1499235, 'configSha256':'a'*64}
        selected = {storage.FIELD:{'stateMiB':32}, 'primerStorageReceipt':receipt}
        readback = dict(receipt,type=0x01021994,bytes=32*storage.MIB)
        client = SimpleNamespace(call=lambda args, read: json.dumps(readback))
        self.assertEqual(primer.storage_readback(selected,client,'prime-pod'),readback)
        readback['bytes'] = storage.MIB
        with self.assertRaisesRegex(k.Refused,'PRIMER_STORAGE_READBACK_CHANGED'):
            primer.storage_readback(selected,client,'prime-pod')
        readback['bytes'] = 32*storage.MIB
        readback['configSha256'] = '0'*64
        with self.assertRaisesRegex(k.Refused,'PRIMER_STORAGE_READBACK_CHANGED'):
            primer.storage_readback(selected,client,'prime-pod')
        readback['configSha256'] = receipt['configSha256']
        self.assertEqual(primer.storage_readback(selected,client,'prime-pod'),readback)
