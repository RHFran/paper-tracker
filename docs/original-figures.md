# Main original paper figures

[Home](../README.md) · [Agent workflow](agent-workflow.md) · [中文](#中文)

The research agent chooses the important scientific figures after reading the
paper: normally a method/framework diagram and/or a key result. The scheduler
only wakes the agent. The program verifies source evidence, licenses and raster
bytes; it does not choose the first image, generate a substitute, or infer reuse
rights from open access.

New `init` and example agent configurations use `images.mode: "embed"`. Existing
configurations, including an explicit `off`, keep their previous behavior.
`links` retains figure links without downloading assets. `max_per_paper` bounds
selection (1–10). The agent may select fewer useful figures.

## Agent-selected manifest

After the paper has been retrieved and ingested, write a JSON object in the job's
workspace, then call the returned `tool_argv` with `figure --input FIGURE_JSON`.
One manifest describes one original figure:

```json
{
  "paper_key": "exact ingested key",
  "id": "Figure 5",
  "caption": "Exact original caption or a substantive contiguous excerpt",
  "explanation": "A useful explanation in the configured language",
  "source_url": "https://arxiv.org/html/ACTUAL_IDv1#ACTUAL_FIGURE_ANCHOR",
  "url": "https://arxiv.org/html/ACTUAL_IDv1/ACTUAL_IMAGE.png",
  "attribution": "Actual authors, title, version, figure number and unchanged-original credit",
  "license": "CC BY 4.0",
  "license_scope": "article",
  "license_url": "https://arxiv.org/abs/ACTUAL_IDv1",
  "license_evidence": "Exact visible license evidence",
  "rights_basis": "Explain why this grant covers the original figure; inspect third-party exclusions",
  "original": true,
  "omission_reason": ""
}
```

This is a shape example, not real evidence or a working image URL. Do not use
placeholders in a live job. The explanation should say what the figure shows,
why it matters and how it supports or limits the paper's findings. Preserve the
exact figure/panel number. The original English caption remains in plain text
and image alternative text; the HTML caption prioritizes the Chinese/configured
language interpretation, with compact attribution and a direct source link.

Embedding currently supports PNG/JPEG assets referenced by exact arXiv or PMC
article HTML pages. Source and license pages must identify the ingested paper;
explicit arXiv versions must agree. A bibliographic mention of an identifier does
not qualify. The source must actually reference the image and contain its quoted
caption. The declared Creative Commons grant must match an article-specific
rights link. Article-level grants are accepted only with an explicit agent
assessment that they cover the selected original and no third-party credit
excludes it. These checks establish provenance, not legal or scientific certainty.

CC BY and CC0 are supported for general reuse. `images.reuse_context:
"personal_noncommercial"` additionally permits an unchanged CC BY-NC-SA figure
for that explicitly noncommercial digest. This setting is a purpose declaration,
not a license override: preserve attribution and terms, do not republish those
assets in public/commercial demos, and comply with ShareAlike for adaptations.
Metadata CC0 (including arXiv API metadata) never grants paper-figure permission.

For unknown rights, unsuitable formats, failed retrieval or a third-party
exclusion, provide the exact source link and a truthful `omission_reason`; do not
supply a fake original or silently replace the figure. In a retrieval failure,
register the source as `license_scope: "unknown"` after recording the reason.
Detailed rights evidence stays in the private audit. The email retains a compact
source link rather than repetitive technical disclaimers.

## Frozen images and email

- Only publicly routable HTTPS destinations are fetched. Direct connections pin
  validated DNS addresses and retain TLS hostname checks. Every redirect is
  revalidated. Managed HTTPS-proxy retrieval is restricted to exact official
  source hosts; proxy bypass uses the direct pinned route.
- Pillow fully verifies and decodes PNG/JPEG after dimension and byte bounds.
  Assets are bounded to 4 MiB each, 12 MiB total and 30 unique images.
- Each image receives a content hash, a safe hash-derived filename and a stable
  Content-ID. Registration is recorded in the job ledger. Finalization freezes
  the actual bytes and rechecks asset integrity and HTML/CID correspondence.
- SMTP produces `multipart/related` under the HTML part; text and citation
  attachments remain available. Connector envelopes keep citation `attachments`
  and add `inline_images` with `filename`, `content_type`, `content_base64`,
  `content_id`, `sha256`, and `size_bytes`.
- For AgentMail, map those image fields to `filename`, `contentType`, `content`,
  `contentId`, and `contentDisposition: "inline"`. Pass `content_id` without angle
  brackets. Other connectors must genuinely support inline Content-ID files;
  do not claim attachment support from a successful text-only test.
- A connector lacking inline support can use the reviewed original HTTPS assets
  in a newly prepared compatible workflow. Never rewrite an immutable envelope
  after claim, silently omit its assets, or use data-URI images in email.

Local preview HTML uses verified original HTTPS URLs; email uses CID. Reading
clients may still hide images, so plain text includes the interpretation,
original caption, source and attribution. No program can guarantee all clients
will display HTML or images.

## Explicit revised editions

Never edit a sent job, receipt, source snapshot or envelope. For a user-requested
revision, use the same audience/state ledger and explicitly run:

```sh
python -m literature_digest --config revision-config.json agent-revise SENT_JOB_ID \
  --reason "Add original main figures and the requested closing synthesis" \
  --prepare-connector
```

This creates a distinct revision linked to the confirmed sent agent job, with a
new frozen contract and new current delivery date. It reuses hash-verified source
evidence and preserves the original publication window; it does not pretend to
repeat the literature search. Only papers from the original digest may appear.
An unresolved or unconfirmed original send cannot be revised. Add figure
registrations, submit and validate the revised research, finalize, review, then
use the normal one-shot claim/send/receipt workflow. Revision preparation never
sends mail. Repeating the same revision request reuses its identity.

Old frozen v3.0 `tool.py` launchers retain their version check. Do not edit them.
To inspect/resume a schema-1 job after upgrading, use the installed CLI with its
original frozen config and original job ID, or retain the matching v3.0 runtime.
Old jobs and explicit image opt-outs remain unchanged; new jobs use schema 2.

## 中文

- 默认新建订阅会尝试展示主要原图。Agent 阅读论文后选择方法框架或核心结果图，程序负责
  来源、图号、原图注、许可和图片字节的校验。已有 `images.mode: off` 不会被悄悄打开。
- 图旁写有用的中文解读，保留准确图号、作者署名、许可和原文链接；不把生成图冒充原图。
- arXiv 元数据 CC0 不等于论文图片授权。不能确认再发布许可时保留原文图链接；非商业
  NC-SA 原图仅用于明确声明的个人非商业摘要，不进入公开演示或商业分发。
- 邮件优先使用 CID 内嵌原图，避免依赖外部图片加载；HTML 和纯文本都保留来源与解释。
- 已发内容保持不变。用户明确要求补发时，用 `agent-revise` 创建关联旧期的新修订任务，
  正常校验、冻结并投递一次，不能改写旧邮件或清空去重记录。
