"""Add live public upstream boards without deleting or reordering local inventory."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import requests


FIELDS = ['company_name', 'platform', 'board_url', 'country_focus', 'notes']
MAIN = 'data/boards/JOB_BOARDS_PURE_WORKING_SUPPORTED_round2.csv'
BROAD = 'data/boards/BROAD_NON_WORKDAY_EXTRA.csv'
STATE = 'data/boards/upstream_check_state.json'
REPORT = 'data/boards/upstream_sync_report.json'
HOSTS = {
    'greenhouse': {'boards.greenhouse.io', 'job-boards.greenhouse.io'},
    'lever': {'jobs.lever.co', 'jobs.eu.lever.co'},
    'ashby': {'jobs.ashbyhq.com'},
    'smartrecruiters': {'jobs.smartrecruiters.com', 'careers.smartrecruiters.com'},
}


def identity(row):
    platform = row.get('platform', '').strip().lower()
    try:
        u = urlsplit(row.get('board_url', '').strip())
        port = u.port
    except ValueError:
        return None
    parts = [part for part in u.path.split('/') if part]
    if (platform not in HOSTS or u.scheme != 'https' or u.hostname not in HOSTS[platform]
            or u.username or u.password or port or len(parts) != 1
            or not re.fullmatch(r'[A-Za-z0-9_.-]+', parts[0])):
        return None
    # EU Lever is a different API region.
    region = ':eu' if u.hostname == 'jobs.eu.lever.co' else ''
    return f'{platform}{region}:{parts[0].lower()}'


def company_key(row):
    return re.sub(r'[^a-z0-9]', '', row.get('company_name', '').lower())


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    columns = set(reader.fieldnames or [])
    if not ({'platform'} <= columns and columns & {'company_name', 'company'}
            and columns & {'board_url', 'url'}):
        raise ValueError('Unrecognized upstream CSV columns')
    rows = []
    for raw in reader:
        if (raw.get('ok') or '').strip().lower() not in {'', 'true', 'yes', '1'}:
            continue
        row = {field: (raw.get(field) or '').strip() for field in FIELDS}
        row['company_name'] = row['company_name'] or (raw.get('company') or '').strip()
        row['board_url'] = row['board_url'] or (raw.get('url') or '').strip()
        row['platform'] = row['platform'].lower()
        if row['company_name'] and identity(row):
            rows.append(row)
    return rows


def load_local(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError(f'Unexpected local columns: {path}')
        return list(reader)


def endpoint(row):
    if not identity(row):
        raise ValueError('Unsupported or unsafe board URL')
    slug = urlsplit(row['board_url']).path.strip('/')
    platform = row['platform']
    if platform == 'greenhouse':
        return f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs'
    if platform == 'lever':
        api = 'api.eu.lever.co' if urlsplit(row['board_url']).hostname == 'jobs.eu.lever.co' else 'api.lever.co'
        return f'https://{api}/v0/postings/{slug}?mode=json&limit=1'
    if platform == 'ashby':
        return f'https://api.ashbyhq.com/posting-api/job-board/{slug}'
    return f'https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1'


def validate(row, session):
    response = session.get(endpoint(row), timeout=(5, 15), allow_redirects=False)
    if response.status_code != 200:
        return False, f'HTTP {response.status_code}'
    data = response.json()
    if row['platform'] == 'lever':
        jobs = data if isinstance(data, list) else None
    else:
        field = 'content' if row['platform'] == 'smartrecruiters' else 'jobs'
        jobs = data.get(field) if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return False, 'Unrecognized response schema'
    if not jobs:
        return False, 'Zero jobs; not proof of a dead board'
    return True, f'Live: {len(jobs)} returned'


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                     dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        handle.write(text)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def sync(root, sources, session, *, apply=False, max_checks=100, now=None):
    now = now or datetime.now(timezone.utc)
    local = load_local(root / MAIN) + load_local(root / BROAD)
    existing = {identity(row) for row in local if identity(row)}
    companies = {company_key(row) for row in local if company_key(row)}
    state_path = root / STATE
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    report = {'checked_at': now.isoformat(), 'sources': [], 'checks': [],
              'added': [], 'replacement_candidates': [], 'errors': []}
    candidates = {}
    for source in sources:
        if not source.get('enabled'):
            report['sources'].append({'name': source['name'], 'status': 'disabled',
                                      'reason': source.get('note', '')})
            continue
        repo, ref = source['repo'], source.get('ref', 'main')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            raise ValueError('Invalid upstream repository')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', ref):
            raise ValueError('Invalid upstream ref')
        for file in source['files']:
            if not re.fullmatch(r'[A-Za-z0-9_./-]+\.csv', file) or '..' in file.split('/'):
                raise ValueError('Invalid upstream path')
            url = f'https://raw.githubusercontent.com/{repo}/{ref}/{file}'
            try:
                response = session.get(url, timeout=(5, 30), allow_redirects=False)
                if response.status_code != 200:
                    raise ValueError(f'HTTP {response.status_code}')
                rows = parse_csv(response.text)
                if not rows:
                    raise ValueError('No supported non-Workday rows; refusing empty inventory')
                report['sources'].append({'url': url, 'accepted_rows': len(rows)})
                for row in rows:
                    key = identity(row)
                    if key not in existing:
                        candidates.setdefault(key, (row, repo))
            except (requests.RequestException, ValueError) as exc:
                report['errors'].append({'url': url, 'error': str(exc)})
    # Fail closed on incomplete downloads, never apply a partial upstream snapshot.
    if not report['errors']:
        due = sorted(candidates, key=lambda k: (state.get(k, {}).get('checked_at', ''), k))
        for key in due:
            previous = state.get(key, {}).get('checked_at')
            if previous and now - datetime.fromisoformat(previous) < timedelta(days=30):
                continue
            if len(report['checks']) >= max_checks:
                break
            row, repo = candidates[key]
            try:
                live, reason = validate(row, session)
            except (requests.RequestException, ValueError) as exc:
                live, reason = False, str(exc)
            result = {'board_id': key, 'checked_at': now.isoformat(), 'live': live, 'reason': reason}
            state[key] = result
            report['checks'].append(result)
            if not live:
                continue
            row = dict(row)
            row['notes'] = f'weekly verified {now.date()}; upstream {repo}'
            if company_key(row) in companies:
                report['replacement_candidates'].append(row)
            else:
                report['added'].append(row)
                companies.add(company_key(row))
        if apply:
            if report['added']:
                rows = load_local(root / BROAD) + report['added']
                buffer = io.StringIO(newline='')
                writer = csv.DictWriter(buffer, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
                atomic_write(root / BROAD, buffer.getvalue())
            atomic_write(state_path, json.dumps(state, indent=2, sort_keys=True) + '\n')
    if apply:
        atomic_write(root / REPORT, json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-checks', type=int, default=100)
    args = parser.parse_args()
    if args.max_checks < 1 or args.max_checks > 500:
        parser.error('--max-checks must be between 1 and 500')
    config = json.loads((args.root / 'data/boards/upstream_sources.json').read_text())
    with requests.Session() as session:
        report = sync(args.root, config['sources'], session,
                      apply=args.apply, max_checks=args.max_checks)
    print(json.dumps(report, indent=2))
    if report['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
