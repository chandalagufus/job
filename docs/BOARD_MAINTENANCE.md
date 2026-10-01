# Board Maintenance

- Lilly uses `lilly.wd115.myworkdayjobs.com/LLY`. A changed board URL bypasses
  the previous endpoint's cooldown and is recorded after the new probe.
- Dell uses its public Oracle HCM careers API instead of the retired Workday
  endpoint. Only external description fields are collected.
- SmartRecruiters paginates up to 5,000 listings instead of silently stopping
  at 500. Set `SMARTRECRUITERS_MAX_JOBS` to adjust that ceiling; reaching it
  logs a warning. Global listings are still subject to location and fit filters.
- Dead boards become eligible for a fresh probe after 30 days, not on every
  sweep. Empty boards retain their existing capped exponential cooldown.
- Cached skips do not count as fresh errors or latency measurements. Historical
  `Board marked dead` events are displayed as skips without rewriting history.
- Job expiry preserves viewed/manual jobs, notes, follow-up dates, pipeline
  statuses, feedback and jobs referenced by generated resumes.

## Snapshot Retention

Cleanup is explicit and offline, not performed in dashboard page requests.
Preview without changing any files:

```powershell
.\.venv\Scripts\python.exe tools\prune_dashboard_snapshots.py
```

Stop all dashboard and scanner processes before applying:

```powershell
.\.venv\Scripts\python.exe tools\prune_dashboard_snapshots.py --apply --dashboard-stopped
```

The newest five snapshots and files younger than seven days are retained.
Up to ten eligible snapshots are handled per invocation. Active sidecars,
corrupt databases, symlinks and unexpected names are excluded or retained.
Source databases such as `gha-jobs.db` and `github-archive.db` are never targets.

Each removal first creates a complete gzip archive in `state/snapshot-archives/`.
The filename contains the uncompressed SHA-256; decompression is verified before
the original is removed. This preserves all jobs, notes, feedback, viewed state,
resumes and artifacts, not merely recent job inventory. Archives are private,
git-ignored, and are not automatically deleted. They still consume disk space.

To recover, decompress an archive to a new `.db` path while the app is stopped;
verify its SHA-256 against the archive filename before inspecting or importing
records. Do not overwrite a running or primary database.
