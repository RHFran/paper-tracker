# Changelog

## 3.0.0 — 2026-10-03

### Agent-led research and Super Paper radar

- New installs and examples default to agent-led research: the timer launches a
  full Codex/Claude Code agent, which chooses queries/tools, reads evidence,
  screens papers, interprets findings and manages the library through project tools.
- Add a durable host-agent contract for Codex dot and other existing agents:
  `agent-export`, `agent-tool` source retrieval/ingestion/validation/finalization,
  and explicit interrupted-process recovery. Exporting a job is not research.
- Verify original metadata and evidence for supported DOI/arXiv/PMC URLs, including
  a narrowly verified arXiv abstract-page fallback for API429/network outages.
- Preserve anchored claims, profile/audience isolation, stable-ID deduplication,
  immutable connector outboxes and actual provider-receipt confirmation.
- Full agents keep normal tools/security settings; no permission bypass,
  credential copying, forced no-tools transformation or account-runtime relocation.
- Support explicit model and provider-specific reasoning effort. Audits distinguish
  requested settings from unverified effective model; host settings are selected
  at the host. The application does not choose a fallback model.
- Existing configs without `workflow` retain the standalone pipeline; its API and
  legacy model-only adapters remain available. API setup is now explicitly opt-in.
- Rename public branding and repository to Super Paper radar, use the selected
  paper-radar logo and recommend the Codex dot host workflow. Existing Python
  package, command aliases, environment names and service filenames are compatible.
- Verified 337 offline tests, source/installed-package portability and an actual
  synthetic agent subprocess/tool lifecycle. Live Codex inference, native Windows
  execution and real mail delivery are not implied by these checks.

## Prior standalone pipeline changes (retained)

### Portable program-owned model workflow

- The program orchestrates bounded model query planning, real source retrieval,
  semantic relevance decisions with evidence anchors, paper analysis, exact-ID
  deduplication, saved literature, and existing scheduled delivery.
- Add selectable Codex CLI and Claude Code CLI model backends beside the existing
  compatible API backend. CLI calls use structured output, isolated working
  directories, no shell invocation, restricted tools and bounded timeouts; no
  separate API key is needed when the chosen CLI has a usable account login.
- Add a profile-scoped persistent literature index and `library` / `library-export`
  commands. Successful dry runs also save papers; immutable audit copies preserve
  provenance when ordinary preview filenames are reused.
- Add `run --prepare-connector`, `begin-send` and `confirm-sent` for immutable
  program-generated mail and explicit provider receipt reconciliation. This is
  an external transport bridge, not a manual research-import path or an in-process
  connector scheduler. Uncertain sends never automatically retry.
- Add arXiv HTML full-text extraction with honest abstract fallback, term-based
  arXiv queries, and explicit `retrieval_policy: "bounded"` with visible incomplete
  coverage. Source throttling and transport errors still fail closed.
- Preserve existing API configurations and SMTP scheduling. New optional paid
  planning/screening failures, including malformed responses and retrieval failure
  after planning, pause automatic same-day model retries.


### Smart Paper Tracker branding

- Adopt **Smart Paper Tracker** across the bilingual README, documentation, demo
  and digest headers, with an original paper-and-tracking-signal SVG logo.
- Move repository and demo links to `RHFran/smart-paper-tracker` and update the
  GitHub Pages deployment guard for the renamed repository.
- Retain the `paper-tracker` distribution and CLI, `literature-digest` alias,
  `literature_digest` import, environment variables and configuration format.
  Existing installations do not need a data or credentials migration.

## 2.1.0 — 2026-10-03

### Topic calendars and clearer onboarding

- Schedule independent topic profiles for different weekdays or explicit local
  calendar dates with `schedule.dates`. Distinct profiles may share a mailbox.
  Date lists do not recur; same-day catch-up never replays earlier missed dates.
- Weekly and dated selectors are exclusive. A profile switching selectors clears
  the inherited selector; omitted selectors retain inheritance. Expired date lists
  validate normally and report `next_run: null` when no future instant remains.
- Concise English and Chinese homepage with corresponding Chinese content inline;
  detailed configuration and operations are in the bilingual user guides.
- Cross-platform setup/launch scripts, agent-assisted installation instructions,
  and a required-model configuration flow with provider/model choices and hidden
  API-key entry. Windows uses a native lock and the `tzdata` package.
- RIS and BibTeX exports for selected papers, linked from local reports and
  attached to email from the immutable prepared snapshot, for Zotero/EndNote import.
- A self-contained project showcase and downloadable, explicitly synthetic demos.

### Required model analysis

- Real `run`, scheduled work and sending require an enabled model with endpoint,
  API key and model environment variables. Offline `preview` still needs none.
  `validate` reports both valid configuration and whether live model setup is ready.
- Missing/invalid model setup is rejected before retrieval. Model errors, invalid
  evidence anchors, empty analyses and failed overview synthesis stop delivery;
  no successful discovery-only digest substitutes for the requested analysis.
- A failed paper/overview model step persists a per-profile automatic-retry pause
  for the current local day, surviving worker restarts and preventing paid calls
  every minute. Correct the model and retry explicitly with `run`, or change its
  model/content configuration. A successful retry clears the pause; normal
  automatic eligibility returns on the next local day. Sent deduplication remains.
- Candidates without sufficient source evidence are audited and skipped before
  consuming the paper cap. A genuinely empty eligible result remains a factual
  empty issue; it does not trigger an unnecessary model call.
- Prepared issues must carry the current model-analysis verification marker and
  export contract. Old prepared discovery-only issues cannot be replayed. Existing
  sent-paper history, recipient/profile ledgers and v1 migration remain intact.

### Upgrade notes

- Stop the worker, keep a consistent private configuration/state backup, and
  install the new code. Existing daily/weekly configuration remains accepted.
- Configure the required model before a real dry run or restarting the worker.
  Live model calls transmit selected source evidence and can incur token/API
  charges even without `--send`. Review provider/model pricing and limits.
- Do not delete state to bypass a refused legacy prepared issue; resolve any
  uncertain delivery first and generate a fresh issue on the next local day.
- Setup and repository publication do not enable automatic sending or install a
  running scheduler. Native Windows and external providers require environment-
  specific verification; see [VALIDATION.md](VALIDATION.md).

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

See the [English upgrade guide](docs/user-guide.md#upgrading-from-1x) or the
[Chinese README](README_中文.md) for the safe sequence.

Version 2 is an operator-run backend. Repository publication, hosted deployment,
real SMTP delivery and real model-provider verification are separate release steps.

## 1.0.0 — 2026-10-02

Initial two-topic Chinese research digest with source provenance, rolling-window
retrieval, mocked SMTP tests and a persistent delivery outbox.
