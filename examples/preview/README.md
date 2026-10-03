# Smart Paper Tracker · Offline demo / 离线演示

[English README](../../README.md) · [中文说明](../../README_中文.md)

## English

A reproducible two-paper demonstration of the complete report layout: a research
overview, four source-anchored blocks per paper, topic sections and one global
numbered bibliography. HTML, text and JSON are generated from the same fixture.

**Every paper, author, journal, date, method, data point and result is invented.**
These files illustrate the product; they are not retrieved literature or scientific
evidence. Source links use the reserved example.org domain and do not lead to
actual publications. No model, source API, SMTP server or delivery database is used.

### Explore the prepared files

- English: [plain text](demo.en.txt) · [HTML](demo.en.html) · [JSON audit](demo.en.json)
- Chinese: [plain text](demo.zh-CN.txt) · [HTML](demo.zh-CN.html) · [JSON audit](demo.zh-CN.json)

GitHub can display the text and JSON directly. For the HTML layout, download
`demo.en.html` or `demo.zh-CN.html` and open it locally in a browser. The pages are
self-contained and load no external images, fonts or scripts.

### Run it yourself

From the repository root, using Python 3.11+ on Linux, macOS or WSL:

```sh
python3 -m literature_digest --config config.example.json preview --language en
python3 -m literature_digest --config config.example.json preview --language zh-CN
```

No installation or secrets required. If installed with `python -m pip install .`,
the equivalent command is `paper-tracker --config config.example.json preview
--language en`. `literature-digest` remains a compatible command alias.

The command prints a JSON array containing the generated paths and these facts:

```json
{
  "status": "demo_preview",
  "synthetic": true,
  "language": "en",
  "paper_count": 2,
  "network_used": false,
  "state_changed": false,
  "mail_sent": false
}
```

This is an excerpt; the full response also includes `paths` and `notice`. Output
files are `output/demo.en.{html,txt,json}` and `output/demo.zh-CN.{html,txt,json}`.
The paths are resolved relative to the configuration file. Repeated runs overwrite
only the same demo files with identical content for the same configuration.

### What to look for

1. **Research overview:** sentences cite the two shared numbered references.
2. **Paper reviews:** Core highlights, Scientific question, Experimental or model
   methods, and Main results. Supporting excerpts point to the synthetic source.
3. **Evidence JSON:** `meta.synthetic` is `true`, `meta.retrieved` is `0`, and each
   paper preserves the hand-authored source text and claim-level evidence anchors.
4. **One bibliography:** references `[1]` and `[2]` remain consistent across topics.

The fixed demo covers forest volatile emissions and remote-sensing tree-species
mapping. Live configuration topics do not alter these fixtures. To use your own
research topics, run `paper-tracker init`, review `validate`, then `run` for actual
retrieval. Real summaries need an enabled model; email needs SMTP plus `--send`.
See the [full setup guide](../../docs/user-guide.md#quickstart).

## 中文

这是一套可重复生成的两篇论文演示，展示完整简报结构：综述导读、每篇论文的四个
解读栏目、主题分组，以及统一编号的参考文献。HTML、纯文本和 JSON 来自同一组数据。

**所有论文、作者、期刊、日期、方法、数据和结果都是虚构的。** 演示只用于理解产品，
不能作为真实科研证据。原文链接使用保留域名 example.org，不对应真实论文。
整个流程不调用检索 API、模型或 SMTP，也不访问投递数据库。

### 查看成品

- 中文：[纯文本](demo.zh-CN.txt) · [HTML](demo.zh-CN.html) · [JSON 审计](demo.zh-CN.json)
- 英文：[纯文本](demo.en.txt) · [HTML](demo.en.html) · [JSON 审计](demo.en.json)

GitHub 可以直接阅读文本与 JSON。查看完整排版时，下载 HTML 并在本地浏览器打开。
页面为自包含文件，不加载外部图片、字体或脚本。

### 本地运行

在仓库根目录使用 Python 3.11+，操作系统为 Linux、macOS 或 WSL：

```sh
python3 -m literature_digest --config config.example.json preview --language zh-CN
python3 -m literature_digest --config config.example.json preview --language en
```

无需安装依赖或填写凭据。安装项目后，也可以使用 `paper-tracker` 命令；旧命令
`literature-digest` 继续可用。命令会返回输出路径、`paper_count: 2`、
`synthetic: true`，以及网络、状态变更、发件均为 `false` 的标记。

生成结果位于 `output/demo.zh-CN.{html,txt,json}` 和 `output/demo.en.{html,txt,json}`。
路径以配置文件为基准；使用相同配置重复执行，只会用相同内容覆盖对应的演示文件。

### 建议检查的细节

1. 综述导读的每条陈述带有统一的参考文献编号。
2. 每篇论文只有四个解读栏目：核心亮点、科学问题、实验或模型方法、主要结果。
3. JSON 中 `meta.synthetic` 为 `true`、`meta.retrieved` 为 `0`；每篇论文保留合成源文
   和逐条证据片段，方便核对来源锚点。
4. 不同主题共用 `[1]`、`[2]` 两个编号，不重复生成参考文献列表。

固定演示主题是森林挥发物排放和遥感树种识别，不会随真实配置的研究方向变化。
要使用自己的主题，先运行 `paper-tracker init`，检查 `validate`，再用 `run` 检索。
真实模型解读和邮件发送需要额外配置。详见[中文设置说明](../../README_中文.md)。
