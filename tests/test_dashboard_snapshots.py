import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.webapp import _copy_db_file, _safe_merge_dashboard_db


class DashboardSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.db"
        conn = sqlite3.connect(self.source)
        conn.execute("CREATE TABLE jobs (key TEXT, score INTEGER, source TEXT, posted TEXT, first_seen TEXT, last_seen TEXT)")
        conn.execute("INSERT INTO jobs VALUES ('one', 60, 'test', '', '2026-09-18', '2026-09-18')")
        conn.commit()
        conn.close()
        self.snap = {"path": self.source, "fresh_ts": 1, "recent_jobs_24h": 1, "total_jobs": 1}

    def merge(self):
        return _safe_merge_dashboard_db(str(self.root), [self.snap], strategy_label="test")

    def test_unchanged_source_reuses_open_snapshot_without_erasing_rescore(self):
        first, _ = self.merge()
        conn = sqlite3.connect(first)
        try:
            conn.execute("UPDATE jobs SET score=75")
            conn.commit()
            with patch("src.webapp._copy_db_file", side_effect=AssertionError("must reuse snapshot")):
                second, _ = self.merge()
            self.assertEqual(first, second)
            self.assertEqual(conn.execute("SELECT score FROM jobs").fetchone()[0], 75)
        finally:
            conn.close()

    def test_source_change_publishes_new_snapshot_and_preserves_old_one(self):
        first, _ = self.merge()
        previous = self.source.stat()
        conn = sqlite3.connect(self.source)
        conn.execute("UPDATE jobs SET score=85")
        conn.commit()
        conn.close()
        os.utime(self.source, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000))
        second, _ = self.merge()
        self.assertNotEqual(first, second)
        for path, expected in ((first, 60), (second, 85)):
            conn = sqlite3.connect(path)
            try:
                self.assertEqual(conn.execute("SELECT score FROM jobs").fetchone()[0], expected)
            finally:
                conn.close()

    def test_simultaneous_builders_share_one_published_snapshot(self):
        with patch("src.webapp._copy_db_file", wraps=_copy_db_file) as copy:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.merge(), range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(copy.call_count, 2)

    def test_backup_timeout_is_bounded(self):
        with patch("src.webapp.time.monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(sqlite3.OperationalError, "snapshot timed out"):
                _copy_db_file(self.source, self.root / "copy.db")

    def test_copy_refuses_existing_database(self):
        with self.assertRaises(FileExistsError):
            _copy_db_file(self.source, self.source)
        conn = sqlite3.connect(self.source)
        self.assertEqual(conn.execute("SELECT score FROM jobs").fetchone()[0], 60)
        conn.close()

    def test_failed_build_does_not_publish_partial_snapshot_or_retry(self):
        with patch("src.webapp._copy_db_file", side_effect=sqlite3.OperationalError("busy")) as copy:
            path, strategy = self.merge()
        self.assertEqual(path, self.source)
        self.assertEqual(strategy, "test-fallback")
        self.assertEqual(copy.call_count, 1)
        self.assertEqual(list((self.root / "state").glob("dashboard-merged-*.db")), [])


if __name__ == "__main__":
    unittest.main()
