# 用 Agent 安装，以及跨平台运行

[English](platform-setup.md) · [首页](../README_中文.md) · [配置指南](user-guide_中文.md)

**最快的方式：把仓库链接和下面这段提示词交给你的编程 Agent。**
Super Paper radar 为 Agent 主导的研究提供工具。Codex、Claude Code 或宿主 Agent
自主规划并执行研究，调用程序的检索、证据、校验和文献库工具。选择已安装并登录的 CLI，
或能执行项目命令的宿主 Agent；可用的 Agent 登录不要求第二把模型 API key。
独立 standalone API 固定流程仍可选。投递可选 SMTP 或获授权的已连接邮件工具。
一次 Agent 对话不会自动提供全天在线主机、可用登录、模型额度或发件邮箱。

真实简报需要可用的研究 Agent，或已配置的 standalone 大模型。
Agent 与 standalone 模式都消耗模型／账户用量，费用与限制取决于套餐、
模型、论文数量和证据长度。安装、配置校验、明确标注为合成数据的
离线预览**不调用模型**。真实 dry-run 虽然不发邮件，仍可能调用模型并产生费用。

## 1. 发给 Agent 的提示词

替换方括号中的内容，不要填写密码或 API Key。

> 请在[这台 Windows 电脑 / 指定的 Linux 服务器 / 我指定的已连接电脑或编程环境]
> 安装 https://github.com/RHFran/super-paper-radar 。先阅读 AGENTS.md 和
> docs/platform-setup_中文.md，检查源码，再运行仓库提供的安装脚本，使用隔离虚拟
> 环境并保留已有私有配置。我的研究方向是[主题]，输出语言[语言]，时区[IANA 时区]，
> 发送计划[星期或具体日期、本地时间]。主题、计划或模型不同时请使用独立订阅。
> 检查执行机器上是否已有安装并登录的 Codex / Claude Code CLI，设置 workflow.mode=agent，
> 由我选择的 Agent 自主规划、检索、阅读证据和综合，调用程序工具完成研究。若我选择
> 当前宿主 Agent，就使用导出的任务契约。只有我选择独立 API 时才使用 standalone 模式
> 和 configure-model，由我在本地隐藏输入 Key。真实调用前说明用量和费用，
> 先展示离线预览。付费真实测试、发邮件或
> 启用持久定时任务前先让我确认。不要把密钥放进聊天、源码、命令参数或日志。

