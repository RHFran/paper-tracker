# Smart Paper Tracker agent setup contract

Smart Paper Tracker is a source-installed Python research-digest application. Read the
concise README and `docs/platform-setup.md` before setup work.

- The program itself retrieves, plans queries, filters, analyzes, deduplicates,
  renders and schedules digests. Do not replace its core pipeline with a host
  agent's manually written report import. Read `docs/model-backends.md`.
- Work on the computer/environment the user selects. Do not imply that an agent
  chat or a temporary execution container supplies durable production hosting.
- Python 3.11+ is required. Use `scripts/setup.sh` or `scripts/setup.ps1`; the
  portable entry is `python scripts/setup.py`. Setup preserves existing configs.
- Start with `--demo` / `-Demo` for a synthetic offline preview, or normal setup
  when the user is ready to supply reader settings. Preview is never real research.
- Real digests require an enabled LLM: `llm.backend` is `codex`, `claude`, or
  `api` (default, preserving existing configs). CLI backends use the already
  installed, signed-in CLI under the execution user; no second API key is needed
  for a supported usable login. Do not copy CLI credentials. Use setup's
  `--skip-model` / `-SkipModel` to skip the API wizard for CLI mode. Optional
  `cli_executable`, `cli_model`, and `cli_timeout_seconds` control the invocation.
- Both CLI and API digests consume model/account usage and can incur charges,
  including dry runs. Explain the cost boundary before a live call. Never claim
  metadata-only output is the full product or that a dry run is always free.
- Opt in to `llm.plan_queries` and `llm.screen_candidates` for model-assisted
  query planning and relevance screening. They add model calls; existing saved
  configs keep them disabled unless requested. `max_screen_candidates` bounds
  relevance screening (default 50).
- `configure-model` is the independent API wizard. It selects provider/base URL/model,
  creates an independent key slot per subscription and uses hidden key entry.
  The user should enter secrets directly in their terminal. Do not request API
  keys/passwords in chat, pass them as command arguments, or print `.env` files.
- `--env-file` on the launchers explicitly loads a private literal environment
  file; `--prompt-secrets` prompts without saving. JSON stores variable names,
  never credentials. Do not force-add ignored private config, `.env`, state,
  generated reports or logs to version control.
- Do not send mail, make paid tests, install/enable persistent schedulers, or
  change OS security settings as an unrequested setup side effect. Review the
  intended recipients, provider and schedule before enabling `--send`.
- Model choice and delivery choice are independent. SMTP `--send` / `tick` /
  `schedule` remain supported. `run --prepare-connector` runs the full pipeline
  and prepares an immutable envelope without SMTP or email sending. Claim it with
  `begin-send DIGEST_ID` before one authorized external mail-tool call; import
  only its confirmed provider receipt via `confirm-sent DIGEST_ID --receipt FILE`.
  Do not modify a claimed envelope, invent receipts, confirm preparation as
  delivery, or retry an uncertain external send. Only `run` supports connector
  preparation; an authorized host orchestrates/schedules the external tool steps.
- Use multiple `profiles` for different topic/schedule/model combinations. One
  config should have one scheduler. Retain the durable state ledger on local disk.
- Run `python -m unittest discover -s tests -v`, compile checks and offline CLI
  smoke tests. Use synthetic adapters, not real SMTP/model calls, for tests.
- Report what was verified and what was not. A valid configuration does not
  establish CLI authentication, account credit, real CLI/API compatibility,
  external connector delivery, or 24/7 hosting. Never describe offline stub tests
  as a live model or mail-provider test.
