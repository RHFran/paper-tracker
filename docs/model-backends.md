# Agent workflows, standalone backends and connector delivery

[Home](../README.md) · [Agent tool contract](agent-workflow.md) · [Platform setup](platform-setup.md) · [User guide](user-guide.md) · [中文要点](#中文要点)

**Agent-led research is the primary workflow.** The agent chooses its searches,
reads evidence, assesses relevance and synthesizes a digest. Super Paper radar
provides retrieval and evidence tools, deterministic result validation,
deduplication, rendering, the saved literature index, scheduling and a delivery
ledger. The agent is an active researcher with its normal tools, not just a
structured-output model embedded in a fixed retrieval pipeline.

## Choose the workflow explicitly

New `init` and example configurations use `workflow.mode: "agent"`. Configure the
agent at the root or per profile:

```json
{
  "workflow": {"mode": "agent"},
  "agent": {
    "backend": "codex",
    "executable": "",
    "model": "",
    "reasoning_effort": "",
    "timeout_seconds": 1800
  }
}
```

| `agent.backend` | Who completes the research job | Prerequisites |
|---|---|---|
| `codex` | A full Codex CLI agent | Installed CLI and a usable login under the execution user |
| `claude` | A full Claude Code CLI agent | Installed CLI and a usable login under the execution user |
| `host` | The current authorized host agent, using an exported task and contract | Access to this checkout, its tools and durable job files |

`run`, due `tick`, and `schedule` dispatch agent jobs in this mode. The CLI can
use tools under its normal permissions and security controls. This project does
not pass permission-bypass flags, disable its research tools, copy its login
credentials or translate a chat subscription into an API key. An empty `model`
uses the agent's configured default. An empty `executable` selects `codex` or
`claude`; an explicit value must be a single command name or executable path,
not a shell command with flags. `timeout_seconds` defaults to 1800 for the whole
agent invocation. `reasoning_effort` is optional; empty inherits the agent's
default, while a supported explicit value is passed through without an
application-selected fallback. Choose the exact account-available model and
supported effort, rather than guessing a newest model name. Requested values are
recorded in the job contract/audit. Host mode cannot change the model/effort of an
already-running host; select them there before starting. See
[model and effort selection](agent-workflow.md#1-select-the-agent-and-execution-host).

The host backend returns `awaiting_agent`, with task/contract files the host must
read and complete. It does not silently fall back to standalone model calls.
[The complete agent workflow](agent-workflow.md) documents exported jobs and
`agent-tool` search, fetch, ingest, validate and finalize operations.

**Upgrade compatibility:** an existing config with no `workflow` remains
`standalone`. To change it, explicitly add `workflow.mode: "agent"` and choose
an agent. Merely configuring `llm.backend` does not select agent-led execution.

## Readiness and costs

A working agent chat does not prove that its CLI is installed and authenticated
on the execution machine. Before a live run:

1. Install/sign in through the CLI's supported flow under the same OS user that
   will execute jobs. This project does not perform login or copy credentials.
2. Check that the command resolves in the scheduler environment; use an absolute
   `agent.executable` path if needed. Keep the normal security/approval policy.
   A job blocked by that policy needs an authorized resolution, not a bypass.
3. Run `validate` and the synthetic `preview`. Neither proves live login, credit,
   model availability, tool access or compatibility with the installed CLI.
4. Approve and inspect one real `run` without email. It can use multiple searches,
   evidence reads and model turns. Failed validation is not a completed digest.
5. Test under the actual scheduler account before unattended use. Keep the machine
   awake, the login usable and the job/state directories on durable private disk.

```sh
bash scripts/run.sh --config config.json validate
bash scripts/run.sh --config config.json preview
# Live agent research and account usage; no email:
bash scripts/run.sh --config config.json run
```

A supported, usable CLI login needs **no separate model API key**. It does not
promise free or unlimited usage. Plan rules, token usage, quotas and possible
charges apply; an API-authenticated CLI may use API billing. Host-agent usage
follows its own provider/account. Real dry runs and connector preparation can
consume usage. Setup, validation, job export and synthetic preview do not call
the model. A failed job is not automatically retried as a new paid invocation
each minute; review it before explicitly allowing `--retry-agent`.

## Standalone compatibility mode

`workflow.mode: "standalone"` retains the fixed retrieve/filter/analyze pipeline.
This is an optional independent deployment path and the unchanged default for old
configs lacking `workflow`. It uses `llm.enabled: true` and one `llm.backend`:

| `llm.backend` | Program-controlled model call | Prerequisites |
|---|---|---|
| `api` (default) | HTTPS OpenAI-compatible Chat Completions | Endpoint, model and API-key environment references |
| `codex` | Model-only Codex CLI structured output | Installed CLI and usable login |
| `claude` | Model-only Claude Code CLI structured output | Installed CLI and usable login |

```json
{
  "workflow": {"mode": "standalone"},
  "llm": {
    "enabled": true,
    "backend": "api",
    "base_url_env": "LITERATURE_LLM_BASE_URL",
    "api_key_env": "LITERATURE_LLM_API_KEY",
    "model_env": "LITERATURE_LLM_MODEL"
  }
}
```

Use the local `configure-model` wizard for the API endpoint, model and hidden-key
entry; setup's `--api` option chooses this path. It is not a CLI login wizard.
Load saved private values explicitly with `--env-file`, or use `--prompt-secrets`
for process-only input. See [API setup](platform-setup.md#3-configure-your-provider-model-and-key).
Never put API keys, passwords or tokens in JSON or command arguments.

For a standalone model-only CLI call, `llm.cli_executable` optionally selects the
command, `llm.cli_model` selects a model, and `llm.cli_timeout_seconds` defaults
to 180 seconds (maximum 1800) per model invocation. Empty `cli_model` uses the
isolated invocation's effective default rather than the user-configured model.
These legacy adapters deliberately constrain the call to structured output;
they are different from the full agent workflow above. `llm.plan_queries` and
`llm.screen_candidates` add model-assisted query planning and screening to the
fixed pipeline. Both default to false; `max_screen_candidates` defaults to 50
(maximum 200). They do not control agent-led research.

Profiles may select different workflows, agents or standalone models. Missing or
failed standalone analysis stops a real digest; metadata-only output is not a
successful research report. Both workflows send research topics/evidence to the
chosen agent or model provider, according to that provider's own data policies.

New standalone/API runs use the same six paper sections as agent-led research:
problem and design, scientific question, method chain (experimental or model
methods), results and highlights, limitations, and research implications. The
model returns the existing four evidence fields plus source-anchored design,
limitation and implication statements, explicitly marked reported or inferred.
After the introduction, a separate model call writes the closing cross-paper
synthesis, cited open questions and proposed, testable ideas with a hypothesis,
experiment/comparator, validation criteria and conditional value. Each citation
must match both its source and evidence supplied to that call. Missing sections,
invalid outlooks or insufficient synthesis input budget stop the report before
delivery and pause automatic paid retries. There is no canned-idea fallback.
This adds one model invocation per nonempty digest and increases input/output
token usage and potentially cost, including dry runs; empty results make none.
The closing call uses all selected papers within `llm.max_overview_chars`
(default: `llm.max_evidence_chars`, normally 60000 characters). If they do not fit,
the report stops with an explicit budget error before the closing call rather
than silently dropping papers or the mandatory outlook. Earlier model stages
may already have consumed usage. Reduce `max_papers_per_track` or deliberately
increase that budget, considering the provider's context limit and token cost.
Existing frozen reports/outboxes remain readable and are never regenerated or
rewritten by this schema change.

新的 standalone／API 运行同样输出六段解读：问题与设计、科学问题、方法链
（实验或模型方法）、结果与亮点、局限性、有何启发。末尾另有基于本期论文的综合、
开放问题和可检验想法，明确区分原文结论与分析推论。非空简报会增加一次模型调用；
内容或证据校验失败时停止，不用固定模板填充，也不改写已冻结的旧报告或发信内容。

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

Research workflow and email transport are independent. Agent-led and standalone
research can produce a report for either delivery path:

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
SMTP credentials. Agent mode supports `run --prepare-connector`,
`tick --prepare-connector` and `schedule --prepare-connector`; standalone mode
supports preparation with `run` only. A `host` job must be finalized before an
envelope exists. The host separately orchestrates/schedules the external-tool
lifecycle. `tick --send` and `schedule --send` remain SMTP, not connector calls.

### Connector send lifecycle

```sh
# Run research, or safely promote a completed dry run; prepare but do not send:
# Host backend returns a task first; finalize it before claiming the envelope.
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

- 新建配置以 **Agent 主导研究** 为主：Agent 自主规划检索、阅读证据、筛选和综合，程序
  提供检索、证据校验、去重、排版、持久文献库、调度与投递记录。
- 设置 `workflow.mode: "agent"`，根层或档案中的 `agent.backend` 可选 `codex`、
  `claude`、`host`；`executable` 和 `model` 留空使用后端默认，`timeout_seconds`
  默认 1800 秒，限制完整 Agent 调用。保留正常工具与安全权限，不绕过审批、不复制凭据。
- `run`、到期的 `tick` 与 `schedule` 启动完整研究任务。`host` 返回 `awaiting_agent`，
  由宿主读取持久任务契约并调用程序工具完成；任务导出不等于已完成研究。
  [详细工具契约](agent-workflow.md)覆盖检索、抓取、导入、校验和完成步骤。
- 缺少 `workflow` 的旧配置继续使用 `standalone`，不会静默迁移。独立固定流程仍支持
  `llm.backend: api/codex/claude`；`llm` 的查询规划与筛选开关只属于这个兼容模式。
- 新安装默认不运行 API 向导；选择独立 API 时用 `--api` 或本地 `configure-model`。
  密钥由用户在本地隐藏输入，不放进聊天、JSON 或命令参数。
- 已登录 CLI 不需要第二把模型 API key，但真实 Agent/API 运行（包括 dry-run）仍消耗
  账户用量并受费用、额度限制。`validate` 和合成预览不能证明真实登录或兼容性。
- 失败任务不会每分钟自动重新付费调用；检查原因后，用明确的 `--retry-agent` 允许重试。
- 研究方式与邮件方式分开选择。SMTP 的 `run --send`、`schedule --send`、`tick --send`
  保持支持；Agent 的工具完成步骤本身不发送邮件。
- 连接邮件工具的流程是 `run --prepare-connector` → `begin-send DIGEST_ID` →
  获授权的外部工具发送一次 → `confirm-sent DIGEST_ID --receipt receipt.json`。
  对 `host` 模式，要先完成返回的研究任务。消息准备或领取均不等于成功发送。
- 准备连接工具消息不需要 SMTP 凭据。Agent 模式可用 `tick --prepare-connector` 或
  `schedule --prepare-connector`；standalone 仅支持 `run` 准备。宿主仍负责实际邮件
  工具调用与回执，内置调度不会自动调用宿主邮件工具。超时或状态不明时先查提供商记录，
  不盲目重发、不编造回执。

[中文安装指南](platform-setup_中文.md) · [中文完整指南](user-guide_中文.md)
