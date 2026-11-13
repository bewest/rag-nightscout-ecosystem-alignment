"""No allocation: validate proposed addresses against actual host metadata."""
import ipaddress,json,subprocess,time
from pathlib import Path

class Refused(RuntimeError):pass
def need(value,code):
    if not value:raise Refused(code)
def subnet(value):
    try:n=ipaddress.IPv4Network(value,strict=True)
    except ValueError:raise Refused('IPAM_FORMAT')
    need(str(n)==value and 8<=n.prefixlen<=30 and any(n.subnet_of(ipaddress.IPv4Network(x))for x in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')),'IPAM_PRIVATE_CANONICAL')
    return n
def assess(plan,networks,routes,listening_ports,projects):
    b,e=map(subnet,(plan['backendSubnet'],plan['edgeSubnet']));need(not b.overlaps(e),'IPAM_OVERLAP')
    need(plan['project']not in projects,'FOREIGN_EXISTING_PROJECT');need(plan['port']not in listening_ports,'PORT_IN_USE')
    need(b.num_addresses-3>=plan['maximumBackendEndpoints']and e.num_addresses-3>=plan['maximumEdgeEndpoints'],'IPAM_ROSTER_CAPACITY')
    for row in networks:
        need((row.get('Labels')or{}).get('com.docker.compose.project')!=plan['project'],'FOREIGN_EXISTING_PROJECT')
        need(isinstance(row.get('IPAM'),dict),'HOST_NETWORK_UNKNOWN')
        for entry in row['IPAM'].get('Config')or[]:
            value=entry.get('Subnet');need(isinstance(value,str),'HOST_NETWORK_UNKNOWN')
            try:other=ipaddress.ip_network(value)
            except ValueError:raise Refused('HOST_NETWORK_UNKNOWN')
            if other.version==4:need(not b.overlaps(other)and not e.overlaps(other),'FOREIGN_DOCKER_IPAM_COLLISION')
    defaults=0
    for row in routes:
        value=row.get('dst');need(isinstance(value,str),'HOST_ROUTE_UNKNOWN')
        if value=='default':defaults+=1;continue # forwarding default is not an allocated subnet
        try:other=ipaddress.IPv4Network(value,strict=False)
        except ValueError:raise Refused('HOST_ROUTE_UNKNOWN')
        need(not b.overlaps(other)and not e.overlaps(other),'FOREIGN_ROUTE_COLLISION')
    return {'kind':'native-readonly-host-preflight','project':plan['project'],'port':plan['port'],'backendSubnet':str(b),'edgeSubnet':str(e),'networksInspected':len(networks),'routesInspected':len(routes),'forwardingDefaultsExcluded':defaults,'result':'PASS','allocation':'NOT_PERFORMED','limits':['Snapshot only; rerun immediately before allocation','No automatic alternative subnet/port, borrowing or collision waiver']}
def read_host(plan,command):
    need(command(['docker','context','show']).strip()=='default','HOST_DOCKER_CONTEXT')
    ids=command(['docker','network','ls','-q']).split();need(len(ids)<=256,'HOST_NETWORK_BOUND')
    networks=json.loads(command(['docker','network','inspect',*ids]))if ids else[]
    routes=json.loads(command(['ip','-j','-4','route','show','table','all']))
    projects=set(command(['docker','ps','-a','--format','{{.Label "com.docker.compose.project"}}']).splitlines())
    ports=[]
    for line in command(['ss','-H','-ltn']).splitlines():
        fields=line.split();need(len(fields)>=5,'HOST_LISTENER_UNKNOWN')
        try:ports.append(int(fields[3].rsplit(':',1)[1]))
        except ValueError:raise Refused('HOST_LISTENER_UNKNOWN')
    value=assess(plan,networks,routes,ports,projects);value['observedMonotonicNs']=time.monotonic_ns();return value
