const root = process.argv[2];
const dl = require(root + '/lib/authorization/delaylist')({settings:{authFailDelay:5000}});
if (dl.keysFor) {
  const k1 = dl.keysFor({ip:'10.0.0.1', token:'bad-token-1'});
  const k2 = dl.keysFor({ip:'10.0.0.1', token:'bad-token-2'});
  const k3 = dl.keysFor({ip:'10.0.0.9', token:'bad-token-1'});
  console.log('FIXED keys(ip,tok1)=', k1.map(s=>s.slice(0,12)+'..'));
  dl.addFailedRequest(k1);
  console.log('  after 1 fail: same ip+tok1 ->', dl.shouldDelayRequest(k1), 'ms; same ip new tok ->', dl.shouldDelayRequest(k2), 'ms; new ip same tok ->', dl.shouldDelayRequest(k3), 'ms');
  dl.addFailedRequest(k2); dl.addFailedRequest(k2);
  console.log('  after 2 more fails on tok2 from same ip: addr delay ->', dl.shouldDelayRequest(dl.keysFor({ip:'10.0.0.1'})), 'ms');
  console.log('  anonymous (no credential) keys ->', dl.keysFor({ip:'10.0.0.1'}).length, 'key(s) ; delay ->', dl.shouldDelayRequest(dl.keysFor({ip:'10.0.0.1'})));
} else {
  dl.addFailedRequest('10.0.0.1');
  console.log('DEV after 1 fail: shouldDelayRequest("10.0.0.1") ->', dl.shouldDelayRequest('10.0.0.1'), 'ms');
  dl.addFailedRequest('10.0.0.1'); dl.addFailedRequest('10.0.0.1');
  console.log('DEV after 3 fails ->', dl.shouldDelayRequest('10.0.0.1'), 'ms  (applied to EVERY later request from that ip, authenticated or not)');
  console.log('DEV raw key stored in the in-memory object:', Object.keys(dl).filter(k=>typeof dl[k]!=="function"));
}
