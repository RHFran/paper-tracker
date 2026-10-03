# Smart Paper Tracker user guide

<a id="english"></a>

Turn your research topics into source-grounded digests, with optional scheduled
email delivery. Choose topics, recipient, local delivery time, recurring weekdays
or specific dates, timezone and output language. Run one reader or several isolated
profiles from the same operator-managed backend.

[Project home](../README.md) · [中文完整指南](../docs/user-guide_中文.md) · [Platform setup](../docs/platform-setup.md) · [Security](../SECURITY.md)

**Python 3.11+ · Windows / Linux / macOS · MIT · Explicit opt-in email**

## What it does

- Searches **Crossref, Europe PMC and arXiv**, with configurable queries and topic filters.
- Produces **HTML, plain text and JSON audit reports** with source links and evidence levels,
  plus **RIS and BibTeX** files for reference-manager import.
- Uses a Codex/Claude Code CLI or compatible API for real research digests, producing an evidence-grounded
  research overview and structured paper summaries. Failed analysis blocks delivery.
- Uses a concise, Nature-inspired editorial layout with **one global numbered
  reference list** across the overview and topic sections.
- Optionally includes rights-checked source figures or source links. It never
  generates an image and presents it as a research figure.
- Supports multiple profiles, persistent deduplication, timezone-aware scheduling
  (recurring weekdays or one-off dates) and an outbox that stops automatic retries
  after an uncertain SMTP outcome.
- Defaults to **no email sending**. `preview` is an offline synthetic demo;
  `run` retrieves real metadata but sends only with `--send`.

This is a self-hosted CLI/backend, not an already-hosted subscription service.
An email address alone cannot activate delivery: an operator must provide a
running host, retrieval network access and a usable model backend. Choose an
already-installed, logged-in Codex/Claude Code CLI (no second API key), or an
independent compatible API. Email uses SMTP or the explicit connector handoff.
See [model backends and delivery](model-backends.md). The program performs the
research pipeline itself; there is no required host-written report import.

## Try the demo first

