# Model backends and connector delivery

[Home](../README.md) · [Platform setup](platform-setup.md) · [User guide](user-guide.md) · [中文要点](#中文要点)

Smart Paper Tracker owns the research pipeline: source retrieval, query filters,
evidence collection, model analysis, deduplication, rendering, scheduling and the
local delivery ledger. A coding agent can configure and run it. The model backend
is a program setting; the main workflow does not import research written manually
by the host agent.

## Choose one model backend per profile

| `llm.backend` | What the program calls | What must already be available |
|---|---|---|
| `codex` | Codex CLI non-interactive structured output | Installed `codex`, a usable login, and allowed model/account usage under the execution user |
| `claude` | Claude Code CLI print mode with structured output | Installed `claude`, a usable login, and allowed model/account usage under the execution user |
| `api` | HTTPS OpenAI-compatible Chat Completions | Provider endpoint, model ID and API key references |

`api` remains the default when `backend` is omitted, so existing API
configurations keep their behavior. Set `llm.enabled` to `true` for any real
backend. Offline synthetic `preview` needs none of them.

For CLI mode, run setup with `--skip-model` (`-SkipModel` in PowerShell) to skip
the separate API wizard. Edit the `llm` object in your private configuration:

```json
{
  "enabled": true,
  "backend": "codex",
  "cli_executable": "codex",
  "cli_model": "",
  "cli_timeout_seconds": 180,
  "plan_queries": true,
  "screen_candidates": true,
  "max_screen_candidates": 50
}
```

Use `"claude"` for both `backend` and `cli_executable` when selecting Claude Code.
The executable is a single command name or path, not a shell command with flags.
Omitting it selects `codex` or `claude` automatically. An empty `cli_model` uses
the isolated CLI default, rather than a model from its user configuration; otherwise supply a model your account can use. The adapters exclude user/project customizations for this model-only invocation while preserving managed security requirements and CLI authentication.
The timeout defaults to 180 seconds and cannot exceed 1800 seconds. It bounds
an individual CLI invocation, not necessarily a complete multi-paper run.

Profiles can choose different backends/models. Existing evidence, language and
paper-selection settings still apply. Do not put passwords, login tokens or API
keys in JSON, executable paths or command arguments.

`plan_queries: true` asks the selected model to help formulate retrieval queries
for the topics; the program executes those queries. `screen_candidates: true`
adds model-assisted relevance screening before detailed analysis, bounded by
`max_screen_candidates` (default 50, maximum 200). Both switches default to `false` for
backward compatibility. Turn them on for the fuller model-assisted workflow;
they add model usage and do not guarantee exhaustive literature coverage.

### CLI behavior and official references

- **Codex:** the adapter uses `codex exec` with a JSON output schema, a read-only
  sandbox and an ephemeral session. It reuses authentication managed by the
  installed CLI. See [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/).
- **Claude Code:** the adapter uses `claude -p` with JSON output, a JSON schema
  and tools disabled. See [Claude Code programmatic usage](https://code.claude.com/docs/en/headless).

These are model calls made by the program. They do not ask the model to run the
literature pipeline, send mail or install a scheduler. CLI authentication stays
with the CLI; this project does not copy its credentials into `.env` or convert
a chat subscription into an API key. Review the installed CLI's own configuration
and provider data policies before using it with private topics or evidence.
Query planning sends topic settings to the selected model; screening sends
candidate metadata/evidence, and detailed analysis sends selected paper evidence.

### Readiness and costs

A working interactive agent chat does not prove that the needed CLI is installed
and authenticated on the execution machine. Before a live run:

1. Install/sign in through the chosen CLI's official workflow, under the same OS
   user that will execute the program. This project does not perform that login.
2. Check that the command resolves in the scheduler's environment. If its `PATH`
   differs from your terminal, configure the absolute `cli_executable` path.
3. Run the local configuration check and an offline preview first. `validate`
   does not establish account credit, authentication validity, model availability
   or end-to-end compatibility with your installed CLI version.
4. Approve and review one real dry run. It retrieves real sources and can make
   multiple model requests. Login expiration, rate limits, usage caps, unsupported
   models, timeouts and invalid structured output stop successful analysis.
5. Test under the actual scheduler account before relying on unattended operation.
   A sleeping laptop, expired login or stopped worker cannot deliver on time.

```sh
bash scripts/run.sh --config config.json validate
bash scripts/run.sh --config config.json preview
# Live retrieval and model usage; no email:
bash scripts/run.sh --config config.json run
```

CLI mode needs **no separate model API key when the CLI has a supported, usable
login**. It is not a promise of free or unlimited inference. CLI/account plan
rules, token usage, quotas and possible charges still apply; an API-authenticated
CLI may use API billing. API mode uses the selected API provider's billing.
Costs depend on the model, paper count, evidence length and number of calls.
Real dry runs and connector preparation also consume model usage. Setup,
validation and synthetic preview do not call the model.

### Keep the independent API workflow

For `llm.backend: "api"`, use the existing local `configure-model` wizard and
its hidden-key entry. It configures a compatible HTTPS endpoint, model and
independent environment-variable slot per subscription. Load the private file
explicitly with `--env-file`, or use `--prompt-secrets` for process-only input.
See [API provider setup](platform-setup.md#3-configure-your-provider-model-and-key).
The API wizard is an API setup path; it does not sign in to Codex or Claude Code.

## Saved literature and coverage

Successful runs save selected paper metadata, validated analysis, provenance and
links to their audit snapshots in the audience/profile-scoped SQLite literature
index, even for dry runs. This is separate from the delivery ledger; saving a
paper never marks it sent. Keep the state and output directories together on
durable private storage.

```sh
bash scripts/run.sh --config config.json library --query "weather" --limit 30
bash scripts/run.sh --config config.json library-export --output exported-references
```

The export command creates RIS/BibTeX and refuses to overwrite existing files.
Use `--profile` for a selected subscription. Exact identifiers and explicit aliases
control deduplication; title similarity does not silently merge different works.

`retrieval_policy` defaults to `complete`: reaching a pagination limit fails closed.
For a deliberately limited review, explicitly set `retrieval_policy: "bounded"`
and choose `max_pages_per_query`. Reports and audits then disclose truncation and
must not be interpreted as a complete bibliography or proof that no new papers exist.
Model screening also has a disclosed candidate cap.

## Choose delivery separately

Model choice and email choice are independent. Any supported model backend can
produce a report for either delivery path:

- **SMTP:** configure `mail.enabled` and your authorized sender, then use
  `run --send`, `tick --send` or `schedule --send`. Existing SMTP state and
  scheduling behavior are retained. See [scheduling](user-guide.md#scheduling).
- **Connected email tool:** the program prepares an immutable mail envelope;
  an authorized host agent performs the actual send through its available mail
  tool, then imports the provider's confirmed receipt. No SMTP credential is
  needed for that external tool's transport.

The email tool must support the required recipient, subject, body and attachment
format. A connector account does not automatically provide a durable execution
host or scheduler. Review recipients and the actual message before approving a
send. Do not copy the connector's credentials into the program.

Connector preparation ignores the SMTP `mail.enabled` switch and does not need
SMTP credentials. Only `run --prepare-connector` is supported for this path:
the host must orchestrate and schedule the external-tool lifecycle. Do not use
`tick --send` or `schedule --send` expecting them to invoke a host connector;
those are the program's existing SMTP send path.

### Connector send lifecycle

```sh
# Full real research pipeline, then prepare the immutable message; no mail sent:
bash scripts/run.sh --config config.json run --prepare-connector
# Use the exact digest ID returned by preparation:
bash scripts/run.sh --config config.json begin-send DIGEST_ID
# Send the claimed envelope ONCE through the authorized external email tool.
# Only after its successful provider response has been saved as a receipt:
bash scripts/run.sh --config config.json confirm-sent DIGEST_ID --receipt receipt.json
```

`begin-send` claims the prepared digest before the one external send. Do not
rebuild or edit its recipients, contents or attachments between claiming and
sending. `confirm-sent` records confirmed provider acceptance; preparation or a
claimed state alone must never mark the digest as sent. Keep the state and
prepared files on durable local disk.

Preparation prints `digest_id`, `envelope_sha256` and `paths`. Read
`paths.envelope` for the exact `recipient`, `subject`, `text`, `html` and
reference-file `attachments` to pass to the authorized tool. The bundle also
contains the rendered reports, audit, reference exports and a manifest. A
multi-profile config needs `--profile PROFILE_ID` before each subcommand, using
the same profile throughout. The claim checks the prepared local day: do not
send yesterday's stale preparation without reconciling its state first.

### Provider receipt contract

Create a UTF-8 JSON receipt from the actual send response, with these fields:

| Field | Value |
|---|---|
| `digest_id` | Exact ID from preparation |
| `envelope_sha256` | Exact hash from preparation; never hash an edited replacement |
| `provider` | Mail provider/tool name |
| `status` | `accepted`, `uncertain`, `pending` or `rejected`, reflecting the actual response |
| `sender` | Actual authorized sender email address |
| `recipient` | The prepared recipient email address |
| `message_id` | Provider's message ID; required to confirm acceptance |
| `accepted_at` | Actual acceptance timestamp in ISO format with a timezone; required to confirm acceptance |
| `provider_receipt` | Actual provider response object; required to confirm acceptance |
| `thread_id` | Optional provider thread ID |

The first six fields are required on every receipt. Unknown fields are rejected.
An `accepted` label without a message ID, acceptance timestamp and nonempty
provider response does not complete delivery. Non-accepted or incomplete receipts
leave the outbox uncertain. Do not invent missing IDs, times or acceptance;
retrieve the provider's record, or keep the outcome unresolved. Never store
passwords or authentication tokens in a receipt. An identical already-confirmed
receipt can be imported again safely; a different replacement is rejected.

If a send times out or the provider response is unclear, stop automatic retries
and inspect the actual provider's sent records. Do not guess a receipt or send a
second copy just because confirmation is missing. Provider acceptance is not
proof of inbox placement. Receipt validation and the ledger protect this
workflow, but cannot create a transaction across an arbitrary external mail API.
This version does not automatically release stale preparations or rejected/uncertain
connector sends for retry. Generic SMTP `resolve` cannot reset a connector outbox.
Reconcile provider records and preserve the ledger; do not delete state to force a retry.

## 中文要点

- 程序自己负责检索、筛选、证据收集、分析、去重、排版、调度和投递记录。Agent 帮助
  安装与操作；无需先由宿主 Agent 手写研究报告再导入。
- `llm.backend` 可选 `codex`、`claude`、`api`；省略时仍为 `api`，兼容旧配置。
  所有真实后端都要设置 `llm.enabled: true`。离线 `preview` 不需要模型。
- CLI 模式安装时用 `--skip-model` / `-SkipModel` 跳过 API 向导。运行机器上须已安装
  对应 CLI，并以执行程序的系统用户登录。`cli_executable` 是一个命令名或路径，
  不是拼接参数的 shell 命令；默认按后端选择 `codex` / `claude`。
- `cli_model` 留空使用隔离调用的 CLI 默认模型（不读取用户配置模型）；`cli_timeout_seconds` 默认 180 秒，最大 1800 秒，
  针对每次调用。CLI 模式不要求第二把 API key，仍消耗账户用量并受费用和额度限制。
- `plan_queries: true` 启用模型辅助检索查询规划；`screen_candidates: true` 启用相关性
  筛选，`max_screen_candidates` 默认 50。两个开关为兼容旧配置默认关闭，启用会增加调用。
- 项目不复制 CLI 登录凭据。`validate` 不能证明登录有效、额度充足或 CLI 版本兼容；
  无人值守前应在实际调度用户下测试。请先确认费用再做真实运行。
- 独立 API 继续使用 `configure-model` 本地隐藏输入向导，随后明确加载 `--env-file`。
  SMTP 发送与 `schedule --send` / `tick --send` 保持原有用法。
- 连接邮件工具的流程是 `run --prepare-connector` → `begin-send DIGEST_ID` →
  获授权的外部邮件工具发送一次 → `confirm-sent DIGEST_ID --receipt receipt.json`。
  程序准备的是不可变消息；准备成功、开始发送都不等于已经发出。只有确认的服务商回执
  才能记为发送成功。超时或状态不明先查服务商记录，不要盲目重发或编造回执。
- 连接工具准备忽略 SMTP 的 `mail.enabled`，不需要 SMTP 凭据。目前仅 `run` 支持
  `--prepare-connector`；宿主负责安排外部工具流程，`tick` / `schedule` 的发送仍使用 SMTP。

[中文安装指南](platform-setup_中文.md) · [中文完整指南](user-guide_中文.md)
