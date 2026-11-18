"""Source/ownership and independent count contracts for the joined M7 adapter."""
import hashlib
import json
import re
from pathlib import Path

COUNTS = (1000, 3000, 5000, 10000)
REPLICAS = (1, 2, 4)
PILOT_COUNTS = (500, 750, 1000)
CADENCE = {"pgstream-sample":{"accel":1,"hotFactor":1,"socketsPerTenant":2,"idleSeconds":120,"loadSeconds":600,"probeEveryMs":300000,"restart":False},
           "capacity":{"accel":1,"hotFactor":10,"socketsPerTenant":2,"idleSeconds":600,"loadSeconds":900},
           "fresh-image-diagnostic":{"trafficSeconds":180,"idleSeconds":0,"loadSeconds":0},
           "remote-pilot":{"accel":1,"hotFactor":10,"socketsPerTenant":2,"idleSeconds":120,"loadSeconds":300}}
UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
OWNER = "org.nightscout.m7.owner"
DIAGNOSTIC_CHECKS=("dataHttp","stockPrimed","currentFrames","restartObserved","stockRecovered","httpAfterRecovery")


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def digest(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def labels_match(labels, core, deploy):
    require(labels.get("org.opencontainers.image.revision") == core, "M7_IMAGE_CORE_MISMATCH")
    require(labels.get("org.nightscout.deploy.revision") == deploy, "M7_IMAGE_DEPLOY_MISMATCH")


def owned(resource, owner):
    labels = resource.get("Config", {}).get("Labels", resource.get("Labels", {})) or {}
    require(labels.get(OWNER) == owner, "M7_RESOURCE_NOT_OWNED")


def tenant_projection(document, count):
    require(isinstance(document, dict) and document.get("version") == 1 and isinstance(document.get("tenants"), list), "M7_PRIMER_SHAPE")
    rows = document["tenants"]
    require(len(rows) == count, "M7_PRIMER_COUNT")
    result = []
    for row in rows:
        require(isinstance(row, dict) and UUID.fullmatch(row.get("id", "")) and isinstance(row.get("host"), str)
                and re.fullmatch(r"[a-z0-9.-]+", row["host"]) and isinstance(row.get("dataToken"), str) and row["dataToken"], "M7_PRIMER_DATA_TOKEN_REQUIRED")
        result.append({"id": row["id"], "host": row["host"], "token": row["dataToken"]})
    require(len({r["id"] for r in result}) == count and len({r["host"] for r in result}) == count, "M7_PRIMER_DUPLICATE")
    return result


def metric(metrics, name, field="count"):
    row = metrics.get(name, {})
    value = row.get("values", row).get(field, 0)
    require(isinstance(value, (int, float)) and value >= 0, "M7_METRIC_INVALID")
    return value


def oracle(stored, metrics, probes, tenants, strict=False, allow_empty=False, probes_known=True):
    """Independent SQL counts vs client-acknowledged counts; never API reads."""
    expected = {row["id"] for row in tenants}
    require(expected and set(stored).issubset(expected) and set(probes).issubset(expected), "M7_ORACLE_TENANT_SCOPE")
    rows, failures = [], []
    total = {kind: 0 for kind in ("entries", "devicestatus", "treatments")}
    for tenant in sorted(expected):
        values = stored.get(tenant, {})
        require(set(values).issubset(set(total) | {"probe"}) and all(isinstance(n, int) and n >= 0 for n in values.values()), "M7_ORACLE_COUNTS_INVALID")
        count = sum(values.get(kind, 0) for kind in total)
        accepted = metric(metrics, f"writes_ok{{tenant:{tenant}}}")
        uncertain = metric(metrics, f"writes_uncertain{{tenant:{tenant}}}")
        match = accepted <= count <= accepted + uncertain and (not probes_known or values.get("probe", 0) == probes.get(tenant, 0))
        if strict:
            match = match and accepted > 0 and uncertain == 0
        rows.append({"tenant": tenant, "stored": count, "accepted": accepted, "uncertain": uncertain,
                     "probeStored": values.get("probe", 0), "probeAccepted": probes.get(tenant, 0) if probes_known else None, "match": match})
        if not match:
            failures.append("tenant:" + tenant)
        for kind in total:
            total[kind] += values.get(kind, 0)
    # Unlike the old baseline formatter, enforce the domain totals too.
    for kind, count in total.items():
        accepted = metric(metrics, f"writes_ok{{kind:{kind}}}")
        # Per-kind uncertain submetrics are absent in the baseline. Nonzero
        # uncertainty therefore cannot establish exact domain equality.
        uncertain = sum(row["uncertain"] for row in rows)
        if not accepted <= count <= accepted + uncertain:
            failures.append("domain:" + kind)
    require(allow_empty or sum(row["accepted"] for row in rows) > 0, "M7_ORACLE_NO_ACCEPTED_WRITES")
    require(sum(row["accepted"] for row in rows) == metric(metrics, "writes_ok"), "M7_ORACLE_CLIENT_TOTAL_MISMATCH")
    return {"verdict": "RED" if failures else "GREEN", "rows": rows, "domains": total, "failures": failures,
            "uncertain": sum(row["uncertain"] for row in rows), **({"probeCountProof":"UNMEASURED"} if not probes_known else {})}


def serving_mounts(config):
    for service, spec in config.get("services", {}).items():
        for volume in spec.get("volumes", []):
            target = volume.get("target", "") if isinstance(volume, dict) else volume.split(":")[1]
            require(not (target == "/opt/app" or target.startswith("/opt/app/")), "M7_SERVING_SOURCE_MOUNT_REFUSED:" + service)


def campaign_check(document):
    accepted_claim_scope(document)
    require(document.get("version") == 1 and document.get("kind") == "m7-joined-capacity", "M7_SUMMARY_SHAPE")
    pair = document.get("pair", {})
    require(all(SHA.fullmatch(pair.get(key, "")) for key in ("core", "deploy")), "M7_SUMMARY_SOURCE_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{64}", document.get("hostIdentity", "")), "M7_SUMMARY_HOST_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{64}", document.get("instrument", "")), "M7_SUMMARY_INSTRUMENT_REQUIRED")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", document.get("imageId", "")), "M7_SUMMARY_IMAGE_REQUIRED")
    cells = document.get("cells", [])
    require({(r.get("tenants"), r.get("replicas")) for r in cells} == {(n, a) for a in REPLICAS for n in COUNTS}, "M7_SUMMARY_MISSING_CELL")
    require(len(cells) == len(COUNTS) * len(REPLICAS), "M7_SUMMARY_DUPLICATE_CELL")
    from profile_provenance import check_identity, observation_check
    chosen=check_identity(document.get("profileSelection"))
    for row in cells:
        accepted_claim_scope(row)
        require(check_identity(row.get("profileSelection"))==chosen,"M7_PROFILE_SELECTION_MISMATCH")
        observation_check(row.get("settingsFingerprintObservation"))
        require(chosen["settings"].get("sourceCommit")==pair["core"],"M7_PROFILE_SETTINGS_SOURCE")
        require(row.get("pair") == pair and row.get("hostIdentity")==document.get("hostIdentity") and row.get("instrument") == document.get("instrument"), "M7_SUMMARY_MIXED_SOURCE")
        require(row.get("imageId")==document["imageId"] and row.get("measurements",{}).get("complete") is True, "M7_SUMMARY_UNMEASURED_CELL")
        require(row.get("verdict") == "PASS", "M7_SUMMARY_NONPASS_CELL")
    return True


