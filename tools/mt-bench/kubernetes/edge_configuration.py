"""Selected Kubernetes nginx directives; source bytes and actor custody stay exact."""
import hashlib
import re
# This phase's source does not contain the separate resource leaf. Anchor the
# Unix implementation directly; workers/helpers/reload generations share slots.
# https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process.h
NGINX_MAX_WORKERS=1024

FIELDS={'workerProcesses','workerConnections'}
MAX_EXACT_INTEGER=(1<<53)-1  # Jsonnet's binary64 number carrier.

def require(ok,code,verdict='FAIL'):
    if not ok:
        error=ValueError('K8S_'+code);error.verdict=verdict;raise error

def selection(value,need=require):
    if value is None:return None
    need(isinstance(value,dict) and set(value)<=FIELDS,'EDGE_CONFIGURATION')
    if not value:return None
    for key,number in value.items():
        maximum=NGINX_MAX_WORKERS if key=='workerProcesses' else MAX_EXACT_INTEGER
        need(type(number)is int and 1<=number<=maximum,'EDGE_'+key.upper())
    return dict(value)

def record(value,need=require):
    selected=selection(value,need)
    if selected is None:return None
    return {'requested':selected,'effective':{'workerProcesses':selected.get('workerProcesses','auto'),
            'workerConnections':selected.get('workerConnections',1024)},
            'sourceAsset':'assets/nginx.conf','descriptorLimit':'INHERITED_OS_UNMEASURED'}

def project(source,value,need=require):
    selected=selection(value,need)
    if selected is None:return source
    need(isinstance(source,str) and source.count('worker_processes')==source.count('worker_connections')==1
         and source.count('worker_processes auto;')==source.count('worker_connections 1024;')==1,'EDGE_SOURCE_SHAPE')
    for field,directive,default in (('workerProcesses','worker_processes','auto'),('workerConnections','worker_connections','1024')):
        if field in selected:source=source.replace(directive+' '+default+';',directive+' '+str(selected[field])+';')
    return source

def check(manifest,inventory,objects,need=require):
    expected=record(manifest.get('edge'),need)
    need(inventory.get('edgeConfiguration')==expected and ('edgeConfiguration'in inventory)==(expected is not None),'EDGE_INVENTORY_CHANGED')
    if expected is None:return None
    rows=[row for row in objects if row.get('kind')=='ConfigMap' and row.get('metadata',{}).get('name')=='edge-nginx']
    need(len(rows)==1,'EDGE_CONFIGMAP')
    data=rows[0].get('data',{});need(set(data)=={'nginx.conf'} and not rows[0].get('binaryData'),'EDGE_CONFIGMAP')
    text=data['nginx.conf'];need(isinstance(text,str),'EDGE_CONFIGMAP')
    for field,directive in (('workerProcesses','worker_processes'),('workerConnections','worker_connections')):
        need(re.findall(r'\b'+directive+r'\s+([^;]+);',text)==[str(expected['effective'][field])],'EDGE_RENDER_CHANGED')
    return {**expected,'configurationSha256':hashlib.sha256(text.encode()).hexdigest()}

def readback(expected,actual,need=require):
    data=actual.get('data',{})
    need(isinstance(data,dict),'EDGE_CONFIGMAP_CHANGED')
    need(data.get('nginx.conf')!='<redacted>','EDGE_CONFIGMAP_UNMEASURED','UNMEASURED')
    need(data==expected.get('data') and not actual.get('binaryData'),'EDGE_CONFIGMAP_CHANGED')
    return hashlib.sha256(data['nginx.conf'].encode()).hexdigest()
