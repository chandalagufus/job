"""Lossless, validated transport for SQLite scan state (no job pruning)."""
from contextlib import closing
import argparse
import gzip
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

MAX_ARCHIVE_BYTES = 95 * 1024 * 1024
MAX_DATABASE_BYTES = 2 * 1024 * 1024 * 1024


def validate(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise sqlite3.DatabaseError('Snapshot integrity check failed')
        db.execute('SELECT key FROM jobs LIMIT 1').fetchall()


def unpack(archive, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        candidate = Path(tmp) / 'snapshot.db'
        with gzip.open(archive, 'rb') as source, candidate.open('wb') as out:
            size = 0
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DATABASE_BYTES:
                    raise ValueError('Expanded snapshot exceeds safety limit')
                out.write(chunk)
        validate(candidate)
        # Replacing a database with an active journal is unsafe.
        if any(Path(str(destination) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            raise RuntimeError('Close the database before restoring its snapshot')
        os.replace(candidate, destination)


def pack(database, archive, max_bytes=MAX_ARCHIVE_BYTES):
    database, archive = Path(database), Path(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=archive.parent) as tmp:
        snapshot = Path(tmp) / 'snapshot.db'
        with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
                target.execute('PRAGMA journal_mode=DELETE')
                target.execute('VACUUM')
        validate(snapshot)
        candidate = Path(tmp) / 'snapshot.db.gz'
        with snapshot.open('rb') as source, candidate.open('wb') as raw:
            with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as out:
                shutil.copyfileobj(source, out)
        if candidate.stat().st_size > max_bytes:
            raise ValueError('Compressed state exceeds Git publishing limit; use the workflow recovery artifact')
        os.replace(candidate, archive)
    print(f'Published snapshot: {archive} ({archive.stat().st_size:,} bytes)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('pack', 'restore'))
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    archive = Path(str(args.database) + '.gz')
    if args.operation == 'pack':
        pack(args.database, archive)
    elif archive.exists():
        unpack(archive, args.database)
        print(f'Restored scan history and cursor from {archive}')
    elif args.database.exists():
        validate(args.database)
        print('Bootstrap: using legacy uncompressed database')
    else:
        print('Bootstrap: no previous state; scanner will create a database')


if __name__ == '__main__':
    main()