def pilot_check(document):
    accepted_claim_scope(document)
    for row in document.get("cells",[]):accepted_claim_scope(row)
    return _pilot_check(document,"m7-joined-remote-pilot")


def _pilot_check(document,kind):
    require(document.get("kind")==kind, "M7_PILOT_SHAPE")
    pair=document.get("pair",{})
    require(all(SHA.fullmatch(pair.get(key,"")) for key in ("core","deploy")) and re.fullmatch(r"sha256:[0-9a-f]{64}",document.get("imageId","")),"M7_PILOT_SOURCE_REQUIRED")
    cells=document.get("cells",[])
    replicas=document.get("profileReplicas")
    require(replicas in REPLICAS,"M7_PILOT_REPLICAS_REQUIRED")
    require(len(cells)==3 and {(r.get("tenants"),r.get("replicas")) for r in cells}=={(n,replicas) for n in PILOT_COUNTS},"M7_PILOT_MISSING_CELL")
    require(re.fullmatch(r"[0-9a-f]{64}",document.get("instrument","")) and re.fullmatch(r"[0-9a-f]{64}",document.get("hostIdentity","")),"M7_PILOT_IDENTITY_REQUIRED")
    from profile_provenance import check_identity, observation_check
    chosen=check_identity(document.get("profileSelection"))
    for row in cells:
        require(check_identity(row.get("profileSelection"))==chosen,"M7_PROFILE_SELECTION_MISMATCH")
        observation_check(row.get("settingsFingerprintObservation"))
        require(chosen["settings"].get("sourceCommit")==pair["core"],"M7_PROFILE_SETTINGS_SOURCE")
        require(row.get("pair")==document.get("pair") and row.get("hostIdentity")==document.get("hostIdentity") and row.get("instrument")==document["instrument"] and row.get("imageId")==document.get("imageId"),"M7_PILOT_MIXED_SOURCE")
        require(row.get("verdict")=="PASS" and row.get("measurements",{}).get("complete") is True and row.get("profile")=="remote-pilot","M7_PILOT_NONPASS_CELL")
    return True


