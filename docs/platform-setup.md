# Agent-assisted and cross-platform setup

[中文](platform-setup_中文.md) · [Home](../README.md) · [Configuration guide](user-guide.md)

**Fastest route: give the repository and the prompt below to your coding agent.**
Paper Tracker is the same Python program whichever agent helps install it. You
still choose a machine, enter a model API key locally, and configure SMTP before
mail delivery. An agent conversation does not automatically provide an always-on
server, an API allowance, or a sender mailbox.

Live digests **require an LLM**. Your provider may charge for input/output tokens;
cost depends on the model, selected paper count and amount of evidence supplied.
Setup, validation and the clearly labeled synthetic preview make **no model calls**.
A live dry run may call the LLM and can cost money even though it sends no email.

## 1. Give an agent this prompt

Replace the bracketed values. Do not include passwords or API keys.

> Set up https://github.com/RHFran/paper-tracker on [this Windows computer / this
> Linux server / the connected computer or coding environment I name]. Read
> AGENTS.md and docs/platform-setup.md. Inspect the source, then run the provided
> setup script in an isolated virtual environment, preserving existing private
> configuration. My topics are [topics], language [language], timezone [IANA
> timezone], and schedule [weekdays or specific dates, local time]. Use separate
> subscriptions when topics need different schedules or models. Guide me through
> configure-model so I enter the provider, model and hidden key directly in my
> local terminal. Explain token costs before any live call. Show the offline
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

The agent should hand you the hidden-key entry step. Never paste a real key into
these prompts. This is a source-based workflow, not a published Paper Tracker MCP
server or a guaranteed one-click installation inside every assistant app.

## 2. Run the setup script yourself

Prerequisites: Python **3.11+**, Git (or download and extract the repository ZIP),
and network access to the Python package registry for installation. On Linux,
your distribution may package `venv`/`ensurepip` separately. No administrator
access is needed once Python and venv are available.

### Linux, macOS, or an existing WSL environment

```bash
git clone https://github.com/RHFran/paper-tracker.git && cd paper-tracker && bash scripts/setup.sh
```

### Native Windows PowerShell

```powershell
git clone https://github.com/RHFran/paper-tracker.git
if ($LASTEXITCODE -eq 0) { Set-Location paper-tracker; .\scripts\setup.ps1 }
```

If you already have a checkout, open a terminal there and run just the last
setup command. If your organization blocks PowerShell scripts, use the Python
entry point instead; do not lower your execution policy:

```powershell
py -3 scripts/setup.py
```

The scripts create/reuse `.venv`, install this checkout, ask for reader settings,
and offer a model configuration wizard for a new config. Then they validate and
generate an **offline synthetic preview**. They never enable email, change system
security settings, install scheduled tasks, or overwrite an existing config.
Configuration/report paths printed by `validate` can contain your email address;
review them before sharing logs.

For a no-questions **demonstration only**, use `bash scripts/setup.sh --demo` or
`.\scripts\setup.ps1 -Demo`. It uses `runtime/demo/config.json` and invented papers,
not a live report for your topics. To skip model entry while doing reader setup,
use `--skip-model` or `-SkipModel`. To reuse a provisioned environment without pip,
use `--skip-install` or `-SkipInstall`.

The wrappers work from any directory. Relative config and environment-file paths
passed to the wrappers are relative to the checkout; state/output paths inside
JSON remain relative to the JSON file. Use absolute paths for a server service.

## 3. Configure your provider, model and key

If you skipped the first-run wizard, run:

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
not test your key against the network, charge tokens, or enable SMTP. Existing
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

Paper Tracker calls `<base URL>/chat/completions` with JSON-object output. Use a
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
coding tools. A ChatGPT/Claude subscription or coding-agent login is not
necessarily an API credential or token budget for this application.

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

After checking a real dry-run report, configure an authorized SMTP account and
sender using the mail variables in [`.env.example`](../.env.example), then set
`mail.enabled` to `true`. The recipient alone cannot send email: the sender still
needs working SMTP credentials. Keep credentials out of command arguments.

```bash
# Explicit one-time real email (LLM API use may incur charges):
bash scripts/run.sh --env-file .env --config config.json run --send
# Explicit foreground schedule, checks each profile every minute:
bash scripts/run.sh --env-file .env --config config.json schedule --send
```

Windows uses the same flags through `run.ps1`. `Ctrl+C` stops the foreground
scheduler; closing the terminal/rebooting stops it. Without `--send`, `run`,
`tick` and `schedule` stay in live dry-run mode, which can still incur model costs.
Never run a foreground scheduler and an OS scheduler for the same config together.

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
