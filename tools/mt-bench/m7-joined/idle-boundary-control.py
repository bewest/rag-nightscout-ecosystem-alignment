#!/usr/bin/env python3
"""In-memory semantic controls; no target source edits or runtime resources."""
import pathlib,sys,types,unittest
import evaluator_idle as idle
import adapter
which=sys.argv[1]
if which=='omit-after-finally':
    original=adapter.enabled_idle
    def broken(d,m,out,seconds):
        adapter.phase_snapshot(d,out,'before')
        with adapter.sampling(d,out),adapter.observe_progress(d,m,out,'idle') as progress:adapter.time.sleep(seconds)
        adapter.phase_snapshot(d,out,'after')
        return progress
    adapter.enabled_idle=broken
    suite=unittest.defaultTestLoader.loadTestsFromName('test_idle_bookends.Bookends')
else:
    needle="i<2 and last['completedTimeCycles']>rows[i]['completedTimeCycles']"
    replacements={'old-boundary':"i<2 and rows[i]['dueAt']<=min(v['start']['wallUs'] for v in rounds[-1]['readWindows'].values())/1000 and last['completedTimeCycles']>rows[i]['completedTimeCycles']",'mask-all-opportunities':'True'}
    source=pathlib.Path(idle.__file__).read_text();assert source.count(needle)==1
    module=types.ModuleType('evaluator_idle');module.__file__=idle.__file__
    exec(compile(source.replace(needle,replacements[which]),'in_memory_idle_control','exec'),module.__dict__)
    sys.modules['evaluator_idle']=module
    suite=unittest.defaultTestLoader.loadTestsFromName('test_evaluator_idle.Idle')
result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