def host_identity(host):
    values={key:host[key] for key in ('cores','cpuModel','kernel','dockerDaemonId','dockerContext')}
    values['memTotalKiB']=host['memory']['MemTotal']
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()


def receipt_scope(manifest,receipt,operation):
    require(receipt.get("pair")==manifest["pair"],"M7_RECEIPT_SOURCE_MISMATCH")
    if manifest.get('profile')=='pgstream-sample' and manifest.get('runPurpose')=='discovery':
        require(operation in ('build','deploy','run'),'M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY')
        require(receipt.get('kind')=='joined-diagnostic' and receipt.get('status')=='AUTHORIZED_DIAGNOSTIC'
                and (receipt.get('version',1)==2 or receipt.get('functionalAcceptanceAtAuthorization')=='PENDING'),'M7_DIAGNOSTIC_RECEIPT_REQUIRED')
        require(re.fullmatch(r'[a-f0-9]{64}',receipt.get('instrument','')) and receipt['instrument']==manifest['instrument']['sha256']
                and re.fullmatch(r'sha256:[a-f0-9]{64}',receipt.get('imageId','')) and receipt['imageId']==manifest.get('imageId'),'M7_DIAGNOSTIC_IDENTITY_MISMATCH')
        if manifest.get('cadence',{}).get('restartDuringLoadAfterSeconds') is not None:
            require(receipt.get('version')==2,'M7_DEMAND_RECOVERY_V2_RECEIPT_REQUIRED')
        limits=receipt.get('limits',{})
        import static_topology
        selected_static=static_topology.receipt(manifest,receipt)
        api_ok=(type(manifest.get('replicas')) is int and type(limits.get('apiReplicas')) is int and manifest['replicas']==limits['apiReplicas'] and manifest['replicas'] in REPLICAS) if selected_static else (type(manifest.get('replicas')) is int and manifest['replicas']==1 and type(limits.get('apiReplicas')) is int and limits['apiReplicas']==1)
        require(type(manifest.get('tenants')) is int and type(limits.get('tenants')) is int and 1<=manifest['tenants']<=limits['tenants']<=10000
                and api_ok
                and type(limits.get('trafficSeconds')) is int and 1<=limits['trafficSeconds']==manifest.get('cadence',CADENCE['pgstream-sample'])['loadSeconds']<=86400,'M7_DIAGNOSTIC_LIMIT_INVALID')
        return {'kind':'diagnostic-discovery',**discovery_authorization(manifest,receipt)}
    measurement_request(manifest)
    if manifest.get("measurementMode")=="unaccepted":
        require(operation in ("build","deploy","run"),"M7_UNACCEPTED_OPERATION")
        fields={"version","kind","status","pair","instrument","imageId","runId","functionalAcceptanceAtAuthorization","purpose","limits"}
        require(set(receipt)==fields and receipt.get("version")==1 and type(receipt["version"]) is int
                and receipt.get("kind")=="joined-measurement-authorization" and receipt.get("status")=="AUTHORIZED_UNACCEPTED_MEASUREMENT"
                and receipt.get("functionalAcceptanceAtAuthorization")=="PENDING" and receipt.get("purpose")=="PRE_ACCEPTANCE_BASELINE_ONLY","M7_UNACCEPTED_AUTHORIZATION_REQUIRED")
        require(isinstance(receipt.get("instrument"),str) and receipt.get("instrument")==manifest["instrument"]["sha256"] and re.fullmatch(r"[a-f0-9]{64}",receipt.get("instrument",""))
                and receipt.get("imageId")==manifest["imageId"] and receipt.get("runId")==manifest["runId"],"M7_UNACCEPTED_IDENTITY_MISMATCH")
        limits=receipt.get('limits')
        require(limits==MEASUREMENT_LIMITS and isinstance(limits,dict) and all(type(limits[k]) is int for k in ('apiReplicas','realtimeReplicas','evaluatorReplicas','maximumRunMinutes'))
                and all(type(n) is int for n in limits['tenantCounts']),"M7_UNACCEPTED_AUTHORIZATION_LIMIT")
        return {"kind":"unaccepted-measurement",**UNACCEPTED_SCOPE}
    if manifest.get("profile")=="fresh-image-diagnostic":
        require(operation in ("build","deploy","diagnose"),"M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY")
        require(receipt.get("kind")=="joined-diagnostic" and receipt.get("status")=="AUTHORIZED_DIAGNOSTIC"
                and receipt.get("instrument")==manifest["instrument"]["sha256"],"M7_DIAGNOSTIC_RECEIPT_REQUIRED")
        limits=receipt.get("limits",{})
        require(isinstance(limits.get("tenants"),int) and 1<=manifest["tenants"]<=limits["tenants"]<=10
                and isinstance(limits.get("apiReplicas"),int) and 1<=manifest["replicas"]<=limits["apiReplicas"]<=2
                and isinstance(limits.get("trafficSeconds"),int) and 1<=limits["trafficSeconds"]<=180,"M7_DIAGNOSTIC_LIMIT_INVALID")
        return {"kind":"diagnostic-only","trafficSeconds":limits["trafficSeconds"]}
    require(receipt.get("kind")=="joined-acceptance" and receipt.get("status")=="PASS","M7_FROZEN_ACCEPTANCE_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{64}",receipt.get("evidenceSha256","")),"M7_ACCEPTANCE_EVIDENCE_REQUIRED")
    return {"kind":"accepted-capacity"}


