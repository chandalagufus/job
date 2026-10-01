from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from src.database import Database


class BoardMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / 'jobs.db'))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def board(self, url='https://old.example', status='dead'):
        self.db.upsert_board(board_id='example', company='Example', platform='workday', url=url, status=status)

    def test_monthly_dead_probe_and_changed_url(self):
        self.board()
        self.assertFalse(self.db.board_probe_due('example', 'https://old.example'))
        self.assertTrue(self.db.board_probe_due('example', 'https://new.example'))
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        with self.db._tx() as conn:
            conn.execute('UPDATE boards SET last_checked=?', (old,))
        self.assertTrue(self.db.board_probe_due('example', 'https://old.example'))
        self.board('https://new.example', 'active')
        self.assertEqual(self.db.list_boards()[0]['url'], 'https://new.example')
        self.assertFalse(self.db.board_probe_due('example', 'https://new.example'))

    def run_record(self, status, error='', latency=0, fetched=0):
        now = datetime.now(timezone.utc).isoformat()
        self.db.record_source_run(source_key='example', entity_type='board', mode='boards',
                                  status=status, started_at=now, finished_at=now,
                                  error_text=error, latency_ms=latency, fetched_count=fetched)

    def test_cached_dead_is_skip_even_when_filtered(self):
        self.run_record('error', 'Board marked dead')
        self.assertEqual(self.db.list_source_runs(status='error'), [])
        self.assertEqual(len(self.db.list_source_runs(status='skipped')), 1)
        self.assertEqual(self.db.get_health_summary()['failures_24h'], 0)

    def test_skips_do_not_change_health_or_average_latency(self):
        self.run_record('success', latency=100, fetched=20)
        self.run_record('skipped', 'Cooldown')
        row = self.db.get_source_health()[0]
        self.assertEqual(row['health'], 'healthy')
        self.assertEqual(row['avg_latency_ms'], 100)
        self.assertEqual(row['recent_success_rate'], 100)
        self.assertEqual(row['last_error'], '')

    def test_expiry_preserves_every_review_signal(self):
        for key in ('plain', 'notes', 'viewed', 'manual', 'status', 'followup', 'feedback', 'resume'):
            self.db.mark_job_seen(key=key, source='test', company='Example', title=key,
                                  location='US', url='https://example.com/'+key, posted='', score=60, label='maybe',
                                  manual_input=key == 'manual', pipeline_notes='Keep' if key == 'notes' else '',
                                  pipeline_status='applied' if key == 'status' else 'new',
                                  follow_up_date='2026-11-01' if key == 'followup' else '')
        self.db.mark_job_viewed('viewed')
        self.db.record_feedback(job_key='feedback', action='interested')
        self.db.save_generated_resume(job_key='resume', job_title='Engineer', company='Example', content='Resume')
        with self.db._tx() as conn:
            conn.execute("UPDATE jobs SET last_seen='2020-01-01'")
        self.assertEqual(self.db.expire_old_jobs(), 1)
        self.assertIsNone(self.db.get_job('plain'))
        self.assertEqual(len(self.db.list_jobs_for_board(limit=None)), 7)
