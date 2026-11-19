"""Finite batch planning and whole-cell custody for the existing runner.

No provider allocation, shell payloads, lease expiry, or orphan reclamation.
The UID legacy driver lock excludes unaccounted legacy drivers for the entire
batch. Child drivers require a birth-bound reservation before a per-cell lock.
"""
from contextlib import contextmanager
import concurrent.futures
import copy
from decimal import Decimal
import fcntl
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid

RESOURCE_KEYS = ('millicpus', 'memoryBytes', 'heapMiB', 'hourlyMicrousd', 'totalMicrousd', 'liveResources')
# Retained legacy reference, not a ceiling on configured ordinary producers.
LOCAL_RESOURCES = dict(zip(RESOURCE_KEYS, (4000, 8192*1024*1024, 1024, 0, 0, 64)))
CAP_KEYS = dict(zip(RESOURCE_KEYS, ('millicpus','memoryBytes','heapMiB','hourlyMicrousd','totalMicrousd','maxLiveResources')))


def need(value, code):
    if not value:raise RuntimeError('M7_BATCH_' + code)


def local_resource_plan(selected):
    """Reserve the selected producer, including its effective discovery driver.

    Profile ceilings are conservative whole-cell bounds, not measured demand or
    a host reservation. Explicit allocations retain their authored driver. Named
    profiles use discovery's larger standalone driver instead of its old default.
    """
    import diagnostic_resources as resources
    need(selected is not None, 'LOCAL_PROFILE_REQUIRED')
    resources.selection(selected)
    original_driver = resources.driver_limit(selected)
    driver = original_driver if isinstance(selected, dict) else resources.DISCOVERY_K6
    sut = {'millicpus': resources.cpu_ceiling(selected) - original_driver.cpu,
           'memoryBytes': resources.memory_ceiling(selected) - original_driver.memory}
    heap = sum(size * count for size, count in resources.HOST.values())
    required = {'millicpus': sut['millicpus'] + driver.cpu,
                'memoryBytes': sut['memoryBytes'] + driver.memory,
                'heapMiB': heap, 'hourlyMicrousd': 0, 'totalMicrousd': 0,
                'liveResources': LOCAL_RESOURCES['liveResources']}
    return {'resources': required,
            'allocationBreakdown': {
                'basis': ('selected allocation ceiling; driver memory accounted at its reservation'
                          if resources.driver_memory_request(selected) else
                          'selected allocation ceiling; conservative concurrent upper bound'),
                'sutAndOneoffs': sut,
                'driverK6': (dict(selected['driver']) if resources.driver_memory_request(selected)
                             else {'millicpus': driver.cpu, 'memoryBytes': driver.memory}),
                'hostV8': {'heapMiB': heap},
                'hostRss': 'SEPARATELY_OBSERVED_NOT_HEAP_BOUNDED',
                'generatorHeadroom': 'UNMEASURED_UNLESS_RETAINED'},
            'capacityAcceptance': 'NOT_GRANTED'}


def check_local_reservation(declared, required):
    """Allow larger authored reservations, refuse every undercount by dimension."""
    need(declared['hourlyMicrousd'] == declared['totalMicrousd'] == 0, 'LOCAL_MONEY')
    for key in RESOURCE_KEYS:
        need(type(declared[key]) is int and declared[key] >= required[key],
             'LOCAL_RESERVATION_UNDERSIZED:' + key)


