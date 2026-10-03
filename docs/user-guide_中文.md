# Super Paper radar 完整使用指南

<a id="chinese"></a>

把你关心的研究方向变成有来源、有证据的文献简报，并按需定时发到邮箱。
研究主题、收件人、当地发送时间、每周星期或指定日期、时区和语言都可以配置；同一个运营后端
可以服务多个独立读者档案。

[项目首页](../README.md) · [English user guide](../docs/user-guide.md) · [分平台安装](../docs/platform-setup_中文.md) · [安全说明](../SECURITY.md)

**Python 3.11+ · Windows / Linux / macOS · MIT 许可证 · 明确确认后发邮件**

## 功能概览

- 检索 **Crossref、Europe PMC 和 arXiv**，支持自定义查询与主题过滤规则。
- 生成 **HTML、纯文本和 JSON 审计报告**，保留来源链接与证据级别，
  同时提供 **RIS 与 BibTeX**，供文献管理软件导入。
- 由 **Codex、Claude Code 或宿主 Agent** 自主规划查询、阅读证据、筛选和综合，调用
  程序工具生成经校验的论文解读与研究综述。独立 API／仅模型调用固定流程仍可选。
- 使用简洁的 Nature 风格编辑结构，综述与各主题共用**全局编号参考文献**。
- 按需展示符合转载条件的原文图或来源链接，不伪造研究配图。
- 支持多读者隔离、持久化去重、按时区调度（每周重复或指定日期单次运行），
  以及 SMTP 结果不确定时停止自动重试。
- **默认不发邮件**。`preview` 是离线合成示例；`run` 检索真实文献，只有明确加上 `--send` 才尝试发送。

