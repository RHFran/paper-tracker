<p align="center">
  <img src="docs/assets/logo.svg" width="104" height="104" alt="Smart Paper Tracker logo: a research paper with a tracking signal">
</p>
<h1 align="center">Smart Paper Tracker</h1>

<a id="chinese"></a>

我们相信，在知识爆炸、信息产生与传播的速度远超阅读与消化能力的时代，借助工具高效获取信息至关重要。我们应把宝贵的神经元留给更关键的信息，做出更重要的判断。

**你的研究方向 → 有证据的 AI 文献简报 → 按你的计划送达邮箱。**

真实简报需要你配置 LLM/API。Token 费用随模型、论文数量和证据文本长度变化；
离线演示不调用 API。

[English](README.md#english) · [中文](#chinese) · [HTML 演示](https://rhfran.github.io/smart-paper-tracker/) · [安装指南](docs/platform-setup_中文.md)

## 你会得到什么

- 一份研究综述，以及按核心亮点、科学问题、研究方法、主要结果组织的论文解读，
  共用一套编号参考文献。
- 来源链接、可匹配的短证据片段和可检查的 JSON 审计记录。
  重要解读仍需回到论文核实。
- 易读的 **HTML 和纯文本**，以及可导入 Zotero、EndNote 等工具的 **RIS / BibTeX** 文献文件。
- 不同主题按不同星期或指定日期运行，自定当地时间、时区、语言和收件邮箱。

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

> 使用项目自带的安装脚本安装 Smart Paper Tracker。帮我配置研究主题、LLM 服务、语言和
> 当地运行计划，先生成演示，再做一次真实预览。发送邮件或启动后台定时任务前，先让我确认。

Agent 需要能读取源码并执行命令的电脑环境。安装好 **Python 3.11+** 后，一条命令
即可创建 `.venv`、安装当前项目、保留已有配置并生成离线演示。
[Agent 与分平台操作说明](docs/platform-setup_中文.md)。

<a id="manual-setup-zh"></a>

## 也可以自己设置

下载或克隆项目，在项目目录打开终端，运行：

```sh
# Linux / macOS
bash scripts/setup.sh
```

```powershell
# Windows PowerShell
./scripts/setup.ps1
```

如果 PowerShell 阻止脚本运行，改用 `py -3 scripts/setup.py`，不需要修改执行策略。
安装脚本不会发送邮件，也不会安装定时服务。

**真实文献简报必须使用 LLM。** 新配置的交互安装会提供本地向导，选择服务商、
HTTPS 接口、模型，并隐藏输入 API key。可接入 OpenAI、DeepSeek、Qwen 等兼容服务。
只有明确确认后才把密钥保存到本地明文 `.env`；请保持文件私密，不要提交到仓库。
[模型配置与仅在当前进程使用凭据的方法](docs/platform-setup_中文.md)。
模型缺失或失败时，不会把纯元数据检索结果作为成功简报。

```sh
# Linux / macOS：为已有安装配置模型，再生成真实报告；不发邮件
bash scripts/run.sh --config config.json configure-model
bash scripts/run.sh --env-file .env run
```

Windows 将 `bash scripts/run.sh` 换成 `./scripts/run.ps1` 即可。检查报告后，如需发邮件再配置 SMTP。
`run` 会立即执行；要自动按时运行，必须持续运行 `schedule --send`，或者由外部定时器
每分钟调用 `tick --send`。[完整配置与调度说明](docs/user-guide_中文.md)。

## 进一步了解

- [中文完整指南](docs/user-guide_中文.md) · [English user guide](docs/user-guide.md)
- [Windows / Linux / macOS 与 Agent 安装](docs/platform-setup_中文.md)
- [部署示例](examples/README.md) · [验证范围](VALIDATION.md)
- [贡献指南](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [MIT 许可证](LICENSE) · [更新记录](CHANGELOG.md)

这是自托管软件，需要你提供运行主机、模型服务，以及发邮件所需的 SMTP 服务。
模型调用可能收费，也会把选定论文证据发送给模型提供方。原文图只有在符合支持的转载
权限时才嵌入，否则使用来源链接。SMTP 接受邮件不等于保证送达收件箱。
