<p align="center">
  <img src="docs/assets/logo.svg" width="440" alt="Super Paper radar">
</p>
<h1 align="center">Super Paper radar</h1>

<a id="chinese"></a>

我们相信，在知识爆炸、信息产生与传播的速度远超阅读与消化能力的时代，借助工具高效获取信息至关重要。我们应把宝贵的神经元留给更关键的信息，做出更重要的判断。

**你的研究方向 → 有证据的 AI 文献简报 → 按你的计划送达邮箱。**

**推荐搭配 Codex 的 dot 使用 / Recommended: use with Codex dot。**
[使用 dot 作为宿主 Agent](docs/agent-workflow.md#using-with-codex-dot)。

**Agent 主导研究，程序提供可靠的工具和记录。** 已安装并登录的 **Codex / Claude Code**
Agent 自主规划检索、阅读证据、筛选论文并组织简报，调用程序完成检索、证据校验、去重、
排版和持久文献库记录。已有的**宿主 Agent** 也可使用同一套任务契约。
可用的 Agent 登录不要求第二把模型 API key，但仍消耗账户用量，受费用和额度限制。
独立 API／仅模型调用的固定流程保留为可选模式。离线演示不调用模型。

[English](README.md#english) · [中文](#chinese) · [HTML 演示](https://rhfran.github.io/super-paper-radar/) · [安装指南](docs/platform-setup_中文.md)

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

[直接打开 HTML 演示](https://rhfran.github.io/super-paper-radar/) · [English demo](https://rhfran.github.io/super-paper-radar/?lang=en) · [演示文件与说明](examples/preview/README.md)

演示明确标注为合成内容，不检索真实论文、不调用模型、不发邮件。
安装会生成 HTML 预览，用浏览器打开命令输出中的文件路径即可查看。
演示说明包含中英文重新生成命令。GitHub 会把仓库里的 `.html` 显示为源代码。

<a id="agent-setup-zh"></a>

## 让 Agent 帮你安装

把这段示例交给 **Codex、Claude Code、ChatGPT 或 dot**，替换主题和邮箱即可：

> 请安装并使用 Super Paper radar（[https://github.com/RHFran/super-paper-radar.git](https://github.com/RHFran/super-paper-radar.git)）。
> 每天北京时间上午 8:30，围绕【xxxx，xxxxx】这两个主题，检索、筛选并解读近期论文，
> 用中文整理后发送到 yourname@example.com。

主题可以是一个或多个，时间、时区和频率也可修改，例如“每周一、周五上午 8:30”。
北京时间对应 `Asia/Shanghai`；不同主题需要不同计划时，使用独立档案。
请在自己的私有配置中替换示例邮箱，不要把真实收件地址提交到公开仓库。

安装时，也请告诉 Agent：

> 使用项目自带的脚本安装 Super Paper radar，配置我的研究主题、语言和当地运行计划。
> 检查执行机器上是否已经安装并登录 Codex 或 Claude Code。使用 Agent 主导模式，
> 由 Agent 自主规划并调用程序的检索、证据、校验和文献库工具完成研究；若我选择宿主
> Agent，就使用导出的任务契约。只有我选择独立 API 时才使用 standalone 模式。
> 先展示离线演示，真实调用前说明账户用量和费用；发邮件或启动后台定时任务前先让我确认。
> 按我的选择使用 SMTP 或获授权的
> 已连接邮件工具。已有 CLI 和邮件工具的凭据留在原来的服务中，不要复制进项目。

Agent 需要能读取源码并执行命令的电脑环境。安装好 **Python 3.11+** 后，脚本会创建
`.venv`、安装当前项目、保留已有配置并生成离线演示。新配置使用 `workflow.mode: "agent"`，
`agent.backend` 可选 `codex`、`claude` 或 `host`；独立 API 向导需主动选择。
未填写 `workflow` 的旧配置保持原有 standalone 流程，不会静默迁移。
[Agent 工作流与工具契约](docs/agent-workflow.md) · [Agent 与分平台操作说明](docs/platform-setup_中文.md)。

<a id="manual-setup-zh"></a>

## 也可以自己设置

下载或克隆项目，在项目目录打开终端，运行：

```sh
# Linux / macOS：安装并设置 Agent 主导的研究流程
bash scripts/setup.sh
```

```powershell
# Windows PowerShell
./scripts/setup.ps1
```

如果 PowerShell 阻止脚本运行，改用 `py -3 scripts/setup.py`，不需要修改执行策略。
安装脚本不会发送邮件，也不会安装定时服务。

### 选择研究 Agent

使用已安装并登录的 Codex CLI，在 `config.json` 或所选档案中设置以下对象。
Claude Code 使用 `"claude"`；由当前项目中的宿主 Agent 执行时使用 `"host"`：

```json
"workflow": {"mode": "agent"},
"agent": {
  "backend": "codex",
  "executable": "",
  "model": "",
  "reasoning_effort": "",
  "timeout_seconds": 1800
}
```

CLI 执行完整研究任务，保留正常工具与安全控制。Agent 自主决定检索与证据阅读步骤，
再调用程序工具校验和完成结果。`model` 留空使用 Agent 配置的默认模型；`executable`
留空使用所选后端的命令。执行程序的系统用户须与 CLI 登录用户一致；聊天订阅本身
不代表另一台机器已经安装和登录 CLI。若使用旗舰模型，请先检查当前账户和 CLI 支持，
再填写准确模型 ID 与支持的 `reasoning_effort`。留空继承默认值；明确设置不受支持时
失败，不由程序静默降级。Host 的模型与推理强度须在宿主侧先选定。

```sh
# 本地校验与离线合成预览，不消耗 Agent／模型用量
bash scripts/run.sh --config config.json validate
bash scripts/run.sh --config config.json preview
# 启动 Agent 的真实研究任务；不发邮件
bash scripts/run.sh --config config.json run
```

`agent.backend: "host"` 时，`run` 返回 `awaiting_agent` 任务，由宿主通过同一套工具完成。
导出任务不等于完成研究。[Agent 工作流与工具契约](docs/agent-workflow.md)。

**想用独立 API 固定流程？** 明确设置 `workflow.mode: "standalone"`，通过本地
`configure-model` 向导配置 `llm.backend: "api"`。未填写 `workflow` 的旧配置继续使用
该兼容流程；旧的 Codex／Claude 仅模型调用后端也保留。
[Standalone 后端与安全输入凭据](docs/model-backends.md#standalone-compatibility-mode)。

Windows 将 `bash scripts/run.sh` 换成 `./scripts/run.ps1`。即使不发邮件，Agent 与 API
真实运行仍消耗账户用量，并可能收费。证据不足或校验失败时，不会生成成功的研究报告。

### 选择投递与调度方式

先检查真实报告。直接使用 SMTP 时，配置后运行 `run --send`；自动运行需持续运行
`schedule --send`，或由外部定时器每分钟调用 `tick --send`。
使用获授权的已连接邮件工具时，运行 `run --prepare-connector`，用 `begin-send` 领取
不可变消息，通过工具发送一次，再用 `confirm-sent` 写入已确认的服务商回执。
准备消息本身不会发送邮件。Agent 模式也支持 `tick --prepare-connector` 与
`schedule --prepare-connector`；实际外部邮件工具调用和回执仍由宿主安排。
Standalone 模式用 `run` 准备。[模型后端与投递流程](docs/model-backends.md)。

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

Python 包与命令 `paper-tracker` / `literature-digest` 保留原名，兼容已有安装。

## 主要原图、六段精读与研究展望

新建 Agent 订阅会选择许可允许再发布的主要原图，配中文解读、准确图号和来源，
通过 CID 内嵌邮件。逐篇内容按“问题与设计、科学问题、方法链（实验或模型方法）、
结果与亮点、局限性、有何启发”六段组织；结尾汇总本期论文并提出可验证的新 idea。
已有图片关闭设置保持不变；已发邮件要增订时，创建保留原始记录的关联修订任务。
[原图工作流](docs/original-figures.md#中文) · [研究展望](docs/research-outlook_中文.md)。