def diagnostic_check(document):
    require(document.get("kind")=="m7-joined-fresh-image-diagnostic" and document.get("fullAcceptance")=="NOT_RUN"
            and document.get("capacity")=="NO-MEASUREMENT","M7_DIAGNOSTIC_SHAPE")
    require(all(SHA.fullmatch(document.get("pair",{}).get(key,"")) for key in ("core","deploy"))
            and re.fullmatch(r"[0-9a-f]{64}",document.get("instrument",""))
            and re.fullmatch(r"[0-9a-f]{64}",document.get("hostIdentity",""))
            and re.fullmatch(r"sha256:[0-9a-f]{64}",document.get("imageId","")),"M7_DIAGNOSTIC_IDENTITY_REQUIRED")
    require(isinstance(document.get("tenants"),int) and 1<=document["tenants"]<=10
            and isinstance(document.get("replicas"),int) and 1<=document["replicas"]<=2,"M7_DIAGNOSTIC_LIMIT_INVALID")
    require(isinstance(document.get("trafficDeadlineSeconds"),int) and 1<=document["trafficDeadlineSeconds"]<=180
            and document.get("acceptedWrites")==document["tenants"] and document.get("dataHttpRequests")==4*document["tenants"],"M7_DIAGNOSTIC_COUNTS_REQUIRED")
    require(all(type(document.get(key)) is int for key in ('criterionHttpRequests','physicalHttpRequests','warmProbeHttpRequests','trailRecords','trailBytes'))
            and document.get('httpAccountingVersion')==2 and document.get('criterionHttpRequests')==4*document['tenants']
            and isinstance(document.get('warmProbeHttpRequests'),int) and 0<=document['warmProbeHttpRequests']<=512
            and document.get('physicalHttpRequests')==document['criterionHttpRequests']+document['warmProbeHttpRequests']
            and document.get('trailRecords')==document['physicalHttpRequests'] and document['trailRecords']<=4*document['tenants']+512
            and isinstance(document.get('trailBytes'),int) and 0<document['trailBytes']<=262144,'M7_DIAGNOSTIC_HTTP_ACCOUNTING_REQUIRED')
    require(document.get("verdict")=="PASS" and document.get("oracle")=="GREEN"
            and document.get("oracleControl")=={"baseline":"GREEN","broken":"RED","restored":"GREEN"}
            and isinstance(document.get("checks"),dict) and set(document["checks"])==set(DIAGNOSTIC_CHECKS) and all(value is True for value in document["checks"].values()),"M7_DIAGNOSTIC_NOT_PASSING")
    return True


