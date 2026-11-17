'use strict';
// Embedded verbatim in the generated k6 workload. Never retain body, URL or error text.
// BEGIN_K6_HTTP_ACCOUNTING
function classifyHttp(response, expected, mutation) {
  const observed = response && response.status;
  const status = Number.isInteger(observed) && (observed === 0 || observed >= 100 && observed <= 599) ? observed : 0;
  // k6 error code 1050 is its request timeout observation. Other transport causes
  // remain unknown; status 5xx says nothing about whether a mutation committed.
  const category = status === 0 ? (response && response.error_code === 1050 ? 'timeout' : 'transport') :
    expected.includes(status) ? 'http_expected' : status >= 400 && status < 500 ? 'http_refused' : 'http_unexpected';
  const writeOutcome = !mutation ? null : category === 'http_expected' ? 'accepted' : category === 'http_refused' ? 'refused' : 'uncertain';
  return {status, category, writeOutcome};
}
function recordHttp(shape, response, expected, mutation) {
  const value = classifyHttp(response, expected, mutation);
  httpCompleted.add(1, {http_shape:shape, status:String(value.status), category:value.category});
  if (value.writeOutcome) httpWriteOutcome.add(1, {http_shape:shape, outcome:value.writeOutcome});
  return value;
}
function httpAccountingThresholds(thresholds, selected) {
  // Only called by the existing main-context metadata guard. One bounded metric,
  // no tenant cross product, no per-VU histogram/map, no per-request log.
  for (const shape of ['jwt_setup', ...selected]) {
    thresholds[`m7_http_attempts{http_shape:${shape}}`] = ['count>=0'];
    thresholds[`m7_http_completed{http_shape:${shape}}`] = ['count>=0'];
    for (const status of [0, ...Array.from({length:500}, (_, i) => i + 100)])
      thresholds[`m7_http_completed{http_shape:${shape},status:${status}}`] = ['count>=0'];
    for (const category of ['http_expected','http_refused','http_unexpected','timeout','transport'])
      thresholds[`m7_http_completed{http_shape:${shape},category:${category}}`] = ['count>=0'];
    if (shape.startsWith('w_')) for (const outcome of ['accepted','refused','uncertain'])
      thresholds[`m7_http_write_outcome{http_shape:${shape},outcome:${outcome}}`] = ['count>=0'];
  }
}
// END_K6_HTTP_ACCOUNTING
module.exports = {classifyHttp};
