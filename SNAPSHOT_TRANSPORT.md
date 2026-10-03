# Durable board snapshots

Board workflows restore `state/gha-boards.db.gz` and
`state/gha-boards-broad-non-workday.db.gz` before scanning. On the first run,
the legacy SQLite file is used if no compressed snapshot exists.

After scanning, a SQLite backup is compacted, integrity-checked, compressed,
and committed. Jobs, first-seen timestamps, and cursors are preserved. The
legacy raw file is no longer authoritative after a gzip snapshot is published.
Only after successful compression is its worktree version restored for Git.

An oversized compressed snapshot fails the workflow instead of reporting
success with stale state. Recovery artifacts retain raw scan state for 14 days;
download all SQLite sidecars together and recover on a stopped database.

Dashboard GitHub sync imports both compressed board lanes as well as the
existing main and Rohith snapshots. Downloads are validated before import.
Existing archive data is retained on partial failures; an incomplete sync is
reported explicitly. No first-seen dates are reset to make older jobs look new.

Deployment requires publishing the workflows and `src/snapshot_transfer.py`,
one successful board workflow run per lane, and restarting the local dashboard
before GitHub sync. Until the first publication, a missing gzip is reported as
a failed source; old data is kept, not falsely reported as a fresh download.

This does not recover unpublished state from runners that have already been
destroyed, reconcile job identities from email subjects, or force local and
upstream scoring profiles to agree. One-time repeat alerts can occur when
bootstrapping from the last stale snapshot. Subsequent runs restore new state.
