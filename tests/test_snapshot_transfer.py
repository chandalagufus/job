from contextlib import closing
import gzip
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from src.snapshot_transfer import pack, unpack
from src.webapp import _download_remote_db, GITHUB_SYNC_SOURCES


class SnapshotTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'jobs.db'
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript("CREATE TABLE jobs(key TEXT PRIMARY KEY, first_seen TEXT); INSERT INTO jobs VALUES('job:1','2026-01-01'); CREATE TABLE cursors(name TEXT,value TEXT); INSERT INTO cursors VALUES('boards_main','950');")

    def test_roundtrip_preserves_jobs_and_cursor(self):
        archive = self.root / 'state.db.gz'
        pack(self.db, archive)
        target = self.root / 'restored.db'
        unpack(archive, target)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT * FROM jobs').fetchall(), [('job:1', '2026-01-01')])
            self.assertEqual(db.execute('SELECT * FROM cursors').fetchall(), [('boards_main', '950')])

    def test_oversize_fails_without_replacing_previous_archive(self):
        archive = self.root / 'state.gz'
        archive.write_bytes(b'previous')
        with self.assertRaises(ValueError):
            pack(self.db, archive, max_bytes=1)
        self.assertEqual(archive.read_bytes(), b'previous')

    def test_corrupt_download_preserves_existing_database(self):
        original = self.db.read_bytes()
        with patch('src.webapp.urlopen', return_value=io.BytesIO(gzip.compress(b'not sqlite'))):
            with self.assertRaises(sqlite3.DatabaseError):
                _download_remote_db('https://example.test/jobs.db.gz', self.db)
        self.assertEqual(self.db.read_bytes(), original)

    def test_download_supports_compressed_database(self):
        target = self.root / 'download.db'
        with patch('src.webapp.urlopen', return_value=io.BytesIO(gzip.compress(self.db.read_bytes()))):
            _download_remote_db('https://example.test/jobs.db.gz', target)
        self.assertEqual(target.read_bytes(), self.db.read_bytes())

    def test_expansion_limit_and_live_journal_preserve_target(self):
        archive = self.root / 'state.gz'
        pack(self.db, archive)
        original = self.db.read_bytes()
        with patch('src.snapshot_transfer.MAX_DATABASE_BYTES', 1):
            with self.assertRaises(ValueError):
                unpack(archive, self.db)
        Path(str(self.db) + '-wal').touch()
        with self.assertRaises(RuntimeError):
            unpack(archive, self.db)
        self.assertEqual(self.db.read_bytes(), original)

    def test_both_board_lanes_included(self):
        urls = [s['url'] for s in GITHUB_SYNC_SOURCES]
        self.assertTrue(any(url.endswith('/gha-boards.db.gz') for url in urls))
        self.assertTrue(any(url.endswith('/gha-boards-broad-non-workday.db.gz') for url in urls))
