# Agent-assisted and cross-platform setup

[中文](platform-setup_中文.md) · [Home](../README.md) · [Configuration guide](user-guide.md)

**Fastest route: give the repository and the prompt below to your coding agent.**
Super Paper radar is a toolkit for agent-led research. A Codex, Claude Code or
host agent plans and carries out the research using the program's retrieval,
evidence, validation and library tools. Choose an installed, signed-in CLI or a
host agent that can execute this project's commands; a usable agent login needs
no second model API key. The independent standalone API pipeline is optional.
Choose SMTP or an authorized connected email tool for delivery. An agent chat
alone does not provide an always-on host, usable login, allowance or mailbox.

Live digests require an available research agent or a configured standalone LLM.
Both agent-led and standalone modes consume model/account usage;
cost and limits depend on your plan, model, paper count and evidence supplied.
Setup, validation and the clearly labeled synthetic preview make **no model calls**.
A live dry run may call the LLM and can cost money even though it sends no email.

## 1. Give an agent this prompt

Replace the bracketed values. Do not include passwords or API keys.

> Set up https://github.com/RHFran/super-paper-radar on [this Windows computer / this
> Linux server / the connected computer or coding environment I name]. Read
> AGENTS.md and docs/platform-setup.md. Inspect the source, then run the provided
> setup script in an isolated virtual environment, preserving existing private
> configuration. My topics are [topics], language [language], timezone [IANA
> timezone], and schedule [weekdays or specific dates, local time]. Use separate
> subscriptions when topics need different schedules or models. Check for an
> installed, signed-in Codex or Claude Code CLI on that machine, then configure
> workflow.mode=agent with my chosen agent backend. The agent should lead planning,
> retrieval, evidence reading and synthesis using the program's tools. If I choose
> my current host agent, use its exported job contract. Use standalone mode and
> configure-model only if I choose an independent API, with hidden local key entry.
> Explain usage and costs before any live call. Show the offline
> preview first. Ask before a paid live test, real email, or enabling a persistent
> scheduler. Keep secrets out of chat, source control, command arguments and logs.