这是需要自行运行的 CLI/后端，不是已经上线的订阅网站。
只填写邮箱不能让服务自动运转：需要持续运行的主机、检索网络和可用研究 Agent。
可选已安装并登录的 Codex / Claude Code CLI（无需第二把模型 API key），或能执行
导出任务契约的宿主 Agent。程序提供检索、证据校验、去重、排版和持久文献库。
邮件可用 SMTP 或明确的连接工具交接流程。详见 [Agent 工作流](agent-workflow.md)
与 [standalone 可选流程](model-backends.md#standalone-compatibility-mode)。

## 先体验离线演示

[直接打开 HTML 演示](https://rhfran.github.io/super-paper-radar/)，
或查看[英文版](https://rhfran.github.io/super-paper-radar/?lang=en)。

不需要 API key、注册账号或邮箱配置。需要已有 Python 3.11+ 和时区数据；
Windows 用户应先运行[安装脚本](../docs/platform-setup_中文.md)，安装时区包。
在下载或克隆的仓库目录运行：

```sh
python3 -m literature_digest --config config.example.json preview --language zh-CN
python3 -m literature_digest --config config.example.json preview --language en
```

用浏览器打开 `output/demo.zh-CN.html` 或 `output/demo.en.html`。每次命令同时生成
对应的 `.txt`、`.json`、`.ris` 和 `.bib`。所有内容都明确标注为**合成示例**：不检索真实论文、
不调用模型、不发邮件、不触碰投递数据库。固定演示主题不会读取你配置的真实研究方向。

也可以直接在 GitHub 查看仓库内的成品：

- 中文：[纯文本](../examples/preview/demo.zh-CN.txt)、[HTML 文件](../examples/preview/demo.zh-CN.html)、[证据 JSON](../examples/preview/demo.zh-CN.json)
- English: [readable text](../examples/preview/demo.en.txt), [HTML file](../examples/preview/demo.en.html), [evidence JSON](../examples/preview/demo.en.json)
- [演示流程与预期输出](../examples/preview/README.md)

GitHub 会把仓库里的 HTML 展示为源代码；下载后在本地浏览器中打开即可查看排版。
演示入口也可从[项目首页](../README.md)找到。

## 快速开始

要求 **Python 3.11+** 和 IANA 时区数据库。支持 Windows、Linux 和 macOS；
Windows 会安装 `tzdata` 包。安装脚本、系统要求和 Agent 辅助安装方式见
[分平台安装指南](../docs/platform-setup_中文.md)。下方命令使用 POSIX shell。
请从仓库源码安装；本次发布不包含 PyPI 上架。

推荐命令为 `paper-tracker`。原有 `literature-digest` 命令、
`python -m literature_digest`、`LITERATURE_*` 环境变量与配置格式继续兼容。

已有 1.x 安装时，请先阅读[从 1.x 原地升级](#upgrade-zh)。新安装在项目目录执行：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# 交互填写研究方向、邮箱、语言、时区和当地发送时间。
paper-tracker init
paper-tracker validate

# 离线查看版式：合成论文，不联网检索、不调用模型、不发邮件。
paper-tracker preview --language zh-CN

# 先按下方说明选择并检查研究 Agent，再执行真实研究；不发送邮件。
paper-tracker run
```

完成运行后的 JSON 会列出报告路径；host 任务先返回任务／契约路径，须完成后才有报告。
用浏览器打开成品 `.html` 查看版式；`.txt`
适合纯文本阅读；`.json` 记录来源、证据与筛选过程。离线示例会明确标注为演示，
不应作为真实研究引用。

也可以不用向导，直接生成配置：

```sh
paper-tracker --config config.json init --yes \
  --recipient researcher@example.org \
  --topic "urban climate adaptation" --topic "battery recycling" \
  --language zh-CN --timezone Asia/Shanghai --time 08:30
```

把示例邮箱改成实际收件地址。初始化不会启用发件，也不会保存凭据。新配置默认使用
`workflow.mode: "agent"` 与 Codex；可用 `init --agent-backend codex|claude|host` 选择。
Host 模式返回 `awaiting_agent` 任务，宿主调用工具完成后才会产生报告，见
[任务契约](agent-workflow.md)。`--config` 和 `--profile` 是全局参数，需放在子命令之前。

<a id="upgrade-zh"></a>

## 从 1.x 原地升级

项目现名 **Super Paper radar**，Python 发行包继续使用 2.0 起的 `paper-tracker`；
现有命令、配置格式与环境变量名称保持兼容。先停止工作进程并完成下方第 1 步的备份，再在旧虚拟环境运行
`python -m pip uninstall daily-literature-digest`，再在新源码目录运行
`python -m pip install .`。私有配置和状态应保留在包文件之外；原命令别名与模块导入路径继续兼容。

本次升级更新应用代码。最稳妥的第一步是保留现有单读者配置，不重新执行 `init`，
也不要用示例覆盖私有文件。旧配置未填写 `workflow` 时继续使用 standalone 固定流程；
若要迁移，须明确选择 `workflow.mode: "agent"` 并配置 `agent`。新示例不会让旧安装静默迁移。

1. 停止旧定时器或工作进程。私下备份旧代码、`config.json`、环境变量/凭据文件及
   整个状态目录，包括 SQLite 数据库和可能存在的 WAL/SHM 文件；备份期间保持所有工作进程停止。
2. 只替换或安装应用代码，保留原配置、`.env`、数据库和输出。为保持投递连续性，
   先不改收件人、`default` 档案 ID 和状态路径。
3. 依次运行 `validate`、`preview`、`status`，再执行不带 `--send` 的真实 `run`。
   检查迁移后的状态和报告，最后只重启**一个**定时器/工作进程。

旧配置未填写 `topics` 时，仍使用原来的 BVOC/遥感树种主题；语言默认 `zh-CN`，
已配置的时区保持不变。首次访问状态数据库时，有效旧投递记录会被非破坏性地复制到
按收件人隔离的 `default` 账本，原表保留，已发送论文标识、检查点和未确定结果随之保留。
即使 v2 的日报 ID 改变，同一当地日期已经发送过的日报也不会再次发送。

旧版 `prepared` 原稿缺少 v2 配置指纹，不能直接重放。先根据服务商记录处理不确定投递，
下一当地日期运行时可生成新一期。重新扫描当前发表窗口属于正常行为，不代表清空发件历史。

建议之后再增加多读者：`profiles` 会生成新的状态子目录，直接把旧配置移入数组
**不会自动转移去重历史**。需要保留原读者时，保持 ID 为 `default`、邮箱不变，
并在所有进程停止时，把其一致的数据库备份明确放到新配置解析出的路径，例如
`state/default/digest.sqlite3`。修改档案 ID 或收件人会使用不同账本。
迁移验证使用测试数据；本次交付尚未迁移你的实际旧安装。

## 配置研究方向、时间和语言

可以复制 `config.example.json`，也可以用 `init` 创建私有的 `config.json`。
主要读者设置如下：

```json
{
  "recipient": "researcher@example.org",
  "timezone": "Asia/Shanghai",
  "language": "zh-CN",
  "schedule": {"time": "08:30", "weekdays": [0, 1, 2, 3, 4], "catch_up": true},
  "topics": [
    {
      "id": "urban-climate",
      "name": "城市气候适应",
      "queries": ["urban climate adaptation", "urban heat resilience"],
      "include_any": ["climate adaptation", "heat resilience"],
      "include_all": [],
      "exclude_any": []
    }
  ]
}
```

- `time` 为读者 IANA 时区内的 `HH:MM`。`weekdays` 是非空、不重复的整数列表，
  `0` 是周一，`6` 是周日，用于每周重复运行。
- 也可以改用 `dates`：包含 1–1000 个不重复、有效的 `YYYY-MM-DD` 字符串，指定档案
  所在时区的当地日期。这些日期只执行当次，不会每年重复。同一个 `schedule` 对象
  不要同时填写 `dates` 和 `weekdays`。默认采用 `dates: null` 和按星期运行的计划，
  已有的星期配置保持原来的行为。
- `catch_up: true` 只允许在计划的当地日期内晚些时候补跑，不回放更早日期的漏跑任务。
  设为 `false` 时，检查必须发生在计划的那一分钟内。
  不同主题分日推送见[不同日期安排不同研究主题](#topic-calendar-zh)。
- `language` 接受 `zh-CN`、`en`、`de`、`ja` 等语言标签。内置报告栏目支持中英两套，
  其他标签用于指导模型正文语言，界面栏目回退为英文；论文原题和证据原文保留原语言。
- `queries` 用于发现候选文献；`include_any`、`include_all`、`exclude_any` 用于过滤文本。
  过滤词应填写字面主题短语，不是检索平台语法；不设置过滤词时，会使用查询短语。
- 可选 `source_queries` 对 `crossref`、`europepmc`、`arxiv` 分别提供查询列表。
  这些也必须是字面搜索短语，不是平台查询语法；运算符和引号语法会被清理。
- `publication_window_days` 是滚动发表窗口，默认 7 天。
  `max_papers_per_track` 是每个主题的篇数上限，沿用旧版字段名。
- `sources` 选择检索来源。Europe PMC 偏重生命科学，Crossref 与 arXiv 扩大覆盖范围；
  不同学科的收录范围、摘要及全文可用程度并不一致。

### 多个读者档案

参考 `config.profiles.example.json` 或
[`templates/profiles.example.json`](../templates/profiles.example.json)。
共享的检索、SMTP 和默认 workflow／agent 配置放在根层；每位读者放在 `profiles` 中，设置唯一的
`id` 及各自的邮箱、主题、语言与计划时间。多个档案可以使用同一个收件邮箱，并分别发送邮件，
包括在同一天发送。想把多个主题合成一封简报时，请将这些主题放在同一个档案中。

```sh
paper-tracker --config config.profiles.example.json validate
paper-tracker --config config.profiles.example.json --profile battery-en run
# 不指定 --profile 时，处理配置中的所有读者。
```

每个档案可覆盖根层的 `workflow` 和 `agent`，选择研究 Agent。采用可选 standalone
流程时，也可覆盖 `llm`，选择服务商、模型或凭据环境。`base_url_env`、`api_key_env`
和 `model_env` 填写的是**环境变量名称，不是 API key**。
例如，将以下片段合并到某个档案，再在运行主机私下设置对应变量：

```json
{
  "workflow": {"mode": "standalone"},
  "llm": {
    "enabled": true,
    "base_url_env": "BVOC_LLM_BASE_URL",
    "api_key_env": "BVOC_LLM_API_KEY",
    "model_env": "BVOC_LLM_MODEL"
  }
}
```

其他档案如未覆盖，仍使用根层默认值。交互配置方式见
[模型提供方配置指南](../docs/platform-setup_中文.md)。

请使用你实际配置中的档案 ID。每个档案的发件箱、去重记录和输出目录相互隔离。
相对路径以配置 JSON 所在目录为基准。状态数据库必须保存在持久存储中；删除或
新建数据库后，程序无法记住旧数据库里已经发送过的论文。
读者档案是逻辑隔离，不是不可信用户之间的安全权限边界。

<a id="topic-calendar-zh"></a>

### 不同日期安排不同研究主题

即使只发到**同一个邮箱**，也可以为每组“主题＋计划”建立一个独立档案。
同一档案中的主题总是一起运行，主题对象本身不设置计划。
完整、安全的示例见 [`config.calendar.example.json`](../config.calendar.example.json)：

- 每周一 08:30：生物源挥发性有机物（BVOCs）研究
- 每周三 09:00：遥感树种识别研究
- 仅 2027 年 3 月 15 日 10:00：城市森林与降温研究

三组计划都使用 `Asia/Shanghai` 当地时间，并继承同一个示例收件人。
请按需要修改邮箱、时区、语言、查询词和日期。核心配置如下（不发邮件，真实运行会消耗 Agent 用量）：

```json
{
  "recipient": "researcher@example.org",
  "timezone": "Asia/Shanghai",
  "language": "en",
  "schedule": {"time": "08:30", "weekdays": [0, 1, 2, 3, 4], "catch_up": true},
  "workflow": {"mode": "agent"},
  "agent": {"backend": "codex", "executable": "", "model": "", "reasoning_effort": "", "timeout_seconds": 1800},
  "mail": {"enabled": false},
  "profiles": [
    {
      "id": "bvoc-monday",
      "schedule": {"time": "08:30", "weekdays": [0]},
      "topics": [{
        "id": "bvoc",
        "name": "Biogenic volatile organic compounds (BVOCs)",
        "queries": ["biogenic volatile organic compounds", "BVOC emissions"],
        "include_any": ["biogenic volatile organic", "BVOC"]
      }]
    },
    {
      "id": "tree-species-wednesday",
      "schedule": {"time": "09:00", "weekdays": [2]},
      "topics": [{
        "id": "tree-species",
        "name": "Remote sensing of tree species",
        "queries": ["tree species mapping hyperspectral", "tree species classification lidar"],
        "include_any": ["tree species", "forest species"]
      }]
    },
    {
      "id": "urban-forest-date",
      "schedule": {"time": "10:00", "dates": ["2027-03-15"]},
      "topics": [{
        "id": "urban-forest",
        "name": "Urban forests and heat mitigation",
        "queries": ["urban forest heat mitigation", "urban trees cooling"],
        "include_any": ["urban forest", "urban trees"]
      }]
    }
  ]
}
```

档案会继承 `catch_up` 等共享计划字段，但明确填写 `dates` 列表时，会取代继承的
`weekdays`；明确填写 `weekdays` 列表则切回每周重复，并清除继承的日期。
如果档案只覆盖 `time`，原有的星期或日期选择不变。档案 ID 应保持稳定：每个档案
有独立的状态和论文去重记录，即使共用邮箱，同一论文若匹配两个档案，仍可能分别出现。
真实 `run` 或到期的 `tick` 前应选择并检查 Agent；使用旧 standalone 配置时，仍须
启用并配置 LLM。

先复制示例，再编辑私有配置：

```sh
cp config.calendar.example.json config.calendar.json
paper-tracker --config config.calendar.json validate
# 可选：立即生成这一档案的真实报告，不受计划日期和时间限制。
bash scripts/run.sh --env-file .env --config config.calendar.json --profile bvoc-monday run
# 只检查并运行当前到期的档案，不发邮件，也不会安装定时器。
bash scripts/run.sh --env-file .env --config config.calendar.json tick
```

`validate` 会显示每个档案的下一个计划时刻。指定日期的档案若显示
`next_run: null`，表示没有未来的计划时刻；过期日期不会自动改为按周重复。
当天计划时间已过时，仍可能符合当天补跑条件。需要下一次运行时，请更新未来日期。
`run` 是立即执行的手动操作，因此按日历执行应使用 `tick` 或 `schedule`。

要真正自动发送，先完成[邮件配置](#email-zh)，然后持续运行
`bash scripts/run.sh --env-file .env --config config.calendar.json schedule --send`，或者让外部定时器
每分钟调用一次 `bash scripts/run.sh --env-file .env --config config.calendar.json tick --send`。
仅保存 JSON 文件不会启动服务。

<a id="email-zh"></a>

## 启用模型解读和发邮件

### Agent 主导研究

新配置选择 `workflow.mode: "agent"`，`agent.backend` 可设为 `codex`、`claude` 或 `host`。
Codex／Claude 应已在执行机器安装并登录，保留正常工具与安全控制。Agent 自主负责规划、
检索选择、相关性判断和综合，调用程序工具获得来源证据、校验并完成结果。

`agent.executable` 可指定命令路径；`agent.model` 留空使用 Agent 配置的默认模型。
`agent.timeout_seconds` 默认 1800 秒，针对完整 Agent 调用。可用登录无需独立模型 API key，
仍受账户用量、费用和额度限制。`llm.enabled`、`plan_queries`、`screen_candidates`
只属于 standalone 模式，不控制 Agent 研究。

`run`、到期的 `tick` 和 `schedule` 使用 Agent 工作流。Host 模式返回 `awaiting_agent`
任务，由宿主读取导出契约，调用 `agent-tool JOB_ID` 的 search／fetch／ingest／validate／
finalize 操作。导出任务不是研究报告；完成步骤校验证据、保存文献、排版，并按需准备
发件箱，但不会发送邮件。[完整工具契约](agent-workflow.md)包含命令与结果格式。

邮件方式独立选择。可使用下方 SMTP，或 `run --prepare-connector`，再由获授权宿主
通过外部工具发送一次并导入确认回执。Host 必须先完成研究，才能领取消息。
`tick`／`schedule` 不会自动调用宿主邮件工具，详见
[邮件工具流程](model-backends.md#connector-send-lifecycle)。

### Standalone 仅模型调用后端

旧配置未填写 `workflow` 时保留固定流程，也可明确设置 `workflow.mode: "standalone"`。
启用 `llm.enabled: true`，选择 `llm.backend: "api"`、`"codex"` 或 `"claude"`，由程序
执行仅模型调用。旧的 `cli_executable`、`cli_model`、`cli_timeout_seconds`、
`plan_queries`、`screen_candidates` 和 `max_screen_candidates` 在此模式继续生效。
[Standalone 后端详情](model-backends.md#standalone-compatibility-mode)。

### 独立 API 与直接 SMTP

本地 API 向导支持 DeepSeek、Qwen、Moonshot、OpenAI 及自定义 HTTPS 兼容接口。
请填写服务商当前可用的实际模型名；可用性和价格可能变化。这是可选 standalone 流程，
应选择 `workflow.mode: "standalone"` 和 `llm.backend: "api"`。安装时可用 `--api` 主动选择，
也可之后单独执行向导：

```sh
bash scripts/run.sh --config config.json configure-model
# 多档案配置应在命令前指定档案：
bash scripts/run.sh --config config.calendar.json --profile bvoc-monday configure-model
# 只加载你信任的私有环境文件；真实调用模型可能产生费用。
bash scripts/run.sh --env-file .env validate
bash scripts/run.sh --env-file .env run
```

Windows 将 `bash scripts/run.sh` 换成 `./scripts/run.ps1`。向导在本地隐藏输入密钥，
不发网络请求，只有确认保存后才启用所选档案的模型。`.env` 是配置文件旁的明文文件，
POSIX 权限为 `0600`；Windows 请核实继承的访问权限足够私密。不要提交到仓库。
替换已有模型设置或槽位需要 `--replace` 并明确确认。不想保存凭据时，可以配置环境变量
引用后用 `--prompt-secrets`，仅在当前进程中输入。详细说明见
[分平台与模型配置指南](../docs/platform-setup_中文.md)。

Standalone 独立 API（其中 `llm.backend` 默认 `"api"`）与 SMTP 也可手工配置：

1. 把 `.env.example` 复制为私有 `.env`，在本地填写运行凭据。
   CLI 读取进程环境变量，**不会自动加载 `.env`**。
2. Standalone 模式的真实 `run`、到期 `tick`/`schedule` 和发送要求启用并配置 LLM。
   把 `llm.enabled` 改为 `true`，配置 HTTPS 的 OpenAI-compatible
   chat-completions 接口基址、模型名和 API key。也可以使用兼容的国产模型服务，
   见[模型提供方配置](../docs/platform-setup_中文.md)。离线合成 `preview` 不需要 LLM。
3. 需要发邮件时，把 `mail.enabled` 改为 `true`，配置 SMTP 主机、账号、
   密码或应用专用密码，以及获授权的发件地址。安全方式使用 `ssl` 或 `starttls`，
   端口按服务商要求填写，常见分别是 465 和 587。
4. 把私有环境文件作为数据读取，先检查真实预览，再明确发送：

```sh
# 只读取你自己创建并信任的私有文件；不要把它作为 shell 脚本执行。
chmod 600 .env
bash scripts/run.sh --env-file .env validate
bash scripts/run.sh --env-file .env run
bash scripts/run.sh --env-file .env run --send
```

向导生成的 `.env` 是交给启动器解析的字面配置数据，不是 shell 脚本。
**不要对它执行 `source` 或 `. ./.env`。** 启动器和 `paper-tracker` /
`python -m literature_digest` 都支持在子命令前明确指定 `--env-file`；不指定时，
只读取进程环境变量，不会自动加载 `.env`。进程中已有的非空变量优先于文件中的值；
只读取配置中引用的变量名称。自带 systemd、cron 示例使用这个安全解析器。
Docker/Compose 的环境文件规则不同，请按[部署示例](../examples/README.md)操作，
不要直接复用向导文件中的带引号值。

即使不加 `--send`，`run` 也可能调用模型接口，并可能产生服务商费用。
启用模型意味着向配置的模型提供方发送选定论文证据。CLI/API 用量与费用随模型、选定
论文数量和证据长度变化。没有符合条件的论文时可能不会请求模型，但仍需有效的模型配置。
凭据缺失、模型失败或无法产出
受证据支持的解读时，真实简报会停止，纯元数据检索结果不能作为成功成品发送。
SMTP 接受邮件也不等于邮件一定进入收件人的收件箱。

## 定时运行

选择一种方式，保持主机运行，并确保进程能访问 Agent 登录／工具或 standalone 模型凭据，
以及持久状态。Agent 模式的每次到期运行分派完整研究任务；host 还需有可用宿主 Agent
完成导出任务，单独的定时器不能研究。以下是直接 SMTP 路径；连接工具的准备、领取、发送与确认流程须由宿主另外安排，
Agent 模式可用 `tick --prepare-connector` 或 `schedule --prepare-connector` 按日历
准备消息；standalone 仍用立即执行的 `run`。准备不等于发送。以下为 SMTP 命令：

```sh
# 前台常驻，每分钟检查各读者的当地计划时间；Ctrl-C 停止。
bash scripts/run.sh --env-file .env schedule --send

# 或由 systemd/cron/其他外部定时器每分钟调用一次。
bash scripts/run.sh --env-file .env tick --send
```

不加 `--send` 时，两种方式都不发邮件。`run` 不检查计划的星期、日期或时间；
`run --send` 在正常邮件配置和发件箱安全检查下尝试立即发送。
`tick` 和 `schedule` 才按各档案的当地计划判断是否到期。
必须实际运行工作进程或外部定时器，配置才会被定时执行。补跑不会追溯更早日期。
需要不同主题在不同星期或指定日期运行时，使用[上方的日历配置](#topic-calendar-zh)。

systemd、cron、Docker 的示例见 [`examples/README.md`](../examples/README.md)。
本仓库不会自动安装或启用这些服务。

## 导入 Zotero 或 EndNote

无需额外导出开关。非空真实报告会在 HTML/TXT/JSON 旁生成 `.ris` 和 `.bib`，
文件名采用 `<local-date>_<digest-id>[_preview].ris` 和 `.bib`。
只导出本次选中并去重的论文，不包含被排除、暂缓处理或此前已经发送的记录。
空简报不会生成文献导入文件。HTML 中提供本地文件链接；发送邮件时会附带 RIS 和
BibTeX 文件。重试发送会复用准备好的固定附件，不重新读取已被改动的本地文件。

- **Zotero 桌面版**：File → Import… → A file，选择 RIS 或 BibTeX 文件。
  [官方导入说明](https://www.zotero.org/support/kb/importing_standardized_formats)。
- **EndNote 桌面版**：File → Import → File，选择 RIS 文件，导入筛选器使用
  **Reference Manager (RIS)**，文本编码选择 UTF-8。
  [官方导入选项说明](https://docs.endnote.com/docs/endnote/2025/v1/windows/en/content/08import/import_options.htm)。

导出会保留可用的作者、题名、期刊、发表日期、DOI、原文网址、摘要以及来源/类型说明。
缺失的元数据会省略，不会编造。直接双击打开是否可用取决于系统文件关联；程序不会
自动同步文献管理软件的云端文献库。菜单名称和步骤可能随软件版本变化。
导入后请检查作者姓名：来源明确给出的姓/名边界会保留，未结构化姓名按原文保留，不猜测姓氏。

离线 `preview` 也会生成 `demo.en.ris` / `.bib` 或 `demo.zh-CN.ris` / `.bib`，
并明确标注 **DEMO / 合成示例**。试用时请导入临时测试库，不要混进真实文献集合。

## 证据、参考文献和原文图

JSON 审计保留来源元数据和证据。系统重复扫描当前发表窗口，以便捕捉延迟收录；
同时合并标识符、过滤已确认发送的论文。发表日期缺失、冲突或精度不足的候选记录
会留下审计信息，不会被悄悄当作近期论文。

每篇论文固定使用四个解读栏目：**核心亮点、科学问题、实验或模型方法、主要结果**。
相关数据细节和作者报告的适用边界纳入方法或结果，不另设数据、局限栏目。

模型断言必须配有来源中能匹配的短证据片段。这证明可追溯性，不代表转述语义必然
正确；重要结论仍应回到论文核实。只有元数据或摘要时，不会冒称读过全文。
研究综述同样遵循来源约束，一篇论文出现在多个主题时保持同一个参考文献编号。

arXiv 检索会把一条查询中的字面词用 `AND` 连接后检索元数据，而不是要求整句精确匹配。
多条查询合并结果，但结果受检索上限约束，不代表穷尽了所有相关文献。

`fetch_full_text` 可按需尝试获取可用全文。arXiv 会尝试官方
`https://arxiv.org/html/<exact-version-id>` 页面；页面不可用或正文不足时，会保留可用的
摘要/元数据证据级别并记录警告，不把导航栏或 HTML 元数据当作全文。

`images.mode` 默认是 `off`，
另有 `links` 与 `embed` 用于支持的来源图。嵌入需要符合支持的图级转载许可和署名条件；
不满足时保留来源链接。手工提供的 `figure_catalog` 条目需明确设置
`license_scope: "figure"` 才能嵌入，不能把文章开放获取状态直接当作每张图的转载授权。填写示例见[图片元数据模板](../templates/README.md)。
能否展示图片取决于来源、论文许可和实际可用数据。
第三方论文正文与图像不因本仓库使用 MIT 许可证而改变版权。
“Nature 风格”指编辑结构，不代表与该期刊有关联或完全复刻其排版。

## 运行状态与故障处理

```sh
paper-tracker status
# 在发件平台/收件记录中核实不确定邮件后，二选一：
paper-tracker resolve DIGEST_ID sent
# 只有确认没有投递，才使用 retry：
paper-tracker resolve DIGEST_ID retry
paper-tracker send DIGEST_ID
```

多读者配置的状态操作请加 `--profile ID`。`send` 使用已经准备好的原稿；
过期原稿会被拒绝。重试前先看 `status`，不要删除数据库绕过去重或不确定发送保护。

- **没有论文**：检查审计中的排除原因、发表日期要求和主题过滤词。
  空结果不等于不存在相关文献。
- **检索失败**：检查网络、服务商限流和错误信息。配置来源检索失败时，不把结果当作正常空简报发送。
- **Agent 任务被阻挡**：查看 `agent-tool JOB_ID status` 与具体错误，检查 CLI 登录、
  额度、来源访问、工具权限和结果校验。导出任务或聊天中声称完成不等于真正完成。
  解决原因后再用 `run --retry-agent`；重复 tick 不会自动产生新的付费调用。
  Host 任务需由宿主完成契约。
- **Standalone 没有解读**：检查必需模型是否启用、凭据、模型错误和摘要／全文证据。
  失败或无法支持的解读会阻止发送。论文解读或综述失败后，该档案的 `tick`/`schedule`
  自动重试会暂停至当地日期结束，避免每分钟重复付费调用。暂停状态重启后仍保留，
  `status` 会显示原因。修好模型后，可明确执行 `run` 重试，建议先不加 `--send`。
  修改模型或内容配置也可恢复尝试；仅修改计划时间不会解除暂停。
  完整解读成功后会清除暂停，已经发送的论文去重记录不受影响。
- **没有邮件**：检查 `mail.enabled`、环境变量、`--send`、计划时间、收件地址、服务商日志与未解决发件状态。
- **未知时区**：安装操作系统的 IANA 时区数据。

## 开发与验证范围

```sh
python -m unittest discover -s tests -v
python -m compileall -q literature_digest
```

CI 配置执行离线测试和 CLI/安装冒烟检查，外部服务使用模拟数据。
本次交付**没有声称验证过真实 SMTP 投递、真实模型响应、线上部署或已安装的定时器**。
具体本地检查范围见 [VALIDATION.md](../VALIDATION.md)。

代码采用 [MIT 许可证](../LICENSE)，版本变化见 [CHANGELOG.md](../CHANGELOG.md)。