def canonical(value):
    """Same JSON number/string domain as the controller's canonical digest.

    JSON spelling 1.0 and 1 denotes the same value in JavaScript. Normalizing
    numbers here prevents one batch acquiring different identities per backend.
    Integers outside the exact shared binary64 domain refuse.
    """
    if value is None:return 'null'
    if type(value) is bool:return 'true' if value else 'false'
    if type(value) is int:
        need(abs(value)<=9007199254740991,'INTEGER_RANGE')
        return str(value)
    if type(value) is float:
        need(math.isfinite(value),'NONFINITE_NUMBER')
        need(not value.is_integer() or abs(value)<=9007199254740991,'INTEGER_RANGE')
        if value==0:return '0'
        text=repr(value)
        if 1e-6<=abs(value)<1e21:
            text=format(Decimal(text),'f')
            return text.rstrip('0').rstrip('.') if '.' in text else text
        mantissa,exponent=text.lower().split('e')
        mantissa=mantissa[:-2] if mantissa.endswith('.0') else mantissa
        exponent=int(exponent)
        return mantissa+'e'+('+' if exponent>=0 else '')+str(exponent)
    if type(value) is str:return json.dumps(value,ensure_ascii=True).replace(chr(127),'\\u007f')
    if type(value) is list:return '['+','.join(canonical(x) for x in value)+']'
    need(type(value) is dict and all(type(k) is str for k in value),'JSON_DOMAIN')
    keys=sorted(value,key=lambda k:k.encode('utf-16-be','surrogatepass'))
    return '{'+','.join(canonical(k)+':'+canonical(value[k]) for k in keys)+'}'


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def birth(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return fields[19] if fields[0] != 'Z' else None
    except (FileNotFoundError, ProcessLookupError):return None


def group_members(group):
    """Read the exact recorded owned group; never kill or reclaim by PGID."""
    need(type(group)is int and group>1,'GROUP_ID')
    members=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            row=(proc/'stat').read_text().rsplit(')',1)[1].split()
            if row[0]!='Z' and row[2]==str(group):members.append({'pid':int(proc.name),'startTicks':row[19]})
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:need(False,'GROUP_CENSUS_UNAVAILABLE')
    return sorted(members,key=lambda row:row['pid'])


def write(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex)
    with open(temporary, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary, path)


def read(path):
    return json.loads(Path(path).read_text())


def number(value, minimum=0):
    return type(value) in (int, float) and math.isfinite(value) and value >= minimum


def verify_payload(spec, root):
    need(Path(root).is_absolute(),'PAYLOAD_ROOT')
    root = Path(root).resolve()
    files = spec['payload']['files']
    need(type(files) is list and bool(files), 'PAYLOAD_REQUIRED')
    seen = set()
    for item in files:
        need(set(item) == {'path','sha256'}, 'PAYLOAD_FIELDS')
        name = item['path'];need(type(name) is str and name not in seen, 'PAYLOAD_DUPLICATE')
        seen.add(name)
        p = Path(name)
        need(not p.is_absolute() and '..' not in p.parts and p.parts, 'PAYLOAD_PATH')
        file = root/p
        need(not any((root/Path(*p.parts[:i])).is_symlink() for i in range(1,len(p.parts)+1)), 'PAYLOAD_SYMLINK')
        need(file.is_file() and re.fullmatch('[a-f0-9]{64}',item['sha256']) and
             hashlib.sha256(file.read_bytes()).hexdigest() == item['sha256'], 'PAYLOAD_CHANGED')
    return seen


def plan(spec, now=None):
    """Pure deterministic review plan. It grants no execution authority."""
    now = time.time() if now is None else now
    need(set(spec) == {'version','id','payload','envelope','cells'} and type(spec['version']) is int and spec['version'] == 1, 'SPEC_FIELDS')
    need(type(spec['id']) is str and re.fullmatch('[a-z][a-z0-9-]{0,62}',spec['id']), 'ID')
    payload = spec['payload'];env = spec['envelope'];cells = spec['cells']
    need(set(payload) == {'files','source','image','helper'}, 'PAYLOAD_FIELDS')
    need(set(payload['source']) == {'core','deploy'} and all(type(x) is str and re.fullmatch('[a-f0-9]{40}',x) for x in payload['source'].values()), 'SOURCE_PIN')
    need(type(payload['image']) is str and re.fullmatch('sha256:[a-f0-9]{64}',payload['image']), 'IMAGE_PIN')
    need(type(payload['helper']) is str and re.fullmatch('[a-f0-9]{64}',payload['helper']), 'HELPER_PIN')
    need(type(env.get('maxConcurrent')) is int and 1 <= env['maxConcurrent'] <= 256, 'CONCURRENCY')
    for key in CAP_KEYS.values():need(type(env.get(key)) is int and env[key] >= 0, 'ENVELOPE')
    need(number(env.get('maxOfferedRps')) and number(env.get('cleanupAt'), now+1), 'DEADLINE_OR_RATE')
    need(type(cells) is list and 1 <= len(cells) <= 10000, 'CELLS')
    axes = env.get('workload');need(type(axes) is dict, 'WORKLOAD_ENVELOPE')
    for axis in ('tenants','offeredRps','durationSeconds','probeEveryMs','hotFactor'):
        bound = axes.get(axis)
        need(type(bound) is list and len(bound)==2 and all(number(x) for x in bound) and bound[0]<=bound[1], 'WORKLOAD_BOUND')
    need(type(axes.get('faultCases')) is list and all(type(x) is str for x in axes['faultCases']), 'FAULT_CASES')
    ids=set();names=set();ports=set();nets=[];total=0
    for cell in cells:
        need(type(cell) is dict and re.fullmatch('[a-z][a-z0-9-]{0,62}',cell.get('id','')) and cell['id'] not in ids, 'CELL_ID')
        ids.add(cell['id'])
        name=cell.get('namespace');need(type(name) is str and re.fullmatch('[a-z][a-z0-9-]{0,62}',name) and name not in names, 'NAMESPACE')
        names.add(name)
        need(type(cell.get('ports')) is list and type(cell.get('subnets')) is list, 'ISOLATION')
        for port in cell['ports']:
            need(type(port) is int and 1024 <= port <= 65535 and port not in ports, 'PORT_CONFLICT');ports.add(port)
        for cidr in cell['subnets']:
            net=ipaddress.ip_network(cidr, strict=True)
            need(net.version == 4 and net.is_private and not any(net.overlaps(other) for other in nets), 'SUBNET_CONFLICT');nets.append(net)
        resources=cell.get('resources');need(type(resources) is dict and set(resources)==set(RESOURCE_KEYS),'RESOURCES')
        for key in RESOURCE_KEYS:
            need(type(resources[key]) is int and 0 <= resources[key] <= env[CAP_KEYS[key]], 'CELL_OVERCOMMIT')
        total += resources['totalMicrousd']
        need(number(cell.get('offeredRps')) and cell['offeredRps'] <= env['maxOfferedRps'], 'CELL_RATE')
        need(type(cell.get('workSeconds')) is int and cell['workSeconds']>0 and type(cell.get('cleanupSeconds')) is int and cell['cleanupSeconds']>0 and now+cell['workSeconds']+cell['cleanupSeconds'] <= env['cleanupAt'], 'CELL_DEADLINE')
        need(type(cell.get('target')) is dict and cell['target'].get('kind') in ('local','remote'), 'TARGET')
    need(total <= env['totalMicrousd'], 'TOTAL_COST')
    return {'version':1,'batch':spec['id'],'specSha256':digest(spec),'payload':copy.deepcopy(payload),
            'envelope':copy.deepcopy(env),'cells':copy.deepcopy(cells),'capacityAcceptance':'NOT_GRANTED',
            'authority':'PLAN_ONLY; effect-specific tool review and resource custody still required'}


class Reservations:
    """Atomic persistent ledger; stale ownership never expires into availability."""
    def __init__(self, directory, spec):
        self.directory=Path(directory).resolve();self.file=self.directory/'reservations.json';self.spec=spec

    @contextmanager
    def locked(self):
        path=self.directory/'reservations.lock'
        fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd);need(info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'LEDGER_LOCK')
            fcntl.flock(fd,fcntl.LOCK_EX)
            value=read(self.file)
            need(value['specSha256']==digest(self.spec),'SPEC_CHANGED')
            need(birth(value['pid'])==value['startTicks'],'STALE_OWNER')
            yield value
            write(self.file,value)
        finally:os.close(fd)

    def create(self):
        need(not self.file.exists(),'LEDGER_EXISTS')
        write(self.file,{'specSha256':digest(self.spec),'pid':os.getpid(),'startTicks':birth(os.getpid()),'nonce':uuid.uuid4().hex,'cells':{},'spentUpperMicrousd':0})

    def reserve(self,cell,now=None):
        now=time.time() if now is None else now
        with self.locked() as ledger:
            need(cell in self.spec['cells'],'CELL_CHANGED')
            need(cell['id'] not in ledger['cells'],'CELL_ALREADY_ENTERED')
            need(now+cell['workSeconds']+cell['cleanupSeconds']<=self.spec['envelope']['cleanupAt'],'CELL_DEADLINE')
            active=[v for v in ledger['cells'].values() if v['status']!='ABSENT']
            if len(active)>=self.spec['envelope']['maxConcurrent']:return None
            for key in RESOURCE_KEYS:
                if key == 'totalMicrousd':continue
                if sum(v['resources'][key] for v in active)+cell['resources'][key]>self.spec['envelope'][CAP_KEYS[key]]:return None
            if sum(v['offeredRps'] for v in active)+cell['offeredRps']>self.spec['envelope']['maxOfferedRps']:return None
            need(ledger['spentUpperMicrousd']+cell['resources']['totalMicrousd']<=self.spec['envelope']['totalMicrousd'],'TOTAL_COST')
            ticket={'id':cell['id'],'nonce':uuid.uuid4().hex,'batchNonce':ledger['nonce'],'specSha256':ledger['specSha256'],'cleanupAt':self.spec['envelope']['cleanupAt']}
            ledger['cells'][cell['id']]={**ticket,'status':'RESERVED','resources':cell['resources'],'offeredRps':cell['offeredRps']}
            ledger['spentUpperMicrousd']+=cell['resources']['totalMicrousd']
            return ticket

    def release(self,ticket,absence):
        with self.locked() as ledger:
            row=ledger['cells'].get(ticket['id'])
            need(row is not None and all(row.get(k)==v for k,v in ticket.items()),'FOREIGN_RELEASE')
            need(absence == {'status':'ABSENT','id':ticket['id'],'nonce':ticket['nonce']},'ABSENCE_REQUIRED')
            need(row['status']=='RESERVED','ALREADY_RELEASED')
            row['status']='ABSENT'


