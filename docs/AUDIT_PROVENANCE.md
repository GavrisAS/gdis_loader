# Runtime and audit provenance (v0.18)

Runtime manifest version 3 stores `run_timestamp_utc`, `runtime_git_commit`,
`runtime_release_tag`, `python_version`, `calculation_date`, `selected_field`.
The timestamp is captured for this operation; a source checkout tag is reliable
only when it points exactly at HEAD. Frozen metadata comes from the embedded
build module. A nearest ancestral tag is not a runtime release tag.

`make audit` with `GDIS_AUDIT_RUNTIME_REPORT` preserves these fields and adds
`audit_timestamp_utc`, `audit_git_commit`, `audit_release_tag`. A known runtime
commit differing from audited HEAD **fails** archive creation; a known runtime
tag differing from the exact audited HEAD tag also fails. Neither is overwritten.
Unknown runtime metadata stays unknown via `runtime_commit_status` and
`runtime_release_status`; it does not assert revision equivalence. Legacy
manifest commit/tag fields are validated too, never silently replaced. Version 2
runtime timestamp is explicitly migrated from its old `audit_timestamp_utc`
name to `run_timestamp_utc` before adding bundle creation metadata.

Without a runtime report, the manifest is explicitly a
`not_executed_config_snapshot`, with unknown runtime commit/tag and no run timestamp.
It cannot prove that production was executed on audited HEAD. Audit timestamp
always describes bundle creation, not calculation or runtime execution.

Runtime SourcePaths supply basenames, sizes and SHA-256 in deterministic role
order. Numeric criteria and origin are snapshotted, without raw config.toml or
absolute paths. Generated calculator hash is retained if available. Runtime JSON,
logs, source workbooks and generated calculator bytes are excluded from bundles.
Aggregate reconciliation and inventory are in REAL_DATA_DELTA_v0.18.md.

For release audit, re-run production after commit and tag fetch, then:

```bash
GDIS_AUDIT_RUNTIME_REPORT=reports/v018/gdis_after.load-report.json make audit
```

Never edit runtime commit/tag to match HEAD. A changed revision requires a new run.
The final run's source hashes must be compared with the baseline to distinguish
code-only deltas from input changes. This provenance does not claim equivalence
for uncommitted changes; use a clean release checkout for final evidence.

## Actual source revalidation

With a runtime report, normal audit is strict: each of the seven input paths
from runtime `input_paths` is reopened, basename/size/SHA-256 compared against
the saved manifest. Mismatch or unavailable path fails before manifest/archive
creation; saved hashes are never silently replaced. Only the privacy-safe
manifest is archived, with per-source `revalidation_status=matched` and aggregate
`source_revalidation_status=revalidated`. Internal paths are not serialized.
The CLI-only `--non-strict` developer option permits unavailable files with
`unavailable` / `not_revalidated`; byte mismatches still fail. Commit/tag guards
run before revalidation. Generated calculator bytes remain excluded.
