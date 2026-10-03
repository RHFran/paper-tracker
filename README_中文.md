# Paper Tracker · 可配置科研文献简报

把你关心的研究方向变成有来源、有证据的文献简报，并按需定时发到邮箱。
研究主题、收件人、发送时间、星期、时区和语言都可以配置；同一个运营后端
可以服务多个独立读者档案。

[English](README.md) · [示例演示](examples/preview/README.md) · [贡献指南](CONTRIBUTING.md) · [安全说明](SECURITY.md)

**Python 3.11+ · 无第三方运行时依赖 · MIT 许可证 · 默认安全预览**

## 功能概览

- 检索 **Crossref、Europe PMC 和 arXiv**，支持自定义查询与主题过滤规则。
- 生成 **HTML、纯文本和 JSON 审计报告**，保留来源链接与证据级别。
- 配置兼容模型后，生成有证据支撑的论文解读与研究综述；未配置模型时，明确输出检索简报。
- 使用简洁的 Nature 风格编辑结构，综述与各主题共用**全局编号参考文献**。
- 按需展示符合转载条件的原文图或来源链接，不伪造研究配图。
- 支持多读者隔离、持久化去重、按时区调度，以及 SMTP 结果不确定时停止自动重试。
- **默认不发邮件**。`preview` 是离线合成示例；`run` 检索真实文献，只有明确加上 `--send` 才尝试发送。

这是需要自行运行的 CLI/后端，不是已经上线的订阅网站。
只填写邮箱不能让服务自动运转：运营者需要提供持续运行的主机、检索网络和 SMTP
发件配置；模型辅助解读还需要模型接口与凭据。

## 先体验离线演示

不需要 API key、注册账号、邮箱配置或安装 Python 包。在下载或克隆的仓库目录运行：

```sh
python3 -m literature_digest --config config.example.json preview --language zh-CN
python3 -m literature_digest --config config.example.json preview --language en
```

用浏览器打开 `output/demo.zh-CN.html` 或 `output/demo.en.html`。每次命令同时生成
对应的 `.txt` 和 `.json`。所有内容都明确标注为**合成示例**：不检索真实论文、
不调用模型、不发邮件、不触碰投递数据库。固定演示主题不会读取你配置的真实研究方向。

也可以直接在 GitHub 查看仓库内的成品：

- 中文：[纯文本](examples/preview/demo.zh-CN.txt)、[HTML 文件](examples/preview/demo.zh-CN.html)、[证据 JSON](examples/preview/demo.zh-CN.json)
- English: [readable text](examples/preview/demo.en.txt), [HTML file](examples/preview/demo.en.html), [evidence JSON](examples/preview/demo.en.json)
- [演示流程与预期输出](examples/preview/README.md)

GitHub 会把 HTML 展示为源代码；下载后在本地浏览器中打开即可查看排版。
这里提供的是可复现离线演示，尚未部署在线网站或 GitHub Pages。

## 快速开始

要求 **Python 3.11+**、系统 IANA 时区数据库；进程锁支持 Linux、macOS 或 WSL。
Python 运行时不依赖第三方包。请从仓库源码安装；本次发布不包含 PyPI 上架。

推荐命令为 `paper-tracker`。原有 `literature-digest` 命令、
`python -m literature_digest`、`LITERATURE_*` 环境变量与配置格式继续兼容。

已有 1.x 安装时，请先阅读下方“从 1.x 原地升级”。新安装在项目目录执行：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# 交互填写研究方向、邮箱、语言、时区和当地发送时间。
paper-tracker init
paper-tracker validate

# 离线查看版式：合成论文，不联网检索、不调用模型、不发邮件。
paper-tracker preview --language zh-CN

# 检索真实元数据并生成报告；不发送邮件。
paper-tracker run
```

命令返回的 JSON 会列出生成文件路径。用浏览器打开 `.html` 查看版式；`.txt`
适合纯文本阅读；`.json` 记录来源、证据与筛选过程。离线示例会明确标注为演示，
不应作为真实研究引用。

也可以不用向导，直接生成配置：

```sh
paper-tracker --config config.json init --yes \
  --recipient researcher@example.org \
  --topic "urban climate adaptation" --topic "battery recycling" \
  --language zh-CN --timezone Asia/Shanghai --time 08:30
