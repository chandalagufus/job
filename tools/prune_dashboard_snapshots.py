"""Preview old dashboard snapshots, or archive them before removal while offline."""
import argparse
from contextlib import closing
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
import time


NAME = re.compile(r'dashboard-merged-[0-9a-f]{12}(?:-[0-9a-f]{12})?\.db')


def sidecars(path):
    return any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal'))


def digest(stream):
    sha = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        sha.update(block)
    return sha.hexdigest()


def archive_snapshot(path, archive_dir):
    """Retain every byte, including notes, resumes and unreviewed jobs."""
    before = path.stat()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
        if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise sqlite3.DatabaseError('Snapshot failed integrity check; retained')
    archive_dir.mkdir(exist_ok=True)
    if archive_dir.is_symlink() or archive_dir.resolve().parent != path.parent:
        raise ValueError('Archive directory must stay inside the state directory')
    with path.open('rb') as source:
        expected = digest(source)
    archive = archive_dir / (path.name + '.' + expected + '.gz')
    if not archive.exists():
        with tempfile.NamedTemporaryFile(dir=archive_dir, suffix='.tmp', delete=False) as temp:
            temporary = Path(temp.name)
        try:
            with path.open('rb') as source, gzip.open(temporary, 'wb', compresslevel=6) as dest:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    dest.write(block)
            with gzip.open(temporary, 'rb') as source:
                if digest(source) != expected:
                    raise ValueError('Archive verification failed; snapshot retained')
            with temporary.open('r+b') as handle:
                os.fsync(handle.fileno())
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if archive.is_symlink():
        raise ValueError('Refusing symlink archive')
    with gzip.open(archive, 'rb') as source:
        if digest(source) != expected:
            raise ValueError('Archive verification failed; snapshot retained')
    after = path.stat()
    if path.is_symlink() or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or sidecars(path):
        raise ValueError('Snapshot changed during archival; retained')
    if archive.stat().st_size >= before.st_size:
        raise ValueError('Archive offers no disk saving; snapshot retained')
    path.unlink()
    return str(archive)


def prune(state_dir, *, apply=False, keep=5, age_days=7, max_delete=10, protected=()):
    root = Path(state_dir).resolve(strict=True)
    if keep < 1 or age_days < 1 or max_delete < 1:
        raise ValueError('Retention limits must be positive')
    protected = {Path(p).resolve() for p in protected}
    candidates = [p for p in root.glob('dashboard-merged-*.db')
                  if NAME.fullmatch(p.name) and not p.is_symlink() and p.resolve().parent == root]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for path in candidates[keep:]:
        if len(results) >= max_delete:
            break
        if path in protected or sidecars(path) or time.time() - path.stat().st_mtime < age_days * 86400:
            continue
        result = {'path': str(path), 'status': 'eligible'}
        if apply:
            try:
                result['archive'] = archive_snapshot(path, root / 'snapshot-archives')
                result['status'] = 'archived-and-removed'
            except (OSError, sqlite3.Error, ValueError, EOFError) as exc:
                result.update(status='retained', reason=str(exc))
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'state')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dashboard-stopped', action='store_true', help='Confirm all dashboard and scan processes are stopped')
    parser.add_argument('--web-port', type=int, default=8080)
    parser.add_argument('--keep', type=int, default=5)
    parser.add_argument('--age-days', type=int, default=7)
    parser.add_argument('--max-delete', type=int, default=10)
    args = parser.parse_args()
    if args.apply:
        if not args.dashboard_stopped:
            parser.error('Stop every dashboard/scan process, then specify --dashboard-stopped')
        try:
            with socket.create_connection(('127.0.0.1', args.web_port), timeout=2):
                parser.error('The dashboard port is still listening; refusing cleanup')
        except OSError:
            pass
    print(json.dumps(prune(args.state_dir, apply=args.apply, keep=args.keep,
                           age_days=args.age_days, max_delete=args.max_delete), indent=2))


if __name__ == '__main__':
    main()
