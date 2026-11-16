"""Pure resource controls; actual patched callsites run with actors mocked."""
import ast
import copy
import datetime
import json
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
import re
import subprocess
import sys
import types
import unittest
from unittest.mock import patch
import diagnostic_resources as r
HERE = Path(__file__).resolve().parent
SERVICES = ('postgres','vault','bootstrap','admin','primer','api','realtime','evaluator','tenant-admin','ui','nginx','placement-operator','demo')


def config():
    return {'name':'synthetic','services':{role:{'image':'synthetic','labels':{},'command':['node','role']} for role in SERVICES}}


def patched_files():
    """Apply delivered unified patch in memory to actual, unchanged modules."""
    if 'import diagnostic_resources\n' in (HERE/'adapter.py').read_text():
        return {name:(HERE/name).read_text() for name in ('adapter.py','discovery.py','orchestration_binding.py')}
    lines=(HERE/'diagnostic_resources.integration.patch').read_text().splitlines(True)
    result={}; i=0
    while i<len(lines):
        if not lines[i].startswith('--- a/'):
            i+=1; continue
        name=lines[i].strip().split('/')[-1]; original=(HERE/name).read_text().splitlines(True)
        output=[]; position=0; i+=2
        while i<len(lines) and not lines[i].startswith('--- a/'):
            match=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',lines[i])
            if not match:
                i+=1; continue
            start=int(match.group(1))-1; output.extend(original[position:start]); position=start; i+=1
            while i<len(lines) and not lines[i].startswith(('@@ ','--- a/')):
                line=' \n' if lines[i]=='\n' else lines[i]
                if line[0] in ' -':
                    if original[position]!=line[1:]: raise AssertionError('CALLSITE_PATCH_BASE_MISMATCH:'+name)
                    position+=1
                if line[0] in ' +': output.append(line[1:])
                i+=1
        output.extend(original[position:]); result[name]=''.join(output)
    return result


def load_patched(name,text):
    module=types.ModuleType(name); module.__file__=str(HERE/(name+'.py')); sys.modules[name]=module
    exec(compile(text,module.__file__,'exec'),module.__dict__)
    return module


