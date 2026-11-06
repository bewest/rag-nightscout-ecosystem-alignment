"""Exercise the acceptance oracle with deliberate shape-preserving corruption."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

LAB = Path(__file__).parent


class ClassifierTests(unittest.TestCase):
    def classify(self, a, b):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, cells in [('a', a), ('b', b)]:
                (root / (name + '.json')).write_text(json.dumps({'cells': cells}))
            result = subprocess.run(['python3', '-I', str(LAB / 'classify.py'), str(root / 'a.json'),
                                     str(root / 'b.json'), str(LAB / 'groups.yaml'), str(root / 'out.json')],
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

    def test_same_values_restore_green(self):
        c = {'entries v1 synthetic': {'st': '200 [1]', 'documents': ['{"sgv":118}']}}
        self.assertEqual(self.classify(c, c)['unexplained'], 0)

    def test_same_shape_corruption_is_unexplained(self):
        a = {'entries v1 synthetic': {'st': '200 [1]', 'documents': ['{"sgv":118}']}}
        b = {'entries v1 synthetic': {'st': '200 [1]', 'documents': ['{"sgv":119}']}}
        self.assertEqual(self.classify(a, b)['unexplained'], 1)

    def test_missing_cells_are_reported_both_ways(self):
        c = {'entries v1 synthetic': {'st': '200 [1]'}}
        self.assertEqual(self.classify(c, {})['missing_in_preview'], list(c))
        self.assertEqual(self.classify({}, c)['missing_in_baseline'], list(c))


if __name__ == '__main__':
    unittest.main()
