# Paper Tracker v2.1.0 validation record

Validated on 2026-10-03 in a Linux cloud workspace with Python 3.12.14. This
record covers local verification of the integrated source before publication.
No real provider request, model charge, SMTP message or installed background
scheduler was part of these checks.

## Passed locally

- **213 offline unit/integration tests** with `python3 -m unittest discover -s tests -v`.
  Fixtures mock retrieval, model responses and SMTP, use temporary state, and
  explicitly refuse unintended network calls.
- Compilation of application, scripts and tests; Python 3.11 grammar parsing;
  Bash syntax checks for setup, launch and cron-wrapper scripts.
- Daily/weekly compatibility, profile-specific topic schedules, finite explicit
  dates, selector inheritance/exclusivity, far-future and exhausted calendars,
  same-day catch-up, timezone boundaries, DST gaps/folds, and a skipped local day.
- Separate topic profiles sharing one mailbox, persistent audience isolation,
  repeat-tick and fold idempotency, and preservation of previous delivery history.
- Mandatory model preflight before live retrieval/state writes; missing and
  invalid credentials/endpoints; malformed/empty/fabricated model output;
  overview failure; legacy prepared-draft rejection at pipeline, CLI and SMTP
  boundaries; metadata-only exclusion without consuming the analysis limit.
- Persistent automatic-retry pause after model failure: worker restarts and
  repeated ticks make no new paid requests that local day. Explicit retry,
  model/content configuration changes, next-local-day recovery and independent
  profiles are tested with simulated clocks. Sent-paper deduplication remains.
- Model setup with hidden-key input, provider/model selection, per-profile key
  slots, explicit save/cancel, private-file permissions on POSIX, no-overwrite
  safeguards, literal environment parsing and cleanup, and no credential echo.
- Cross-process locking on Linux and mocked Windows byte-lock behavior; native
  Windows execution is delegated to CI and is not claimed by this local record.
- RIS/BibTeX fields, author names, identifiers, Unicode/escaping, selected-paper
  deduplication, immutable attachment snapshots, real MIME attachment structure,
  and cleanup of stale local citation files for an empty rerun. Independent
  `rispy` and `bibtexparser` checks also parsed the synthetic export fixtures.
- Reproducible bilingual HTML/TXT/JSON/RIS/BibTeX demos and static website assets;
  public copies match the audited synthetic fixtures. The website neither
  collects credentials nor calls a backend, model or literature provider.
- Homepage Chinese section matches the standalone Chinese README. Detailed
  guides retain configuration/upgrade/operations information behind concise
  setup and result examples.

## Independent review

Separate offline review harnesses exercised 15 scheduling cases and 10 required-
model integration cases. The reviewer also checked late-stage model-failure cost
protection, setup behavior and installed-package CLI operation. The permanent
suite includes those core regression contracts; independent harnesses use only
synthetic data and are not part of the published runtime.

## Upgrade and privacy

Old daily/weekly configuration remains accepted. Synthetic v1 ledger fixtures
retain sent aliases/checkpoints and uncertain outcomes without deleting legacy
tables. An already-sent issue prevents a second delivery on the same local day.
Old prepared snapshots cannot bypass the new model-quality/export checks.
No actual user's installed database was migrated during validation.

The publication payload is an explicit source/docs/tests/examples allowlist.
Private `.env`, user configuration, `.venv`, build output, generated subscriber
reports, databases, logs and runtime directories are excluded. Demo addresses
use reserved domains and all included research examples are labeled synthetic.

## Not established by local checks

- Real literature-provider retrieval in the eventual deployment network
- Provider authentication, account balance, live model compatibility or scientific
  correctness beyond schema/evidence-anchor checks
- Real SMTP delivery, inbox arrival, bounce handling or email-client image support
- Native Zotero/EndNote UI import (portable files and independent parsers tested)
- Native Windows execution, Docker build/run or unattended real-time scheduling
- GitHub CI result, Pages publication or other deployment for the final commit;
  those must be verified separately after publishing that exact source

Do not interpret passing local tests or a valid configuration as a running
service. Production requires a durable host, correctly configured model and
optional SMTP service, retained state, and an explicitly started scheduler.