MEASUREMENT_LIMITS={"tenantCounts":list(PILOT_COUNTS),"apiReplicas":1,"realtimeReplicas":1,"evaluatorReplicas":1,"maximumRunMinutes":180}
MEASUREMENT_AUTHORIZATION={'version':1,'kind':'m7-unaccepted-measurement-admission','receiptKind':'joined-measurement-authorization','receiptStatus':'AUTHORIZED_UNACCEPTED_MEASUREMENT','measurementMode':'unaccepted','profile':'remote-pilot','limits':MEASUREMENT_LIMITS,'diagnostics':'off','diagnosticsIntervalMs':5000,'functionalAcceptance':'UNACCEPTED','functionalAcceptanceAtAuthorization':'PENDING','capacityAcceptance':'NOT_GRANTED','cellKind':'m7-joined-unaccepted-measurement-cell','aggregateKind':'m7-joined-unaccepted-measurement','acceptedClaims':False}
UNACCEPTED_SCOPE={"measurementMode":"unaccepted","functionalAcceptance":"UNACCEPTED","functionalAcceptanceAtAuthorization":"PENDING","capacityAcceptance":"NOT_GRANTED"}


def is_unaccepted(document):
    return (document.get("measurementMode") == "unaccepted" or str(document.get("kind","")).startswith("m7-joined-unaccepted-measurement")
            or document.get("functionalAcceptance")=="UNACCEPTED" or document.get("functionalAcceptanceAtAuthorization")=="PENDING"
            or document.get("capacityAcceptance")=="NOT_GRANTED")


def accepted_claim_scope(document):
    require(document.get("runPurpose","acceptance")!="discovery","M7_DISCOVERY_NOT_ACCEPTANCE")
    require(not is_unaccepted(document),"M7_UNACCEPTED_MEASUREMENT_NOT_ACCEPTANCE")


