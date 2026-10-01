import csv
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('upstream_sync', Path(__file__).resolve().parents[1] / 'tools/sync_upstream_boards.py')
syncer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(syncer)


def row(company='NewCo', slug='newco', platform='greenhouse'):
    return dict(zip(syncer.FIELDS, [company, platform, f'https://boards.greenhouse.io/{slug}', '', '']))


def csv_text(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=syncer.FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


class Response:
    def __init__(self, *, text='', data=None, status=200):
        self.text, self.data, self.status_code = text, data, status

    def json(self):
        return self.data


class Session:
    def __init__(self, rows, live=True, status=200):
        self.rows, self.live, self.status = rows, live, status
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url.startswith('https://raw.githubusercontent.com/'):
            return Response(text=csv_text(self.rows), status=self.status)
        return Response(data={'jobs': [{'title': 'Data Analyst'}] if self.live else []})


class UpstreamSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data/boards').mkdir(parents=True)
        (self.root / syncer.MAIN).write_text(csv_text([row('Existing', 'existing')]))
        (self.root / syncer.BROAD).write_text(csv_text([row('Broad', 'broad')]))
        self.sources = [{'name': 'Example', 'enabled': True, 'repo': 'example/boards', 'ref': 'main', 'files': ['boards.csv']}]
        self.now = datetime(2026,10,1,tzinfo=timezone.utc)

    def run_sync(self, session, **kwargs):
        return syncer.sync(self.root, self.sources, session, now=self.now, **kwargs)

    def test_append_preserves_existing_rows_and_main_file(self):
        before = (self.root / syncer.MAIN).read_bytes()
        report = self.run_sync(Session([row()]), apply=True)
        rows = syncer.load_local(self.root / syncer.BROAD)
        self.assertEqual([r['company_name'] for r in rows], ['Broad', 'NewCo'])
        self.assertEqual((self.root / syncer.MAIN).read_bytes(), before)
        self.assertEqual(len(report['added']), 1)

    def test_preview_writes_nothing(self):
        before = (self.root / syncer.BROAD).read_bytes()
        self.run_sync(Session([row()]))
        self.assertEqual((self.root / syncer.BROAD).read_bytes(), before)
        self.assertFalse((self.root / syncer.STATE).exists())
        self.assertFalse((self.root / syncer.REPORT).exists())

    def test_existing_ids_not_rechecked(self):
        session = Session([row('Existing','existing'), row('Broad','broad')])
        result = self.run_sync(session, apply=True)
        self.assertEqual(result['checks'], [])
        self.assertEqual(len(session.calls), 1)

    def test_failure_and_empty_results_never_add(self):
        before = (self.root / syncer.BROAD).read_bytes()
        result = self.run_sync(Session([row()], live=False), apply=True)
        self.assertEqual(result['added'], [])
        self.assertEqual((self.root / syncer.BROAD).read_bytes(), before)
        result = self.run_sync(Session([row()], status=503), apply=True)
        self.assertTrue(result['errors'])
        self.assertEqual((self.root / syncer.BROAD).read_bytes(), before)

    def test_replacement_is_reported_not_overwritten(self):
        result = self.run_sync(Session([row('Existing','newslug')]), apply=True)
        self.assertEqual(len(result['replacement_candidates']), 1)
        self.assertEqual(result['added'], [])

    def test_validation_budget_and_failed_candidate_cooldown(self):
        session = Session([row('A','a'),row('B','b')],live=False)
        result = self.run_sync(session,apply=True,max_checks=1)
        self.assertEqual(len(result['checks']),1)
        self.now += timedelta(days=7)
        result = self.run_sync(session,apply=True,max_checks=1)
        self.assertEqual(result['checks'][0]['board_id'],'greenhouse:b')

    def test_unsafe_urls_and_new_workday_are_rejected(self):
        for url in ['http://boards.greenhouse.io/x','https://localhost/x',
                    'https://boards.greenhouse.io.evil.test/x','https://boards.greenhouse.io:bad/x',
                    'https://user:pw@boards.greenhouse.io/x','https://boards.greenhouse.io/x/jobs/123']:
            candidate = row()
            candidate['board_url'] = url
            self.assertIsNone(syncer.identity(candidate))
        candidate = row(platform='workday')
        candidate['board_url']='https://lilly.wd115.myworkdayjobs.com/LLY'
        self.assertIsNone(syncer.identity(candidate))

    def test_platform_response_shapes(self):
        class Stub:
            def __init__(self,data): self.data=data
            def get(self,*args,**kwargs): return Response(data=self.data)
        for platform,host,data in [
            ('lever','jobs.lever.co',[{'text':'Engineer'}]),
            ('ashby','jobs.ashbyhq.com',{'jobs':[{'title':'Engineer'}]}),
            ('smartrecruiters','careers.smartrecruiters.com',{'content':[{'name':'Engineer'}]}),
        ]:
            candidate=row(platform=platform)
            candidate['board_url']=f'https://{host}/example'
            self.assertTrue(syncer.validate(candidate,Stub(data))[0])
            self.assertFalse(syncer.validate(candidate,Stub({'unexpected':[]}))[0])

    def test_disabled_unconfirmed_source_not_fetched(self):
        self.sources=[{'name':'rbayya','enabled':False}]
        session=Session([])
        report=self.run_sync(session,apply=True)
        self.assertEqual(session.calls,[])
        self.assertEqual(report['added'],[])

    def test_bad_schema_is_not_silently_treated_as_empty(self):
        with self.assertRaises(ValueError): syncer.parse_csv('<html>error</html>')


if __name__ == '__main__':
    unittest.main()
