# Super Paper radar agent setup and research contract

Super Paper radar is a source-installed Python toolkit for agent-led research
digests. Read the concise README, `docs/agent-workflow.md` and
`docs/platform-setup.md` before setup or research work.

- The research agent owns planning, discovery, evidence reading, relevance
  decisions and synthesis. Use the program's search/fetch/ingest, validation,
  finalization and library tools rather than treating the agent as a JSON-only
  model call. The program owns the durable job contract, provenance checks,
  deduplication, rendering, literature index, schedules and delivery ledger.
- New `init` and example configurations use `workflow.mode: "agent"`. Root or
  profile `agent` settings are `backend` (`codex`, `claude` or `host`),
  `executable`, `model`, `reasoning_effort`, and `timeout_seconds` (default 1800).
  Empty model/effort inherit defaults. Select a current account-available flagship
  model only after checking installed support; do not guess model IDs. Record the
  requested model/effort, do not silently fall back, and do not claim that host
  settings change an already-running agent. Existing configs without `workflow` retain `standalone`; never silently migrate them.
- In agent mode, `run`, due `tick`, and `schedule` launch a complete agent job.
  Codex/Claude retain their normal tools and security controls. Never disable
  tools to turn this workflow into model-only calls, bypass permission checks,
  copy credentials, or weaken managed settings to make a run succeed.
- A `host` backend exports a durable `awaiting_agent` job. Read its generated
  task and contract, then use `agent-tool JOB_ID` operations. Export/preparation
  is not completed research. `validate` and `finalize` must pass the program's
  evidence and result checks; finalization saves literature and never sends mail.
- Use the same private config/profile throughout a job. Preserve job files,
  retrieved evidence and the state ledger on durable local storage. Do not
  fabricate evidence, decisions, provenance or a successful finalization. A
  failed agent job must not cause an automatic paid retry every minute; inspect
  the error and use the explicit `--retry-agent` only when a retry is intended.
  For an interrupted running job, use `agent-recover JOB_ID --agent-stopped` only
  after the operator verifies every prior agent/tool descendant has stopped.
  Never infer this from one missing parent PID or reset a send claim.
- `workflow.mode: "standalone"` preserves the optional fixed pipeline. Only this
  compatibility mode uses `llm.backend` (`api`, `codex` or `claude`) and its
  model-only planning/screening switches. Read `docs/model-backends.md`.
- Work on the computer/environment the user selects. An agent chat or temporary
  execution container does not supply durable production hosting.
- Python 3.11+ is required. Use `scripts/setup.sh` or `scripts/setup.ps1`; the
  portable entry is `python scripts/setup.py`. Setup preserves existing configs.
  Start with `--demo` / `-Demo` for a synthetic offline preview. Preview is never
  real research. The API wizard is opt-in rather than the main setup path.
- CLI execution uses the already installed, signed-in CLI under the execution
  user. A supported usable login needs no second model API key. Keep CLI and
  connector credentials in their own service; do not copy them into this project.
- Agent and standalone live runs consume account usage and may incur charges,
  including dry runs and connector preparation. Explain that boundary before a
  live call. Setup, validation and synthetic preview make no model calls.
- `configure-model` is the independent API wizard. It selects provider/base URL/
  model, creates a key slot per subscription and uses hidden local input. The
  user enters secrets directly in their terminal. Never request secrets in chat,
  pass them as command arguments or print `.env` files.
- `--env-file` explicitly loads a private literal environment file;
  `--prompt-secrets` prompts without saving. JSON stores variable names, never
  credentials. Do not force-add ignored private config, `.env`, state, job files,
  generated reports or logs to version control.
- Do not send mail, make paid tests, install/enable persistent schedulers or
  change OS security settings as an unrequested setup side effect. Review the
  intended recipients, provider and schedule before enabling `--send`.
- Research and delivery choices are independent. SMTP `--send` / `tick` /
  `schedule` remain supported. `run --prepare-connector` prepares an immutable
  envelope after validated research, without SMTP or sending. Claim it with
  `begin-send DIGEST_ID` before one authorized external mail-tool call, then
  import only a confirmed provider receipt using `confirm-sent DIGEST_ID
  --receipt FILE`. Do not alter a claimed envelope, invent receipts, equate
  preparation with delivery or retry an uncertain send. Agent-mode `tick` /
  `schedule --prepare-connector` can prepare jobs, but the host orchestrates actual
  connector calls; see `docs/model-backends.md`. A completed dry run can be safely
  promoted with `run --send` or `run --prepare-connector`; it revalidates the saved
  result without repeating research or replacing a prepared/claimed envelope.
- Use multiple profiles for different topic/schedule/agent combinations. One
  config should have one scheduler; retain its durable local state ledger.
- New agent setups enable lawful main original figures. Read
  `docs/original-figures.md`; the agent chooses method/framework and key-result
  figures, registers exact caption/source/rights evidence with `figure --input`,
  and adds a useful configured-language explanation. Never use metadata CC0 as
  image rights, generated substitutes, or unsupported claims of inline delivery.
  Existing explicit images.off stays off. Use CID original-image attachments.
- New jobs use six per-paper sections and a grounded closing research outlook;
  read `docs/research-outlook.md`. Ideas are hypotheses with citations and tests,
  not findings proved by the papers. Preserve schema-1 compatibility.
- Use `agent-revise` only for a user-requested revised edition of a confirmed sent
  agent job. Keep the same audience ledger and old files; no sends happen during
  preparation. Never edit sent history or clear deduplication to resend.
- Run `python -m unittest discover -s tests -v`, compile checks and offline CLI
  smoke tests. Use synthetic adapters, not real SMTP/model calls, for tests.
- Report what was verified and what was not. Configuration validation and stub
  tests do not establish CLI login, account credit, live agent/API compatibility,
  external connector delivery or 24/7 hosting.
