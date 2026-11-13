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
    ledger={'version':1,'planSha256':plan['sha256'],'resourceEpoch':['synthetic','synthetic-epoch'],'slots':{'api':[{'state':'ISSUED','incarnation':incarnation,'nonce':'b'*32,'tags':[tag],'container':{k:v for k,v in container.items() if k!='running'}}]}}
    processes=[{'processInstanceId':'api','incarnation':incarnation,'container':copy.deepcopy(container),'inspection':'RUNNING','inspectedCid':container['cid']}]
    census={'resource':{'systemIdentifier':'synthetic','postmasterStartedAt':'synthetic-epoch','pgResourceId':'synthetic-pg','serverMaximum':20,'superuserReserved':3,'otherReserved':0,'unmanagedClients':0},'tags':[{'applicationName':tag,'count':0}]}
    return dict(expected=expected,plan=plan,ledger=ledger,processes=processes,census=census)


def operator_fixture(state='UNKNOWN', bound=True):
    v=fixture();p=v['plan'];p['resource']['allowances']={'controlRecovery':1,'observers':2}
    tenant='11111111-1111-4111-8111-111111111111'
    p['lifecycleOperator']={'version':1,'tenants':[tenant],'principal':{'role':'synthetic_operator','roleOid':'31','database':'synthetic','databaseOid':'16384'},'files':{'env.json':'e'*64,'config.json':'f'*64},'placement':False}
    p['sha256']=T.sha({k:x for k,x in p.items()if k!='sha256'});v['expected']['planSha256']=p['sha256'];v['ledger'].update(version=2,planSha256=p['sha256'])
    intent={'version':1,'command':'inspect','tenant':tenant};inc='c'*32
    container={k:v for k,v in v['processes'][0]['container'].items()if k!='running'};container.update(service=T.CONTROL,cid='d'*64,startedAt='operator-birth')
    row={'state':state,'credits':1,'incarnation':inc,'nonce':'d'*32,'tags':[T.tag(inc,T.CONTROL)],'intent':intent,'intentSha256':T.sha(intent),'planSha256':p['sha256'],'source':p['source'],'container':container if bound and state!='ISSUED'else None}
    if state in('UNKNOWN','CLOSED'):row['outcome']='OUTCOME_UNCERTAIN'if state=='UNKNOWN'else'COMPLETED'
    v['ledger']['controlLeases']=[row]
    v['controlProcesses']=[]if state=='CLOSED'else[{'processInstanceId':T.CONTROL,'incarnation':inc,'container':{**container,'running':False,'operatorIncarnation':inc}if row['container']else None,'inspectedCid':container['cid'],'inspection':'STOPPED'if row['container']else'UNBOUND'}]
    if state!='CLOSED':v['census']['tags'].append({'applicationName':row['tags'][0],'count':0})
    v['census']['occupancy']={'workers':0,'control':0}
    return v


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

    def test_previous_deployment_plan_cannot_be_relabelled_as_current(self):
        v=fixture();old={'coreCommit':'074eab44ee75b9175c951b6a8add3df3e9554af7','deployCommit':'af328d87e2f1a242a6af7d1315760c6bffdd7d85'}
        v['expected']['source']=old;v['plan']['source']=old
        v['plan']['sha256']=T.sha({k:x for k,x in v['plan'].items()if k!='sha256'})
        v['expected']['planSha256']=v['plan']['sha256'];v['ledger']['planSha256']=v['plan']['sha256']
        with self.assertRaisesRegex(ValueError,'SOURCE'):T.observe(**v)
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