class Resources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=patched_files()
        cls.a=load_patched('resource_adapter_control',cls.sources['adapter.py'])
        cls.d=load_patched('resource_discovery_control',cls.sources['discovery.py'])
        cls.b=load_patched('resource_binding_control',cls.sources['orchestration_binding.py'])

    def setUp(self):
        r.configure(); self.config=r.overlay(config(),r.NAME)
        self.runtime=r.configure(r.NAME,self.config,observe=lambda:[])
        self.addCleanup(r.configure)

    def test_immutable_source_maxima_include_transients_and_overlaps(self):
        with self.assertRaises(TypeError): r.LIMITS['api']=r.LIMITS['nginx']
        with self.assertRaises(FrozenInstanceError): r.LIMITS['api'].cpu=1
        for cpu,memory in [(True,r.MIB),(0,r.MIB),(1,0)]:
            with self.assertRaises(RuntimeError): r.Limit(cpu,memory)
        record=self.runtime.budget.record()
        self.assertEqual(set(record['services']),set(SERVICES))
        self.assertEqual(record['services']['bootstrap']['maximumConcurrent'],2)
        self.assertEqual(record['services']['primer']['maximumConcurrent'],2)
        self.assertEqual(record['aggregate'],{'millicpus':3875,'memoryBytes':8192*r.MIB,'heapMiB':1024})
        for role in ('api-2','feed-reader','unknown'):
            other=config(); other['services'][role]={}
            with self.assertRaisesRegex(RuntimeError,'AGGREGATE_EXCEEDED|UNKNOWN_ROLE'): r.overlay(other,r.NAME)
        with self.assertRaisesRegex(RuntimeError,'SELECTION_INVALID'): r.selection('automatic')

    def test_every_selected_role_limited_defaults_unchanged(self):
        original=config(); self.assertIs(r.overlay(original,None),original)
        for role,spec in self.config['services'].items():
            limit=r.role_limit(role)
            self.assertEqual(spec['cpus'],float(limit.cpus))
            self.assertEqual((spec['mem_limit'],spec['memswap_limit']),(limit.memory,limit.memory))
        broken=copy.deepcopy(self.config); del broken['services']['bootstrap']['mem_limit']
        with self.assertRaisesRegex(RuntimeError,'CONFIG_LIMITS_CHANGED'): r.verify_config(broken,self.runtime.budget)
        broken=copy.deepcopy(self.config); broken['services']['primer']['mem_limit']=0
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'): r.verify_config(broken,self.runtime.budget)
        broken=config(); broken['services']['api']['deploy']={'resources':{'limits':{'cpus':'9'}}}
        with self.assertRaisesRegex(RuntimeError,'ALTERNATE_LIMITS'): r.overlay(broken,r.NAME)

    def test_actual_adapter_node_argv_and_red_restored_stripped_cap(self):
        a=self.a; recorded=[]
        def run(argv,**kw):
            recorded.append((argv,kw)); return subprocess.CompletedProcess(argv,0,stdout=b'{}',stderr=b'')
        with patch.object(a.subprocess,'run',side_effect=run),patch.dict(a.os.environ,{'NODE_OPTIONS':'--require=private'}):
            a.command(['/qualified/node','-e','synthetic'],phase='generator-client-preflight')
        self.assertEqual(recorded[0][0][:2],['/qualified/node','--max-heap-size=256'])
        self.assertNotIn('NODE_OPTIONS',recorded[0][1]['env'])
        def check(call):
            recorded.clear()
            with patch.object(a.subprocess,'run',side_effect=run): call(['node','-e','synthetic'])
            self.assertIn('--max-heap-size=128',recorded[0][0],'NODE_HEAP_STRIPPED')
        check(a.command)
        with self.assertRaisesRegex(AssertionError,'NODE_HEAP_STRIPPED'): check(a._command)
        check(a.command)
        with patch.object(a.subprocess,'run') as actor:
            with self.assertRaisesRegex(RuntimeError,'NODE_OPTIONS_REFUSED'):
                a.command(['node','-e','synthetic'],env={'NODE_OPTIONS':'--require=private'})
            with self.assertRaisesRegex(RuntimeError,'INSTALL_OR_NPM_ACTOR_REFUSED'): a.command(['/qualified/npm-cli.js','ci'])
            actor.assert_not_called()
        self.assertFalse(any(self.runtime.host.values()))

    def test_actual_compose_callsite_refuses_before_actor(self):
        a=self.a; effects=[]
        with patch.object(a.orchestration_binding,'fixture_argv',return_value=['docker','compose','run','bootstrap']),patch.object(a.orchestration_binding,'fixture_mutation_preflight'),patch.object(a,'document',return_value=self.config),patch.object(a,'command',side_effect=lambda *x,**kw:effects.append(x)):
            a.compose(Path('/synthetic'),'--profile','ops','run','--rm','bootstrap')
            self.assertEqual(len(effects),1)
            broken=copy.deepcopy(self.config); del broken['services']['bootstrap']['cpus']
            with patch.object(a,'document',return_value=broken):
                with self.assertRaisesRegex(RuntimeError,'CONFIG_LIMITS_CHANGED'): a.compose(Path('/synthetic'),'--profile','ops','run','--rm','bootstrap')
            self.assertEqual(len(effects),1,'MISSING_ROLE_LIMIT_REACHED_ACTOR')
        self.runtime.observe=lambda:(_ for _ in ()).throw(AssertionError('CLEANUP_BLOCKED'))
        r.before_compose(['down','--volumes'],{})

    def test_native_limits_multiplicity_no_observed_cpu_substitution(self):
        def row(role,cpu=None):
            limit=r.role_limit(role)
            return {'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':role}},'HostConfig':{'NanoCpus':limit.cpu*1000000 if cpu is None else cpu,'Memory':limit.memory,'MemorySwap':limit.memory}}
        self.runtime.observe=lambda:[row('primer'),row('primer')]
        with self.assertRaisesRegex(RuntimeError,'CONTAINER_CONCURRENCY_EXCEEDED'): self.runtime.compose(['run','--rm','primer'],self.config)
        self.runtime.observe=lambda:[row('api',0)]
        with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'): self.runtime.containers()
        self.runtime.observe=lambda:[row('k6')]
        with self.assertRaisesRegex(RuntimeError,'CONTAINER_CONCURRENCY_EXCEEDED'):
            with r.command(['docker','run','--rm','image','version'],{}): self.fail('OVERLAP_REACHED_ACTOR')
        self.runtime.observe=None
        with self.assertRaisesRegex(RuntimeError,'CENSUS_REQUIRED'):
            with r.command(['docker','run','--rm','image','version'],{}): self.fail('NO_CENSUS_REACHED_ACTOR')

    def test_actual_discovery_argv_and_standalone_recorder(self):
        a=self.a; m={'owner':'a'*32,'project':'synthetic','port':18080,'settingsFingerprint':{'sha256':'b'*64},'cadence':{'loadSeconds':1}}
        argv=self.d.k6_command(a,Path('/synthetic'),m,'sha256:'+'c'*64,'synthetic-run')
        self.assertEqual(argv[:9],['docker','run','--rm','--cpus','0.5','--memory',str(1024*r.MIB),'--memory-swap',str(1024*r.MIB)])
        self.assertIn('com.docker.compose.service=k6',argv)
        self.assertEqual(argv[-5:],['run','--quiet','--summary-export','/out/k6-summary.json','/scripts/workload.js'])
        recorded=[]
        with patch.object(a.subprocess,'run',side_effect=lambda argv,**kw:recorded.append(argv) or subprocess.CompletedProcess(argv,0,stdout=b'',stderr=b'')): a.command(argv)
        self.assertEqual(recorded,[argv])
        custodied=argv[:3]+['--label','org.nightscout.m7.attempt='+'d'*32,'--cidfile','/synthetic/owned.cid']+argv[3:]
        self.assertEqual(r.standalone(custodied,self.runtime.budget),custodied)
        with self.assertRaisesRegex(RuntimeError,'STANDALONE_LIMIT_OVERRIDE'): r.standalone(['docker','run','--rm','--memory','0','image'],self.runtime.budget)

    def test_host_overlap_retains_lease_until_confirmed_exit(self):
        class Process:
            pid=123; result=None
            def poll(self): return self.result
            def wait(self,timeout=None):
                if self.result is None: raise subprocess.TimeoutExpired('synthetic',timeout)
                return self.result
        actual=Process(); recorded=[]
        process=r.popen(lambda argv,**kw:recorded.append(argv) or actual,['node','probe.js'],env={})
        self.assertEqual(recorded[0][:2],['node','--max-heap-size=512'])
        with self.assertRaises(subprocess.TimeoutExpired): process.wait(timeout=1)
        self.assertEqual(self.runtime.host['probe'],1)
        with self.assertRaisesRegex(RuntimeError,'HOST_CONCURRENCY_EXCEEDED'): r.popen(lambda *a,**kw:self.fail('SECOND_PROBE_EFFECT'),['node','probe.js'],env={})
        actual.result=0; self.assertEqual(process.wait(),0); self.assertEqual(self.runtime.host['probe'],0)
        with self.assertRaisesRegex(RuntimeError,'SPAWN_FAILED'): r.popen(lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('SPAWN_FAILED')),['node','probe.js'],env={})
        self.assertEqual(self.runtime.host['probe'],0)
        with self.runtime.host_lease('probe'),self.runtime.host_lease('generator'),self.runtime.host_lease('helper'),self.runtime.host_lease('helper'):
            self.assertEqual(sum(self.runtime.host[k]*r.HOST[k][0] for k in self.runtime.host),1024)
            with self.assertRaisesRegex(RuntimeError,'HOST_CONCURRENCY_EXCEEDED'):
                with self.runtime.host_lease('helper'): self.fail('FIFTH_HOST_EFFECT')

    def test_sealed_record_and_default_calls(self):
        changed=self.runtime.budget.record(); changed['services']['primer']['maximumConcurrent']=1
        with self.assertRaisesRegex(RuntimeError,'RECORD_CHANGED'): r.Runtime(self.config,changed)
        r.configure(); argv=['node','synthetic']; env={'NODE_OPTIONS':'existing'}
        with r.command(argv,env) as bounded:
            self.assertIs(bounded[0],argv); self.assertIs(bounded[1],env)
        self.assertIs(r.bounded_standalone(argv),argv)
        self.assertEqual(r.popen(lambda a,**kw:(a,kw),argv,env=env),(argv,{'env':env}))





    def test_actual_down_load_bypasses_resource_lock_and_preserves_cleanup(self):
        a=self.a; directory=Path('/synthetic').resolve()
        manifest={'directory':str(directory),'owner':'a'*32,'instrument':{'sha256':'synthetic'},'diagnosticResources':{'deliberately':'invalid'}}
        with patch.object(a,'document',return_value=manifest),patch.object(a,'instrument',return_value={'sha256':'synthetic'}):
            d,m=a.load(directory,resource_limits=False)
        self.assertEqual((d,m),(directory,manifest))
        self.assertIsNone(r._ACTIVE)
        # Capacity selections and stale-lock refusals never become cleanup GO.
        # This only preserves the existing teardown; its ownership guards remain.

    def test_other_driver_and_stale_heap_marker_refuse_before_actors(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'heap.lock'
            first=r.Runtime();second=r.Runtime();first.acquire(path)
            try:
                with self.assertRaisesRegex(RuntimeError,'OTHER_DRIVER_ACTIVE'): second.acquire(path)
            finally:first.close()
            path.write_text('{"hostLeases":{"probe":1}}')
            with self.assertRaisesRegex(RuntimeError,'STALE_HOST_LEASES'): second.acquire(path)
            # Synthetic marker restoration only; production stale-marker removal
            # requires separately verified exact-owned orphan cleanup.
            path.write_text('');second.acquire(path);second.close()

    def test_actual_probe_and_diagnostic_popen_expressions(self):
        a=self.a; recorded=[]
        class Process:
            pid=123
            def wait(self,*args,**kwargs):return 0
        m={'tenants':1,'generator':{'tools':{'node':{'path':'/qualified/node'}}},'port':18080,'cadence':{'loadSeconds':1}}
        namespace={'viewer_plan':__import__('viewer_plan'),'HERE':HERE,'str':str,'a':a,'subprocess':a.subprocess,'diagnostic_resources':r,'m':m,'d':Path('/synthetic'),
                   'out':Path('/synthetic/load'),'runid':'synthetic-run','spec':'synthetic-compose',
                   'argv':['/qualified/node','/synthetic/probe.js'],'env':{},'probe_env':{},'probe_log':object(),'log':object(),'scope':{'trafficSeconds':1}}
        # Evaluate each ACTUAL production launch expression with its launcher
        # recorded. No surrounding runner, DB, HTTP, file or process executes.
        found=0
        with patch.object(a.subprocess,'Popen',side_effect=lambda argv,**kw:recorded.append((argv,kw)) or Process()):
            for filename in ('adapter.py','discovery.py'):
                tree=ast.parse(self.sources[filename])
                for node in ast.walk(tree):
                    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='popen':
                        process=eval(compile(ast.Expression(node),filename,'eval'),namespace)
                        self.assertEqual(recorded[-1][0][:2],['/qualified/node','--max-heap-size=512'])
                        process.wait();found+=1
        self.assertEqual(found,4)
        self.assertFalse(any(self.runtime.host.values()))

    def test_red_restored_aggregate_undercount(self):
        source=(HERE/'diagnostic_resources.py').read_text()
        # Break both validation and record accounting; the independent exact
        # maxima oracle still detects missing transient overlap reservations.
        broken=source.replace('limit.cpu * count','limit.cpu').replace('limit.memory * count','limit.memory').replace('l.cpu*n','l.cpu').replace('l.memory*n','l.memory')
        self.assertNotEqual(source,broken)
        module=load_patched('broken_diagnostic_resources_control',broken)
        def check(plan):
            self.assertEqual(plan(config()).record()['aggregate']['memoryBytes'],8192*r.MIB,'TRANSIENT_OVERLAP_UNDERCOUNT')
        check(r.plan)
        with self.assertRaisesRegex(AssertionError,'TRANSIENT_OVERLAP_UNDERCOUNT'): check(module.plan)
        check(r.plan)

    def test_red_restored_actual_k6_flag_omission(self):
        a=self.a; m={'owner':'a'*32,'project':'synthetic','port':18080,'settingsFingerprint':{'sha256':'b'*64},'cadence':{'loadSeconds':1}}
        def check():
            argv=self.d.k6_command(a,Path('/synthetic'),m,'sha256:'+'c'*64,'synthetic-run')
            self.assertIn('--memory-swap',argv,'STANDALONE_LIMITS_OMITTED')
        check()
        with patch.object(r,'bounded_standalone',side_effect=lambda argv:argv):
            with self.assertRaisesRegex(AssertionError,'STANDALONE_LIMITS_OMITTED'): check()
        check()

    def test_actual_oneoff_parser_preserves_pins_and_checks_native_limits(self):
        b=self.b; image='sha256:'+'c'*64; observed=[]
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); attached=root/'attachment'; attached.mkdir()
            (attached/'owner.json').write_text(json.dumps({'owner':'a'*32,'project':'synthetic','attached':True}))
            binding={'project':'synthetic','oneoffRoot':str(root),'oneoffImages':{'k6':image},'attempt':'b'*32}
            scope={'directory':str(attached),'owner':'a'*32,'imageId':image}
            original=['docker','run','--rm','--network','none','--label',b.OWNER+'='+scope['owner'],'--label',b.PROJECT+'=synthetic',image,'version']
            owner=json.loads((attached/'owner.json').read_text())
            owner['diagnosticResources']=self.runtime.budget.record()
            (attached/'owner.json').write_text(json.dumps(owner))
            (attached/'frozen.compose.json').write_text(json.dumps(self.config))
            argv=self.a.bounded_k6_argv(original)
            def meta(args):
                observed.append(args)
                return json.dumps([{'Id':image,'Config':{'Entrypoint':['k6'],'Env':[],'User':''}}])
            intent=b._oneoff_intent(binding,'k6-version',argv,scope,meta,root/'exclusive.cid')
            limits=intent['layout']['resourceLimits']
            self.assertEqual(limits,{'NanoCpus':500000000,'Memory':1024*r.MIB,'MemorySwap':1024*r.MIB})
            row={'Id':'e'*64,'Image':image,'Config':{'Image':image,'Cmd':['version'],'Entrypoint':['k6'],'Env':[],'User':'','Labels':intent['layout']['labels']},'HostConfig':{'NetworkMode':'none','Tmpfs':{},'Privileged':False,**limits},'Mounts':[]}
            b.qualify_oneoff(binding,row,intent)
            for key in limits:
                bad=copy.deepcopy(row);bad['HostConfig'][key]=0
                with self.assertRaisesRegex(RuntimeError,'RESOURCE_LIMITS_CHANGED'): b.qualify_oneoff(binding,bad,intent)
            bad=copy.deepcopy(row);bad['Image']='sha256:'+'f'*64
            with self.assertRaisesRegex(RuntimeError,'COMMAND_IMAGE_CHANGED'): b.qualify_oneoff(binding,bad,intent)
            wrong=argv.copy();wrong[4]='4';observed.clear()
            with self.assertRaisesRegex(RuntimeError,'RESOURCE_LIMITS_CHANGED'): b._oneoff_intent(binding,'k6-version',wrong,scope,meta,root/'none.cid')
            self.assertEqual(observed,[],'WRONG_LIMIT_REACHED_IMAGE_READER')
            owner.pop('diagnosticResources');(attached/'owner.json').write_text(json.dumps(owner))
            legacy=b._oneoff_intent(binding,'k6-version',original,scope,meta,root/'legacy.cid')
            self.assertNotIn('resourceLimits',legacy['layout'])

    def test_retained_actual_service_roster_when_explicitly_supplied(self):
        import os
        path=os.environ.get('NS_DIAGNOSTIC_RESOURCE_COMPOSE')
        if not path:self.skipTest('explicit retained Compose input not supplied')
        actual=json.loads(Path(path).read_text())
        selected=r.overlay(actual,r.NAME)
        self.assertEqual(set(selected['services']),set(SERVICES))
        self.assertEqual(r.plan(selected).record()['aggregate'],self.runtime.budget.record()['aggregate'])


