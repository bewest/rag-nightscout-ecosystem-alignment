"""Reused generator dependencies: copied when the lockfile matches; nothing hashed."""
from pathlib import Path
import tempfile
import unittest
import dependency_reuse as r

PACKAGE, LOCK = b'{"name":"synthetic"}', b'{"lockfileVersion":3}'


class DependencyReuse(unittest.TestCase):
    def tree(self, root):
        root.mkdir(); (root/'package.json').write_bytes(PACKAGE); (root/'package-lock.json').write_bytes(LOCK)
        (root/'node_modules/pg').mkdir(parents=True); (root/'node_modules/pg/index.js').write_text('module.exports={}')
        return root

    def test_copy_when_lock_matches_and_refuse_a_different_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.tree(Path(tmp)/'source')
            q = r.preflight(source=source, package_bytes=PACKAGE, lock_bytes=LOCK)
            with self.assertRaisesRegex(RuntimeError, 'SOURCE_LOCK'):
                r.preflight(source=source, package_bytes=PACKAGE, lock_bytes=b'{}')
            r.copy_owned(destination=Path(tmp)/'copy', qualification=q, package_bytes=PACKAGE, lock_bytes=LOCK)
            self.assertTrue((Path(tmp)/'copy/node_modules/pg/index.js').is_file())
            self.assertTrue((Path(tmp)/'copy/dependency-reuse-ready.json').is_file())
            with self.assertRaisesRegex(RuntimeError, 'TARGET_EXISTS'):
                r.copy_owned(destination=Path(tmp)/'copy', qualification=q, package_bytes=PACKAGE, lock_bytes=LOCK)


if __name__ == '__main__':
    unittest.main()
