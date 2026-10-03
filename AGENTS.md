# Paper Tracker agent setup contract

Paper Tracker is a source-installed Python research-digest application. Read the
concise README and `docs/platform-setup.md` before setup work.

- Work on the computer/environment the user selects. Do not imply that an agent
  chat or a temporary execution container supplies durable production hosting.
- Python 3.11+ is required. Use `scripts/setup.sh` or `scripts/setup.ps1`; the
  portable entry is `python scripts/setup.py`. Setup preserves existing configs.
- Start with `--demo` / `-Demo` for a synthetic offline preview, or normal setup
  when the user is ready to supply reader settings. Preview is never real research.
- Real digests require a configured LLM and can incur provider token charges,
  including dry runs. Explain the cost boundary before a live call. Never claim
  metadata-only output is the full product or that a dry run is always free.
- `configure-model` is a real local wizard. It selects provider/base URL/model,
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
- Use multiple `profiles` for different topic/schedule/model combinations. One
  config should have one scheduler. Retain the durable state ledger on local disk.
- Run `python -m unittest discover -s tests -v`, compile checks and offline CLI
  smoke tests. Use synthetic adapters, not real SMTP/model calls, for tests.
- Report what was verified and what was not. A valid configuration does not
  establish model credit, real API compatibility, delivery, or 24/7 hosting.
