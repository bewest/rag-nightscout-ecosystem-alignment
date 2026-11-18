"""Offline SQL identity/cost controls; no database, actors or fixture writes."""
import copy
from pathlib import Path
import unittest
import sql_attribution as sql


def uri(role,host='invalid',database='synthetic'):
    return 'postgresql'+':'+'//'+role+'@'+host+'/'+database

def fixture():
    config={'postgres':{'connectionEnv':'EVALUATOR_PG'},'pgstream':{'streamRole':'synthetic_stream','recovery':{'connectionEnv':'RECOVERY_PG'}}}
    envs=[{'EVALUATOR_PG':uri('synthetic_evaluator'),'RECOVERY_PG':uri('synthetic_stream')},{'REALTIME_PG':uri('synthetic_realtime')}]
    return config,envs

def statements():
    before={('synthetic_stream','1','1','00'):{'calls':10,'executionMs':4.0},('synthetic_evaluator','2','1','00'):{'calls':20,'executionMs':10.0},('synthetic_realtime','3','1','00'):{'calls':2,'executionMs':1.0},('synthetic_other','4','1','00'):{'calls':1,'executionMs':.5}}
    after=copy.deepcopy(before)
    for role,calls,execution in [('synthetic_stream',7,11.5),('synthetic_evaluator',3,2.5),('synthetic_realtime',2,1.0),('synthetic_other',1,.5)]:
        key=next(key for key in after if key[0]==role);after[key]['calls']+=calls;after[key]['executionMs']+=execution
    return before,after

