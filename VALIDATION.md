# Paper Tracker v2.0.0 validation record

Validated on 2026-10-03 in a Linux cloud workspace. This document records local
checks before GitHub publication, including the Paper Tracker naming update.
No service was installed and no real messages were sent during validation.

## Passed

- **131 offline unit/integration tests** (`python3 -m unittest discover -s tests -v`)
- A separate **24-assertion independent review harness**, covering profile/recipient
  isolation, prepared-outbox replay, uncertainty, DST, wizard safety and due-time gating
- `compileall` for source and tests, plus Python 3.11 grammar parsing; the initial v2 checks used
  Python 3.13, and the publication recheck used Python 3.12.14. CI is configured for
  Python 3.11, 3.12 and 3.13; remote runs are outside this local record
- Single- and multi-profile example validation, interactive/noninteractive setup,
  refusal to overwrite existing configuration, and network-free offline demos
- Chinese and English previews with exactly four paper blocks, validated global
  numbered references, escaped untrusted text, and matching HTML/TXT/JSON output
- Package wheel build with no runtime dependencies; MIT license; installation in
  a separate virtual environment and invocation from outside the source checkout
- Preferred `paper-tracker` and legacy `literature-digest` commands: help, all three
  example configurations, noninteractive setup and identical bilingual demos
- Checked-in demo byte-for-byte regeneration and publication-contract regression
  tests; synthetic status, no network/mail/state writes, self-contained HTML
- 54 relative Markdown links, JSON/TOML/YAML examples and shell syntax
- Release scan: examples/defaults contain reserved addresses, no previous private
  recipient, credentials, real state database or personal configuration

### Covered behaviors

Configurable topics and source-specific literal queries; Crossref/Europe PMC/arXiv
pagination and failures; publication-date precision, conflicts, future dates and
preprint submission dates; DOI/PMCID/arXiv identity deduplication; preprint-to-journal
relations preserved without false identity merges; exact source anchors and invalid
reference rejection; multilingual output; full-text fallback; figure-scoped reuse
rights and unsafe URL blocking; HTML injection; HTTP retry/redirect protection;
recipient and profile ledger isolation; dry-run side effects; uncertain SMTP result
handling, stable outbox replay, configuration mismatch refusal, file locks and
same-local-day idempotency; timezones, weekdays and DST gaps/folds.

### Upgrade checks

The original v1 configuration shape remains accepted. Legacy database fixtures
are copied into audience-scoped v2 tables without deleting original tables. Sent
aliases/checkpoints and uncertain delivery states are preserved. A previously sent
v1 issue prevents a second send on that local day. Legacy prepared drafts do not
bypass the new content-fingerprint guard. An independent reviewer also exercised these migration paths using the untouched
v1 implementation to create the legacy fixtures. No real user's installed database was
modified; these checks used synthetic temporary databases.

## Not covered by local validation

- Real literature-provider end-to-end retrieval in the eventual deployment network
- Live model responses or scientific semantic correctness beyond evidence anchors
- Real SMTP delivery, inbox arrival, image loading in email clients or bounce handling
- Running an unattended scheduler over real elapsed days
- Docker build/run (Docker was unavailable)
- Remote GitHub CI, deployment, repository publication or distribution to recipients;
  check the actual repository and commit separately
- Browser visual rendering: Chromium failed to create a required local socket even
  with approved escalation; cloud-browser file URLs were prohibited. HTML was tested
  structurally, but no visual screenshot or email-client compatibility pass is claimed

The included preview files are entirely synthetic, hand-authored fixtures. Their
papers, authors, dates, data and results are not actual research. They make no API,
model, SMTP or state-database calls. Real operation requires the operator's own
network-enabled host, private provider settings and successful local smoke tests.
