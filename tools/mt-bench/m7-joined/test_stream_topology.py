"""Synthetic actual-helper topology/resource/process controls; no app effects."""
import copy
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
import adapter as a
import diagnostic_resources as r
import profile_provenance as p
import stream_topology as t
from test_diagnostic_resources import config
from reduce import measurements
EXTERNAL={'profile':'pgstream-sample','pgstreamTopology':t.EXTERNAL}


def cfg():
    value=config();value['services']['pgstream']={'command':list(t.EXTERNAL_COMMAND)}
    value['services']['evaluator']['command']=['node','entrypoint.js','evaluator'];return value


def source_schema():
    return {'properties':{'pgstream':{'type':'object','required':['receiver','slot','streamRole','bounds'],
        'additionalProperties':False,'properties':{
            **dict.fromkeys(['receiver','slot','streamRole','bounds'],{}),
            'transactionRows':{'type':'integer','minimum':1,'maximum':1000000},
            'generation':{'type':'string','pattern':'^[a-f0-9]{32}$'},
            'recovery':{'type':'object','required':['connectionEnv','timeoutMs','maxQueued'],
                'additionalProperties':False,'properties':{
                    'connectionEnv':{'type':'string','pattern':'^[A-Z][A-Z0-9_]{0,127}$'},
                    'timeoutMs':{'type':'integer','minimum':1,'maximum':30000},
                    'maxQueued':{'type':'integer','minimum':1,'maximum':1024}}}},
        'dependentRequired':{'generation':['transactionRows'],'recovery':['transactionRows']}}}}


