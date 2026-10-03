<p align="center">
  <img src="docs/assets/logo.svg" width="104" height="104" alt="Smart Paper Tracker logo: a research paper with a tracking signal">
</p>
<h1 align="center">Smart Paper Tracker</h1>

<a id="english"></a>

We believe that in an age of exploding knowledge, when information is created and
shared far faster than we can read and absorb it, tools are essential to getting
information efficiently. We should save our precious neurons for the information
that matters most and for making more important judgments.

**Your research topics → evidence-grounded AI digests → your inbox, on your schedule.**

Let your agent help set up the program. The program retrieves, filters, analyzes,
deduplicates and schedules your research digests. Choose an already-installed,
logged-in **Codex or Claude Code CLI**, or a compatible **model API**. CLI mode
does not require a second API key; account usage, token costs and limits still
apply. The offline demo makes no model calls.

[English](#english) · [中文](#chinese) · [HTML demo](https://rhfran.github.io/smart-paper-tracker/?lang=en) · [Setup guide](docs/platform-setup.md)

## What you get

- A research overview and structured paper summaries: highlights, scientific
  question, methods and main results, with one numbered reference list.
- Source links and short matching evidence excerpts, with a JSON audit you can
  inspect. Important interpretations still need checking against the paper.
- Readable **HTML and plain text**, plus **RIS / BibTeX** for importing references
  into tools such as Zotero and EndNote.
- Different topics on different weekdays or specific dates, with your chosen
  local time, timezone, language and email recipient.
- Email through your configured **SMTP sender**, or a prepared message that an
  authorized agent sends through its **connected email tool** and confirms back
  to the program's delivery ledger.

For example: **BVOCs on Monday at 08:30**, **tree-species remote sensing on
Wednesday at 09:00**, and **urban forests only on March 15, 2027 at 10:00**.
Use separate profiles for separate messages to one inbox, or put several topics
in one profile for a combined digest. [Ready-to-edit calendar example](config.calendar.example.json).

## See the result

[Open the rendered HTML demo](https://rhfran.github.io/smart-paper-tracker/?lang=en) · [中文演示](https://rhfran.github.io/smart-paper-tracker/) · [Demo files and walkthrough](examples/preview/README.md)

The demo is clearly labeled synthetic: no real papers, model calls or email.
Setup generates an HTML preview; open the file path it prints in your browser.
The walkthrough includes English/Chinese regeneration commands. GitHub displays
repository `.html` files as source.

<a id="agent-setup"></a>

## Install with your agent

Give **Codex, Claude Code, ChatGPT or dot** this source repository and ask:

> Install Smart Paper Tracker using its setup script. Configure my research
> topics, language and local schedule. Check whether Codex or Claude Code is
> already installed and signed in on the execution machine, and let the program
> use that CLI as its model backend; use a separate API only if I choose it.
> The program should retrieve, filter, analyze and deduplicate the papers itself.
> Show the offline preview, explain account usage and costs before a real run,
> and ask before sending email or starting a background scheduler. Use SMTP or
> my authorized connected email tool according to my choice. Keep existing CLI and connector
> credentials in their original service; never copy them into this project.

The agent needs access to a machine where it can read the source and run commands.
With **Python 3.11+**, setup creates `.venv`, installs this checkout, preserves
existing configuration and generates an offline preview. For a CLI backend, use
`--skip-model` (`-SkipModel` on PowerShell) to skip the separate API wizard, then
set `llm.backend`. [Agent and platform instructions](docs/platform-setup.md) ·
[Model backends and connector delivery](docs/model-backends.md).

<a id="manual-setup"></a>

## Or set it up yourself

Download or clone this repository, open a terminal in its directory, then run:

```sh
# Linux / macOS: install and configure reader settings without the API wizard
bash scripts/setup.sh --skip-model
```

```powershell
# Windows PowerShell
./scripts/setup.ps1 -SkipModel
```

If PowerShell blocks scripts, use `py -3 scripts/setup.py --skip-model`; no policy
change is needed. Setup neither sends mail nor installs a scheduler.

### Choose the model backend

For an already-installed and signed-in Codex CLI, set this object in `config.json`
(or in the chosen profile). Use `"claude"` for a signed-in Claude Code CLI:

```json
"llm": {
  "enabled": true,
  "backend": "codex",
  "cli_model": "",
  "cli_timeout_seconds": 180,
  "plan_queries": true,
  "screen_candidates": true,
  "max_screen_candidates": 50
}
```

An empty `cli_model` uses the effective default of the isolated CLI invocation, without loading the user's configured model. Run under the same OS user
that is signed in; a chat subscription alone does not install or authenticate a
CLI on another machine. The program invokes the CLI for structured model output;
you do not need to assemble or import a manually written research report.

```sh
# Validate locally, then retrieve and analyze real papers without sending email
bash scripts/run.sh --config config.json validate
bash scripts/run.sh --config config.json run
```

**Prefer an independent API?** Keep `llm.backend` as `"api"` (the default for
existing configs) and use the local `configure-model` wizard for the provider,
HTTPS endpoint, model and hidden key entry. OpenAI, DeepSeek, Qwen and other
compatible services can be used. Saving a key to a private plaintext `.env`
requires confirmation. [API setup and safe secret input](docs/platform-setup.md).

```sh
bash scripts/run.sh --config config.json configure-model
bash scripts/run.sh --env-file .env --config config.json run
```

On Windows, replace `bash scripts/run.sh` with `./scripts/run.ps1`. Missing or
failed model analysis stops the digest; metadata-only results are not a successful
research report. CLI/API live runs consume account usage and may incur charges.

### Choose delivery and scheduling

Review a real report first. For direct SMTP delivery, configure SMTP, then use
`run --send`; automatic timing uses `schedule --send` or an external minute timer
calling `tick --send`. For an authorized connected email tool, use
`run --prepare-connector`, claim the immutable message with `begin-send`, send it
once through that tool, then record the confirmed provider receipt with
`confirm-sent`. Preparation alone sends no email. Only `run` prepares connector messages; the host
must arrange its recurring connector calls. [Backend and delivery workflow](docs/model-backends.md).

Keep the chosen execution machine online and retain its state directory.
[Full configuration and scheduling guide](docs/user-guide.md).

## More detail

- [English user guide](docs/user-guide.md) · [中文完整指南](docs/user-guide_中文.md)
- [Model backends and connector delivery](docs/model-backends.md)
- [Windows / Linux / macOS and agent setup](docs/platform-setup.md)
- [Deployment examples](examples/README.md) · [Validation scope](VALIDATION.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT license](LICENSE) · [Changelog](CHANGELOG.md)

Self-hosted software: you provide a running machine and model access. Email needs
an SMTP sender or an authorized external email tool. Model calls send selected
topic settings, candidate metadata and paper evidence to the chosen provider,
and consume its account usage. Source
figures are linked or embedded only where supported reuse rights permit.
Provider acceptance does not guarantee inbox delivery.

---

<a id="中文说明"></a>

<p align="center">
  <img src="docs/assets/logo.svg" width="104" height="104" alt="Smart Paper Tracker logo: a research paper with a tracking signal">
</p>
<h1 align="center">Smart Paper Tracker</h1>

<a id="chinese"></a>

我们相信，在知识爆炸、信息产生与传播的速度远超阅读与消化能力的时代，借助工具高效获取信息至关重要。我们应把宝贵的神经元留给更关键的信息，做出更重要的判断。

**你的研究方向 → 有证据的 AI 文献简报 → 按你的计划送达邮箱。**

让 Agent 帮你安装，程序自己检索、筛选、分析、去重和调度文献简报。模型后端可选
已安装并登录的 **Codex / Claude Code CLI**，也可选兼容的 **模型 API**。
CLI 模式不需要另配一把 API key，但仍消耗账户用量，受 token 费用和额度限制。
离线演示不调用模型。

[English](README.md#english) · [中文](#chinese) · [HTML 演示](https://rhfran.github.io/smart-paper-tracker/) · [安装指南](docs/platform-setup_中文.md)

## 你会得到什么

- 一份研究综述，以及按核心亮点、科学问题、研究方法、主要结果组织的论文解读，
  共用一套编号参考文献。
- 来源链接、可匹配的短证据片段和可检查的 JSON 审计记录。
  重要解读仍需回到论文核实。
- 易读的 **HTML 和纯文本**，以及可导入 Zotero、EndNote 等工具的 **RIS / BibTeX** 文献文件。
- 不同主题按不同星期或指定日期运行，自定当地时间、时区、语言和收件邮箱。
- 通过配置好的 **SMTP** 发信，或由获授权的 Agent 使用**已连接的邮件工具**发送
  程序准备的消息，再把确认回执写回程序的投递记录。

例如：**每周一 08:30 看 BVOCs**、**每周三 09:00 看遥感树种识别**，
**仅在 2027 年 3 月 15 日 10:00 看城市森林**。
同一个邮箱可以对应多个档案、分别收信；想合成一封简报，就把多个主题放在同一个档案里。
[可直接修改的日历配置](config.calendar.example.json)。

## 先看效果

[直接打开 HTML 演示](https://rhfran.github.io/smart-paper-tracker/) · [English demo](https://rhfran.github.io/smart-paper-tracker/?lang=en) · [演示文件与说明](examples/preview/README.md)

演示明确标注为合成内容，不检索真实论文、不调用模型、不发邮件。
安装会生成 HTML 预览，用浏览器打开命令输出中的文件路径即可查看。
演示说明包含中英文重新生成命令。GitHub 会把仓库里的 `.html` 显示为源代码。

<a id="agent-setup-zh"></a>

## 让 Agent 帮你安装

把这份源码项目交给 **Codex、Claude Code、ChatGPT 或 dot**，告诉它：

> 使用项目自带的脚本安装 Smart Paper Tracker，配置我的研究主题、语言和当地运行计划。
> 检查执行机器上是否已经安装并登录 Codex 或 Claude Code，让程序调用这个 CLI 作为模型
> 后端；只有我选择独立 API 时才另配 API。程序自己负责检索、筛选、分析和去重，
> 不要以人工写好研究报告再导入作为主要流程。先展示离线演示，真实调用前说明账户用量
> 和费用；发邮件或启动后台定时任务前先让我确认。按我的选择使用 SMTP 或获授权的
> 已连接邮件工具。已有 CLI 和邮件工具的凭据留在原来的服务中，不要复制进项目。

Agent 需要能读取源码并执行命令的电脑环境。安装好 **Python 3.11+** 后，脚本会创建
`.venv`、安装当前项目、保留已有配置并生成离线演示。选 CLI 后端时，用 `--skip-model`
（PowerShell 用 `-SkipModel`）跳过独立 API 向导，然后设置 `llm.backend`。
[Agent 与分平台操作说明](docs/platform-setup_中文.md) · [模型后端与邮件工具流程](docs/model-backends.md)。

<a id="manual-setup-zh"></a>

## 也可以自己设置

下载或克隆项目，在项目目录打开终端，运行：

```sh
# Linux / macOS：安装并设置读者信息，跳过独立 API 向导
bash scripts/setup.sh --skip-model
```

```powershell
# Windows PowerShell
./scripts/setup.ps1 -SkipModel
```

如果 PowerShell 阻止脚本运行，改用 `py -3 scripts/setup.py --skip-model`，不需要修改执行策略。
安装脚本不会发送邮件，也不会安装定时服务。

### 选择模型后端

使用已安装并登录的 Codex CLI，在 `config.json` 或所选档案中设置以下对象；
使用已登录的 Claude Code CLI 时，把后端改为 `"claude"`：

```json
"llm": {
  "enabled": true,
  "backend": "codex",
  "cli_model": "",
  "cli_timeout_seconds": 180,
  "plan_queries": true,
  "screen_candidates": true,
  "max_screen_candidates": 50
}
```

`cli_model` 留空使用隔离调用的有效 CLI 默认模型，不读取用户配置中的模型。执行程序的系统用户必须与登录 CLI 的用户一致；
仅有聊天订阅，不代表另一台机器已经安装和登录 CLI。程序直接调用 CLI 获取结构化模型
结果，不需要你或宿主 Agent 先手写一份研究报告再导入。

```sh
# 本地校验后，检索和分析真实论文；不发邮件
bash scripts/run.sh --config config.json validate
bash scripts/run.sh --config config.json run
```

**想用独立 API？** 使用 `llm.backend: "api"`（旧配置的默认值），运行本地
`configure-model` 向导，选择服务商、HTTPS 接口、模型，并隐藏输入 API key。
可接入 OpenAI、DeepSeek、Qwen 等兼容服务。明确确认后才把密钥保存到私有明文 `.env`。
[API 配置与安全输入凭据的方法](docs/platform-setup_中文.md)。

```sh
bash scripts/run.sh --config config.json configure-model
bash scripts/run.sh --env-file .env --config config.json run
```

Windows 将 `bash scripts/run.sh` 换成 `./scripts/run.ps1` 即可。模型缺失或分析失败时会
停止简报，不会把纯元数据当作成功的研究报告。CLI/API 真实运行都会消耗账户用量，并可能收费。

### 选择投递与调度方式

先检查真实报告。直接使用 SMTP 时，配置后运行 `run --send`；自动运行需持续运行
`schedule --send`，或由外部定时器每分钟调用 `tick --send`。
使用获授权的已连接邮件工具时，运行 `run --prepare-connector`，用 `begin-send` 领取
不可变消息，通过工具发送一次，再用 `confirm-sent` 写入已确认的服务商回执。
准备消息本身不会发送邮件。目前只有 `run` 支持准备连接工具消息，由宿主另行安排
重复执行与外部工具调用。[模型后端与投递流程](docs/model-backends.md)。

保持执行机器在线，并保留持久状态目录。[完整配置与调度说明](docs/user-guide_中文.md)。

## 进一步了解

- [中文完整指南](docs/user-guide_中文.md) · [English user guide](docs/user-guide.md)
- [模型后端与邮件工具流程](docs/model-backends.md)
- [Windows / Linux / macOS 与 Agent 安装](docs/platform-setup_中文.md)
- [部署示例](examples/README.md) · [验证范围](VALIDATION.md)
- [贡献指南](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [MIT 许可证](LICENSE) · [更新记录](CHANGELOG.md)

这是自托管软件，需要你提供运行主机和模型访问。发邮件可用 SMTP 或获授权的外部邮件工具。
模型调用会把主题设置、候选元数据和论文证据发送给所选提供方，并消耗该账户用量。原文图只有在符合支持的
转载权限时才嵌入，否则使用来源链接。服务商接受邮件不等于保证送达收件箱。