def global_lock_path():
    return Path('/tmp/nightscout-m7-diagnostic-heap-'+str(os.getuid())+'.lock')


def child_lock():
    """Validate aggregate custody before selecting a cell-local heap lock."""
    file=os.environ.get('M7_BATCH_RESERVATION')
    if not file:return None
    file=Path(file);need(file.is_absolute(),'TICKET_PATH')
    for p in (file,file.parent/'reservations.json',file.parent):
        info=p.lstat();need(not stat.S_ISLNK(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o077==0,'TICKET_CUSTODY')
    ticket=read(file);ledger=read(file.parent/'reservations.json')
    row=ledger['cells'].get(ticket['id'])
    need(birth(ledger['pid'])==ledger['startTicks'],'STALE_OWNER')
    need(row is not None and row['status']=='RESERVED' and all(row.get(k)==v for k,v in ticket.items()),'FOREIGN_TICKET')
    global_path=global_lock_path()
    with global_path.open('r') as lock:
        marker=json.load(lock)
    need(marker=={'batchNonce':ledger['nonce'],'ledger':str(file.parent/'reservations.json'),'pid':ledger['pid'],'startTicks':ledger['startTicks']},'GLOBAL_CUSTODY')
    return file.parent/(ticket['id']+'.heap.lock')


def reserved_cell(config):
    """Bind a typed child to its parent's exact reviewed cell, not just a lock."""
    need(child_lock() is not None,'TICKET_REQUIRED')
    file=Path(os.environ['M7_BATCH_RESERVATION']);ticket=read(file)
    for p in (file.parent/'batch.json',file.parent/'batch-payload.json'):
        info=p.lstat();need(not stat.S_ISLNK(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o077==0,'TICKET_CUSTODY')
    spec=read(file.parent/'batch.json');payload=read(file.parent/'batch-payload.json');ledger=read(file.parent/'reservations.json')
    need(digest(spec)==ticket['specSha256']==payload['specSha256'],'SPEC_CHANGED')
    cells=[cell for cell in spec['cells'] if cell['id']==ticket['id']]
    need(len(cells)==1 and cells[0]['config']==config,'CELL_CONFIG_CHANGED')
    cell=cells[0];row=ledger['cells'][ticket['id']]
    need(row['resources']==cell['resources'] and row['offeredRps']==cell['offeredRps'],'CELL_RESERVATION_CHANGED')
    need(type(payload['root']) is str and Path(payload['root']).is_absolute(),'PAYLOAD_ROOT')
    return cell,spec,Path(payload['root'])


@contextmanager
def local_custody(directory, spec):
    import diagnostic_resources as resources
    need(not os.environ.get('M7_BATCH_RESERVATION'),'NESTED_BATCH')
    directory=Path(directory).resolve();need(not directory.exists(),'OUTPUT_EXISTS')
    directory.mkdir(parents=True,mode=0o700)
    lease=resources.Runtime();lease.acquire()  # unchanged UID-global legacy exclusion
    ledger=Reservations(directory,spec)
    try:
        ledger.create();value=read(ledger.file)
        marker={'batchNonce':value['nonce'],'ledger':str(ledger.file),'pid':value['pid'],'startTicks':value['startTicks']}
        os.write(lease.driver_fd,json.dumps(marker).encode());os.fsync(lease.driver_fd)
        yield ledger
    finally:
        # Any unresolved cell retains the marker; later callers refuse, never
        # reclaim by PID/time alone. Exact orphan reconciliation is external.
        if ledger.file.exists() and all(v['status']=='ABSENT' for v in read(ledger.file)['cells'].values()):
            os.ftruncate(lease.driver_fd,0);os.fsync(lease.driver_fd)
        lease.close()


def schedule(spec, ledger, execute, cancelled=lambda:False, now=time.time, changed=lambda:None):
    """Injected executor returns (retained result, exact verified absence).

    Cancellation stops admission only. Entered finite executors finish cleanup.
    A failed cleanup retains its reservation and prevents over-admission.
    """
    pending=list(spec['cells']);active={};results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=spec['envelope']['maxConcurrent']) as pool:
        while pending or active:
            if cancelled():
                results.update({c['id']:{'status':'CANCELLED_NOT_STARTED'} for c in pending});pending=[]
            progress=False
            for cell in list(pending):
                if now()+cell['workSeconds']+cell['cleanupSeconds']>spec['envelope']['cleanupAt']:
                    results[cell['id']]={'status':'DEADLINE_NOT_STARTED'};pending.remove(cell);progress=True;continue
                try:changed()  # rehash before each entered cell
                except Exception as error:
                    results.update({c['id']:{'status':'REFUSED_NOT_STARTED','error':str(error)} for c in pending});pending=[];break
                ticket=ledger.reserve(cell,now())
                if ticket is None:continue
                active[pool.submit(execute,cell,ticket)]=(cell,ticket);pending.remove(cell);progress=True
            done=[f for f in active if f.done()]
            for future in done:
                cell,ticket=active.pop(future)
                try:
                    result,absence=future.result()
                    results[cell['id']]=result
                    ledger.release(ticket,absence)
                except Exception as error:
                    results[cell['id']]={**results.get(cell['id'],{}),'status':'FAILED_PARTIAL','error':str(error),'cleanup':'UNCONFIRMED'}
                progress=True
            if not active and pending and not progress:
                results.update({c['id']:{'status':'BLOCKED_RESERVATION_RETAINED'} for c in pending});pending=[]
            if active and not progress:time.sleep(.02)
    return {'batch':spec['id'],'specSha256':digest(spec),'cells':results,'capacityAcceptance':'NOT_GRANTED'}
