import copy
import unittest
import tagged_admission as T


def fixture():
    source={'coreCommit':T.CORE,'deployCommit':T.DEPLOY}
    resource={'systemIdentifier':'synthetic','postmasterStartedAt':'synthetic-epoch','pgResourceId':'synthetic-pg','serverMaximum':20,'reserved':{'superuser':3,'other':0}}
    plan={'version':1,'kind':'controlled-connection-budget-plan','source':source,'resource':resource,'slots':[{'processInstanceId':'api','declaredMaximum':4,'capabilities':{'synthetic-capability':{}}}]}
    plan['sha256']=T.sha(plan)
    expected={'kind':T.KIND,'source':source,'imageId':'sha256:'+'1'*64,'project':'synthetic-project','workingDirectory':'/tmp/synthetic','planSha256':plan['sha256']}
    container={'cid':'2'*64,'startedAt':'synthetic-birth','project':expected['project'],'workingDirectory':expected['workingDirectory'],'service':'api','imageId':expected['imageId'],'source':source,'running':True}
    incarnation='a'*32;tag=T.tag(incarnation,'synthetic-capability')
    ledger={'planSha256':plan['sha256'],'resourceEpoch':['synthetic','synthetic-epoch'],'slots':{'api':[{'state':'ISSUED','incarnation':incarnation,'nonce':'b'*32,'tags':[tag],'container':{k:v for k,v in container.items() if k!='running'}}]}}
    processes=[{'processInstanceId':'api','incarnation':incarnation,'container':copy.deepcopy(container),'inspection':'RUNNING','inspectedCid':container['cid']}]
    census={'resource':{'systemIdentifier':'synthetic','postmasterStartedAt':'synthetic-epoch','pgResourceId':'synthetic-pg','serverMaximum':20,'superuserReserved':3,'otherReserved':0,'unmanagedClients':0},'tags':[{'applicationName':tag,'count':0}]}
    return dict(expected=expected,plan=plan,ledger=ledger,processes=processes,census=census)


class TaggedIntake(unittest.TestCase):
    def test_ledger_attribution_without_live_original_names_stays_unknown(self):
        value=fixture();before=copy.deepcopy(value);r=T.observe(**value)
        self.assertEqual(value,before);self.assertEqual(r['nativeAcceptance'],'UNMEASURED');self.assertEqual(r['lifecycleAuthority'],'NONE')
        self.assertEqual(r['generations'][0]['declaredMaximumHeld'],4)
        self.assertEqual(r['census'][0]['attribution']['originalApplicationNameStatus'],'UNKNOWN')
        self.assertEqual(r['census'][0]['attribution']['capability'],'synthetic-capability')
        self.assertEqual(r['census'][0]['raw'],value['census']['tags'][0])

    def test_identity_and_coverage_refusals(self):
        mutations=[lambda x:x['expected'].update(source={}),lambda x:x['processes'][0]['container'].update(imageId='sha256:'+'9'*64),lambda x:x['processes'][0]['container'].update(cid='3'*64),lambda x:x['census']['resource'].update(postmasterStartedAt='other'),lambda x:x['census'].update(tags=[]),lambda x:x.update(processes=[]),lambda x:x['ledger']['slots']['api'][0].update(tags=[]),lambda x:x['census']['tags'][0].update(applicationName='nscb:unknown'),lambda x:x['census']['resource'].update(serverMaximum=21)]
        for mutate in mutations:
            value=fixture();mutate(value)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):T.observe(**value)
            self.assertEqual(T.observe(**fixture())['nativeAcceptance'],'UNMEASURED')

    def test_real_health_mapping_requires_exact_incarnation(self):
        v=fixture();p=v['processes'][0];row=v['ledger']['slots']['api'][0];name=row['tags'][0]
        p['health']={'source':v['expected']['source'],'nonce':row['nonce'],'planSha256':v['plan']['sha256'],'processInstanceId':'api','incarnation':p['incarnation'],'tags':[name],'applicationNames':{name:{'capability':'synthetic-capability','originalApplicationName':'synthetic-original'}}}
        self.assertEqual(T.observe(**v)['census'][0]['attribution']['originalApplicationName'],'synthetic-original')
        p['health']['incarnation']='f'*32
        with self.assertRaisesRegex(ValueError,'HEALTH_IDENTITY'):T.observe(**v)

    def test_stopped_missing_unknown_and_unbound_credits_are_retained(self):
        for mode in ['STOPPED','MISSING','UNKNOWN','UNBOUND']:
            v=fixture();p=v['processes'][0];p['inspection']=mode
            if mode=='STOPPED':p['container']['running']=False
            else:p['container']=None
            if mode=='UNBOUND':v['ledger']['slots']['api'][0]['container']=None
            r=T.observe(**v)
            self.assertEqual(r['generations'][0]['declaredMaximumHeld'],4)
            self.assertEqual(r['generations'][0]['inspection'],mode)
            self.assertEqual(r['nativeAcceptance'],'UNMEASURED')

    def test_json_hash_rejects_unsupported_unicode_float_and_numeric_keys(self):
        for v in [{'x':0.5},{'x':'é'},{'12':1}]:
            with self.assertRaisesRegex(ValueError,'PARITY_DOMAIN'):T.sha(v)

    def test_invalid_count_duplicate_and_unknown_state_refuse(self):
        for mutate in [lambda x:x['census']['tags'][0].update(count=True),lambda x:x['census']['tags'].append(x['census']['tags'][0]),lambda x:x['ledger']['slots']['api'][0].update(state='BOGUS')]:
            v=fixture();mutate(v)
            with self.assertRaises(ValueError):T.observe(**v)


if __name__=='__main__':unittest.main()