class OperatorIntake(unittest.TestCase):
    def test_unsupported_or_missing_legacy_ledger_version_refuses(self):
        for version in (None,0,3,False,'1'):
            v=fixture()
            if version is None:v['ledger'].pop('version')
            else:v['ledger']['version']=version
            with self.subTest(version=version),self.assertRaisesRegex(ValueError,'LEDGER_VERSION'):T.observe(**v)
    def test_explicit_v2_worker_and_control_attribution_zero_never_refunds(self):
        for state in ('ISSUED','BOUND','UNKNOWN'):
            v=operator_fixture(state);before=copy.deepcopy(v);r=T.observe(**v)
            self.assertEqual(v,before);self.assertEqual(r['ledgerVersion'],2);self.assertEqual(r['heldCredits'],{'workers':4,'control':1});self.assertEqual(r['occupancy'],{'workers':0,'control':0});self.assertEqual(r['controls'][0]['leaseState'],state);self.assertEqual(r['census'][-1]['attribution']['actor'],'control');self.assertEqual(r['census'][0]['attribution']['actor'],'worker');self.assertEqual(r['lifecycleAuthority'],'NONE');self.assertEqual(r['nativeAcceptance'],'UNMEASURED')
    def test_empty_and_closed_history_are_explicit(self):
        for empty in (False,True):
            v=operator_fixture('CLOSED')
            if empty:v['ledger']['controlLeases']=[]
            r=T.observe(**v);self.assertEqual(r['ledgerVersion'],2);self.assertEqual(r['controls'],[]);self.assertEqual(r['heldCredits']['control'],0);self.assertEqual(r['controlHistory'],{'total':0 if empty else 1,'closed':0 if empty else 1})
    def test_missing_malformed_or_unadmitted_control_refuses(self):
        changes=[lambda v:v['census'].pop('occupancy'),lambda v:v['ledger'].update(version=3),lambda v:v['ledger'].pop('version'),lambda v:v['ledger'].pop('controlLeases'),lambda v:v.pop('controlProcesses'),lambda v:v['ledger']['controlLeases'][0].update(credits=0),lambda v:v['ledger']['controlLeases'][0].update(source={}),lambda v:v['ledger']['controlLeases'][0].update(planSha256='0'*64),lambda v:v['ledger']['controlLeases'][0].update(nonce='bad'),lambda v:v['ledger']['controlLeases'][0].update(nonce='b'*32),lambda v:v['ledger']['controlLeases'][0].update(incarnation='a'*32),lambda v:v['ledger']['controlLeases'][0].update(tags=[]),lambda v:v['ledger']['controlLeases'][0]['intent'].update(command='query'),lambda v:v['ledger']['controlLeases'][0]['intent'].update(sql='synthetic'),lambda v:v['ledger']['controlLeases'][0].update(intentSha256='0'*64),lambda v:v['ledger']['controlLeases'].append(copy.deepcopy(v['ledger']['controlLeases'][0])),lambda v:v['ledger']['controlLeases'][0].update(state='CLOSED'),lambda v:v['controlProcesses'][0]['container'].update(operatorIncarnation='0'*32),lambda v:v['controlProcesses'][0]['container'].update(startedAt='other-birth'),lambda v:v['ledger']['controlLeases'][0]['container'].update(project='foreign'),lambda v:v['census']['tags'][-1].update(count=True),lambda v:v['census']['tags'][-1].update(applicationName='nscb:foreign'),lambda v:v['census'].update(occupancy={'workers':False,'control':0})]
        for mutate in changes:
            v=operator_fixture();mutate(v)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):T.observe(**v)
    def test_version_plan_binding_and_closed_tag_refuse(self):
        for mode in ('disabled','v1','closed-tag','missing-plan','config-version'):
            v=operator_fixture('CLOSED'if mode=='closed-tag'else'UNKNOWN')
            if mode in ('disabled','missing-plan'):v['plan'].pop('lifecycleOperator')
            if mode=='v1':v['ledger']['version']=1
            if mode=='config-version':v['plan']['lifecycleOperator']['version']=2
            if mode=='closed-tag':v['census']['tags'].append({'applicationName':v['ledger']['controlLeases'][0]['tags'][0],'count':0})
            v['plan']['sha256']=T.sha({k:x for k,x in v['plan'].items()if k!='sha256'});v['expected']['planSha256']=v['plan']['sha256'];v['ledger']['planSha256']=v['plan']['sha256']
            with self.subTest(mode=mode),self.assertRaises(ValueError):T.observe(**v)
    def test_unknown_missing_control_process_still_holds_credit(self):
        for mode in ('UNKNOWN','MISSING','UNBOUND'):
            v=operator_fixture(bound=mode!='UNBOUND');p=v['controlProcesses'][0];p.update(container=None,inspection=mode)
            r=T.observe(**v);self.assertEqual(r['heldCredits']['control'],1);self.assertEqual(r['controls'][0]['inspection'],mode)
    def test_second_distinct_unclosed_control_lease_is_refused(self):
        v=operator_fixture();row=copy.deepcopy(v['ledger']['controlLeases'][0]);row.update(incarnation='e'*32,nonce='f'*32,tags=[T.tag('e'*32,T.CONTROL)]);v['ledger']['controlLeases'].append(row)
        with self.assertRaisesRegex(ValueError,'CONTROL_HELD_BOUND'):T.control_leases(v['plan'],v['ledger'])
    def test_observed_occupancy_is_separate_from_credits(self):
        v=operator_fixture();v['census']['tags'][0]['count']=2;v['census']['tags'][-1]['count']=2;v['census']['occupancy']={'workers':2,'control':2}
        r=T.observe(**v);self.assertEqual(r['occupancy'],{'workers':2,'control':2});self.assertEqual(r['heldCredits']['control'],1);self.assertFalse(r['occupancyWithinHeldCredits']['control']);self.assertEqual(r['controls'][0]['leaseState'],'UNKNOWN')
        v['census']['occupancy']['control']=0
        with self.assertRaisesRegex(ValueError,'OCCUPANCY_MISMATCH'):T.observe(**v)


if __name__=='__main__':unittest.main()