class Topology(unittest.TestCase):
    def test_explicit_rebalance_preserves_old_and_aggregate(self):
        old=r.plan(r.overlay(config(),r.NAME)).record()
        self.assertEqual(old['aggregate'],{'millicpus':3875,'memoryBytes':8192*r.MIB,'heapMiB':1024})
        with self.assertRaisesRegex(RuntimeError,'UNKNOWN_ROLE'):r.overlay(cfg(),r.NAME)
        new=r.overlay(cfg(),r.EXTERNAL_NAME);budget=r.plan(new)
        self.assertEqual(budget.record()['aggregate'],old['aggregate']);self.assertEqual(budget.record()['profile'],r.EXTERNAL_NAME)
        self.assertEqual(r.role_limit('evaluator'),r.Limit(250,512*r.MIB))
        self.assertEqual(new['services']['evaluator']['mem_limit'],256*r.MIB);self.assertEqual(new['services']['pgstream']['mem_limit'],256*r.MIB)
        r.verify_config(new,budget)
        changed=copy.deepcopy(new);changed['services']['pgstream']['mem_limit']+=r.MIB
        with self.assertRaisesRegex(RuntimeError,'EXISTING_LIMIT_CONFLICT'):r.verify_config(changed,budget)
        extra=copy.deepcopy(new);extra['services']['api-2']={}
        with self.assertRaisesRegex(RuntimeError,'AGGREGATE_EXCEEDED'):r.plan(extra)
        self.assertEqual(r.plan(r.overlay(config(),r.NAME)).record(),old)

    def test_explicit_source_and_startup_roster(self):
        selected=cfg();t.verify_config(EXTERNAL,selected)
        with self.assertRaisesRegex(RuntimeError,'SELECTION_REQUIRED'):t.verify_config({},selected)
        missing=copy.deepcopy(selected);missing['services'].pop('pgstream')
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_SERVICE_REQUIRED'):t.verify_config(EXTERNAL,missing)
        remaining=next(args for name,scope,args in a.deployment_plan(selected,pgstream=True) if name=='remaining-roles')
        self.assertIn('pgstream',remaining);self.assertNotIn('feed-reader',remaining)
        schema=source_schema()
        t.verify_source(EXTERNAL,schema)
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_SOURCE_REQUIRED'):t.verify_source(EXTERNAL,{'properties':{}})

    def test_native_schema_missing_wrong_generation_and_recovery_refuse(self):
        original=source_schema();green=lambda:t.verify_source(EXTERNAL,original)
        green()
        cases=[
            ('missing generation',lambda v:v['properties'].pop('generation'),'EXTERNAL_SOURCE'),
            ('missing recovery',lambda v:v['properties'].pop('recovery'),'EXTERNAL_SOURCE'),
            ('wrong generation domain',lambda v:v['properties']['generation'].update(pattern='^[a-f0-9]{64}$'),'NATIVE_SOURCE'),
            ('unbounded transaction',lambda v:v['properties']['transactionRows'].pop('maximum'),'NATIVE_SOURCE'),
            ('missing recovery field',lambda v:v['properties']['recovery']['required'].remove('connectionEnv'),'NATIVE_RECOVERY'),
            ('unknown recovery property',lambda v:v['properties']['recovery']['properties'].update(optionalFallback={}),'NATIVE_RECOVERY'),
            ('unbounded recovery',lambda v:v['properties']['recovery']['properties']['timeoutMs'].pop('maximum'),'NATIVE_RECOVERY'),
            ('wrong recovery bound',lambda v:v['properties']['recovery']['properties']['maxQueued'].update(maximum=1025),'NATIVE_RECOVERY'),
            ('open recovery object',lambda v:v['properties']['recovery'].update(additionalProperties=True),'NATIVE_RECOVERY'),
            ('missing generation dependency',lambda v:v['dependentRequired'].pop('generation'),'NATIVE_DEPENDENCIES'),
            ('wrong recovery dependency',lambda v:v['dependentRequired'].update(recovery=['generation']),'NATIVE_DEPENDENCIES')]
        for label,change,code in cases:
            with self.subTest(label=label):
                broken=copy.deepcopy(original);change(broken['properties']['pgstream'])
                with self.assertRaisesRegex(RuntimeError,code+'_REQUIRED'):t.verify_source(EXTERNAL,broken)
                green()
        annotated=copy.deepcopy(original)
        for key in ('transactionRows','generation','recovery'):annotated['properties']['pgstream']['properties'][key]['description']='annotation only'
        t.verify_source(EXTERNAL,annotated)
        extended=copy.deepcopy(original)
        extended['properties']['pgstream']['properties']['startupTransport']={'type':'object'}
        t.verify_source(EXTERNAL,extended)
        old=copy.deepcopy(original);pgstream=old['properties']['pgstream']
        for key in ('transactionRows','generation','recovery'):pgstream['properties'].pop(key)
        pgstream.pop('dependentRequired')
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_SOURCE_REQUIRED'):t.verify_source(EXTERNAL,old)
        green()

    def test_native_recovery_validator_ablation_is_red_and_restoration_passes(self):
        source=Path(t.__file__).read_text()
        needle="recovery.get('additionalProperties') is False"
        self.assertEqual(source.count(needle),1)
        namespace=dict(t.__dict__)
        exec(compile(source.replace(needle,'True'),t.__file__,'exec'),namespace)
        broken=source_schema();broken['properties']['pgstream']['properties']['recovery']['additionalProperties']=True
        def criterion(verify):
            with self.assertRaisesRegex(RuntimeError,'NATIVE_RECOVERY_REQUIRED'):verify(EXTERNAL,broken)
        criterion(t.verify_source)
        with self.assertRaises(AssertionError):criterion(namespace['verify_source'])
        criterion(t.verify_source);t.verify_source(EXTERNAL,source_schema())

    @unittest.skipUnless(os.environ.get('M7_NATIVE_CORE_REPO') and os.environ.get('M7_NATIVE_CORE_COMMIT'),'exact selected Git source required')
    def test_actual_selected_schema_from_exact_git_object(self):
        repo=os.environ['M7_NATIVE_CORE_REPO'];head=os.environ['M7_NATIVE_CORE_COMMIT']
        exact=subprocess.check_output(['git','-C',repo,'rev-parse',head+'^{commit}'],text=True).strip()
        self.assertRegex(exact,r'^[a-f0-9]{40}$')
        raw=subprocess.check_output(['git','-C',repo,'show',exact+':lib/server/serve/plan-contract/schema/evaluator.schema.json'],text=True)
        schema=json.loads(raw);t.verify_source(EXTERNAL,schema)
        broken=copy.deepcopy(schema);broken['properties']['pgstream']['properties']['generation']['pattern']='.*'
        with self.assertRaisesRegex(RuntimeError,'NATIVE_SOURCE_REQUIRED'):t.verify_source(EXTERNAL,broken)
        t.verify_source(EXTERNAL,schema)

    @unittest.skipUnless(os.environ.get('M7_NATIVE_CORE_REPO') and os.environ.get('M7_NATIVE_CORE_COMMIT'),'exact selected Git source required')
    def test_selected_shipping_parser_owns_optional_startup_transport_and_native_refusals(self):
        repo=os.environ['M7_NATIVE_CORE_REPO'];head=os.environ['M7_NATIVE_CORE_COMMIT']
        self.assertEqual(subprocess.check_output(['git','-C',repo,'rev-parse','HEAD'],text=True).strip(),head)
        subprocess.run(['git','-C',repo,'diff','--quiet','HEAD','--','lib/pgstream/config.js'],check=True)
        code="""const assert=require('node:assert/strict'),parse=require(process.argv[1]+'/lib/pgstream/config').parse;
        const value={receiver:{url:'http://evaluator:19913/',trust:'network',bindHost:'0.0.0.0',maxBytes:16777216,timeoutMs:5000},slot:'synthetic_slot',streamRole:'synthetic_stream',bounds:{stepMs:5000,recoveryMs:30000,pendingMs:30000},transactionRows:10000,generation:'a'.repeat(32),recovery:{connectionEnv:'NS_SYNTHETIC_PG',timeoutMs:30000,maxQueued:1024},startupTransport:{timeoutMs:30000,retryIntervalMs:500}};
        const green=()=>assert.deepEqual(parse(value).startupTransport,value.startupTransport);green();
        for(const mutate of [x=>x.startupTransport.retryIntervalMs=30001,x=>x.generation='foreign',x=>x.recovery.maxQueued=1025,x=>delete x.transactionRows,x=>x.unsupported=true]){
          const bad=structuredClone(value);mutate(bad);assert.throws(()=>parse(bad));green();
        }
        console.log('SHIPPING_PARSER_OPTIONAL_NATIVE_RED_RESTORED');"""
        result=subprocess.run(['node','-e',code,repo],check=True,capture_output=True,text=True,timeout=15)
        self.assertIn('SHIPPING_PARSER_OPTIONAL_NATIVE_RED_RESTORED',result.stdout)

    def test_process_container_and_image_birth(self):
        old={'evaluator':{'hostProcesses':{'1':{'name':'node'},'2':{'name':'pgstream'}}}}
        new={'evaluator':{'hostProcesses':{'1':{'name':'node'}}},'pgstream':{'hostProcesses':{'2':{'name':'pgstream'}}}}
        t.readable_processes(old,{});t.readable_processes(new,EXTERNAL)
        with self.assertRaisesRegex(RuntimeError,'PROCESS_INSTRUMENT'):t.readable_processes(new,{})
        with self.assertRaisesRegex(RuntimeError,'PROCESS_INSTRUMENT'):t.readable_processes(old,EXTERNAL)
        new['pgstream']['hostProcesses']['2']['unavailable']=True
        with self.assertRaisesRegex(RuntimeError,'PROCESS_INSTRUMENT'):t.readable_processes(new,EXTERNAL)
        m={**EXTERNAL,'imageId':'sha256:'+'a'*64};row={'Image':m['imageId'],'State':{'Running':True,'Pid':12,'StartedAt':'birth'},'Config':{'Cmd':list(t.EXTERNAL_COMMAND),'Labels':{'com.docker.compose.service':'pgstream'}}}
        t.external_runtime([row],m)
        for key in ('Image','State'):
            changed=copy.deepcopy(row);changed[key]='foreign' if key=='Image' else {'Running':True}
            with self.assertRaisesRegex(RuntimeError,'RUNTIME_'):t.external_runtime([changed],m)
        with self.assertRaisesRegex(RuntimeError,'ROSTER'):t.external_runtime([],m)

    def test_go_logs_without_node_flags(self):
        chosen=p.selection('on');value=cfg();p.select_environment(value,chosen);p.verify_environment(value,chosen)
        self.assertIn('pgstream',p.LOG_ROLES);self.assertNotIn('NS_M7_DIAGNOSTICS',value['services']['pgstream'].get('environment',{}))
        rows=[{'Config':{'Labels':{'com.docker.compose.service':role},'Env':[k+'='+v for k,v in chosen['environment'].items()] if role!='pgstream' else []},'State':{'Running':True}} for role in value['services'] if role in p.LOG_ROLES and role not in ('postgres','vault','nginx')]
        p.runtime_environment(rows,chosen,value,pgstream=True)

    def test_reducer_requires_separate_go_and_same_birth(self):
        def proc(name,at):return {'name':name,'component':name,'startTicks':10,'executable':'/bin/'+name,'clockTicksPerSecond':100,'cpuTicks':at*100,'rssKiB':10}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('idle-disabled','idle','load'):
                folder=root/name;folder.mkdir()
                for edge,at in [('before',1),('after',3)]:
                    roles={role:{'id':role,'cgroup':'usage_usec '+str(at*1000000)+'\n1024\nanon 512\n','processRssKiB':'PID COMMAND RSS\n1 '+component+' 100','hostProcesses':{'1':proc(component,at)}} for role,component in [('evaluator','node'),('pgstream','pgstream')]}
                    a.write(folder/(edge+'-cgroups.json'),{'at':at,'roles':roles});(folder/(edge+'-pg-role.tsv')).write_text('role\t'+str(at)+'\t'+str(at*10)+'\n')
                if name!='idle-disabled':
                    (folder/'docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n2\towned-evaluator-1\t1%\t1MiB / 1GiB\n2\towned-pgstream-1\t1%\t1MiB / 1GiB\n')
                    (folder/'pg-activity.tsv').write_text('t\trole\tstate\twait_event_type\twait_event\tn\n2\trole\tidle\tClient\tClientRead\t1\n')
            shapes={shape:{'med':1,'p(95)':2,'p(99)':3,'count':1} for shape in ('w_sgv','w_devicestatus','w_treatments_v3','r_sgv','r_devicestatus','r_treatments','r_status')}
            a.write(root/'load/k6-summary.json',{'metrics':{'http_req_duration{shape:'+k+'}':v for k,v in shapes.items()}})
            m={**EXTERNAL,'project':'owned','tenants':2};self.assertTrue(measurements(root,m)['complete'])
            file=root/'load/after-cgroups.json';value=a.document(file);original=copy.deepcopy(value)
            value['roles'].pop('pgstream');a.write(file,value);self.assertFalse(measurements(root,m)['complete'])
            value=copy.deepcopy(original);value['roles']['pgstream']['hostProcesses']['1']['startTicks']=20;a.write(file,value);self.assertFalse(measurements(root,m)['complete'])
            a.write(file,original);self.assertTrue(measurements(root,m)['complete'])

if __name__=='__main__':unittest.main()