def measurement_request(manifest):
    mode=manifest.get("measurementMode","accepted")
    require(mode in ("accepted","unaccepted"),"M7_MEASUREMENT_MODE_INVALID")
    if mode=="accepted":return
    require(manifest.get("profile")=="remote-pilot" and type(manifest.get("tenants")) is int and manifest["tenants"] in PILOT_COUNTS
            and type(manifest.get("replicas")) is int and manifest["replicas"]==1,"M7_UNACCEPTED_PROFILE_LIMIT")
    require(isinstance(manifest.get("runId"),str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",manifest["runId"])
            and isinstance(manifest.get("imageId"),str) and re.fullmatch(r"sha256:[a-f0-9]{64}",manifest["imageId"])
            and type(manifest.get("maximumRunMinutes")) is int and manifest["maximumRunMinutes"]==180,"M7_UNACCEPTED_RUN_IMAGE_REQUIRED")
    from profile_provenance import selection
    require(manifest.get("diagnostics")==selection('off',5000),"M7_UNACCEPTED_DIAGNOSTICS_REQUIRED")


def measurement_topology(manifest,config):
    if manifest.get("measurementMode")!="unaccepted":return
    services=config.get('services',{})
    for role in ('api','realtime','evaluator'):
        names=[name for name,row in services.items() if isinstance(row.get('command'),list) and row['command'][-1:]==[role]]
        require(names==[role],"M7_UNACCEPTED_ROLE_TOPOLOGY")
    require(not any('vault-agent' in name for name in services) and isinstance(services.get('vault',{}).get('command'),list)
            and services['vault']['command'][:2]==['vault','server'],"M7_UNACCEPTED_VAULT_SERVER_REQUIRED")


def measurement_output(manifest,aggregate=False,complete=True):
    if manifest.get('measurementMode')!='unaccepted':return {}
    return {**UNACCEPTED_SCOPE,'kind':'m7-joined-unaccepted-measurement' if aggregate else 'm7-joined-unaccepted-measurement-cell',
            'runId':manifest['runId'],'maximumRunMinutes':manifest['maximumRunMinutes'],'collectionStatus':'COMPLETE' if complete else 'FAILED'}


def unaccepted_check(document):
    require(document.get('kind')=='m7-joined-unaccepted-measurement' and all(document.get(k)==v for k,v in UNACCEPTED_SCOPE.items()),'M7_UNACCEPTED_RESULT_SCOPE')
    measurement_request({**document,'profile':'remote-pilot','tenants':500,'replicas':document.get('profileReplicas')})
    require(document.get('collectionStatus')=='COMPLETE' and document.get('verdict')=='PASS','M7_UNACCEPTED_COLLECTION_INCOMPLETE')
    for row in document.get('cells',[]):
        require(row.get('kind')=='m7-joined-unaccepted-measurement-cell' and all(row.get(k)==v for k,v in UNACCEPTED_SCOPE.items())
                and row.get('runId')==document['runId'] and row.get('maximumRunMinutes')==180 and row.get('collectionStatus')=='COMPLETE','M7_UNACCEPTED_CELL_SCOPE')
    return _pilot_check(document,'m7-joined-unaccepted-measurement')


def discovery_authorization(manifest, receipt):
    """Version 1 preserves the original PENDING contract; v2 binds projections."""
    version=receipt.get('version',1)
    require(type(version) is int and version in (1,2),'M7_DIAGNOSTIC_RECEIPT_VERSION')
    require('commissioningSlotWalMiB' not in manifest or version==2,
            'M7_COMMISSIONING_SLOT_WAL_BOUND_RECEIPT_REQUIRED')
    if version==1:return dict(UNACCEPTED_SCOPE)
    from run_configuration import sha
    import static_topology
    static_topology.receipt(manifest,receipt)
    resolved=manifest.get('runConfiguration')
    require(isinstance(resolved,dict) and receipt.get('configurationSha256')==sha(resolved),
            'M7_DIAGNOSTIC_CONFIGURATION_MISMATCH')
    require(resolved.get('staticTopology') == manifest.get('staticTopology') and
            resolved.get('staticBuildReceiptSha256') == manifest.get('staticBuildReceiptSha256'),
            'M7_STATIC_CONFIGURATION_MISMATCH')
    require(all(resolved.get(k)==manifest.get(k) for k in ('pair','imageId','tenants','replicas','cadence'))
            and resolved.get('instrument')==manifest['instrument']['sha256'], 'M7_DIAGNOSTIC_CONFIGURATION_MISMATCH')
    import commissioning_wal
    commissioning_wal.from_manifest(manifest)
    require((commissioning_wal.FIELD in resolved)==(commissioning_wal.FIELD in manifest)
            and resolved.get(commissioning_wal.FIELD)==manifest.get(commissioning_wal.FIELD),
            'M7_DIAGNOSTIC_CONFIGURATION_MISMATCH')
    require(receipt.get('purpose')=='BOUNDED_DISCOVERY' and resolved.get('runPurpose')=='discovery',
            'M7_DIAGNOSTIC_PURPOSE_REQUIRED')
    execution=receipt.get('execution')
    require(isinstance(execution, dict) and set(execution) == {'workSeconds', 'cleanupSeconds', 'k6Image'},
            'M7_DIAGNOSTIC_EXECUTION_LIMIT')
    work = execution['workSeconds']
    cadence = resolved.get('cadence', {})
    phase_seconds = sum(cadence.get(k, 86400) for k in ('warmupSeconds','idleSeconds','loadSeconds'))
    phase_seconds += sum(cadence.get(key, 0) for key in ('setupSeconds','drainSeconds'))
    work_ok = (receipt.get('executionScope') == 'LOCAL_OWNED_TO_COMPLETION' if work is None
               else type(work) is int and 30 <= work <= 86400 and phase_seconds < work)
    require(work_ok and type(execution['cleanupSeconds']) is int and 30 <= execution['cleanupSeconds'] <= 3600
            and re.fullmatch('sha256:[a-f0-9]{64}', execution.get('k6Image', '')),
            'M7_DIAGNOSTIC_EXECUTION_LIMIT')
    acceptance=receipt.get('sourceAcceptance')
    require(isinstance(acceptance,dict) and acceptance.get('status') in ('PENDING','PASS')
            and receipt.get('functionalAcceptanceAtAuthorization')==acceptance['status'], 'M7_DIAGNOSTIC_ACCEPTANCE_STATUS')
    if acceptance['status']=='PENDING':
        require(set(acceptance)=={'status'},'M7_DIAGNOSTIC_PENDING_EVIDENCE')
    else:
        require(set(acceptance)=={'status','reference','sha256'} and isinstance(acceptance['reference'],str)
                and Path(acceptance['reference']).is_absolute() and re.fullmatch('[a-f0-9]{64}',acceptance.get('sha256','')),
                'M7_DIAGNOSTIC_ACCEPTANCE_EVIDENCE')
        evidence=Path(acceptance['reference'])
        require(evidence.is_file() and digest(evidence)==acceptance['sha256'],'M7_DIAGNOSTIC_ACCEPTANCE_EVIDENCE')
        value=json.loads(evidence.read_text())
        require(value.get('kind')=='joined-acceptance' and value.get('status')=='PASS'
                and value.get('pair')==manifest['pair'] and value.get('imageId')==manifest['imageId']
                and re.fullmatch('[a-f0-9]{64}',value.get('instrument',''))
                and re.fullmatch('[a-f0-9]{64}',value.get('evidenceSha256','')), 'M7_DIAGNOSTIC_ACCEPTANCE_TUPLE')
    return {'authorizationVersion':2,'measurementMode':'diagnostic','functionalAcceptance':acceptance['status'],
            'functionalAcceptanceAtAuthorization':acceptance['status'],'sourceAcceptance':acceptance,
            'configurationSha256':receipt['configurationSha256'],'capacityAcceptance':'NOT_GRANTED',
            **({'executionScope': 'LOCAL_OWNED_TO_COMPLETION'} if work is None else {})}


def discovery_scope(manifest):
    return manifest.get('discoveryAuthorization',dict(UNACCEPTED_SCOPE))


def check_discovery_scope(value):
    if value.get('authorizationVersion')!=2:
        require(all(value.get(k)==v for k,v in UNACCEPTED_SCOPE.items()),'M7_DISCOVERY_PENDING_SCOPE')
        return
    status=value.get('functionalAcceptanceAtAuthorization')
    require(status in ('PENDING','PASS') and value.get('functionalAcceptance')==status
            and value.get('sourceAcceptance',{}).get('status')==status and value.get('measurementMode')=='diagnostic'
            and value.get('capacityAcceptance')=='NOT_GRANTED' and re.fullmatch('[a-f0-9]{64}',value.get('configurationSha256','')),
            'M7_DISCOVERY_ACCEPTANCE_SCOPE')

    acceptance=value['sourceAcceptance']
    if status=='PENDING':
        require(set(acceptance)=={'status'},'M7_DISCOVERY_ACCEPTANCE_SCOPE')
    else:
        require(set(acceptance)=={'status','reference','sha256'} and isinstance(acceptance['reference'],str)
                and Path(acceptance['reference']).is_absolute() and re.fullmatch('[a-f0-9]{64}',acceptance.get('sha256','')),
                'M7_DISCOVERY_ACCEPTANCE_SCOPE')
