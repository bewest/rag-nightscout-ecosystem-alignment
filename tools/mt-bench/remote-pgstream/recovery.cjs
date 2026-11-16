'use strict';
// The controller's restart can lag the generator arm. Old-connection frames
// never prove recovery, even if their timestamp is after the arm timestamp.
function recoveredAfterRestart(socket,arm,at,acknowledged){
  return acknowledged===true&&socket.connected===true&&socket.disconnectCount>arm.disconnectCount&&socket.connects>arm.connects&&
    socket.connectionFrames.some(frame=>frame.at>=at&&frame.connection>arm.connects&&frame.disconnectCount>arm.disconnectCount);
}
module.exports={recoveredAfterRestart};
