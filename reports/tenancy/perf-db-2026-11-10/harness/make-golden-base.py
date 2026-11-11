import subprocess
s=subprocess.check_output(['git','show','540d3998:lib/server/serve/preview-domains.js']).decode()
s=s.replace("      const graph = createLegacy({ env, ctx, domains: legacyNames });","      graph = createLegacy({ env, ctx, domains: legacyNames });")
s=s.replace("    let frameService, snapshotPorts;","    let frameService, snapshotPorts, graph;")
s=s.replace("services.set(tenant, { initialize, env, storagePorts, frameService, snapshotPorts, context, contextFor });","services.set(tenant, { initialize, env, storagePorts, frameService, snapshotPorts, context, contextFor, routes, graph, collections, ports });")
new=open('lib/server/serve/preview-domains.js').read()
desc=new[new.index("  function describeTenant (tenant) {"):new.index("  return { data, legacyRouter")]
desc=desc.replace("const service = serviceOf(tenant), seen","const service = services.get(tenant), seen")
s=s.replace("  return { data, legacyRouter, rootRouter, safeRoutes, v3Names, legacyNames, socketContextFor,",desc+"  return { data, legacyRouter, rootRouter, safeRoutes, v3Names, legacyNames, socketContextFor, describeTenant,")
open('lib/server/serve/.preview-domains-base.js','w').write(s)
