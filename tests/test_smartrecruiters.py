import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.sources.smartrecruiters import SmartRecruitersSource, _extract_description


class SmartRecruitersTests(unittest.TestCase):
    def _pages(self, pages, **kwargs):
        session = Mock()
        session.get.side_effect = [Mock(content=b'json', json=Mock(return_value=p)) for p in pages]
        with patch('src.sources.smartrecruiters.get_session', return_value=session), patch(
            'src.sources.smartrecruiters.classify', return_value=SimpleNamespace(score=0, label='no')
        ):
            jobs = SmartRecruitersSource('Example', 'https://jobs.smartrecruiters.com/Example', **kwargs).fetch(set())
        return jobs, session

    def test_paginates_beyond_old_500_cap(self):
        pages = [{'totalFound': 625, 'content': [
            {'id': str(i), 'name': 'Cashier'} for i in range(start, min(start+100, 625))
        ]} for start in range(0, 625, 100)]
        jobs, session = self._pages(pages)
        self.assertEqual(len(jobs), 625)
        self.assertEqual(session.get.call_count, 7)
        self.assertEqual(session.get.call_args_list[-1].kwargs['params']['offset'], 600)

    def test_invalid_schema_is_not_reported_as_zero_jobs(self):
        with self.assertRaises(ValueError):
            self._pages([{'unexpected': []}])

    def test_configurable_cap_and_repeat_guard(self):
        page = {'totalFound': 200, 'content': [{'id': str(i), 'name': 'Cashier'} for i in range(100)]}
        with self.assertLogs('src.sources.smartrecruiters', level='WARNING'):
            jobs, session = self._pages([page], max_jobs=50)
        self.assertEqual(len(jobs), 50)
        with self.assertLogs('src.sources.smartrecruiters', level='WARNING'):
            jobs, session = self._pages([page, page])
        self.assertEqual(len(jobs), 100)
        self.assertEqual(session.get.call_count, 2)

    def test_dict_sections_with_real_api_shape(self):
        data = {'jobAd': {'sections': {
            'companyDescription': {'title': 'Company Description', 'text': '<p>We build cloud infrastructure.</p>'},
            'jobDescription': {'title': 'Job Description', 'text': '<p>Build Python &amp; SQL pipelines.</p>'},
            'qualifications': {'title': 'Qualifications', 'text': '<ul><li>Three years of data engineering experience.</li></ul>'},
            'additionalInformation': {'text': '<p>Collaborate with analysts and engineers.</p>'},
        }}}
        text = _extract_description(data)
        self.assertIn('Build Python & SQL pipelines.', text)
        self.assertIn('Three years of data engineering experience.', text)
        self.assertIn('Additional Information:', text)
        self.assertNotIn('<p>', text)
        self.assertNotIn('&amp;', text)

    def test_legacy_list_sections_still_work(self):
        text = _extract_description({'jobAd': {'sections': [
            {'title':'Responsibilities', 'text':'Build and maintain reporting pipelines using SQL and Python.'},
            {'name':'Requirements', 'content':'Experience validating complex analytical datasets.'},
        ]}})
        self.assertIn('Responsibilities:', text)
        self.assertIn('Requirements:', text)

    def test_null_job_ad_with_top_level_sections(self):
        text = _extract_description({'jobAd': None, 'sections': {
            'jobDescription': {'text': 'Build production data pipelines and optimize SQL queries.'}
        }})
        self.assertIn('Build production data pipelines', text)

    def test_null_and_unexpected_values_do_not_crash(self):
        for data in [None, [], {}, {'jobAd':None}, {'jobAd':{'sections': {'jobDescription':None}}}]:
            self.assertEqual(_extract_description(data), '')

    def test_string_sections_and_description_fallback(self):
        self.assertIn('Build predictive models', _extract_description({'sections': {
            'jobDescription':'Build predictive models and deploy them to production.'
        }}))
        self.assertIn('Analyze customer datasets', _extract_description({
            'description':'Responsibilities: Analyze customer datasets and create actionable business reports.'
        }))

    def test_fetch_populates_description_on_job(self):
        def response(data):
            result=Mock()
            result.content=b'json'
            result.json.return_value=data
            return result
        session=Mock()
        session.get.side_effect=[
            response({'content':[{'id':'123','name':'Data Engineer','location':{'city':'Boston','country':'US'}}]}),
            response({'content':[]}),
            response({'jobAd':{'sections':{'jobDescription':{'text':'Build reliable Python and SQL data pipelines for analytics.'}}}}),
        ]
        with patch('src.sources.smartrecruiters.get_session',return_value=session), patch(
            'src.sources.smartrecruiters.classify',return_value=SimpleNamespace(score=80,label='yes')
        ):
            jobs=SmartRecruitersSource('Example','https://jobs.smartrecruiters.com/Example').fetch(set())
        self.assertEqual(len(jobs),1)
        self.assertIn('Build reliable Python and SQL',jobs[0].description)
        self.assertEqual(jobs[0].key,'smartrecruiters:Example:123')


if __name__ == '__main__':
    unittest.main()
