function dex_to_entry (d) {
/*
[ { DT: '/Date(1426292016000-0700)/',
    ST: '/Date(1426295616000)/',
    Trend: 4,
    Value: 101,
    WT: '/Date(1426292039000)/' } ]
*/
  var regex = /\((.*)\)/;
  var wall = parseInt(d.WT.match(regex)[1]);
  var date = new Date(wall);
  var trend = matchTrend(d.Trend);
  
  var entry = {
    sgv: d.Value
  , date: wall
  , dateString: date.toISOString( )
  , trend: trend
  , direction: trendToDirection(trend)
  , device: 'share2'
  , type: 'sgv'
  };
  return entry;
}
