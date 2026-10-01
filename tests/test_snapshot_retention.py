import gzip
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('retention', Path(__file__).resolve().parents[1] / 'tools/prune_dashboard_snapshots.py')
retention = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retention)


class SnapshotRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = []
        for i in range(4):
            path = self.root / f'dashboard-merged-{i:012x}.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE notes (text TEXT)')
                conn.execute('INSERT INTO notes VALUES (?)', ('private review ' * 500,))
            conn.close()
            when = time.time() - (20-i) * 86400
            os.utime(path, (when, when))
            self.paths.append(path)

    def test_preview_writes_nothing(self):
        result = retention.prune(self.root, keep=1)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(p.exists() for p in self.paths))
        self.assertFalse((self.root / 'snapshot-archives').exists())

    def test_full_byte_for_byte_backup_before_delete(self):
        before = {str(p): p.read_bytes() for p in self.paths}
        result = retention.prune(self.root, apply=True, keep=1, max_delete=2)
        self.assertEqual(len(result), 2)
        for row in result:
            self.assertEqual(row['status'], 'archived-and-removed', row)
            with gzip.open(row['archive'], 'rb') as stream:
                self.assertEqual(stream.read(), before[row['path']])
            self.assertFalse(Path(row['path']).exists())
        self.assertTrue(self.paths[-1].exists())

    def test_sidecar_protected_and_source_db_never_deleted(self):
        Path(str(self.paths[1]) + '-wal').touch()
        other = self.root / 'gha-jobs.db'
        other.write_bytes(b'untouched')
        result = retention.prune(self.root, apply=True, keep=1, protected=[self.paths[0]])
        self.assertEqual(len(result), 1)
        self.assertTrue(self.paths[0].exists())
        self.assertTrue(self.paths[1].exists())
        self.assertEqual(other.read_bytes(), b'untouched')

    def test_backup_failure_preserves_original(self):
        with patch.object(retention.gzip, 'open', side_effect=OSError('disk full')):
            result = retention.prune(self.root, apply=True, keep=1)
        self.assertTrue(all(r['status'] == 'retained' for r in result))
        self.assertTrue(all(p.exists() for p in self.paths))

    def test_corrupt_snapshot_retained(self):
        self.paths[0].write_bytes(b'corrupt')
        old = time.time() - 30 * 86400
        os.utime(self.paths[0], (old, old))
        result = retention.prune(self.root, apply=True, keep=1)
        row = next(r for r in result if r['path'] == str(self.paths[0]))
        self.assertEqual(row['status'], 'retained')
        self.assertTrue(self.paths[0].exists())