```

把示例邮箱改成实际收件地址。初始化不会启用发件，也不会保存凭据。
`--config` 和 `--profile` 是全局参数，需要放在子命令之前。

## 从 1.x 原地升级

项目现名 Paper Tracker，Python 发行包名改为 `paper-tracker`。先停止工作进程并完成下方第 1 步的备份，再在旧虚拟环境运行
`python -m pip uninstall daily-literature-digest`，再在新源码目录运行
`python -m pip install .`。私有配置和状态应保留在包文件之外；原命令别名与模块导入路径继续兼容。

本次升级更新应用代码。最稳妥的第一步是保留现有单读者配置，不重新执行 `init`，
也不要用示例覆盖私有文件。

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

- `time` 为读者 IANA 时区内的 `HH:MM`；`weekdays` 中 `0` 是周一，`6` 是周日。
  `catch_up: true` 允许当天晚于计划时间时补跑，不回放更早日期的漏跑任务。
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
[`templates/profiles.example.json`](templates/profiles.example.json)。
共享的检索、模型和 SMTP 配置放在根层；每位读者放在 `profiles` 中，设置唯一的
`id`、邮箱、主题、语言与计划时间。

```sh
paper-tracker --config config.profiles.example.json validate
paper-tracker --config config.profiles.example.json --profile battery-en run
# 不指定 --profile 时，处理配置中的所有读者。
```

请使用你实际配置中的档案 ID。每个档案的发件箱、去重记录和输出目录相互隔离。
相对路径以配置 JSON 所在目录为基准。状态数据库必须保存在持久存储中；删除或
新建数据库后，程序无法记住旧数据库里已经发送过的论文。
读者档案是逻辑隔离，不是不可信用户之间的安全权限边界。

## 启用模型解读和发邮件

1. 把 `.env.example` 复制为私有 `.env`，在本地填写运行凭据。
   CLI 读取进程环境变量，**不会自动加载 `.env`**。
2. 需要模型解读时，把 `llm.enabled` 改为 `true`，配置 HTTPS 的
   OpenAI-compatible chat-completions 接口基址、模型名和 API key。
3. 需要发邮件时，把 `mail.enabled` 改为 `true`，配置 SMTP 主机、账号、
   密码或应用专用密码，以及获授权的发件地址。安全方式使用 `ssl` 或 `starttls`，
   端口按服务商要求填写，常见分别是 465 和 587。
4. 导出变量，先检查真实检索预览，再明确发送：

```sh
# 只加载你自己创建并信任的私有环境文件。
chmod 600 .env
set -a
. ./.env
set +a
paper-tracker validate
paper-tracker run
paper-tracker run --send
```

即使不加 `--send`，`run` 也会在启用模型时调用接口，并可能产生服务商费用。
启用模型意味着向配置的模型提供方发送选定论文证据。没有模型或可用证据时，输出
检索简报，不冒充深度解读。SMTP 接受邮件也不等于邮件一定进入收件人的收件箱。

## 定时运行

选择一种方式，保持主机运行，并确保进程能访问运行凭据和持久状态：

```sh
# 前台常驻，每分钟检查各读者的当地计划时间；Ctrl-C 停止。
paper-tracker schedule --send

# 或由 systemd/cron/其他外部定时器每分钟调用一次。
paper-tracker tick --send
```

不加 `--send` 时，两种方式都保持预览模式。`run --send` 立即发送；
`tick --send` 按计划判断是否到期。仅写入配置不会自动启动定时服务。

systemd、cron、Docker 的示例见 [`examples/README.md`](examples/README.md)。
本仓库不会自动安装或启用这些服务。

## 证据、参考文献和原文图

JSON 审计保留来源元数据和证据。系统重复扫描当前发表窗口，以便捕捉延迟收录；
同时合并标识符、过滤已确认发送的论文。发表日期缺失、冲突或精度不足的候选记录
会留下审计信息，不会被悄悄当作近期论文。

每篇论文固定使用四个解读栏目：**核心亮点、科学问题、实验或模型方法、主要结果**。
相关数据细节和作者报告的适用边界纳入方法或结果，不另设数据、局限栏目。

模型断言必须配有来源中能匹配的短证据片段。这证明可追溯性，不代表转述语义必然
正确；重要结论仍应回到论文核实。只有元数据或摘要时，不会冒称读过全文。
研究综述同样遵循来源约束，一篇论文出现在多个主题时保持同一个参考文献编号。

`fetch_full_text` 可按需尝试获取可用全文。`images.mode` 默认是 `off`，
另有 `links` 与 `embed` 用于支持的来源图。嵌入需要符合支持的图级转载许可和署名条件；
不满足时保留来源链接。手工提供的 `figure_catalog` 条目需明确设置
`license_scope: "figure"` 才能嵌入，不能把文章开放获取状态直接当作每张图的转载授权。填写示例见[图片元数据模板](templates/README.md)。
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
- **没有解读**：检查是否启用模型、环境变量是否完整，以及是否有摘要或全文证据；失败时会降级为检索简报。
- **没有邮件**：检查 `mail.enabled`、环境变量、`--send`、计划时间、收件地址、服务商日志与未解决发件状态。
- **未知时区**：安装操作系统的 IANA 时区数据。

## 开发与验证范围

```sh
python -m unittest discover -s tests -v
python -m compileall -q literature_digest
```

CI 配置执行离线测试和 CLI/安装冒烟检查，外部服务使用模拟数据。
本次交付**没有声称验证过真实 SMTP 投递、真实模型响应、线上部署或已安装的定时器**。
具体本地检查范围见 [VALIDATION.md](VALIDATION.md)。

代码采用 [MIT 许可证](LICENSE)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。
