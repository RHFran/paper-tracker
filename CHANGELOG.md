# Changelog

## 2.0.0 — 2026-10-03

### Project name

- Named **Paper Tracker** with distribution `paper-tracker` and preferred CLI
  `paper-tracker`; the `literature-digest` command, `literature_digest` import
  package and existing environment variable names remain compatible.
- GitHub-ready bilingual demo walkthrough and checked-in HTML/TXT/JSON fixtures.

### Added

- Guided and noninteractive setup for research topics, recipient, language,
  local delivery time and IANA timezone, plus strict configuration validation.
- Multiple reader profiles with isolated report/outbox/deduplication state.
- Foreground scheduling and external-timer ticks with configured weekdays and
  same-day catch-up; sending remains explicit.
- Configurable Crossref, Europe PMC and arXiv discovery queries and text filters.
- Multilingual model-directed summaries, a source-grounded overview and a
  single numbered reference list across topics.
- Optional rights-aware source figures, with source links where embedding is
  unavailable or not eligible.
- An explicitly labeled offline preview, bilingual quickstarts, MIT license,
  contribution/security guidance, deployment examples and offline CI.

### Preserved

- Default dry-run, HTML/text/JSON output, publication-date auditing and provenance.
- Persistent delivery state and manual recovery for uncertain SMTP outcomes.
- Python standard-library-only runtime and environment-based secrets.

### Migration from 1.x

- Upgrade application code in place. Stop the old worker and privately back up
  source, config, secrets and the entire state directory (including WAL/SHM)
  first, with all workers stopped; do not replace
  private `config.json`, `.env` or state with example files.
- Keep the original single `default` profile, recipient and database path for
  the initial upgrade. Omitted `topics` retains BVOC/tree-species behavior;
  `language` defaults to `zh-CN`, and the configured timezone is retained.
- First state access copies valid legacy delivery records into a
  recipient-isolated default ledger, retaining the original tables and migrated
  sent aliases, checkpoints and uncertain outcomes. Same-local-day delivery
  checks prevent a second message despite the new digest identifier.
- Legacy `prepared` payloads lack the new configuration fingerprint and cannot
  be replayed. After resolving any uncertainty, the next local day's run can
  prepare a fresh issue. Publication-window rescanning remains normal.
- Run `validate`, `preview`, `status` and a real dry run before restarting one
  worker. Migration tests use fixtures; no actual existing user installation has
  been migrated by this release.
- Adding `profiles` changes state subpaths. Preserve the existing reader as
  `default` with the same recipient and explicitly transfer a consistent database
  backup to its new resolved path if converting later; changing IDs/recipients or
  naively creating profile directories does not preserve delivery continuity.

See the [English upgrade guide](README.md#upgrading-from-1x) or the
[Chinese README](README_中文.md) for the safe sequence.

Version 2 is an operator-run backend. Repository publication, hosted deployment,
real SMTP delivery and real model-provider verification are separate release steps.

## 1.0.0 — 2026-10-02

Initial two-topic Chinese research digest with source provenance, rolling-window
retrieval, mocked SMTP tests and a persistent delivery outbox.