class SqlRoleAdaptation(unittest.TestCase):
    def test_legacy_disjoint_shape_and_output_preserved(self):
        roles=sql.identities({'pgstream':{'streamRole':'synthetic_stream'}},[{'A':uri('synthetic_evaluator')}])
        self.assertEqual(roles,{'pgstream':['synthetic_stream'],'adapter':['synthetic_evaluator']})
        before,after=statements();value=sql.assess(before,after,roles)
        self.assertEqual(value,{'status':'MEASURED','roles':roles,'totals':{'pgstream':{'calls':7,'executionMs':11.5},'adapter':{'calls':3,'executionMs':2.5}},'scope':'pg_stat_statements execution work, not PostgreSQL CPU; full private statements retained'})
    def test_selected_native_recovery_has_disjoint_shared_bucket_and_honest_cost(self):
        config,envs=fixture();roles=sql.identities(config,envs)
        self.assertEqual(roles,{'pgstream':[],'adapter':['synthetic_evaluator','synthetic_realtime'],'shared':['synthetic_stream']})
        before,after=statements();value=sql.assess(before,after,roles)
        self.assertEqual(value['totals']['adapter'],{'calls':5,'executionMs':3.5})
        self.assertEqual(value['totals']['shared'],{'calls':7,'executionMs':11.5})
        self.assertEqual(value['totals']['pgstream']['status'],'UNMEASURED');self.assertIsNone(value['totals']['pgstream']['calls']);self.assertIsNone(value['totals']['pgstream']['executionMs'])
        self.assertEqual(value['roleTotals']['synthetic_stream'],{'calls':7,'executionMs':11.5});self.assertEqual(value['unattributedRoles'],['synthetic_other']);self.assertEqual(value['processAttribution']['status'],'UNMEASURED')
        self.assertEqual(value['totals']['adapter']['calls']+value['totals']['shared']['calls'],12)
    def test_missing_wrong_named_wrong_role_and_foreign_endpoint_recovery_refuse(self):
        config,envs=fixture()
        changes=[lambda c,e:c['pgstream'].pop('recovery'),lambda c,e:c['pgstream'].update(recovery={}),lambda c,e:c['pgstream']['recovery'].update(connectionEnv='WRONG_NAME'),lambda c,e:e[0].pop('RECOVERY_PG'),lambda c,e:e[0].update(RECOVERY_PG=uri('synthetic_wrong')),lambda c,e:e[0].update(RECOVERY_PG=uri('synthetic_stream','other-host')),lambda c,e:e[0].update(RECOVERY_PG=uri('synthetic_stream',database='other-database'))]
        for change in changes:
            c,e=copy.deepcopy(config),copy.deepcopy(envs);change(c,e)
            with self.assertRaisesRegex(RuntimeError,'M7_SQL_'):sql.identities(c,e)
        self.assertEqual(sql.identities(config,envs)['shared'],['synthetic_stream'])
    def test_unjustified_alias_or_other_adapter_stream_role_refuses(self):
        config,envs=fixture()
        for index in [0,1]:
            e=copy.deepcopy(envs);e[index]['FOREIGN_STREAM_REFERENCE']=uri('synthetic_stream')
            with self.assertRaisesRegex(RuntimeError,'SHARED_IDENTITY'):sql.identities(config,e)
        with self.assertRaisesRegex(RuntimeError,'SHARED_IDENTITY'):sql.identities({'pgstream':{'streamRole':'synthetic_stream'}},envs)
    def test_double_count_missing_shared_and_duplicated_roles_refuse(self):
        config,envs=fixture();roles=sql.identities(config,envs);before,after=statements()
        for change in [lambda r:r['adapter'].append('synthetic_stream'),lambda r:r['adapter'].append(r['adapter'][0]),lambda r:r['shared'].append('synthetic_stream'),lambda r:r.update(shared=[]),lambda r:r.pop('shared'),lambda r:r.update(pgstream=['synthetic_stream'])]:
            bad=copy.deepcopy(roles);change(bad)
            with self.assertRaisesRegex(RuntimeError,'SHARED_IDENTITY'):sql.assess(before,after,bad)
        self.assertEqual(sql.assess(before,after,roles)['totals']['shared']['calls'],7)
    def test_counter_reset_eviction_and_new_unselected_role_preserved(self):
        config,envs=fixture();roles=sql.identities(config,envs);before,after=statements()
        with self.assertRaisesRegex(RuntimeError,'COUNTER_RESET'):sql.assess(after,before,roles)
        with self.assertRaisesRegex(RuntimeError,'EVICTED'):sql.assess(before,{},roles)
        broken=copy.deepcopy(after);broken[next(key for key in broken if key[0]=='synthetic_stream')]['executionMs']=0
        with self.assertRaisesRegex(RuntimeError,'COUNTER_RESET'):sql.assess(before,broken,roles)
        value=sql.assess(before,after,roles);self.assertEqual(value['roleTotals']['synthetic_other'],{'calls':1,'executionMs':.5})
    def test_actual_shared_assignment_omission_breaks_criterion_and_restore_passes(self):
        text=Path(sql.__file__).read_text();anchor="'shared':[stream]";self.assertEqual(text.count(anchor),1)
        namespace={};exec(compile(text.replace(anchor,"'shared':[]"),sql.__file__,'exec'),namespace)
        config,envs=fixture();before,after=statements()
        def criterion(identities,assess):
            roles=identities(config,envs);self.assertEqual(roles['shared'],['synthetic_stream']);self.assertEqual(assess(before,after,roles)['totals']['shared']['calls'],7)
        criterion(sql.identities,sql.assess)
        with self.assertRaises(AssertionError):criterion(namespace['identities'],namespace['assess'])
        criterion(sql.identities,sql.assess)
    def test_quiet_shared_role_is_role_zero_and_not_empty_exclusive_actor_zero(self):
        config,envs=fixture();roles=sql.identities(config,envs);before,after=statements();value=sql.assess(before,before,roles)
        self.assertEqual(value['totals']['shared']['calls'],0);self.assertIsNone(value['totals']['pgstream']['calls']);self.assertEqual(value['processAttribution']['status'],'UNMEASURED')

    def test_actual_sample_context_requires_shared_role_and_union_ablation_goes_red(self):
        import adapter as a
        import inspect,tempfile
        from unittest.mock import patch
        config,environments=fixture()
        def criterion(target_factory):
            with tempfile.TemporaryDirectory() as folder:
                d=Path(folder)
                for role,cfg,env in [('evaluator',config,environments[0]),('realtime',{},environments[1])]:
                    state=d/'state'/role;state.mkdir(parents=True);(state/'config.json').write_text(__import__('json').dumps(cfg));(state/'env.json').write_text(__import__('json').dumps(env))
                (d/'frozen.compose.json').write_text(__import__('json').dumps({'services':{role:{'command':['node','entry',role]} for role in ['evaluator','realtime']}}))
                observed=['synthetic_evaluator','synthetic_realtime','synthetic_stream']
                def compose(*args,**kwargs):
                    role=args[args.index('node')-1]
                    return __import__('json').dumps({'privateConfig':{'sha256':a.digest(d/'state'/role/'config.json')}})
                def psql(folder,query):
                    self.assertEqual(query,'SELECT rolname FROM pg_roles;');return '\n'.join(observed)
                manifest={'completionContract':'evaluator-work-v2','pair':{'core':'a'*40,'deploy':'b'*40},'imageId':'sha256:'+'c'*64,'instrument':{'sha256':'d'*64}}
                with patch.object(a,'compose',side_effect=compose),patch.object(a,'command',return_value='{}'),patch.object(a,'psql',side_effect=psql):
                    # The mutated function gets the actual module's patched ports.
                    target=target_factory()
                    completion,roles=target(d,manifest);self.assertEqual(roles['shared'],['synthetic_stream'])
                    observed.remove('synthetic_stream')
                    with self.assertRaisesRegex(RuntimeError,'M7_SQL_ROLE_MISSING'):target(d,manifest)
                    observed.append('synthetic_stream');self.assertEqual(target(d,manifest)[1],roles)
        criterion(lambda:a.sample_context)
        source=inspect.getsource(a.sample_context)
        anchor="{role for values in sql_roles.values() for role in values}"
        self.assertEqual(source.count(anchor),1)
        def omitted_union():
            namespace=dict(vars(a));exec(compile(source.replace(anchor,"set(sql_roles['pgstream']+sql_roles['adapter'])"),a.__file__,'exec'),namespace);return namespace['sample_context']
        with self.assertRaises(AssertionError):criterion(omitted_union)
        criterion(lambda:a.sample_context)

if __name__=='__main__':unittest.main(verbosity=2)
