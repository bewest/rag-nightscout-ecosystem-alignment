"""Typed observed k6 1.3.0 summary export; absent metrics never become zero."""
import copy,math,tempfile,unittest
from pathlib import Path
import protocol

class K6Schema(unittest.TestCase):
    def probe(self):
        return {'prime':{'primed':20},'window':{'deliveredFrames':1,'expectedFrames':1,'writes':{'failed':0},'sockets':20,'connectedAtEnd':20,'writeToEvaluationMs':{'measurement':'UNMEASURED','reason':'Per-write SQL latency observer NOT_RUN; strict progress remains app-side; no cross-host latency inferred'}}}
    def metrics(self):
        return {**{k:{'count':0,'rate':0,'thresholds':{'count>=0':False}}for k in ('writes_refused','responses_refused','dropped_iterations')},'http_req_failed':{'passes':0,'fails':60,'value':0}}
    def test_observed_raw_rate_and_legacy_wrapped_model(self):
        self.assertTrue(protocol.traffic_verdict(self.probe(),self.metrics(),10))
        for row,expected in [({'passes':49,'fails':10,'value':49/59},49/59),({'passes':0,'fails':0,'value':0},0),({'values':{'rate':0.5}},0.5)]:self.assertEqual(protocol.k6_metric({'rate':row},'rate','rate'),expected)
        self.assertEqual(protocol.k6_metric({'counter':{'values':{'count':0}}},'counter'),0)
    def test_missing_and_positive_refusal_drop_rate_are_not_green(self):
        for key in ('writes_refused','responses_refused','dropped_iterations','http_req_failed'):
            m=self.metrics();del m[key]
            with self.assertRaisesRegex(RuntimeError,'METRIC_MISSING'):protocol.traffic_verdict(self.probe(),m,10)
        for key in ('writes_refused','responses_refused','dropped_iterations'):
            m=self.metrics();m[key]={'count':1,'rate':1}
            with self.assertRaisesRegex(RuntimeError,'HTTP_FAILED'):protocol.traffic_verdict(self.probe(),m,10)
        m=self.metrics();m['http_req_failed']={'passes':49,'fails':10,'value':49/59}
        with self.assertRaisesRegex(RuntimeError,'HTTP_FAILED'):protocol.traffic_verdict(self.probe(),m,10)
    def test_raw_rate_rejects_malformed_types_aliases_and_inconsistent_ratio(self):
        good={'passes':0,'fails':60,'value':0}
        bads=[{'rate':0},{'values':{'value':0}},{'values':{'rate':False}},{'values':{'rate':float('nan')}},{**good,'value':0.5},{**good,'value':float('nan')},{**good,'value':False},{**good,'passes':True},{**good,'fails':0.5},{**good,'fails':-1},{**good,'extra':0},{'value':1,'passes':0,'fails':0}]
        for row in bads:
            with self.subTest(row=row),self.assertRaisesRegex(RuntimeError,'METRIC_INVALID'):protocol.k6_metric({'m':row},'m','rate')
    def test_counter_rejects_malformed_missing_fractional_bool_and_nan(self):
        for row in ({'rate':0},{'count':False},{'count':0.0},{'count':-1},{'count':float('nan')},{'count':0,'rate':float('nan')},{'count':0,'rate':1},{'count':0,'unknown':0},{'values':{'count':True}},{'count':0,'thresholds':{'count>=0':'false'}}):
            with self.subTest(row=row),self.assertRaisesRegex(RuntimeError,'METRIC_INVALID'):protocol.k6_metric({'m':row},'m')
    def test_actual_workload_producer_initializes_all_required_zero_metrics(self):
        import sys
        root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'tools/mt-bench/m7-joined'));import workload
        with tempfile.TemporaryDirectory()as tmp:
            out=Path(tmp)/'workload.js';workload.generate(root,out);source=out.read_text()
            for key in ('writes_refused','responses_refused','dropped_iterations'):self.assertIn(key+":[\'count>=0\']",source)

if __name__=='__main__':unittest.main()