[Open the rendered HTML demo](https://rhfran.github.io/smart-paper-tracker/?lang=en)
or [switch to Chinese](https://rhfran.github.io/smart-paper-tracker/).

No API keys, account or email configuration needed. Python 3.11+ and timezone
data must be available; Windows users should run [setup](../docs/platform-setup.md)
first to install the timezone package. From a downloaded or cloned repository:

```sh
python3 -m literature_digest --config config.example.json preview --language en
python3 -m literature_digest --config config.example.json preview --language zh-CN
```

Open `output/demo.en.html` or `output/demo.zh-CN.html` in your browser. Each command
also creates matching `.txt`, `.json`, `.ris` and `.bib` files. All content is **clearly labeled
synthetic**: no real papers are retrieved, no model is called, no mail is sent and
no delivery database is touched. The fixed demo topics are independent of your
live configuration.

Browse the checked-in examples directly on GitHub:

- English: [readable text](../examples/preview/demo.en.txt), [HTML file](../examples/preview/demo.en.html), [evidence JSON](../examples/preview/demo.en.json)
- 中文：[纯文本](../examples/preview/demo.zh-CN.txt)、[HTML 文件](../examples/preview/demo.zh-CN.html)、[证据 JSON](../examples/preview/demo.zh-CN.json)
- [Demo walkthrough and expected output](../examples/preview/README.md)

GitHub displays repository HTML files as source. Download the file and open it
locally to view the layout; see the [project home](../README.md) for demo links.

## Quickstart

Requires **Python 3.11+** and an IANA timezone database. Windows, Linux and macOS
are supported; Windows installs the `tzdata` package. See the
[platform setup guide](../docs/platform-setup.md) for scripts, prerequisites and
agent-assisted setup. The commands below use a POSIX shell. Install from this
checkout; publication to PyPI is not part of this release.

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

# After configuring the required LLM below, generate a real report without email.
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

The project is now **Smart Paper Tracker**. The distribution remains `paper-tracker`,
as introduced in 2.0; existing commands, configurations and environment names stay
compatible.
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

- `time` is `HH:MM` in the profile's IANA timezone. `weekdays` is a nonempty list
  of unique integers, `0=Monday` through `6=Sunday`, for weekly recurrence.
- Alternatively, use `dates`, a list of 1–1000 unique, valid `YYYY-MM-DD`
  strings, for specific local calendar dates. Dates are one-off and do not recur
  annually. Do not supply both `dates` and `weekdays` in the same schedule object.
  The default is `dates: null` with weekday-based scheduling; existing weekday
  configurations keep their behavior.
- `catch_up: true` permits a late run only on the scheduled local day; it never
  replays earlier missed dates. With `false`, a tick must arrive during the
  scheduled minute. See [different topics on different days](#different-topics-on-different-days).
- `language` accepts tags such as `zh-CN`, `en`, `de` and `ja`. Built-in report
  labels are Chinese or English; other tags guide model-generated prose, with
  English interface labels. Titles and quoted evidence retain the source language.
- `queries` retrieve candidates. `include_any`, `include_all` and `exclude_any`
  filter their text. Use literal topic phrases, not provider query syntax, in
  filters. Empty filters fall back to the topic's query phrases.
- Optional `source_queries` supplies separate query lists for `crossref`,
  `europepmc` or `arxiv`. These are literal search phrases too, not provider query
  syntax; operators and quotation syntax are sanitized.
- arXiv joins a query's literal words with `AND` in metadata search rather than
  requiring the full phrase. Multiple queries contribute a union of results;
  searches are bounded and do not claim exhaustive literature coverage.
- `publication_window_days` controls the rolling publication window (default 7).
  `max_papers_per_track` is the per-topic paper cap; the legacy key name is retained.
- `sources` selects adapters. Europe PMC focuses on life sciences; Crossref and
  arXiv broaden discovery. Coverage and abstract availability vary by field/source.

### Several readers

Use `config.profiles.example.json` or the alternative
[`templates/profiles.example.json`](../templates/profiles.example.json). Put shared
retrieval, mail and default model settings at the root and each reader's settings
in `profiles`. Each profile has a unique `id` and its own recipient, topics and
schedule. Several profiles may share the same recipient and send separate
messages, including on the same day. Use one profile with several topics when you
want one combined digest.

```sh
paper-tracker --config config.profiles.example.json validate
paper-tracker --config config.profiles.example.json --profile battery-en run
# Omit --profile to process all configured readers.
```

A profile can override the root `llm` settings to use a different provider, model
or credential environment. Put **environment variable names, never API keys**, in
`base_url_env`, `api_key_env` and `model_env`. For example, merge this fragment into
one profile, then set the corresponding variables privately on its host:

```json
{
  "llm": {
    "enabled": true,
    "base_url_env": "BVOC_LLM_BASE_URL",
    "api_key_env": "BVOC_LLM_API_KEY",
    "model_env": "BVOC_LLM_MODEL"
  }
}
```

Other profiles retain root defaults unless they override them. See the
[provider setup guide](../docs/platform-setup.md) for interactive configuration.

Use the actual profile ID from your file. Outboxes, deduplication and output paths
are isolated by profile. Paths are relative to the JSON file. Keep state on durable
storage; a new or deleted database cannot remember previously delivered papers.
Profiles are not a security boundary between untrusted users.

### Different topics on different days

Use **one profile per topic/schedule combination**, even when every digest goes to
one inbox. Topics inside one profile always run together; individual topic objects
do not have schedules. Start from the complete, safe
[`config.calendar.example.json`](../config.calendar.example.json):

- Monday at 08:30: BVOC research
- Wednesday at 09:00: remote sensing of tree species
- March 15, 2027 at 10:00 only: urban forests and heat mitigation

All three use `Asia/Shanghai` local time and inherit the same example recipient.
Change the address, timezone, language, queries and date to your needs. Here is the
core configuration (model calls and email are disabled):

```json
{
  "recipient": "researcher@example.org",
  "timezone": "Asia/Shanghai",
  "language": "en",
  "schedule": {"time": "08:30", "weekdays": [0, 1, 2, 3, 4], "catch_up": true},
  "llm": {"enabled": false},
  "mail": {"enabled": false},
  "profiles": [
    {
      "id": "bvoc-monday",
      "schedule": {"time": "08:30", "weekdays": [0]},
      "topics": [{
        "id": "bvoc",
        "name": "Biogenic volatile organic compounds (BVOCs)",
        "queries": ["biogenic volatile organic compounds", "BVOC emissions"],
        "include_any": ["biogenic volatile organic", "BVOC"]
      }]
    },
    {
      "id": "tree-species-wednesday",
      "schedule": {"time": "09:00", "weekdays": [2]},
      "topics": [{
        "id": "tree-species",
        "name": "Remote sensing of tree species",
        "queries": ["tree species mapping hyperspectral", "tree species classification lidar"],
        "include_any": ["tree species", "forest species"]
      }]
    },
    {
      "id": "urban-forest-date",
      "schedule": {"time": "10:00", "dates": ["2027-03-15"]},
      "topics": [{
        "id": "urban-forest",
        "name": "Urban forests and heat mitigation",
        "queries": ["urban forest heat mitigation", "urban trees cooling"],
        "include_any": ["urban forest", "urban trees"]
      }]
    }
  ]
}
```

A profile inherits shared schedule fields such as `catch_up`, but an explicit
`dates` list replaces inherited `weekdays`. An explicit `weekdays` list switches
back to recurring weekdays and clears inherited dates. A profile that overrides
only `time` retains its inherited day/date selection. Keep profile IDs stable:
state and paper deduplication are separate for each profile, so a paper matching
two profiles can appear in both, even when they share a recipient. Enable and
configure the required LLM before using a real `run` or a due `tick`.

Copy the example to a private file before editing:

```sh
cp config.calendar.example.json config.calendar.json
paper-tracker --config config.calendar.json validate
# Optional: generate this profile's real report now, regardless of its schedule.
bash scripts/run.sh --env-file .env --config config.calendar.json --profile bvoc-monday run
# Run due profiles once without sending; this does not install a timer.
bash scripts/run.sh --env-file .env --config config.calendar.json tick
```

`validate` reports each profile's next scheduled instant. For a date-based profile,
`next_run: null` means no future scheduled instant remains; past dates do not turn
into a weekly schedule. Same-day catch-up can still be due after today's planned
time. Edit future dates when needed. `run` is an immediate manual override, so use
`tick` or `schedule` for calendar-controlled execution.

To actually deliver automatically, complete [email setup](#enable-model-summaries-and-email),
then keep `bash scripts/run.sh --env-file .env --config config.calendar.json schedule --send` running,
or have an external timer call `bash scripts/run.sh --env-file .env --config config.calendar.json tick --send`
once per minute. Simply saving the JSON does not activate a service.

## Enable model summaries and email

### CLI backends and model-assisted discovery

For Codex/Claude Code, install and log in to the CLI on the execution machine,
then set `llm.enabled: true` and `llm.backend: "codex"` or `"claude"`. The
program invokes it for structured output; its credentials stay with the CLI.
Optional `cli_executable` selects a command path, `cli_model` selects a model
(empty uses the effective default of the isolated CLI invocation, not its user-configured model), and `cli_timeout_seconds` defaults to 180 with a
maximum of 1800 per call. CLI/account usage and limits still apply.

Enable `llm.plan_queries` for model-assisted query planning and
`llm.screen_candidates` for relevance screening; `max_screen_candidates` defaults
to 50. Both switches default to false for old configurations. They add model
calls before evidence-grounded paper analysis. See [backend configuration](model-backends.md).

Email transport is independent: choose the existing SMTP route below, or
`run --prepare-connector` followed by the authorized host's one external tool send
and confirmed receipt import. Only `run` prepares connector messages; `tick` and
`schedule` do not invoke an external connector. See the [connector lifecycle](model-backends.md#connector-send-lifecycle).

### Independent API and direct SMTP

The local API wizard supports OpenAI-compatible providers including DeepSeek,
Qwen, Moonshot, OpenAI and a custom HTTPS endpoint. Choose your actual model ID;
provider availability and pricing can change. New interactive setup offers the
wizard automatically, or run it later:

```sh
bash scripts/run.sh --config config.json configure-model
# For a multi-profile file, select the profile before the command:
bash scripts/run.sh --config config.calendar.json --profile bvoc-monday configure-model
# Load only your trusted private environment file; live model use may incur charges.
bash scripts/run.sh --env-file .env validate
bash scripts/run.sh --env-file .env run
```

On Windows replace `bash scripts/run.sh` with `./scripts/run.ps1`. The wizard
uses hidden local key entry, makes no network request, and enables the selected
profile's model only after you approve saving. `.env` is plaintext beside the
config, private mode `0600` on POSIX; verify private inherited permissions on
Windows. Never commit it. Existing model settings/slots require `--replace` and
confirmation before replacement. For process-only input without saving, configure
environment references and use `--prompt-secrets` instead. See
[platform/provider instructions](../docs/platform-setup.md) for full details.

For manual API (`llm.backend: "api"`, the default) and SMTP setup:

1. Copy `.env.example` to a private `.env`, then fill it in locally. The CLI reads
   process environment variables; it does **not** automatically load `.env`.
2. Real `run`, due `tick`/`schedule`, and delivery require an enabled, configured LLM.
   Set `llm.enabled` to `true` and configure an HTTPS OpenAI-compatible
   chat-completions base URL, model and API key. Compatible domestic providers
   can be used too; see [provider setup](../docs/platform-setup.md). The offline
   synthetic `preview` does not need an LLM.
3. Set `mail.enabled` to `true` for email, and configure SMTP host, account,
   password/app-password and an authorized From address. Use `ssl` with the
   provider's port (commonly 465), or `starttls` (commonly 587).
4. Load the private environment file as data, review a real dry run, then send explicitly:

```sh
# Only read a private file you created and trust; do not execute it as shell code.
chmod 600 .env
bash scripts/run.sh --env-file .env validate
bash scripts/run.sh --env-file .env run
bash scripts/run.sh --env-file .env run --send
```

The wizard's `.env` is literal configuration data for the launcher's parser, not
a shell script. **Do not `source` it or run `. ./.env`.** Both the launcher and
the `paper-tracker` / `python -m literature_digest` CLI support an explicit
`--env-file` before the subcommand; without it, they use the process environment
and do not load `.env` automatically. Existing nonempty process environment
values take precedence over file entries; only names referenced by the loaded
configuration are read. The supplied systemd and cron examples use
this safe parser. Docker/Compose have different environment-file rules; follow
the [deployment examples](../examples/README.md) rather than reusing quoted wizard
values blindly.

`run` can contact the configured model and incur provider charges even without
`--send`. Enabling a model transmits selected paper evidence to that provider. CLI/API usage and costs vary with the chosen
model, selected paper count and evidence length. An empty eligible selection may
not require a model request, but still requires valid model configuration.
Missing credentials or failed/unsupported model analysis stops a real digest;
metadata-only discovery output is not a successful substitute for the product.
SMTP acceptance means the sender accepted the message, not guaranteed inbox delivery.

## Scheduling

Choose one scheduling approach and keep the machine running with its configured
model login/secrets and durable state accessible. These commands are the direct
SMTP path. A connector host separately schedules the prepare/claim/send/confirm
workflow; connector preparation is currently an immediate `run` operation.

```sh
# Foreground worker, checking each reader's local schedule; Ctrl-C to stop.
bash scripts/run.sh --env-file .env schedule --send

# Or call this once per minute from systemd/cron/another external timer.
bash scripts/run.sh --env-file .env tick --send
```

Without `--send`, both commands remain dry-run. `run` bypasses weekday/date/time
checks, and `run --send` attempts immediate delivery with the normal mail and
outbox safeguards. `tick` and `schedule` obey each profile's local schedule. A
schedule is configuration until a worker or external timer is actually running.
Catch-up does not replay historical missed days. For different topics on different
weekdays or one-off dates, use the [calendar configuration above](#different-topics-on-different-days).

See [`examples/README.md`](../examples/README.md) for systemd, cron and Docker.
Nothing in this repository automatically installs or enables a scheduler.

## Import references into Zotero or EndNote

No extra export option is needed. Each nonempty real report writes `.ris` and
`.bib` beside its HTML/TXT/JSON files; names use
`<local-date>_<digest-id>[_preview].ris` and `.bib`. Exports contain only the selected,
deduplicated papers, not excluded, deferred or previously sent records. Empty
issues do not produce citation files. The HTML report links to the local export
files. When sending email, RIS and BibTeX are attached as files; a delivery retry
uses the prepared, immutable export snapshots rather than rereading changed files.

- **Zotero desktop:** File → Import… → A file, then choose RIS or BibTeX.
  [Official import guide](https://www.zotero.org/support/kb/importing_standardized_formats).
- **EndNote desktop:** File → Import → File, choose the RIS file and the
  **Reference Manager (RIS)** import filter; use UTF-8 text encoding.
  [Official import options](https://docs.endnote.com/docs/endnote/2025/v1/windows/en/content/08import/import_options.htm).

Exports preserve available authors, title, journal, publication date, DOI, original
URL, abstract and source/type notes. Missing metadata is omitted, never invented.
Opening a file directly depends on operating-system associations; the application
does not automatically synchronize a reference manager's cloud library. Import
UI steps can vary by application/version. Review imported author names: supplied
given/family boundaries are retained, while unstructured names are kept literally.

Offline `preview` also writes `demo.en.ris` / `.bib` or `demo.zh-CN.ris` / `.bib`.
These are conspicuously marked **DEMO / synthetic**. Use a disposable test library,
not your real reference collection, when trying these files.

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

`fetch_full_text` optionally requests available full text. For arXiv, the program
tries the official `https://arxiv.org/html/<exact-version-id>` page. If it is
unavailable or its article body is insufficient, evidence stays at the available
abstract/metadata level with a warning; navigation or HTML metadata is never
treated as full text.

`images.mode` is `off`
by default, with `links` and `embed` for supported source figures. Embedding needs
explicitly supported figure-level reuse rights and attribution; otherwise the
report links to the source. A manually supplied `figure_catalog` entry needs
`license_scope: "figure"` for embedding; article-level open-access status is not
sufficient. See the [figure metadata template](../templates/README.md). Availability
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
- **No summaries:** enable/configure the required model, inspect model errors and
  check evidence availability. Failed or unsupported analysis blocks delivery.
  After a failed paper/overview analysis, automatic `tick`/`schedule` retries for
  that profile pause for the rest of its local day to avoid repeated paid calls
  every minute. The pause survives a restart; `status` shows its reason. After
  fixing the model, use an explicit `run` (without `--send` first) to retry.
  Changing the model/content configuration also permits recovery; changing only
  the schedule does not. A successful complete analysis clears the pause, and
  sent-paper deduplication remains intact.
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
[VALIDATION.md](../VALIDATION.md) for the recorded verification scope.

[MIT license](../LICENSE). Release history: [CHANGELOG.md](../CHANGELOG.md).