- **Codex:** open the checkout as a project or start `codex` inside it, then paste
  the prompt. Install/sign in using the current [official CLI guide](https://learn.chatgpt.com/docs/codex/cli).
- **Claude Code:** open the repository in Claude Code or start `claude` there.
  Follow its [official setup guide](https://code.claude.com/docs/en/setup) for your
  OS. The repository does not require a special Claude plugin.
- **ChatGPT:** use a task with access to the intended checkout and execution
  tools. A chat without those tools can explain the commands for you to run.
  [Computer access](https://learn.chatgpt.com/docs/computer-use) and
  [remote connections](https://learn.chatgpt.com/docs/remote-connections) depend on
  your app, account, workspace and permissions.
- **ChatGPT dot:** name the target computer/environment. For a local installation,
  allow that computer in your dot's profile and keep it online with the desktop
  app running while setup takes place. Check the current
  [computer connection guide](https://learn.chatgpt.com/docs/dots/computers-and-apps).
  An install on the dot's cloud computer is separate from an install on yours.

For API mode, the agent should hand you the hidden-key entry step. For CLI mode,
sign in through the CLI's own supported flow; do not copy its credentials into the
project. Never paste a real key into these prompts. This is a source-based workflow, not a published Super Paper radar MCP
server or a guaranteed one-click installation inside every assistant app.

## 2. Run the setup script yourself

Prerequisites: Python **3.11+**, Git (or download and extract the repository ZIP),
and network access to the Python package registry for installation. On Linux,
your distribution may package `venv`/`ensurepip` separately. No administrator
access is needed once Python and venv are available.

### Linux, macOS, or an existing WSL environment

```bash
git clone https://github.com/RHFran/super-paper-radar.git && cd super-paper-radar && bash scripts/setup.sh
```

### Native Windows PowerShell

```powershell
git clone https://github.com/RHFran/super-paper-radar.git
if ($LASTEXITCODE -eq 0) { Set-Location super-paper-radar; .\scripts\setup.ps1 }
```

If you already have a checkout, open a terminal there and run just the last
setup command. If your organization blocks PowerShell scripts, use the Python
entry point instead; do not lower your execution policy:

```powershell
py -3 scripts/setup.py
```

The scripts create/reuse `.venv`, install this checkout, ask for reader settings,
and create an agent-led configuration. The API wizard is an explicit opt-in via
`--api`. They then validate and generate an **offline synthetic preview**. They never enable email, change system
security settings, install scheduled tasks, or overwrite an existing config.
Configuration/report paths printed by `validate` can contain your email address;
review them before sharing logs.

For a no-questions **demonstration only**, use `bash scripts/setup.sh --demo` or
`.\scripts\setup.ps1 -Demo`. It uses `runtime/demo/config.json` and invented papers,
not a live report for your topics. Normal setup does not ask for a separate model
API key. `--skip-model` / `-SkipModel` remains a compatible way to skip the API
wizard. To reuse a provisioned environment without pip, use `--skip-install` or
`-SkipInstall`.

The wrappers work from any directory. Relative config and environment-file paths
passed to the wrappers are relative to the checkout; state/output paths inside
JSON remain relative to the JSON file. Use absolute paths for a server service.

## 3. Configure your provider, model and key

### Choose agent-led research first

New configurations use `workflow.mode: "agent"` and root/profile `agent` settings:

```json
{
  "workflow": {"mode": "agent"},
  "agent": {"backend": "codex", "executable": "", "model": "", "reasoning_effort": "", "timeout_seconds": 1800}
}
```

Use `agent.backend: "claude"` for Claude Code, or `"host"` for an existing agent
working in the project. `init --agent-backend codex|claude|host` selects the backend
when creating a new config. Empty `agent.model` keeps the agent's configured
default; `agent.executable` can set its command path. Keep the execution user and
CLI login consistent. Normal tools and security controls stay enabled; resolve
blocked permissions through the approved flow, never with bypass flags.

`run`, due `tick`, and `schedule` launch complete agent jobs. With `host`, they
return `awaiting_agent` and persistent task/contract files for the host to finish
using the program's tools. See [agent workflow](agent-workflow.md) for the exact
export/search/fetch/ingest/validate/finalize contract. Research completion is
verified by the program; an exported job or an agent's final chat message alone
is not a completed digest.

Existing configs lacking `workflow` stay in `standalone` mode until deliberately
changed. In agent mode, `llm.enabled` and the old planning/screening switches do
not control research. [Workflow choices and readiness](model-backends.md) explain
usage limits and delivery options. Agent CLI authentication stays with its CLI;
SMTP secrets, if using SMTP, are configured separately.

### Independent API: the existing local wizard

The remainder of this section is for the optional `workflow.mode: "standalone"`
pipeline. Its `llm.backend` defaults to `"api"` when omitted. Choose this workflow
explicitly for a new installation (`bash scripts/setup.sh --api`), or select it
in your private config and run the independent wizard:

```bash
bash scripts/run.sh --config config.json configure-model
```

```powershell
.\scripts\run.ps1 --config config.json configure-model
```

The actual wizard asks for:

1. DeepSeek, Qwen, Moonshot/Kimi, OpenAI, or a custom compatible provider
2. HTTPS base URL (a preset is offered; editable for region/workspace/gateway)
3. Model ID from your provider console, with no hard-coded model restriction
4. A local model/key slot name
5. API key via hidden terminal input
6. Explicit confirmation before saving locally

It enables `llm` for the selected subscription, puts only environment-variable
references in JSON, and stores the values in `.env` next to the config. It does
not test your key against the network, charge tokens, or enable SMTP. It is the
API setup path, not a CLI sign-in wizard. Existing
models/slots are protected: replacement requires `--replace` plus confirmation.
`--secrets-file .env.work` chooses a different ignored secret filename.

The saved file is **plaintext**, excluded by `.gitignore`, and owner-only `0600`
on POSIX. On Windows, permissions inherit from its directory: use a private
user-owned folder and verify its ACLs. Git ignores are not encryption or access
control. Do not force-add this file, upload it, put it in shared folders, or include
it in screenshots/backups sent to others.

### Multiple models and keys

Each subscription can use a different provider/model/key. With an existing
multi-profile config, run the wizard once per subscription:

```bash
bash scripts/run.sh --config config.json --profile forest-weekly configure-model
bash scripts/run.sh --config config.json --profile battery-daily configure-model
```

Use actual profile IDs from your config. For example, the first wizard creates
`PAPER_TRACKER_FOREST_WEEKLY_BASE_URL`, `PAPER_TRACKER_FOREST_WEEKLY_MODEL`, and
`PAPER_TRACKER_FOREST_WEEKLY_API_KEY`, and links that profile's `llm` fields to them.
The second profile gets independent entries in the same `.env`. Existing SMTP
entries and other profile settings are preserved. This is per-subscription model
selection, not automatic key rotation or failover across providers.

### Provider presets and compatibility

In API mode, Super Paper radar calls `<base URL>/chat/completions` with JSON-object output. Use a
model supporting that request format. Native Anthropic Messages, Responses-only,
and streaming-only endpoints are not interchangeable with it. A preset is a
configuration starting point, not evidence that a particular model/key works.

| Provider | Preset base URL | Official reference |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | [JSON output](https://api-docs.deepseek.com/guides/json_mode/) |
| Qwen / Alibaba Cloud, Beijing | `https://dashscope.aliyuncs.com/compatible-mode/v1` | [Regional and workspace URLs](https://help.aliyun.com/en/model-studio/base-url), [JSON output](https://help.aliyun.com/zh/model-studio/qwen-structured-output) |
| Moonshot / Kimi, China | `https://api.moonshot.cn/v1` | [API quickstart](https://platform.kimi.com/docs/get-api-key) |
| OpenAI | `https://api.openai.com/v1` | [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) |
| Custom | You supply an HTTPS base URL | Your provider's Chat Completions documentation |

Check the current model list, price and JSON support in your chosen provider
console. Qwen keys/endpoints must match the region and workspace; use the
pay-as-you-go/backend API route, not a coding-plan key restricted to interactive
coding tools. A CLI login is not an API credential: choose the `codex` or `claude`
agent backend for the main workflow instead of placing login credentials in an
API-key slot. The legacy model-only CLI backends remain available in standalone
mode; see [compatibility mode](model-backends.md#standalone-compatibility-mode).

### Load saved credentials or prompt without saving

Neither the CLI nor the launcher automatically loads `.env`. Both support an
explicit `--env-file` option:

```bash
bash scripts/run.sh --env-file .env --config config.json validate
# Next command retrieves real papers and may call the model and incur token charges:
bash scripts/run.sh --env-file .env --config config.json run
```

On Windows, replace `bash scripts/run.sh` with `.\scripts\run.ps1`. Without
PowerShell scripts, use `.\.venv\Scripts\python.exe scripts\launch.py` followed
by the same flags.

The environment parser treats `KEY=value` or `KEY='value'` as literal data. It
never executes a shell, expands `$variables`, or evaluates commands. Use one
entry per line, with no multiline values, duplicate names, or inline comments.
**Do not shell-source this file.** Docker's own `--env-file` uses different quoting
rules: mount the file and use the application's `--env-file` option after the
image name instead. Only variable names referenced in the configuration are loaded; existing nonempty
process environment values take precedence. `validate` checks configuration and
presence, not authentication, provider compatibility, credit or deliverability.

Alternatively, set `llm.enabled` and its environment references, then run
`bash scripts/run.sh --prompt-secrets run`. Missing enabled-provider values are
requested with hidden input, kept in this process only, and not saved. This mode
requires an interactive terminal; it is unsuitable for an unattended service.

## 4. Enable email and unattended operation deliberately

After checking a real dry-run report, choose a delivery path. Model and mail
backends are independent. The instructions below cover direct SMTP delivery.
For an authorized connected email tool, use the [connector workflow](model-backends.md#connector-send-lifecycle):
`run --prepare-connector`, claim with `begin-send`, send once through the external
tool, and record its confirmed receipt with `confirm-sent`. Preparation ignores
SMTP `mail.enabled` and needs no SMTP credentials. Agent mode also supports
`tick --prepare-connector` and `schedule --prepare-connector`; standalone uses
`run` only. A host agent first finishes the returned research task. The host
orchestrates the actual external tool calls and receipt import. `--send` remains
SMTP, while `--prepare-connector` never sends mail.

For SMTP, configure an authorized account and
sender using the mail variables in [`.env.example`](../.env.example), then set
`mail.enabled` to `true`. The recipient alone cannot send email: the sender still
needs working SMTP credentials. Keep credentials out of command arguments.

```bash
# Explicit one-time real email (agent/API usage may incur charges):
bash scripts/run.sh --env-file .env --config config.json run --send
# Explicit foreground schedule, checks each profile every minute:
bash scripts/run.sh --env-file .env --config config.json schedule --send
```

Windows uses the same flags through `run.ps1`. `Ctrl+C` stops the foreground
scheduler; closing the terminal/rebooting stops it. Without `--send`, `run`,
`tick` and `schedule` stay in live dry-run mode, which can still incur model costs.
Never run a foreground scheduler and an OS scheduler for the same config together.
For an agent CLI backend, run the worker under the logged-in CLI user with the
command on `PATH` or an explicit `agent.executable` path. The host backend needs
an available host agent to finish exported jobs; a timer alone cannot do its
research. Check login freshness, tool permissions and account limits. Failed
agent jobs require inspection and explicit `--retry-agent` before a new attempt;
repeated ticks must not generate repeated paid retries.

- **Linux server:** use an unprivileged account and one service manager. Review
  the [systemd, cron and Docker examples](../examples/README.md). Supply private
  environment variables or use `scripts/launch.py --env-file /private/.env` in
  your service command. Install/enable a service only after an explicit decision.
- **Windows server:** after a one-time test, you can create a Task Scheduler task
  under the intended user. Program: the absolute `.venv\Scripts\python.exe`.
  Arguments: the absolute `scripts\launch.py`, then `--env-file` and `--config`
  with absolute paths, followed by `tick --send`. Set the working directory to
  the checkout. Repeat every minute, choose “Do not start a new instance” for
  overlap, and review missed-start/restart settings. Test `validate` under that
  same task account first. Do not put passwords into task arguments or grant
  administrator privileges. Remove `--send` while rehearsing.
- **Docker / WSL alternative:** use the existing Linux instructions inside your
  chosen environment. Keep state/config/output on durable storage. A container
  or laptop that is stopped cannot deliver on time.

Native Windows uses standard-library byte-range locking plus the `tzdata`
package for IANA timezones; POSIX uses `flock` and normally the OS timezone data.
Keep the SQLite state and lock on local durable disk, not a shared network drive.
Protect and retain the state directory across upgrades, or duplicate delivery
protection is lost. On uncertain SMTP results, inspect provider records and use
the documented `resolve` command rather than blindly resending.

## Validation scope

Linux setup/install, safe repeat runs, offline previews, configuration, redaction,
secret-file parsing and lock contention are tested. The CI workflow includes
Windows/Python versions and the native PowerShell bootstrap. This checkout's
implementation session had no Windows/PowerShell executor, so native Windows was
not locally executed; check the repository's CI result for the exact revision.
No real model request, SMTP delivery, OS scheduler installation or Docker runtime
test is implied by offline tests. Validate those in your deployment before relying
on unattended delivery.
