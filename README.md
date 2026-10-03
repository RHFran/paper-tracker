# Paper Tracker

Turn your research topics into source-grounded digests, with optional scheduled
email delivery. Choose topics, recipient, local delivery time, weekdays, timezone
and output language. Run one reader or several isolated profiles from the same
operator-managed backend.

[中文说明](README_中文.md) · [Demo](examples/preview/README.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

**Python 3.11+ · No runtime dependencies · MIT · Safe dry-run by default**

## What it does

- Searches **Crossref, Europe PMC and arXiv**, with configurable queries and topic filters.
- Produces **HTML, plain text and JSON audit reports** with source links and evidence levels.
- Adds an evidence-grounded research overview and paper summaries when a compatible
  model is configured; otherwise produces a clearly labeled discovery digest.
- Uses a concise, Nature-inspired editorial layout with **one global numbered
  reference list** across the overview and topic sections.
- Optionally includes rights-checked source figures or source links. It never
  generates an image and presents it as a research figure.
- Supports multiple profiles, persistent deduplication, timezone-aware scheduling
  and an outbox that stops automatic retries after an uncertain SMTP outcome.
- Defaults to **no email sending**. `preview` is an offline synthetic demo;
  `run` retrieves real metadata but sends only with `--send`.

This is a self-hosted CLI/backend, not an already-hosted subscription service.
An email address alone cannot activate delivery: an operator must provide a
running host, retrieval network access and an SMTP sender. Model-assisted
interpretation also needs a model endpoint and credentials.

## Try the demo first

No API keys, account, email configuration or Python package installation needed.
From a downloaded or cloned copy of this repository:

```sh
python3 -m literature_digest --config config.example.json preview --language en
python3 -m literature_digest --config config.example.json preview --language zh-CN
```

Open `output/demo.en.html` or `output/demo.zh-CN.html` in your browser. Each command
also creates a matching `.txt` and `.json` file. All content is **clearly labeled
synthetic**: no real papers are retrieved, no model is called, no mail is sent and
no delivery database is touched. The fixed demo topics are independent of your
live configuration.

Browse the checked-in examples directly on GitHub:

- English: [readable text](examples/preview/demo.en.txt), [HTML file](examples/preview/demo.en.html), [evidence JSON](examples/preview/demo.en.json)
- 中文：[纯文本](examples/preview/demo.zh-CN.txt)、[HTML 文件](examples/preview/demo.zh-CN.html)、[证据 JSON](examples/preview/demo.zh-CN.json)
- [Demo walkthrough and expected output](examples/preview/README.md)

GitHub displays HTML as source. Download the file and open it locally to view the
layout; no hosted demo or GitHub Pages deployment is implied.

## Quickstart

Requires **Python 3.11+**, an IANA timezone database, and Linux, macOS or WSL for
process locking. The runtime has no third-party Python dependencies. Install from this checkout;
publication to PyPI is not part of this release.

`paper-tracker` is the preferred command. The existing `literature-digest` command,
`python -m literature_digest`, `LITERATURE_*` environment variables and configuration
format remain supported for existing installations.

Already running 1.x? Follow [the upgrade steps](#upgrading-from-1x) first.
For a new setup, run from this project's directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# Guided setup: topics, recipient, language, timezone and local delivery time.
paper-tracker init
paper-tracker validate

# Safe visual demo: synthetic papers, no retrieval, model call or email.
paper-tracker preview --language en

# Retrieve actual metadata and write a report; do not send email.
paper-tracker run
```

The JSON response reports generated file paths. Open the `.html` report in your
browser, read `.txt` for a mail-friendly version, and inspect `.json` for provenance.
The offline preview is explicitly marked as demonstration content, not real research.

For repeatable setup instead of prompts:

```sh
paper-tracker --config config.json init --yes \
  --recipient researcher@example.org \
  --topic "urban climate adaptation" --topic "battery recycling" \
  --language en --timezone Europe/London --time 08:30
```

Replace the reserved example address with the intended recipient. Initialization
does not enable sending or store credentials. `--config` and `--profile` are global
options: put them before the command.

## Upgrading from 1.x

Paper Tracker is the new project name; the distribution is now `paper-tracker`.
After stopping the worker and completing the backup in step 1 below, uninstall
the old distribution from an existing virtual environment with
`python -m pip uninstall daily-literature-digest`, then install the new checkout
with `python -m pip install .`. Keep private config/state outside package files.
The command alias and import package remain compatible.

This is an in-place code upgrade. Keep your existing single-reader configuration
first; do not rerun `init` or replace private files with the examples.

1. Stop the old scheduler/worker. Privately back up the old source, `config.json`,
   environment/secrets file and the entire state directory, including SQLite
   database and any WAL/SHM files. Keep all workers stopped during the backup.
2. Replace/install the application code only. Retain your private configuration,
   `.env`, database and output. Keep the original recipient, `default` profile ID
   and state path for delivery continuity.
3. Run `validate`, `preview`, `status`, then a real `run` without `--send`. Review
   the migrated status and reports before restarting **one** scheduler/worker.

An existing config without `topics` keeps the original BVOC/tree-species topics.
The language defaults to `zh-CN`; your configured timezone is retained. On first
state access, valid v1 delivery records are copied non-destructively into the
recipient-scoped `default` ledger. Original tables remain, along with migrated
sent-paper identities, checkpoints and unresolved outcomes. A previously sent
issue blocks another send on the same local day even though v2 digest IDs differ.

Old `prepared` payloads have no v2 configuration fingerprint and cannot be
replayed. Resolve any uncertain delivery against provider records; a run on the
next local day can prepare a fresh issue. Rescanning the current publication
window is normal and does not itself discard delivery history.

Convert to multiple readers later: `profiles` creates new state subdirectories,
so simply moving the settings into that array **does not transfer deduplication
history**. To retain the existing reader, keep its ID `default` and the same
recipient, and deliberately place a consistent backup of its database at the new
resolved path (for example, `state/default/digest.sqlite3`) while workers are
stopped. Renaming a profile or changing its recipient creates a different ledger.
Migration has been tested with fixtures; this release has not migrated your actual
existing installation.

## Your research, schedule and language

Start with `config.example.json`, or let `init` create your private `config.json`.
These reader settings are the main controls:

```json
{
  "recipient": "researcher@example.org",
  "timezone": "Europe/London",
  "language": "en",
  "schedule": {"time": "08:30", "weekdays": [0, 1, 2, 3, 4], "catch_up": true},
  "topics": [
    {
      "id": "urban-climate",
      "name": "Urban climate adaptation",
      "queries": ["urban climate adaptation", "urban heat resilience"],
      "include_any": ["climate adaptation", "heat resilience"],
      "include_all": [],
      "exclude_any": []
    }
  ]
}
```

- `time` is `HH:MM` in the profile's IANA timezone; weekdays are `0=Monday` through
  `6=Sunday`. `catch_up: true` permits a late run on that same local day.
- `language` accepts tags such as `zh-CN`, `en`, `de` and `ja`. Built-in report
  labels are Chinese or English; other tags guide model-generated prose, with
  English interface labels. Titles and quoted evidence retain the source language.
- `queries` retrieve candidates. `include_any`, `include_all` and `exclude_any`
  filter their text. Use literal topic phrases, not provider query syntax, in
  filters. Empty filters fall back to the topic's query phrases.
- Optional `source_queries` supplies separate query lists for `crossref`,
  `europepmc` or `arxiv`. These are literal search phrases too, not provider query
  syntax; operators and quotation syntax are sanitized.
- `publication_window_days` controls the rolling publication window (default 7).
  `max_papers_per_track` is the per-topic paper cap; the legacy key name is retained.
- `sources` selects adapters. Europe PMC focuses on life sciences; Crossref and
  arXiv broaden discovery. Coverage and abstract availability vary by field/source.

### Several readers

Use `config.profiles.example.json` or the alternative
[`templates/profiles.example.json`](templates/profiles.example.json). Put shared
retrieval, model and mail settings at the root and each reader's settings in
`profiles`. Each profile has a unique `id`, recipient, topics and schedule.

```sh
paper-tracker --config config.profiles.example.json validate
paper-tracker --config config.profiles.example.json --profile battery-en run
# Omit --profile to process all configured readers.
```

Use the actual profile ID from your file. Outboxes, deduplication and output paths
are isolated by profile. Paths are relative to the JSON file. Keep state on durable
storage; a new or deleted database cannot remember previously delivered papers.
Profiles are not a security boundary between untrusted users.

## Enable model summaries and email

1. Copy `.env.example` to a private `.env`, then fill it in locally. The CLI reads
   process environment variables; it does **not** automatically load `.env`.
2. Set `llm.enabled` to `true` for model-assisted analysis, and configure an
   HTTPS OpenAI-compatible chat-completions base URL, model and API key.
3. Set `mail.enabled` to `true` for email, and configure SMTP host, account,
   password/app-password and an authorized From address. Use `ssl` with the
   provider's port (commonly 465), or `starttls` (commonly 587).
4. Export the environment, review a real dry run, then send explicitly:

```sh
# Only source a private file you created and trust.
chmod 600 .env
set -a
. ./.env
set +a
paper-tracker validate
paper-tracker run
paper-tracker run --send
```

`run` can contact the configured model and incur provider charges even without
`--send`. Enabling a model transmits selected paper evidence to that provider.
No model configuration means discovery output, not an invented deep interpretation.
SMTP acceptance means the sender accepted the message, not guaranteed inbox delivery.

## Scheduling

Choose one scheduling approach and keep the machine running with its configured
secrets and durable state accessible.

```sh
# Foreground worker, checking each reader's local schedule; Ctrl-C to stop.
paper-tracker schedule --send

# Or call this once per minute from systemd/cron/another external timer.
paper-tracker tick --send
```

Without `--send`, both commands remain dry-run. `run --send` sends immediately;
`tick --send` obeys the schedule. A schedule is configuration until a worker or
external timer is actually running. Catch-up does not replay historical missed days.

See [`examples/README.md`](examples/README.md) for systemd, cron and Docker.
Nothing in this repository automatically installs or enables a scheduler.

## Evidence, references and figures

Source metadata and evidence are retained in the JSON audit. The pipeline rescans
the publication window to catch late-indexed records, reconciles identifiers and
excludes papers already recorded as sent. Missing, conflicting or insufficiently
precise publication dates are audited rather than silently treated as recent.

Each paper uses four blocks: **Highlights**, **Scientific question**,
**Experimental or modeling methods**, and **Main results**. Relevant data details
and reported bounds stay within methods/results.

Model statements require short matching evidence excerpts. That check establishes
traceability, not semantic correctness; review important interpretations against
the cited paper. Metadata-only entries do not masquerade as full-text analysis.
The overview follows the same source-grounding principle and numbered references
remain consistent when a paper appears under several topics.

`fetch_full_text` optionally requests available full text. `images.mode` is `off`
by default, with `links` and `embed` for supported source figures. Embedding needs
explicitly supported figure-level reuse rights and attribution; otherwise the
report links to the source. A manually supplied `figure_catalog` entry needs
`license_scope: "figure"` for embedding; article-level open-access status is not
sufficient. See the [figure metadata template](templates/README.md). Availability
depends on the source and the paper's license. Third-party
paper text and images are not relicensed by this repository's MIT license.
“Nature-inspired” describes the layout, not journal affiliation or publisher-exact formatting.

## Operations and troubleshooting

```sh
paper-tracker status
# After checking the provider/recipient records for an uncertain delivery:
paper-tracker resolve DIGEST_ID sent
# OR, only after confirming it was not delivered:
paper-tracker resolve DIGEST_ID retry
paper-tracker send DIGEST_ID
```

Use `--profile ID` for state operations in a multi-reader configuration. `send`
reuses a prepared report; stale reports are refused. Check `status` before retrying
and never delete the database to bypass uncertainty safeguards.

- **No papers:** check the audit's exclusions, date requirements and topic filters.
  Empty output does not establish that no relevant literature exists.
- **Retrieval failure:** check network access, provider limits and returned errors.
  A failed required source is reported rather than sent as a successful empty digest.
- **No summaries:** enable/configure the model and check evidence availability.
  A failed or unsupported analysis falls back to discovery mode.
- **No email:** check `mail.enabled`, exported variables, explicit `--send`, due time,
  recipient, provider logs and unresolved outbox entries.
- **Unknown timezone:** install the operating system's IANA timezone data.

## Development and release status

```sh
python -m unittest discover -s tests -v
python -m compileall -q literature_digest
```

The CI workflow runs offline tests and a CLI/package smoke check. Automated fixtures
mock external services. This release does **not** claim a real SMTP delivery,
real model response, live deployment or an installed scheduler was tested. See
[VALIDATION.md](VALIDATION.md) for the recorded verification scope.

[MIT license](LICENSE). Release history: [CHANGELOG.md](CHANGELOG.md).
