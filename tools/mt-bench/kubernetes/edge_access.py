"""How the attach step reaches the case's edge (lane nominal-ladder, 2026-11-23).

A workstation-attached run forwards one loopback port to the edge Pod (`kubectl port-forward`). A controller running in
the cluster (kube context `in-cluster`, campaign.py) addresses the edge Service's ClusterIP directly: the viewer probe opens one socket
per viewer, and a single port-forward through the API server stalled priming at 13,000 sockets (campaign lanel-c2-02,
M7_VIEWER_SETUP_STALLED). On an enforcing CNI, the controller Job needs an in-cluster ingress peer on the case edge.
The clients resolve every tenant host name to the base URL's host (Host-header routing), so the base is an IPv4 literal,
as the loopback forward was.
"""
import ipaddress
import re

IN_CLUSTER = 'in-cluster'
NAMESPACE = re.compile(r'[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?')


def controller_policy(service, source_namespace, job_name):
    """Admit one campaign Job to the selected test edge at the Service's target port."""
    owner = {'nightscout.org/run-id': service['metadata']['labels']['nightscout.org/run-id']}
    port, = service['spec']['ports']
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
            'metadata': {'name': 'campaign-controller-to-edge', 'namespace': service['metadata']['namespace'],
                         'labels': owner},
            'spec': {'podSelector': {'matchLabels': {**service['spec']['selector'], **owner}},
                     'policyTypes': ['Ingress'],
                     'ingress': [{'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': source_namespace}},
                                            'podSelector': {'matchLabels': {'batch.kubernetes.io/job-name': job_name}}}],
                                  'ports': [{'protocol': port.get('protocol', 'TCP'), 'port': port['targetPort']}]}]}}


def base_url(context, namespace, port, cluster_ip):
    """The edge base URL for an in-cluster controller (the edge Service's ClusterIP), or None when the caller must
    port-forward."""
    if not (isinstance(namespace, str) and NAMESPACE.fullmatch(namespace) and type(port) is int and 0 < port < 65536):
        raise ValueError('K8S_EDGE_ACCESS_INPUT')
    if context != IN_CLUSTER:
        return None
    try:
        address = ipaddress.IPv4Address(cluster_ip)
    except (ipaddress.AddressValueError, ValueError):
        raise ValueError('K8S_EDGE_ACCESS_CLUSTER_IP') from None
    if address.is_unspecified or address.is_loopback:
        raise ValueError('K8S_EDGE_ACCESS_CLUSTER_IP')
    return 'http://%s:%d' % (address, port)
