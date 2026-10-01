import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3

from src.webapp import _safe_merge_dashboard_db


class DashboardDiskSpaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.source = Path(self.temp) / "source.db"
        conn = sqlite3.connect(self.source)
        conn.execute("CREATE TABLE jobs (key TEXT, source TEXT, posted TEXT, first_seen TEXT, last_seen TEXT)")
        conn.execute("INSERT INTO jobs VALUES ('one','test','','2026-09-24','2026-09-24')")
        conn.commit()
        conn.close()
        self.snap = {"path": self.source, "fresh_ts": 1, "recent_jobs_24h": 1, "total_jobs": 1}

    def merge(self):
        return _safe_merge_dashboard_db(self.temp, [self.snap], strategy_label="test")

    def test_low_disk_stops_before_copying_and_preserves_source(self):
        with patch("src.webapp.shutil.disk_usage", return_value=SimpleNamespace(free=100)), \
             patch("src.webapp._copy_db_file") as copy, \
             self.assertLogs("src.webapp", level="WARNING") as logs:
            path, strategy = self.merge()
        self.assertEqual(path, self.source)
        self.assertEqual(strategy, "test-fallback")
        copy.assert_not_called()
        self.assertIn("Insufficient free space", logs.output[0])
        self.assertTrue(self.source.exists())
        self.assertEqual(list((Path(self.temp) / "state").iterdir()), [])

    def test_healthy_existing_snapshot_is_reused_even_with_low_disk(self):
        with patch("src.webapp.shutil.disk_usage", return_value=SimpleNamespace(free=10 * 1024 ** 3)):
            original = self.merge()
        with patch("src.webapp.shutil.disk_usage", return_value=SimpleNamespace(free=0)), \
             patch("src.webapp._copy_db_file") as copy:
            reused = self.merge()
        self.assertEqual(original, reused)
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
