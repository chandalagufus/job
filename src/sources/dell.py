"""Dell's public Oracle HCM careers API (replacement for its Workday board)."""
import logging
from html import unescape
from urllib.parse import quote

from ..classifier import classify
from ..utils.http import get_session
from .base import BaseSource, Job, merge_text

log = logging.getLogger(__name__)
ORIGIN = 'https://enterpriseplatform.dell.com'
BOARD_URL = ORIGIN + '/hcmUI/CandidateExperience/en/sites/careers'
API = ORIGIN + '/hcmRestApi/resources/latest/'


class DellSource(BaseSource):
    name = 'oracle_hcm:dell:careers'
    board_id = name

    def __init__(self, company='Dell Technologies', board_url=BOARD_URL, *, max_jobs=2000):
        if board_url.rstrip('/') != BOARD_URL:
            raise ValueError('This Oracle HCM adapter currently supports only the verified Dell careers site')
        self.company = company
        self.max_jobs = max(1, int(max_jobs))

    def fetch(self, seen_keys, timeout=30):
        session = get_session('oracle_hcm')
        rows, seen, offset = [], set(), 0
        while len(rows) < self.max_jobs:
            response = session.get(API+'recruitingCEJobRequisitions', params={
                'onlyData':'true', 'expand':'requisitionList',
                'finder':f'findReqs;siteNumber=careers,limit=100,offset={offset},sortBy=POSTING_DATES_DESC',
            }, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            containers = payload.get('items') if isinstance(payload, dict) else None
            if not isinstance(containers, list) or not containers:
                raise ValueError('Unexpected Dell listing schema: missing items container')
            container = containers[0]
            page = container.get('requisitionList') if isinstance(container, dict) else None
            if not isinstance(page, list):
                raise ValueError('Unexpected Dell listing schema: missing requisitionList')
            if not page:
                break
            fresh = []
            for row in page:
                if row.get('Id') and row['Id'] not in seen:
                    fresh.append(row)
                    seen.add(row['Id'])
            if not fresh:
                log.warning('Dell returned a repeated page; stopping at offset %s', offset)
                break
            rows.extend(fresh[:self.max_jobs-len(rows)])
            offset += len(page)
            total = int(container.get('TotalJobsCount') or 0)
            if len(rows) >= self.max_jobs and (not total or total > len(rows)):
                log.warning('Dell inventory truncated at %s of %s jobs', self.max_jobs, total or 'unknown')
                break
            if total and offset >= total:
                break
        jobs = []
        for row in rows:
            rid = str(row['Id'])
            title = str(row.get('Title') or 'Unknown Title')
            match = classify(title)
            description = ''
            if match.label in {'yes', 'maybe'}:
                try:
                    response = session.get(API+'recruitingCEJobRequisitionDetails', params={
                        'onlyData':'true', 'finder':f'ById;Id={rid},siteNumber=careers',
                    }, timeout=timeout)
                    response.raise_for_status()
                    details = response.json().get('items', [])
                    if details:
                        detail = details[0]
                        description = unescape(merge_text(*(detail.get(k) for k in (
                            'ExternalDescriptionStr', 'ExternalQualificationsStr',
                            'ExternalResponsibilitiesStr', 'CorporateDescriptionStr',
                        ))))
                except Exception as exc:
                    log.warning('Dell description unavailable for %s: %s', rid, exc)
            jobs.append(Job(
                key=f'oracle_hcm:dell:{rid}', source='oracle_hcm', company=self.company,
                title=title, location=str(row.get('PrimaryLocation') or row.get('PrimaryLocationCountry') or 'Unknown Location'),
                url=BOARD_URL+'/job/'+quote(rid,safe=''), posted=str(row.get('PostedDate') or ''),
                description=description, score=match.score, label=match.label,
            ))
        return jobs