class EvaluatorCpuDiscriminator(unittest.TestCase):
    def setUp(self):
        self.source=config()
        self.source['services']['pgstream']={'image':'synthetic'}
        self.old=r.overlay(self.source,r.EXTERNAL_NAME)
        self.new=r.overlay(self.source,r.EVALUATOR250_NAME)
        self.addCleanup(r.configure)

    def test_only_evaluator_cpu_changes_with_same_aggregate_ceiling(self):
        before=copy.deepcopy(self.old);after=copy.deepcopy(self.new)
        self.assertEqual(before.pop(r.PROFILE_KEY),r.EXTERNAL_NAME)
        self.assertEqual(after.pop(r.PROFILE_KEY),r.EVALUATOR250_NAME)
        self.assertEqual(before['services']['evaluator']['cpus'],.125)
        self.assertEqual(after['services']['evaluator']['cpus'],.25)
        after['services']['evaluator']['cpus']=.125
        self.assertEqual(before,after)
        old=r.plan(self.old).record();new=r.plan(self.new).record()
        self.assertEqual(old['aggregate'],{'millicpus':3875,'memoryBytes':8192*r.MIB,'heapMiB':1024})
        self.assertEqual(new['aggregate'],{'millicpus':4000,'memoryBytes':8192*r.MIB,'heapMiB':1024})
        self.assertEqual(r.MAX_CPU,4000)

    def test_wrong_cpu_memory_profile_and_aggregate_refuse_restored(self):
        budget=r.plan(self.new)
        for key,value in [('cpus',.125),('mem_limit',512*r.MIB)]:
            broken=copy.deepcopy(self.new);broken['services']['evaluator'][key]=value
            with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):
                r.verify_config(broken,budget)
        broken=copy.deepcopy(self.new);broken[r.PROFILE_KEY]=r.EXTERNAL_NAME
        with self.assertRaisesRegex(RuntimeError,'PLAN_CHANGED'):r.verify_config(broken,budget)
        for profile in [r.EXTERNAL_NAME,r.EVALUATOR250_NAME]:
            broken=copy.deepcopy(self.source);broken['services']['api-2']={}
            with self.assertRaisesRegex(RuntimeError,'AGGREGATE_EXCEEDED'):r.overlay(broken,profile)
        r.verify_config(self.new,budget)

    def test_actual_runtime_quota_control_and_source_ablation(self):
        runtime=r.configure(r.EVALUATOR250_NAME,self.new,observe=lambda:[])
        row={'State':{'Status':'running'},'Config':{'Labels':{'com.docker.compose.service':'evaluator'}},
             'HostConfig':{'NanoCpus':250000000,'Memory':256*r.MIB,'MemorySwap':256*r.MIB}}
        runtime.observe=lambda:[row]
        self.assertEqual(runtime.containers()['evaluator'],1)
        for key,value in [('NanoCpus',125000000),('Memory',512*r.MIB),('MemorySwap',512*r.MIB)]:
            broken=copy.deepcopy(row);broken['HostConfig'][key]=value;runtime.observe=lambda:[broken]
            with self.assertRaisesRegex(RuntimeError,'NATIVE_LIMITS_CHANGED'):runtime.containers()
        runtime.observe=lambda:[row];self.assertEqual(runtime.containers()['evaluator'],1)
        actual=r.role_limit
        def omitted(role,profile=r.NAME):
            return actual(role,r.EXTERNAL_NAME if profile==r.EVALUATOR250_NAME else profile)
        with patch.object(r,'role_limit',side_effect=omitted):
            broken=r.overlay(self.source,r.EVALUATOR250_NAME)
            with self.assertRaisesRegex(AssertionError,'EVALUATOR_CPU_CHANGE_MUST_REACH_PRODUCER'):
                self.assertEqual(broken['services']['evaluator']['cpus'],.25,'EVALUATOR_CPU_CHANGE_MUST_REACH_PRODUCER')
        self.assertEqual(r.overlay(self.source,r.EVALUATOR250_NAME)['services']['evaluator']['cpus'],.25)


if __name__=='__main__': unittest.main()
