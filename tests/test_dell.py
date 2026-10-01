from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.sources.dell import BOARD_URL, DellSource


class DellTests(unittest.TestCase):
    def fetch(self, payloads, label='no', **kwargs):
        session = Mock()
        session.get.side_effect = [Mock(json=Mock(return_value=data)) for data in payloads]
        with patch('src.sources.dell.get_session', return_value=session), patch(
            'src.sources.dell.classify', return_value=SimpleNamespace(score=70, label=label)
        ):
            jobs = DellSource(**kwargs).fetch(set())
        return jobs, session

    def test_external_details_only(self):
        jobs, _ = self.fetch([
            {'items': [{'TotalJobsCount': 1, 'requisitionList': [
                {'Id': 'R123', 'Title': 'Data Engineer', 'PrimaryLocation': 'Austin, TX', 'PostedDate': '2026-10-01'}
            ]}]},
            {'items': [{'ExternalDescriptionStr': 'Build Python pipelines.',
                        'ExternalQualificationsStr': 'SQL and testing.',
                        'InternalDescriptionStr': 'Internal confidential text'}]},
        ], label='yes')
        self.assertEqual(jobs[0].key, 'oracle_hcm:dell:R123')
        self.assertEqual(jobs[0].url, BOARD_URL + '/job/R123')
        self.assertIn('SQL and testing', jobs[0].description)
        self.assertNotIn('confidential', jobs[0].description)

    def test_pagination_and_stable_ids(self):
        jobs, session = self.fetch([
            {'items': [{'TotalJobsCount': 2, 'requisitionList': [{'Id': 'R1', 'Title': 'Cashier'}]}]},
            {'items': [{'TotalJobsCount': 2, 'requisitionList': [{'Id': 'R2', 'Title': 'Cashier'}]}]},
        ])
        self.assertEqual(len(jobs), 2)
        self.assertIn('offset=1', session.get.call_args.kwargs['params']['finder'])

    def test_repeated_page_stops(self):
        page = {'items': [{'requisitionList': [{'Id': 'R1'}]}]}
        with self.assertLogs('src.sources.dell', level='WARNING'):
            jobs, session = self.fetch([page, page])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(session.get.call_count, 2)

    def test_other_hosts_rejected(self):
        with self.assertRaises(ValueError):
            DellSource(board_url='https://other.example/careers')

    def test_bad_schema_is_not_an_empty_board(self):
        with self.assertRaises(ValueError):
            self.fetch([{'unexpected': []}])

    def test_cap_inside_final_page_warns(self):
        page = {'items': [{'TotalJobsCount': 2, 'requisitionList': [{'Id': 'R1'}, {'Id': 'R2'}]}]}
        with self.assertLogs('src.sources.dell', level='WARNING'):
            jobs, _ = self.fetch([page], max_jobs=1)
        self.assertEqual(len(jobs), 1)

    def test_board_factory(self):
        from src.main import _board_source_for, _get_board_id
        board = {'platform': 'oracle_hcm', 'company': 'Dell', 'board_url': BOARD_URL}
        self.assertIsInstance(_board_source_for(board), DellSource)
        self.assertEqual(_get_board_id(board), DellSource.board_id)
