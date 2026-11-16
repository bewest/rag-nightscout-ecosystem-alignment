"""Synthetic actual-helper topology/resource/process controls; no app effects."""
import copy
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
        schema={'properties':{'pgstream':{'required':['receiver','slot','streamRole','bounds'],'additionalProperties':False,'properties':dict.fromkeys(['receiver','slot','streamRole','bounds'],{})}}}
        t.verify_source(EXTERNAL,schema)
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_SOURCE_REQUIRED'):t.verify_source(EXTERNAL,{'properties':{}})

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
