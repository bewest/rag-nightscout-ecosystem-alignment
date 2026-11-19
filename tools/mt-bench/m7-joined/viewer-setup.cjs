// Inlined into the generated local and Kubernetes probes. The same stock
// Socket.IO callbacks and authorization exchange remain responsible for frames.
async function primeViewers(out, selection) {
  const { opensPerSecond, stallSeconds, transport, scenario } = selection;
  if (!(Number.isFinite(opensPerSecond) && opensPerSecond > 0 &&
        Number.isSafeInteger(stallSeconds) && stallSeconds > 0 &&
        ['websocket-first', 'polling'].includes(transport) &&
        ['ordinary', 'simultaneous-reconnect'].includes(scenario)))
    throw Error('M7_VIEWER_SETUP_CONFIGURATION');
  delete out.args.open;  // Only the legacy actor uses the --open millisecond interval.
  const start = performance.now();
  let lastProgress = start, stopped = false, timer;
  const progress = out.viewerSetup = {
    ...selection, requested: TOTAL, exchanged: 0, opened: 0,
    initial: { connected: 0, firstFrames: 0, transports: {} },
    reconnect: null, elapsedMs: 0, status: 'RUNNING'
  };
  let epoch = progress.initial;
  const stallMs = stallSeconds * 1000;
  function check() {
    if (stopped || performance.now() - lastProgress >= stallMs)
      throw Error('M7_VIEWER_SETUP_STALLED');
  }
  function advanced() {
    const now = performance.now();
    if (stopped || now - lastProgress >= stallMs) return false;
    lastProgress = now;
    return true;
  }
  function observe(slot, counters) {
    let connected = false, received = false;
    slot.once('connect', () => {
      if (!advanced()) return;
      connected = true;
      counters.connected++;
    });
    slot.on('dataUpdate', function firstFrame() {
      if (received || !connected || !slot.connected || !advanced()) return;
      received = true;
      counters.firstFrames++;
      const name = slot.io.engine.transport.name;
      counters.transports[name] = (counters.transports[name] || 0) + 1;
      slot.off('dataUpdate', firstFrame);
    });
  }
  async function work() {
    const jwts = new Array(tenants.length);
    let nextTenant = 0;
    const x0 = performance.now();
    // Bound concurrent exchanges independently of the connection ramp.
    await Promise.all(Array.from({ length: Math.min(16, tenants.length) }, async () => {
      while (nextTenant < tenants.length) {
        check();
        const index = nextTenant++;
        if (viewers[index] === 0) continue;
        jwts[index] = await exchange(tenants[index]);
        if (!advanced()) throw Error('M7_VIEWER_SETUP_STALLED');
        progress.exchanged++;
      }
    }));
    out.exchangeMs = performance.now() - x0;
    let nextOpen = performance.now();
    for (let i = 0; i < tenants.length; i++) {
      for (let n = 0; n < viewers[i]; n++) {
        while (performance.now() < nextOpen) {
          check();
          await sleep(Math.min(2147483647, Math.ceil(nextOpen - performance.now())));
        }
        check();
        open(i, jwts[i]);
        observe(sockets.at(-1).socket, epoch);
        progress.opened++;
        // Never catch up a delayed scheduler by opening a burst.
        nextOpen = performance.now() + 1000 / opensPerSecond;
      }
    }
    async function waitForFrames() {
      while (epoch.firstFrames !== TOTAL || sockets.some(s => !s.connected)) {
        check();
        await sleep(Math.min(100, stallMs));
      }
      check();
    }
    await waitForFrames();
    if (scenario === 'simultaneous-reconnect') {
      if (!TOTAL) throw Error('M7_VIEWER_RECONNECT_EMPTY');
      epoch = progress.reconnect = { connected: 0, firstFrames: 0, transports: {} };
      for (const s of sockets) s.socket.disconnect();
      for (const s of sockets) observe(s.socket, epoch);
      for (const s of sockets) s.socket.connect();
      await waitForFrames();
    }
  }
  // Detect a stall even while the actor is waiting for a pending HTTP response.
  const expiry = new Promise((_, reject) => {
    function arm() {
      const left = lastProgress + stallMs - performance.now();
      if (left <= 0) reject(Error('M7_VIEWER_SETUP_STALLED'));
      else timer = setTimeout(arm, Math.min(2147483647, Math.ceil(left)));
    }
    arm();
  });
  try {
    await Promise.race([work(), expiry]);
    progress.status = 'COMPLETE';
  } catch (error) {
    progress.status = 'INCOMPLETE';
    progress.code = error.message === 'M7_VIEWER_SETUP_STALLED'
      ? error.message : 'M7_VIEWER_SETUP_INCOMPLETE';
    progress.reasons = { ...reasons };
    for (const s of sockets) s.socket.close();
    throw Error(progress.code);
  } finally {
    stopped = true;
    clearTimeout(timer);
    progress.elapsedMs = performance.now() - start;
    progress.lastProgressElapsedMs = lastProgress - start;
    savePartial();
  }
}
