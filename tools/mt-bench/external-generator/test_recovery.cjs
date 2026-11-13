'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {recoveredAfterRestart}=require('./recovery.cjs');
test('controller delay and old connected frames cannot count as stock recovery',()=>{
  const arm={connects:1,disconnectCount:0},socket={connected:true,connects:1,disconnectCount:0,connectionFrames:[{at:1001,connection:1,disconnectCount:0}]};
  assert.equal(recoveredAfterRestart(socket,arm,1000,false),false);
  assert.equal(recoveredAfterRestart(socket,arm,1000,true),false);
});
test('only actual disconnect, reconnect and its later frame plus restart acknowledgement count',()=>{
  const arm={connects:1,disconnectCount:0},socket={connected:true,connects:2,disconnectCount:1,connectionFrames:[{at:1001,connection:1,disconnectCount:0},{at:1100,connection:2,disconnectCount:1}]};
  assert.equal(recoveredAfterRestart(socket,arm,1000,true),true);
  assert.equal(recoveredAfterRestart(socket,arm,1000,false),false);
  assert.equal(recoveredAfterRestart({...socket,connectionFrames:socket.connectionFrames.slice(0,1)},arm,1000,true),false);
  assert.equal(recoveredAfterRestart({...socket,connected:false},arm,1000,true),false);
});
