'use strict';

const assert = require('node:assert/strict');
function committed (deliveries) {
  assert.ok(deliveries.length > 0, 'Expected actual logical events');
  for (const delivery of deliveries) assert.equal(delivery.commitAcknowledged, true, 'EVENT_BEFORE_COMMIT');
}
function tenant (event, expected) {
  assert.equal(event.tenant, expected, 'EVENT_TENANT_CAPTURE_MISMATCH');
}
function finalFloor (event, independent, expectedTenant) {
  tenant(event, expectedTenant);
  assert.equal(event.stamp, independent.floor, 'EVENT_FINAL_FLOOR_MISMATCH');
}
function rowStamp (stored, allocation, expectedTenant) {
  assert.equal(stored.tenant_id, expectedTenant, 'PHYSICAL_TENANT_MISMATCH');
  assert.equal(stored.doc.srvModified, allocation, 'PHYSICAL_ALLOCATION_MISMATCH');
}
module.exports = { committed, tenant, finalFloor, rowStamp };
