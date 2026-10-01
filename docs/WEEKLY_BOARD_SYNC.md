# Weekly Upstream Board Updates

The GitHub Actions workflow runs Sundays at 10:17 UTC and can also be run manually.
It becomes active only after these files are pushed to the default `main` branch.
Set repository variable `UPSTREAM_BOARD_SYNC_ENABLED=false` to disable it.

## Sources

Edit `data/boards/upstream_sources.json`. Both confirmed public upstreams are enabled:
`vedansh-adepu/ms-job-watcher` and `Rohith066/job-radar`. Each contributes its main
board CSV and `greenhouse_lever_verified_live.csv`. This does not import their
job databases or run their code.

## Safety and Scope

- Only Greenhouse, Lever (US/EU), Ashby, and SmartRecruiters API board URLs are supported.
- No new Workday boards are imported. Other platforms remain unchanged.
- Existing rows are never deleted or reordered; new verified boards append to the broad list.
- Both main and broad lists are checked for duplicate board IDs.
- Same-company alternate URLs are reported as replacement candidates, not automatically substituted.
- New boards must return HTTP 200 and a nonempty jobs array from the public ATS API.
- Empty lists, HTTP failures, and unrecognized schemas do not qualify for import.
- An upstream download/schema failure prevents all inventory changes in that run.
- At most 100 candidate boards are checked weekly. Failed candidates wait 30 days;
  never-checked candidates are considered first, avoiding starvation of later entries.
- Validation state and reports are committed, never job databases, credentials, resumes, or source code.
- Existing dead-board database flags are not cleared automatically.

Run `python tools/sync_upstream_boards.py --max-checks 10` for a read-only preview.
Add `--apply` to update inventory and save results. Preview mode writes nothing.

The report is `data/boards/upstream_sync_report.json`, also uploaded as a workflow
artifact. Global board counts do not imply US jobs or matching jobs.

The existing broad-board workflow and dashboard broad scan read the updated CSV.
Local dashboards require pulling the repository changes; this workflow does not
restart the local app or launch a scan. Existing main-only sweeps are not expanded.
