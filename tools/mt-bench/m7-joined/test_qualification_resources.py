"""One explicit qualification allocation; no application or Docker effects."""
import copy
import unittest
from unittest.mock import patch
import diagnostic_resources as r

ROLES = ('postgres','vault','bootstrap','admin','primer','api','realtime','evaluator',
         'tenant-admin','ui','nginx','placement-operator','demo','pgstream')

def source():
    return {'services': {name: {'image':'synthetic'} for name in ROLES}}

class QualificationResources(unittest.TestCase):
    def test_complete_native_roster_uses_selected_ceiling(self):
        selected=r.overlay(source(),r.QUALIFICATION_NAME)
        rows=[]
        for role,limit,count in r.plan(selected).services:
            rows.extend({'State':{'Status':'running'},
                         'Config':{'Labels':{'com.docker.compose.service':role}},
                         'HostConfig':{'NanoCpus':limit.cpu*1000000,
                                       'Memory':limit.memory,'MemorySwap':limit.memory}}
                        for _ in range(count))
        runtime=r.Runtime(selected,observe=lambda:rows)
        self.assertEqual(sum(runtime.containers({'k6':1}).values()),len(rows)+1)
        # The declared profile can exceed the old4CPU ceiling. Reinstating it
        # must reproduce the native census refusal, not bypass quota checks.
        with patch.object(r,'cpu_ceiling',return_value=r.MAX_CPU):
            with self.assertRaisesRegex(RuntimeError,'RUNTIME_AGGREGATE_EXCEEDED'):
                runtime.containers({'k6':1})
        self.assertEqual(sum(runtime.containers({'k6':1}).values()),len(rows)+1)
        with self.assertRaisesRegex(RuntimeError,'CONTAINER_CONCURRENCY_EXCEEDED'):
            runtime.containers({'k6':2})

    def test_fixed_roles_overlap_accounting_and_unchanged_defaults(self):
        original=source(); saved=copy.deepcopy(original)
        selected=r.overlay(original,r.QUALIFICATION_NAME)
        self.assertEqual(original,saved)
        self.assertIs(r.overlay(original,None),original)
        expected={'postgres':(1000,1536),'vault':(250,512),
                  'evaluator':(1000,1024),'pgstream':(250,256)}
        for role,(cpu,mib) in expected.items():
            spec=selected['services'][role]
            self.assertEqual(spec['cpus'],cpu/1000)
            self.assertEqual((spec['mem_limit'],spec['memswap_limit']),(mib*r.MIB,)*2)
        record=r.plan(selected).record()
        self.assertEqual(record['aggregate'],{'millicpus':5500,'memoryBytes':9216*r.MIB,'heapMiB':1024})
        self.assertEqual(record['services']['bootstrap']['maximumConcurrent'],2)
        self.assertEqual(record['services']['primer']['maximumConcurrent'],2)
        self.assertEqual(record['standalone']['k6']['memoryBytes'],1024*r.MIB)
        self.assertEqual(r.cpu_ceiling(r.EVALUATOR250_MEMORY512_NAME),4000)
        self.assertEqual(r.memory_ceiling(r.EVALUATOR250_MEMORY512_NAME),8448*r.MIB)

    def test_actual_native_admission_rejects_old_limits_and_restores(self):
        selected=r.overlay(source(),r.QUALIFICATION_NAME)
        limit=r.role_limit('evaluator',r.QUALIFICATION_NAME)
        row={'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':'evaluator'}},
             'HostConfig':{'NanoCpus':limit.cpu*1000000,'Memory':limit.memory,'MemorySwap':limit.memory}}
        runtime=r.Runtime(selected,observe=lambda:[row])
        self.assertEqual(runtime.containers()['evaluator'],1)
        for key,value in [('NanoCpus',250000000),('Memory',512*r.MIB),('MemorySwap',2*limit.memory)]:
            broken=copy.deepcopy(row);broken['HostConfig'][key]=value
            runtime.observe=lambda:[broken]
            with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
        runtime.observe=lambda:[row]
        self.assertEqual(runtime.containers()['evaluator'],1)
        self.assertEqual(r.verify_evaluator_cgroup(r.QUALIFICATION_NAME,'100000 100000',str(1024*r.MIB),'0')['millicpus'],1000)

    def test_actual_role_omission_red_restored_and_aggregate_limit(self):
        actual=r.role_limit
        def omitted(role,profile=r.NAME):
            return actual(role,r.EVALUATOR250_MEMORY512_NAME if profile==r.QUALIFICATION_NAME else profile)
        def check():
            self.assertEqual(r.overlay(source(),r.QUALIFICATION_NAME)['services']['evaluator']['cpus'],1,'EVALUATOR_QUOTA_OMITTED')
        check()
        with patch.object(r,'role_limit',side_effect=omitted):
            with self.assertRaisesRegex(AssertionError,'EVALUATOR_QUOTA_OMITTED'):check()
        check()
        broken=source();broken['services']['api-2']={};broken['services']['api-3']={}
        with self.assertRaisesRegex(RuntimeError,'AGGREGATE_EXCEEDED'):r.overlay(broken,r.QUALIFICATION_NAME)
        good=r.overlay(source(),r.QUALIFICATION_NAME)
        broken=copy.deepcopy(good);broken['services']['postgres']['cpus']=.5
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(broken,r.plan(good))
        r.verify_config(good,r.plan(good))

if __name__=='__main__':unittest.main()