- **Codex：** 把仓库作为项目打开，或在仓库目录运行 `codex`，粘贴上面的提示词。
  安装与登录按[官方 CLI 指南](https://learn.chatgpt.com/docs/codex/cli)操作。
- **Claude Code：** 打开仓库，或在目录内运行 `claude`。不同系统的安装方式见
  [官方安装指南](https://code.claude.com/docs/en/setup)。无需专用 Super Paper radar 插件。
- **ChatGPT：** 使用能访问目标仓库和执行工具的任务。没有这些工具的普通对话可以
  提供命令，由你执行。[电脑访问](https://learn.chatgpt.com/docs/computer-use)与
  [远程连接](https://learn.chatgpt.com/docs/remote-connections)能力取决于客户端、
  账户、工作区和授权。
- **ChatGPT dot：** 说明目标电脑/环境。安装到自己的电脑时，在 dot 的资料页允许
  访问该电脑，安装期间保持电脑在线且桌面应用运行。以当前
  [连接电脑指南](https://learn.chatgpt.com/docs/dots/computers-and-apps)为准。
  安装在 dot 的云电脑和安装在你的电脑是两回事。

API 模式的隐藏输入 Key 步骤应交给你在本地完成。CLI 模式通过对应 CLI 的官方流程登录，
不要把其凭据复制到项目中。不要把真实 Key 粘贴到提示词里。
这是源码安装流程，并非已经上架的 Super Paper radar MCP 服务，也不意味着每种助手
客户端都能无条件“一键安装”。

## 2. 自己运行安装脚本

前置条件：**Python 3.11+**、Git（也可下载并解压仓库 ZIP），以及安装时能访问
Python 包仓库。部分 Linux 发行版需要单独安装 `venv`/`ensurepip`。Python 和
venv 可用后，项目安装本身不需要管理员权限。

### Linux、macOS 或已准备好的 WSL

```bash
git clone https://github.com/RHFran/super-paper-radar.git && cd super-paper-radar && bash scripts/setup.sh
```

### 原生 Windows PowerShell

```powershell
git clone https://github.com/RHFran/super-paper-radar.git
if ($LASTEXITCODE -eq 0) { Set-Location super-paper-radar; .\scripts\setup.ps1 }
```

已有仓库时，在仓库目录只运行安装脚本。如果组织策略阻止 PowerShell 脚本，
改用 Python 入口，不要降低执行策略：

```powershell
py -3 scripts/setup.py
```

脚本创建或复用 `.venv`、安装当前源码、询问读者设置，并创建 Agent 主导的新配置。
独立 API 向导须用 `--api` 主动选择。最后校验并生成**离线合成预览**。不会启用邮件、修改系统安全设置、
安装系统定时任务，也不会覆盖已有配置。`validate` 输出可能含收件地址，分享日志前
请自行检查。

只想先看**无交互演示**：使用 `bash scripts/setup.sh --demo` 或
`.\scripts\setup.ps1 -Demo`。配置位于 `runtime/demo/config.json`，展示的是虚构
论文，不是按你的主题检索的真实结果。正常安装不要求独立模型 API key；`--skip-model`
或 `-SkipModel` 仍兼容用于跳过 API 向导。已有环境且不想运行 pip 可加
`--skip-install` 或 `-SkipInstall`。

包装脚本可从其他目录启动。传给包装脚本的相对配置/环境文件路径按仓库目录解析；
JSON 内的状态和输出路径按该 JSON 所在目录解析。服务器服务建议全部使用绝对路径。

## 3. 输入供应商、模型与 Key

### 优先选择 Agent 主导研究

新配置使用 `workflow.mode: "agent"`，在根层或对应档案配置 `agent`：

```json
{
  "workflow": {"mode": "agent"},
  "agent": {"backend": "codex", "executable": "", "model": "", "reasoning_effort": "", "timeout_seconds": 1800}
}
```

Claude Code 选择 `agent.backend: "claude"`；由现有宿主 Agent 执行时选择 `"host"`。
创建新配置时可用 `init --agent-backend codex|claude|host`。`agent.model` 留空保留 Agent
配置的默认模型；`agent.executable` 可指定命令路径。执行用户应与 CLI 登录用户一致。
保留正常工具和安全控制；权限阻挡须按授权流程解决，不能使用绕过权限的参数。

`run`、到期的 `tick` 和 `schedule` 启动完整研究任务。`host` 会返回 `awaiting_agent`
及持久任务／契约文件，由宿主通过程序工具完成。详见 [Agent 工作流](agent-workflow.md)
中的导出、检索、抓取、导入、校验与完成契约。导出任务或 Agent 在聊天中声称完成，都
不能替代程序对研究结果的检查。

旧配置缺少 `workflow` 时继续使用 `standalone`，只有明确修改才迁移。Agent 模式不由
`llm.enabled` 或旧的查询规划／筛选开关控制。[模式选择与就绪检查](model-backends.md)
说明用量限制及投递选择。CLI 凭据留在 CLI 中；如选 SMTP，另行配置 SMTP 凭据。

### 独立 API：保留原有本地向导

本节余下内容适用于可选的 `workflow.mode: "standalone"` 固定流程，其中 `llm.backend`
省略时默认 `"api"`。新安装可用 `bash scripts/setup.sh --api` 明确选择，或在私有配置
选择 standalone 后，单独运行向导：

```bash
bash scripts/run.sh --config config.json configure-model
```

```powershell
.\scripts\run.ps1 --config config.json configure-model
```

实际向导会依次询问：

1. DeepSeek、通义千问、Moonshot/Kimi、OpenAI 或自定义兼容供应商
2. HTTPS base URL，提供可修改的预设，可切换地区、工作区或网关
3. 供应商控制台中的模型 ID，不把模型限制为固定名单
4. 本地模型/密钥配置槽名称
5. 隐藏输入的 API Key
6. 是否确认保存到本地

向导为所选订阅启用 `llm`，JSON 只保存环境变量名，实际值保存在配置旁的 `.env`。
不会联网测试 Key、消耗 token 或启用 SMTP。已有模型或密钥槽不会静默覆盖，替换时
需要 `--replace`，并再次确认保存。`--secrets-file .env.work` 可指定其他被忽略的
私有环境文件名。

这个文件是**明文文件**，被 `.gitignore` 排除；POSIX 下以仅所有者可读写的 `0600`
权限保存。Windows 权限继承自目录：请使用自己的私有用户目录并检查 ACL。
Git 忽略不是加密或访问控制。不要强制加入版本库、上传、放到共享目录，或在截图和
发给别人的备份中包含它。

### 多模型、多 Key

每个订阅都可选择独立的供应商、模型和 Key。已有多订阅配置时，分别运行：

```bash
bash scripts/run.sh --config config.json --profile forest-weekly configure-model
bash scripts/run.sh --config config.json --profile battery-daily configure-model
```

请使用配置中实际存在的 profile ID。第一个示例生成
`PAPER_TRACKER_FOREST_WEEKLY_BASE_URL`、`PAPER_TRACKER_FOREST_WEEKLY_MODEL`
和 `PAPER_TRACKER_FOREST_WEEKLY_API_KEY`，并在对应订阅的 `llm` 字段引用它们。
第二个订阅会在同一个 `.env` 中新增独立条目。已有 SMTP 值和其他订阅设置保留。
这是按订阅选择模型，不是自动轮换 Key 或供应商失败后的自动切换。

### 供应商预设及兼容范围

API 模式请求 `<base URL>/chat/completions`，使用 JSON-object 输出。模型必须支持该
请求格式；原生 Anthropic Messages、仅支持 Responses 或仅支持流式输出的接口不能
直接替换。预设只是配置起点，不代表某个模型/Key 已完成真实兼容性测试。

| 供应商 | 预设 base URL | 官方说明 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | [JSON 输出](https://api-docs.deepseek.com/guides/json_mode/) |
| 通义千问 / 阿里云，北京 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | [地区与工作区地址](https://help.aliyun.com/en/model-studio/base-url)、[结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output) |
| Moonshot / Kimi，中国 | `https://api.moonshot.cn/v1` | [快速开始](https://platform.kimi.com/docs/get-api-key) |
| OpenAI | `https://api.openai.com/v1` | [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) |
| 自定义 | 你提供的 HTTPS base URL | 对应供应商的 Chat Completions 文档 |

模型名单、价格和 JSON 支持情况请以供应商当前控制台为准。千问 Key、地区和工作区
必须匹配；后台服务应使用按量付费/API 通道，不要使用限定交互式编程工具的 Coding
Plan Key。CLI 登录不是 API key；主流程请选择 `codex` 或 `claude` Agent 后端，不要把
登录凭据填进 API key 槽位。Standalone 中仍保留旧的仅模型调用 CLI 后端，见
[兼容模式](model-backends.md#standalone-compatibility-mode)。

### 加载已保存的 Key，或仅临时输入

CLI 与包装脚本都不会自动读取 `.env`，需要明确传入 `--env-file`：

```bash
bash scripts/run.sh --env-file .env --config config.json validate
# 下一条命令检索真实论文，可能调用模型并产生 token 费用：
bash scripts/run.sh --env-file .env --config config.json run
```

Windows 将 `bash scripts/run.sh` 替换为 `.\scripts\run.ps1`。若不使用 PowerShell
脚本，可用 `.\.venv\Scripts\python.exe scripts\launch.py` 加相同参数。已安装的
`paper-tracker` 命令和 `python -m literature_digest` 也支持全局 `--env-file` 参数。

环境文件的 `KEY=value` 或 `KEY='value'` 按字面值读取，不执行 shell、不展开变量、
不执行命令。一行一个条目，不支持多行值、重复变量名或行尾注释。
**不要用 shell 的 source 读取该文件。** Docker 自己的 `--env-file` 引号规则不同；
应挂载文件，并在镜像名之后传给应用的 `--env-file`，或使用部署指南中的独立 Docker
环境文件。只加载配置引用的变量名；进程中已有的非空环境变量优先。`validate`
只检查配置与变量是否存在，不验证认证、余额、模型兼容性或邮件送达。

另一个选项是在配置中启用 `llm` 并设置变量引用后，运行
`bash scripts/run.sh --prompt-secrets run`。缺失值会通过隐藏输入读取，只在当前
进程内保留，不写入文件。它需要交互终端，不能用于无人值守的后台服务。

## 4. 明确选择发邮件与后台运行

检查真实 dry-run 报告后，选择投递方式，模型与邮件后端互不绑定。下面是直接 SMTP
发送流程。使用获授权的已连接邮件工具时，按[邮件工具流程](model-backends.md#connector-send-lifecycle)
执行 `run --prepare-connector`、`begin-send`、外部工具发送一次，再用 `confirm-sent`
写入已确认回执。准备过程忽略 SMTP 的 `mail.enabled`，不需要 SMTP 凭据。
Agent 模式也支持 `tick --prepare-connector` 与 `schedule --prepare-connector`；
standalone 仅支持 `run` 准备。Host 先完成返回的研究任务，由宿主安排实际外部邮件工具
调用和回执导入。`--send` 仍为 SMTP；`--prepare-connector` 本身不发送。

使用 SMTP 时，按 [`.env.example`](../.env.example) 中的邮件变量配置
你有权使用的 SMTP 账户和发件地址，并设置 `mail.enabled: true`。仅提供收件邮箱
无法发信，仍需要可用的发件服务器凭据。不要把凭据写进命令参数。

```bash
# 明确执行一次真实邮件发送，可能产生模型调用费用：
bash scripts/run.sh --env-file .env --config config.json run --send
# 明确启动前台定时程序，每分钟检查各订阅：
bash scripts/run.sh --env-file .env --config config.json schedule --send
```

Windows 通过 `run.ps1` 使用相同参数。`Ctrl+C` 停止前台定时程序；关终端、重启电脑
也会停止。不加 `--send` 的 `run`、`tick`、`schedule` 都是**真实 dry-run**，仍可能
消耗模型 token。不要给同一份配置同时启动前台定时程序和系统定时任务。
Agent CLI 的调度进程须以已登录的 CLI 用户运行，通过 `PATH` 或 `agent.executable`
找到命令。Host 后端还需要可用宿主 Agent 完成导出的任务，定时器本身不能完成研究。
请检查登录有效性、工具权限和账户额度。失败任务应先查原因，再明确使用 `--retry-agent`
允许重试，不能让每分钟 tick 重复产生付费调用。

- **Linux 自有服务器：** 使用普通用户与一种进程管理方式。参考
  [systemd、cron、Docker 部署示例](../examples/README.md)。使用私有环境变量，
  或在命令中加 `--env-file /private/.env`。安装/启用服务应是单独确认的步骤。
- **Windows 自有服务器：** 一次性测试成功后，可在 Task Scheduler 创建任务。
  程序填 `.venv\Scripts\python.exe` 的绝对路径；参数填 `scripts\launch.py`
  的绝对路径，接 `--env-file`、`--config` 的绝对路径，再接 `tick --send`。
  工作目录设为仓库。每分钟重复，重叠策略选择“不启动新实例”，检查错过触发与重启
  设置。先在同一任务账户下运行 `validate`。不要把密码放进任务参数，不要授予
  管理员权限。演练期间去掉 `--send`。
- **Docker / WSL：** 在已选择的环境中使用 Linux 运行方式。配置、状态、输出应保存
  在持久存储中。停止的容器、休眠或关机的电脑都不能准时发信。

原生 Windows 使用标准库字节区间锁，以及 `tzdata` 包提供 IANA 时区。POSIX 使用
`flock`，通常读取系统时区数据。SQLite 状态库和锁应放在本地持久磁盘，不使用网络
共享盘。升级时保留并保护状态目录，删除它会失去历史去重保护。SMTP 结果不明确时，
先查提供商记录，再使用 `resolve`，不要盲目重发。

## 验证范围

Linux 安装、重复运行安全性、离线预览、配置、Key 不泄露、环境文件解析和进程锁
竞争已测试。CI 工作流包含 Windows、多版本 Python 和原生 PowerShell 安装测试。
本次实现环境没有 Windows/PowerShell 执行器，因此未在本地执行原生 Windows；
请查看仓库对应提交的 CI 结果。离线测试不代表真实模型调用、SMTP 送达、系统定时任务
安装或 Docker 实际运行已验证。投入无人值守运行前，请在自己的环境完成这些检查。
