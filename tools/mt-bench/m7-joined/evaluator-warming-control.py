#!/usr/bin/env python3
"""In-memory collector ablations only; no target source mutation or resources."""
from pathlib import Path
import sys
import types
import unittest
import evaluator_progress as p

specs={
    'old-age':("first_release=warming and all(value[k]==0 for k in ('completedAcquisitions','completedTimeCycles','failedCompletions'))","first_release=False"),
    'unscoped-age':("first_release=warming and all(value[k]==0 for k in ('completedAcquisitions','completedTimeCycles','failedCompletions'))","first_release=True"),
    'omit-diagnostic':("'diagnostic':getattr(error,'diagnostic',None)","'diagnostic':None"),
}
needle,replacement=specs[sys.argv[1]]
source=Path(p.__file__).read_text();assert source.count(needle)==1
module=types.ModuleType('evaluator_progress');module.__file__=p.__file__
exec(compile(source.replace(needle,replacement),'in_memory_collector_control','exec'),module.__dict__)
sys.modules['evaluator_progress']=module
suite=unittest.defaultTestLoader.loadTestsFromName('test_evaluator_warming.Warming')
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
