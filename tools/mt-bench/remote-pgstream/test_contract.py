import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import protocol
import transport as t
import traffic_probe
import producer

HERE=Path(__file__).resolve().parent

def selected():
    return dict(version=1, profile=protocol.PROFILE, runId='remote-test', cloudId='remote-test-'+'a'*12,
                nonce='b'*32, cell=1, tenants=1000, appAddress='10.8.0.2', generatorAddress='10.8.0.3',
                port=18080, expiresAt=11800, pair=dict(core=t.CORE,deploy=t.DEPLOY), imageId=t.APP,
                k6Image='grafana/k6@sha256:'+'f'*64, sourceSha256='1'*64,
                transport=dict(interface='ens7',mac='02:00:00:00:00:01',approvedAddress='10.8.0.2',approvalReference='human-approved-fixture'))

def nics():
    return [dict(ifname='ens7',address='02:00:00:00:00:01',flags=['UP'],addr_info=[dict(family='inet',local='10.8.0.2',scope='global')])]

def config():
    return dict(services=dict(nginx=dict(ports=[dict(host_ip='127.0.0.1',published='18080',target=8080,protocol='tcp')]),api=dict(command=['node','api'])))

class Contract(unittest.TestCase):
    def test_small_binding_keeps_finite_tenant_selection(self):
        b = selected(); b['tenants'] = 10
        self.assertEqual(protocol.binding(b, 1000)['tenants'], 10)
        for tenants in (True, 11, 0, 1001):
            with self.assertRaisesRegex(RuntimeError, 'EXTERNAL_CELL'):
                protocol.binding({**b, 'tenants': tenants}, 1000)
        self.assertEqual(protocol.binding(b, 1000)['tenants'], 10)

    def test_binding_and_negative_controls(self):
        b=selected();self.assertEqual(protocol.binding(b,1000),b)
        for key,value in [('tenants',999),('cell',2),('imageId','sha256:'+'a'*64),('profile','joined-external-generator-v1'),('appAddress','8.8.8.8'),('appAddress','0.0.0.0'),('appAddress','10.8.0.4')]:
            with self.subTest(key=key,value=value), self.assertRaises(RuntimeError):protocol.binding({**b,key:value},1000)
        for key in ('core','deploy'):
            bad=copy.deepcopy(b);bad['pair'][key]='a'*40
            with self.assertRaisesRegex(RuntimeError,'QUALIFIED_SOURCE'):protocol.binding(bad,1000)

    def test_actual_serializer_order_and_strict_unsafe_variants(self):
        b=selected();chain,rules=t.firewall_rules(b)
        # iptables-save 1.8.10 canonicalizes source before input interface.
        canonical=rules.copy();canonical[1]='-A '+chain+' -s '+b['generatorAddress']+'/32 -i '+b['transport']['interface']+' -j ACCEPT'
        saved='\n'.join(canonical)
        self.assertEqual(t.firewall_check(b,saved)['rules'],rules)
        bads=[saved.replace(b['generatorAddress']+'/32','10.8.0.9/32'),saved.replace('-i ens7','-i foreign0'),saved.replace('--dport 18080','--dport 18081'),saved+'\n-A '+chain+' -j ACCEPT',saved.replace('-i ens7','-i ens7 -i ens7'),saved.replace('-i ens7','-i ens7 --unknown x'),saved.replace('-i ens7','! -i ens7'),saved.replace(canonical[2],''),'\n'.join([canonical[0],canonical[2],canonical[1]]),canonical[0]+'\n'+saved,'-A PREROUTING -j FOREIGN\n'+saved,saved+'\n-A OUTPUT -j '+chain+' -p tcp',saved.replace('-j ACCEPT','-j DROP'),saved.replace('-i ens7','-i "unterminated')]
        for bad in bads:
            with self.subTest(saved=bad),self.assertRaisesRegex(RuntimeError,'REMOTE_GENERATOR_ONLY_FIREWALL_REQUIRED'):
                t.firewall_check(b,bad)
        self.assertEqual(t.firewall_check(b,saved)['rules'],rules)

    def test_additive_overlay_and_actual_nic(self):
        b=selected(); saved='\n'.join(t.firewall_rules(b)[1]); fw=t.firewall_check(b,saved)
        rules=t.firewall_rules(b)[1]
        self.assertNotIn(' -i ',rules[0])
        self.assertIn(' -i ens7 -s 10.8.0.3/32 -j ACCEPT',rules[1])
        # The first destination/port rule must reach DROP for another NIC.
        def verdict(interface,source):
            accept=rules[1].split();return 'ACCEPT' if interface==accept[accept.index('-i')+1] and source+'/32'==accept[accept.index('-s')+1] else rules[2].split()[-1]
        self.assertEqual(verdict('ens7','10.8.0.3'),'ACCEPT')
        self.assertEqual(verdict('ens8','10.8.0.3'),'DROP')
        self.assertEqual(verdict('ens7','10.8.0.4'),'DROP')
        c=config();after,evidence=t.overlay(c,b,nics(),fw)
        self.assertEqual(c,config());self.assertEqual(len(after['services']['nginx']['ports']),2)
        self.assertEqual(after['services']['nginx']['ports'][0],c['services']['nginx']['ports'][0])
        self.assertEqual(after['services']['nginx']['ports'][1]['host_ip'],b['appAddress'])
        self.assertNotEqual(evidence['beforeSha256'],evidence['afterSha256'])
        t.verify_overlay(after,b,evidence)
        bad=copy.deepcopy(after);bad['services']['nginx']['ports'][1]['host_ip']='10.8.0.9'
        with self.assertRaises(RuntimeError):t.verify_overlay(bad,b,evidence)
        with self.assertRaisesRegex(RuntimeError,'HASH'):t.verify_overlay(after,b,{**evidence,'afterSha256':'0'*64})
        for mutate in (lambda n:n[0].update(ifname='other'),lambda n:n[0].update(address='02:00:00:00:00:02'),lambda n:n[0]['addr_info'][0].update(local='10.8.0.99'),lambda n:n[0].update(flags=[])):
            ns=nics();mutate(ns)
            with self.assertRaisesRegex(RuntimeError,'NOT_ON_APPROVED'):t.overlay(c,b,ns,fw)
        for mutate in (lambda c:c['services']['api'].update(ports=[dict(target=8080,published=18080)]),lambda c:c['services']['nginx']['ports'].append(c['services']['nginx']['ports'][0]),lambda c:c['services']['nginx']['ports'][0].update(host_ip='0.0.0.0'),lambda c:c['services']['nginx']['ports'][0].update(protocol='udp'),lambda c:c['services']['nginx']['ports'][0].update(target=80)):
            bad=config();mutate(bad)
            with self.assertRaises(RuntimeError):t.overlay(bad,b,nics(),fw)
        for bad in (saved.replace(' -j DROP',' -j ACCEPT'),'-A PREROUTING -j ACCEPT\n'+saved,saved.replace('10.8.0.3/32','10.8.0.0/24'),saved.replace('PREROUTING','INPUT')):
            with self.assertRaisesRegex(RuntimeError,'FIREWALL'):t.firewall_check(b,bad)

    def test_linux_address_shape_keeps_link_identity_and_filters_inet(self):
        b=selected()
        linux=[{'ifindex':2,'ifname':'ens7','flags':['BROADCAST','MULTICAST','UP','LOWER_UP'],
                'mtu':1500,'qdisc':'fq_codel','operstate':'UP','group':'default','txqlen':1000,
                'link_type':'ether','address':'02:00:00:00:00:01','broadcast':'ff:ff:ff:ff:ff:ff',
                'addr_info':[{'family':'inet6','local':'fe80::1','prefixlen':64,'scope':'link'},
                             {'family':'inet','local':'10.8.0.2','prefixlen':20,'broadcast':'10.8.15.255','scope':'global','label':'ens7'}]}]
        with mock.patch.object(t.subprocess,'check_output',return_value=json.dumps(linux).encode()) as call:
            actual=t.local_nics()
            call.assert_called_once_with(['ip','-j','address','show'],timeout=10)
        self.assertEqual(t.owned_nic(b,actual)['mac'],b['transport']['mac'])
        # IPv4-only ip output may omit link identity: it must not invent a MAC.
        missing=copy.deepcopy(linux);del missing[0]['address']
        with self.assertRaisesRegex(RuntimeError,'NOT_ON_APPROVED'):t.owned_nic(b,missing)
        wrong=copy.deepcopy(linux);wrong[0]['address']='02:00:00:00:00:02'
        with self.assertRaisesRegex(RuntimeError,'NOT_ON_APPROVED'):t.owned_nic(b,wrong)
        v6only=copy.deepcopy(linux);v6only[0]['addr_info']=v6only[0]['addr_info'][:1]
        with self.assertRaisesRegex(RuntimeError,'NOT_ON_APPROVED'):t.owned_nic(b,v6only)

    def test_cell_source_cadence_and_producer(self):
        m=dict(pair=dict(core=t.CORE,deploy=t.DEPLOY),imageId=t.APP,postgresImageId=t.POSTGRES,profile='pgstream-sample',runPurpose='discovery',tenants=1000,replicas=1,cadence=t.CADENCE)
        t.cell_contract(m)
        for key,value in [('postgresImageId','sha256:'+'a'*64),('runPurpose','acceptance'),('profile','remote-pilot')]:
            with self.assertRaises(RuntimeError):t.cell_contract({**m,key:value})
        for key,value in [('hotFactor',10),('loadSeconds',300),('probeEveryMs',3000),('restart',True)]:
            with self.assertRaisesRegex(RuntimeError,'CADENCE'):t.cell_contract({**m,'cadence':{**t.CADENCE,key:value}})
        plan=producer.deployment_plan(config(),True); names=[r[0] for r in plan]
        self.assertEqual(names,['infrastructure','bootstrap','admin-feed','provision','commission','pool-initialize','apis','prime','publish-primer','remaining-roles'])
        self.assertEqual(plan[5][2][-2:],['deploy/multitenant/evaluator-pool.js','initialize'])
        for name, scope, args in plan:
            if scope == 'compose':
                self.assertIn('--no-deps', args); self.assertEqual(args[args.index('--pull')+1], 'never')
                if '--wait-timeout' in args:self.assertEqual(args[args.index('--wait-timeout')+1], '90' if name in ('infrastructure','admin-feed') else '900')
        with self.assertRaises(RuntimeError):producer.deployment_plan(config(),False)

    def test_generated_probe_scope_and_anchor_control(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'probe.js';traffic_probe.generate(HERE.parents[2],target)
            source=target.read_text();subprocess.run(['node','--check',target],check=True)
            executable='\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('//'))
            for forbidden in ('child_process','psqlAsync','docker','composeArgs'):self.assertNotIn(forbidden,executable)
            self.assertIn("transports: ['polling']",source)
            self.assertIn("'.load-start'",source);self.assertIn("args.restart==='0'",source)
            self.assertIn("measurement:'UNMEASURED'",source)
        with self.assertRaisesRegex(RuntimeError,'ANCHOR'):traffic_probe.replace_once('broken','expected','replacement')

class Clinical(unittest.TestCase):
    def test_sut_assessment_refuses_missing_client_and_changed_clinical_output(self):
        import clinical
        tenant='11111111-1111-4111-8111-111111111111'; stamp='9007199254740993'
        doc=dict(_id='synthetic-id',date=123456789,sgv=123)
        sgv=dict(_id=doc['_id'],mills=doc['date'],mgdl=123)
        witness=dict(tenant=tenant,date=doc['date'],acked=True,clients=[dict(socket=i,connects=1,sgv=sgv) for i in range(2)])
        row=dict(tenant=tenant,stamp=stamp,stored=[doc],state=dict(kind='evaluator-work-v1',observed=dict(clock=stamp),completed=dict(clock=stamp),output=dict(tenant=tenant,inputCheckpoint=stamp,outputRevision=3,contentDigest='a'*64,result=dict(properties=dict(bgnow=dict(mean=123,last=123,mills=doc['date'],sgvs=[sgv]))),rows=[dict(domain='entries',doc=doc)],frame=dict(sgvs=[sgv]))))
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/'load').mkdir()
            protocol.write(d/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':'nightscout_compose_test'}}}})
            selected = dict(kind='evaluator-work-v1', pair=dict(core=t.CORE, deploy=t.DEPLOY), imageId=t.APP, instrument='a'*64)
            row['reader'] = selected
            protocol.write(d/'completion-source.json',dict(clock='sample_clock',checkpoint='sample_checkpoint',entries='sample_entries',consumer='evaluator-sample-completed',kind='evaluator-work-v1',binding=selected))
            protocol.write(d/'tenants.private.json',[dict(id=tenant)])
            (d/'load/runid').write_text('synthetic-run')
            def capture(w,r,cadence=None):
                protocol.write(d/'load/probe.json',dict(clientWitnesses=[w]))
                with mock.patch.object(clinical.a,'psql',return_value=json.dumps(r)):
                    return clinical.completed(d,dict(tenants=1,cadence=cadence or {}),maximum=0)
            self.assertEqual(capture(witness,row)['verdict'],'PASS')
            bad=copy.deepcopy(row);bad['state']['output']['result']['properties']['bgnow']['mean']=124
            with self.assertRaisesRegex(RuntimeError,'CLINICAL_COMPLETION_UNMEASURED'):capture(witness,bad)
            self.assertEqual(json.loads((d/'completed-output.json').read_text())['verdict'],'UNMEASURED')
            missing=copy.deepcopy(witness);missing['clients']=missing['clients'][:1]
            with self.assertRaisesRegex(RuntimeError,'CLINICAL_VIEWER_BINDING'):capture(missing,row)
            self.assertEqual(capture(witness,row)['verdict'],'PASS')
            quiet=copy.deepcopy(witness);quiet['clients']=[]
            evidence=capture(quiet,row,{'logicalPollingClients':0})
            self.assertEqual(evidence['verdict'],'PASS') # durable output remains checked
            self.assertEqual(evidence['clientFrames']['verdict'],'NOT_EXERCISED')
            for field,value in [('socket',17),('socket',True)]:
                wrong=copy.deepcopy(witness);wrong['clients'][0][field]=value
                with self.assertRaisesRegex(RuntimeError,'CLINICAL_VIEWER_BINDING'):capture(wrong,row)

if __name__=='__main__':unittest.main()
