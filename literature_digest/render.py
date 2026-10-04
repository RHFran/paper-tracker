"""Readable bilingual text and conservative, self-contained HTML email rendering."""
from __future__ import annotations

import ipaddress
import re
from html import escape
from urllib.parse import urlsplit

from .analysis import (FIELDS, compose_overview, is_chinese, output_language,
                       reference_map, unique_papers, validate_analysis, validate_overview)
from .models import TRACKS
from .outlook import IDEA_FIELDS, checked_outlook
from .perspective import checked_perspective
from .sources import _reuse_license

LABELS = {
    "zh": {
        "title": "科研文献日报", "eyebrow": "SUPER PAPER RADAR / RESEARCH BRIEF",
        "overview": "综述导读", "papers": "逐篇精读", "references": "参考文献",
        "highlights": "核心亮点", "question": "科学问题", "methods": "实验或模型方法",
        "findings": "主要结果",
        "authors": "作者", "published": "线上发表", "read": "论文原文", "fulltext": "开放全文",
        "abstract": "摘要（原文）", "discovery": "检索线索", "abstract_level": "摘要证据",
        "fulltext_level": "全文证据", "metadata_level": "书目信息", "figure": "论文图示",
        "figure_source": "查看原始图示", "source": "来源", "license": "许可", "attribution": "署名",
        "records": "检索记录", "selected": "本期论文", "topics": "研究主题",
        "empty": "本期未检出符合条件的新增论文。", "empty_topic": "本期无新增论文。",
        "failure": "检索失败或不完整：不能判断是否有新论文。未发送邮件，未推进成功检查点。",
        "window": "发表日期范围", "deferred": "篇候选因本期篇数上限暂缓",
        "footer": "范围与方法：仅收录已核实线上发表日期的文献；日精度边界保留标记。公开来源覆盖有限，期刊记录不等于已核实同行评审。",
        "audit": "逐条证据与检索记录保存在本地审计记录中。引文锚点核对仅验证出处，模型概括仍需结合原文判断。",
        "other": "其他研究", "preprint": "预印本", "intro": "本期收录 {count} 篇新近文献，涵盖{topics}。",
        "extracts": "以下摘取经来源锚点核对的主要发现。",
        "demo": "合成演示：所有论文、作者、数据与研究结论均为测试夹具，不是真实文献。",
        "demo_records": "演示记录", "demo_evidence": "合成夹具文本", "demo_footer": "合成演示仅用于核对版式、功能与引文编号。",
    },
    "en": {
        "title": "Research Literature Digest", "eyebrow": "SUPER PAPER RADAR / RESEARCH BRIEF",
        "overview": "Research overview", "papers": "Paper-by-paper review", "references": "References",
        "highlights": "Core highlights", "question": "Scientific question", "methods": "Experimental or model methods",
        "findings": "Main results",
        "authors": "Authors", "published": "Published online", "read": "Read paper", "fulltext": "Open full text",
        "abstract": "Abstract (source text)", "discovery": "Discovery record", "abstract_level": "Abstract evidence",
        "fulltext_level": "Full-text evidence", "metadata_level": "Bibliographic record", "figure": "Paper figure",
        "figure_source": "View original figure", "source": "Source", "license": "License", "attribution": "Attribution",
        "records": "Records retrieved", "selected": "Papers selected", "topics": "Research topics",
        "empty": "No new papers matched the current sources and filters.", "empty_topic": "No new papers in this topic.",
        "failure": "Retrieval failed or was incomplete; new-paper availability is unknown. No email was sent and the success checkpoint was not advanced.",
        "window": "Publication window", "deferred": "additional candidates deferred by the issue limit",
        "footer": "Scope and methods: verified online publication dates only; date-only window boundaries are flagged. Public-source coverage is limited, and journal indexing does not establish peer-review status.",
        "audit": "Claim-level evidence and retrieval records are saved in the local audit record. Anchor matching checks provenance; model interpretations still need source review.",
        "other": "Other research", "preprint": "Preprint", "intro": "This issue includes {count} recent papers covering {topics}.",
        "extracts": "Selected source-anchored findings are highlighted below.",
        "demo": "SYNTHETIC DEMO: all papers, authors, data and research claims are test fixtures, not real publications.",
        "demo_records": "Demo records", "demo_evidence": "Synthetic fixture text", "demo_footer": "Synthetic demonstration for layout, functionality and citation numbering only.",
    },
}

DEFAULT_ENGLISH_TOPICS = {
    "bvoc": "Biogenic volatile organic compounds (BVOCs)",
    "tree_species": "Remote sensing of tree species",
}
# These are established public scholarly image hosts. User-controlled domains and
# IP literals are intentionally not accepted for remote email image embedding.
TRUSTED_IMAGE_HOSTS = frozenset({
    "cdn.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov",
    "europepmc.org", "www.europepmc.org", "www.ebi.ac.uk", "arxiv.org", "export.arxiv.org",
})


def safe_link(url):
    if not isinstance(url, str) or not url or re.search(r"[\x00-\x20\x7f\\]", url):
        return ""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return ""
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid")):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return url
    except ValueError:
        return ""


def safe_image_url(url):
    """Conservative public-host allowlist, independent of publisher-supplied HTML."""
    if not safe_link(url):
        return ""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname.lower() not in TRUSTED_IMAGE_HOSTS
                or parsed.port not in {None, 443}):
            return ""
        return url
    except ValueError:
        return ""


def _link(url, label, style="color:#17614d;text-decoration:none;font-weight:600"):
    safe = safe_link(url)
    return '<a href="' + escape(safe, quote=True) + '" style="' + style + '">' + escape(str(label)) + '</a>' if safe else escape(str(label))


def _topic_groups(papers, config, labels, language):
    configured = config.get("topics")
    topics = []
    if isinstance(configured, list):
        for topic in configured:
            if not isinstance(topic, dict) or not topic.get("id"):
                continue
            name = topic.get("name") or topic["id"]
            if isinstance(name, dict):
                name = name.get(language) or name.get("en") or name.get("zh-CN") or topic["id"]
            topics.append((str(topic["id"]), str(name)))
    else:
        topics = [(key, title if is_chinese(language) else DEFAULT_ENGLISH_TOPICS.get(key, title))
                  for key, title in TRACKS.items()]
    known = {key for key, _ in topics}
    for paper in papers:
        for track in paper.tracks:
            if track not in known:
                topics.append((track, track)); known.add(track)
    if any(not p.tracks for p in papers):
        topics.append(("_other", labels["other"]))
    return [(key, title, [p for p in papers if key in p.tracks or (key == "_other" and not p.tracks)])
            for key, title in topics]


def _valid_fields(paper, language, allow_synthetic=False):
    analysis = paper.analysis or {}
    if analysis.get("mode") not in ({"llm_grounded", "synthetic_demo"} if allow_synthetic else {"llm_grounded"}):
        return {}
    try:
        return validate_analysis(analysis.get("fields"), paper.evidence, language)
    except ValueError:
        return {}


def _checked_overview(papers, config, overview, language):
    if overview is None:
        # Rendering never calls a model or a network service.
        return compose_overview(papers, {**config, "llm": {"enabled": False}}, None)
    try:
        if not isinstance(overview, dict) or overview.get("references") != reference_map(papers):
            raise ValueError("Reference map does not match this issue")
        if not overview.get("paragraphs"):
            return {**overview, "paragraphs": []}
        paragraphs = validate_overview({"paragraphs": overview["paragraphs"]}, papers, language)
        return {**overview, "paragraphs": paragraphs}
    except (ValueError, TypeError, KeyError):
        # Reject a tampered/stale introduction rather than rendering unsupported claims.
        return compose_overview(papers, {**config, "llm": {"enabled": False}}, None)


def _paper_sections(paper, fields, labels, language, allow_synthetic=False):
    perspective = checked_perspective(paper, language, allow_synthetic=allow_synthetic)
    if perspective is None:
        return [(key, labels[key], fields.get(key, [])) for key in ("highlights", "question", "methods", "findings")]
    zh = is_chinese(language)
    titles = (["问题与设计", "科学问题", "方法链", "结果与亮点", "局限性", "有何启发"] if zh else
              ["Problem and design", "Scientific question", "Method chain", "Results and highlights", "Limitations", "Research implications"])
    results, seen = [], set()
    for claim in fields.get("findings", []) + fields.get("highlights", []):
        if claim["text"] not in seen:
            results.append(claim)
            seen.add(claim["text"])
    return list(zip(("design_logic", "question", "methods", "findings", "limitations", "inspiration"), titles,
                    (perspective["design_logic"], fields.get("question", []), fields.get("methods", []),
                     results, perspective["limitations"], perspective["inspiration"])))


def _citation_html(citations):
    links = ['<a href="#ref-' + str(c["ref"]) + '" style="color:#17614d;text-decoration:none">' + str(c["ref"]) + '</a>'
             for c in citations]
    return '<sup style="font-size:10px;line-height:0;vertical-align:super">' + ','.join(links) + '</sup>'


def _excerpt(text, limit=1400):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;，；") + "…"


def _figures(paper, config, delivery="remote"):
    options = config.get("images", {})
    mode = options.get("mode", "off") if isinstance(options, dict) else str(options)
    if mode not in {"links", "embed"}:
        return []
    limit = options.get("max_per_paper", 2) if isinstance(options, dict) else 2
    try:
        limit = min(10, max(0, int(limit)))
    except (ValueError, TypeError):
        limit = 2
    result = []
    for figure in getattr(paper, "figures", []) or []:
        if not isinstance(figure, dict):
            continue
        source_url = safe_link(figure.get("source_url", ""))
        image_url = safe_link(figure.get("url", ""))
        if not source_url and not image_url:
            continue
        attribution, license_value = figure.get("attribution"), figure.get("license")
        explicit_rights = (figure.get("license_scope") == "figure"
                           and isinstance(attribution, str) and bool(attribution.strip())
                           and isinstance(license_value, str) and _reuse_license(license_value)
                           and bool(source_url))
        verified_original = (figure.get("verified_original") is True
                             and figure.get("provenance", {}).get("license_evidence_verified") is True
                             and isinstance(figure.get("asset_sha256"), str)
                             and re.fullmatch(r"[a-f0-9]{64}", figure["asset_sha256"])
                             and figure.get("content_id") == "figure-" + figure["asset_sha256"] + "@super-paper-radar")
        embed = (safe_image_url(figure.get("url", ""))
                 if mode == "embed" and figure.get("embed_allowed") is True and (explicit_rights or verified_original) else "")
        if embed and verified_original and delivery == "inline":
            embed = "cid:" + figure["content_id"]
        result.append({**figure, "source_url": source_url or image_url, "embed": embed})
        if len(result) >= limit:
            break
    return result if limit else []


def _reference_text(number, paper):
    authors = ", ".join(paper.authors[:6])
    if len(paper.authors) > 6:
        authors += " et al."
    parts = [authors, paper.title, paper.journal or paper.source, paper.publication_date]
    citation = ". ".join(str(part).rstrip(".") for part in parts if part) + "."
    doi = safe_link("https://doi.org/" + paper.doi) if paper.doi else ""
    link = doi or safe_link(paper.url)
    return f"{number}. {citation}" + (" " + link if link else "")



def _reference_downloads(meta, language):
    """Only safe sibling filenames in local HTML; mail has no file: links."""
    exports = meta.get("reference_exports", [])
    files = []
    for item in exports if isinstance(exports, list) else []:
        if not isinstance(item, dict):
            continue
        filename, extension = item.get("filename", ""), item.get("format")
        if extension in {"ris", "bib"} and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\." + extension, filename):
            files.append((filename, "RIS" if extension == "ris" else "BibTeX"))
    if not files:
        return [], ""
    zh = is_chinese(language)
    title = "导入文献管理器" if zh else "Import into your reference manager"
    instructions = ("RIS 适用于 Zotero / EndNote；BibTeX 适用于 Zotero。下载后在软件中选择文件导入；是否可双击打开取决于本机文件关联。" if zh else
                    "Use RIS for Zotero / EndNote, or BibTeX for Zotero. Download, then use File → Import in your app. Opening the file directly depends on your local file associations.")
    if meta.get("reference_delivery") == "attachments":
        action = "本邮件已附上 " if zh else "Attached to this email: "
        action += ", ".join(filename for filename, _ in files)
        actions = escape(action)
        lines = [title, instructions, action]
    else:
        actions = " &nbsp; · &nbsp; ".join('<a download href="' + escape(filename, quote=True) + '" style="color:#315d40">' + label + ' ↓</a>' for filename, label in files)
        lines = [title, instructions] + [label + ": " + filename for filename, label in files]
    if meta.get("demo"):
        warning = "仅含虚构演示记录，请勿作为真实文献导入。" if zh else "Contains invented demo records only; do not import as real research."
        lines.append(warning)
        instructions += " " + warning
    html = ('<tr><td style="padding:20px 36px;background:#eef5e7;border-top:1px solid #dfe6dc">'
            '<h2 style="margin:0 0 10px;font-size:17px;color:#173f35">' + escape(title) + '</h2>'
            '<p style="margin:0 0 12px;font-size:12px;line-height:1.7;color:#526153">' + escape(instructions) + '</p>'
            '<p style="margin:0;font-size:12px;overflow-wrap:anywhere">' + actions + '</p></td></tr>')
    return lines, html

def _outlook_blocks(outlook, language):
    """Render the source-grounded closing argument and visibly prospective ideas."""
    zh = is_chinese(language)
    labels = ({"title": "本期总结与研究启发", "questions": "仍待解决的问题",
               "ideas": "值得验证的研究设想", "basis": "论文依据", "hypothesis": "可检验假设",
               "experiment": "实验设计", "validation": "验证与反证", "expected_value": "预期价值"}
              if zh else
              {"title": "Closing synthesis and research outlook", "questions": "Open questions",
               "ideas": "Research ideas to test", "basis": "Evidence basis", "hypothesis": "Testable hypothesis",
               "experiment": "Experiment design", "validation": "Validation and falsification", "expected_value": "Expected value"})
    lines = ["", labels["title"]]
    html = ['<tr><td style="padding:30px 36px;background:#f4f7ef;border-top:2px solid #b0c573">'
            '<h2 style="margin:0 0 20px;color:#173f35;font-size:22px;font-family:Georgia,serif">'
            + escape(labels["title"]) + '</h2>']

    def cited(statements):
        text, fragments = [], []
        for item in statements:
            refs = ",".join(str(c["ref"]) for c in item["citations"])
            text.append(item["text"] + " [" + refs + "]")
            fragments.append(escape(item["text"]) + _citation_html(item["citations"]))
        return " ".join(text), " ".join(fragments)

    for paragraph in outlook["synthesis"]["paragraphs"]:
        text, fragment = cited(paragraph["sentences"])
        lines += [text, ""]
        html.append('<p style="margin:0 0 14px;font-size:15px;line-height:1.9;color:#2d4238">' + fragment + '</p>')
    lines.append(labels["questions"])
    html.append('<h3 style="margin:22px 0 12px;font-size:17px;color:#173f35">' + escape(labels["questions"]) + '</h3><ul style="padding-left:20px">')
    for question in outlook["open_questions"]:
        text, fragment = cited([question])
        lines.append("- " + text)
        html.append('<li style="margin:0 0 10px;font-size:14px;line-height:1.8">' + fragment + '</li>')
    html.append('</ul><h3 style="margin:24px 0 14px;font-size:17px;color:#173f35">' + escape(labels["ideas"]) + '</h3>')
    lines += ["", labels["ideas"]]
    for index, idea in enumerate(outlook["ideas"], 1):
        lines += ["", str(index) + ". " + idea["title"]]
        html.append('<div style="margin:0 0 18px;padding:18px;background:#fff;border:1px solid #dfe6dc;border-radius:6px">'
                    '<h4 style="margin:0 0 12px;font-size:16px;line-height:1.6;color:#173f35">'
                    + str(index) + '. ' + escape(idea["title"]) + '</h4>')
        text, fragment = cited(idea["basis"])
        lines.append(labels["basis"] + ": " + text)
        html.append('<p style="margin:0 0 10px;font-size:13px;line-height:1.8"><strong>'
                    + escape(labels["basis"]) + ':</strong> ' + fragment + '</p>')
        for field in IDEA_FIELDS:
            lines.append(labels[field] + ": " + idea[field])
            html.append('<p style="margin:0 0 10px;font-size:13px;line-height:1.8"><strong>'
                        + escape(labels[field]) + ':</strong> ' + escape(idea[field]) + '</p>')
        html.append('</div>')
    html.append('</td></tr>')
    return lines, "".join(html)


def render(papers, meta, config=None, overview=None, outlook=None):
    """Return plain text and email-client-friendly HTML, with one global bibliography."""
    config = config or {}
    language = output_language(config)
    labels = dict(LABELS["zh" if is_chinese(language) else "en"])
    coverage_notes = meta.get("coverage_notes")
    has_coverage_notes = isinstance(coverage_notes, str) and bool(coverage_notes.strip())
    if meta.get("partial_coverage"):
        labels["empty"] = "本次有限检索未发现符合条件的新增论文，不能据此判断完整范围内没有新论文。" if is_chinese(language) else "No matching new papers were found in this bounded retrieval; this does not establish that none exist in the full window."
        if has_coverage_notes:
            labels["empty_topic"] = ("本期该主题未纳入正文论文；检索覆盖与局限见上方说明。" if is_chinese(language) else
                                     "No papers from this topic were included in this issue; see the search coverage and limitations above.")
        else:
            labels["empty_topic"] = ("本次有限检索中，该主题未纳入正文论文，不能据此判断没有新增论文。" if is_chinese(language) else
                                     "No papers from this topic were included in this bounded retrieval; this does not establish that no new papers exist.")
        labels["footer"] = ("范围与方法：本次检索受配置的分页/候选上限限制，来源覆盖不完整；已收录文献日期与证据锚点按程序规则核对。" if is_chinese(language) else
                            "Scope and methods: retrieval was limited by configured page/candidate bounds and source coverage is incomplete. Included publication dates and evidence anchors were checked by the program.")
    if meta.get("demo"):
        labels["records"] = labels["demo_records"]
        labels["footer"] = labels["demo_footer"]
        if meta.get("title"):
            labels["title"] = str(meta["title"])
    papers = unique_papers(papers)
    numbers = {paper.key: index for index, paper in enumerate(papers, 1)}
    groups = _topic_groups(papers, config, labels, language)
    overview = _checked_overview(papers, config, overview, language)
    local_date, timezone = str(meta.get("local_date", "")), str(meta.get("timezone", ""))
    window_start = str(meta.get("publication_start") or meta.get("window_start", ""))
    window_end = str(meta.get("publication_end") or meta.get("local_date") or meta.get("window_end", ""))
    window = f'{labels["window"]}: {window_start} – {window_end}'
    date_line = local_date + (" · " + timezone if timezone else "")
    lines = [labels["title"] + " | " + date_line, window, ""]
    body = []
    if meta.get("demo"):
        notice = str(meta.get("demo_notice") or labels["demo"])
        lines += [notice, ""]
        body.append('<tr><td style="padding:18px 36px;background:#fff0c5;color:#76531c;font-size:13px;line-height:1.7"><strong>' + escape(notice) + '</strong></td></tr>')

    if meta.get("partial_coverage"):
        notice = "有限检索：结果并非该时段的完整文献清单。" if is_chinese(language) else "Bounded retrieval: this is not an exhaustive bibliography for the window."
        lines += [notice, ""]
        body.append('<tr><td style="padding:18px 36px;background:#fff0c5;color:#76531c;font-size:13px">' + escape(notice) + '</td></tr>')
    if has_coverage_notes:
        title = "检索覆盖与局限" if is_chinese(language) else "Search coverage and limitations"
        lines += [title, coverage_notes, ""]
        # Notes are plain text, never publisher HTML or Markdown. Preserve the
        # disclosure and visible URLs without interpreting untrusted markup.
        note_html = escape(coverage_notes).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br />")
        body.append('<tr><td style="padding:18px 36px;background:#fff8e6;color:#76531c">'
                    '<h2 style="margin:0 0 8px;font-size:15px">' + escape(title) + '</h2>'
                    '<p style="margin:0;font-size:13px;line-height:1.7;overflow-wrap:anywhere">'
                    + note_html + '</p></td></tr>')
    if meta.get("failure"):
        lines.append(labels["failure"])
        lines.extend("- " + str(error) for error in meta.get("errors", []))
        body.append('<tr><td style="padding:28px 36px;background:#fff1ed;color:#923d29"><strong>' + escape(labels["failure"]) + '</strong>')
        body.append('<ul>' + ''.join('<li>' + escape(str(e)) + '</li>' for e in meta.get("errors", [])) + '</ul></td></tr>')
    else:
        record_count = meta.get("fixture_count", len(papers)) if meta.get("demo") else meta.get("retrieved", 0)
        stats = [(str(record_count), labels["records"]), (str(len(papers)), labels["selected"]),
                 (str(len(groups)), labels["topics"])]
        lines.append(" · ".join(value + " " + label for value, label in stats))
        body.append('<tr><td style="padding:24px 36px;border-bottom:1px solid #e1e7df"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>')
        for value, label in stats:
            body.append('<td width="33%" style="vertical-align:top"><div style="font-size:28px;font-weight:700;color:#173f35">' + escape(value) + '</div><div style="font-size:11px;color:#68766d;letter-spacing:.5px">' + escape(label) + '</div></td>')
        body.append('</tr></table></td></tr>')
        if meta.get("deferred"):
            message = str(meta["deferred"]) + " " + labels["deferred"]
            lines.append(message)
            body.append('<tr><td style="padding:12px 36px;color:#6a755f;font-size:12px">' + escape(message) + '</td></tr>')
        if not papers:
            lines += ["", labels["empty"]]
            body.append('<tr><td style="padding:38px 36px;font-size:17px">' + escape(labels["empty"]) + '</td></tr>')
        else:
            lines += ["", labels["overview"]]
            body.append('<tr><td style="padding:32px 36px 28px;background:#f7f9f3"><h2 style="margin:0 0 18px;color:#173f35;font-size:22px;font-family:Georgia,serif">' + escape(labels["overview"]) + '</h2>')
            paragraphs = overview.get("paragraphs", [])
            if not paragraphs:
                topic_names = ("、" if is_chinese(language) else "; ").join(title for _, title, group in groups if group)
                intro = labels["intro"].format(count=len(papers), topics=topic_names)
                lines.append(intro)
                body.append('<p style="margin:0;line-height:1.85;font-size:15px">' + escape(intro) + '</p>')
            else:
                for paragraph in paragraphs:
                    text_sentences, html_sentences = [], []
                    for sentence in paragraph["sentences"]:
                        refs = ",".join(str(c["ref"]) for c in sentence["citations"])
                        text_sentences.append(sentence["text"] + " [" + refs + "]")
                        html_sentences.append(escape(sentence["text"]) + _citation_html(sentence["citations"]))
                    lines += [" ".join(text_sentences), ""]
                    body.append('<p style="margin:0 0 14px;line-height:1.9;font-size:15px;color:#2d4238">' + ' '.join(html_sentences) + '</p>')
            body.append('</td></tr>')

    if papers and not meta.get("failure"):
        for topic_index, (_, title, group) in enumerate(groups, 1):
            lines += ["", title]
            body.append('<tr><td style="padding:30px 36px 16px;border-top:1px solid #e1e7df"><div style="font-size:10px;color:#71806e;letter-spacing:2px">' + f'{topic_index:02d}' + '</div><h2 style="margin:7px 0 0;font-size:21px;color:#173f35">' + escape(title) + '</h2></td></tr>')
            if not group:
                lines.append(labels["empty_topic"])
                body.append('<tr><td style="padding:0 36px 24px;color:#768173;font-size:13px">' + escape(labels["empty_topic"]) + '</td></tr>')
            for paper in group:
                number = numbers[paper.key]
                fields = _valid_fields(paper, language, allow_synthetic=bool(meta.get("demo")))
                has_claims = any(fields.values())
                level = labels["fulltext_level"] if paper.full_text else labels["abstract_level"] if paper.abstract else labels["metadata_level"]
                if meta.get("demo"):
                    level = labels["demo_evidence"]
                badges = [level] if has_claims else [labels["discovery"]]
                if "预印本" in paper.kind or "preprint" in paper.kind.lower():
                    badges.append(labels["preprint"])
                lines += ["", f"[{number}] {paper.title}", " · ".join(badges)]
                journal_date = " · ".join(value for value in [paper.journal or paper.source, paper.publication_date] if value)
                if journal_date:
                    lines.append(journal_date)
                if paper.authors:
                    authors = "; ".join(paper.authors[:8]) + (" et al." if len(paper.authors) > 8 else "")
                    lines.append(labels["authors"] + ": " + authors)
                else:
                    authors = ""
                body.append('<tr><td style="padding:0 24px 20px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #dfe6dc;background:#ffffff;border-radius:8px"><tr><td style="padding:24px">')
                body.append('<div style="font-size:10px;letter-spacing:.6px;color:#527257;margin-bottom:12px">' + escape(" · ".join(badges)) + '</div>')
                body.append('<h3 style="margin:0 0 10px;font-family:Georgia,serif;font-size:21px;line-height:1.4;color:#1c352b"><span style="color:#83926e;font-size:15px">' + f'{number:02d}' + '</span> ' + _link(paper.url, paper.title, "color:#1c352b;text-decoration:none") + '</h3>')
                body.append('<p style="margin:0 0 6px;font-size:12px;color:#53685b">' + escape(journal_date) + '</p>')
                if authors:
                    body.append('<p style="margin:0 0 18px;font-size:12px;color:#6c776d">' + escape(authors) + '</p>')
                # New agent reviews have exactly six sections; old reports retain their schema.
                for field, section_title, claims in _paper_sections(paper, fields, labels, language, allow_synthetic=bool(meta.get("demo"))):
                    if not claims:
                        continue
                    lines.append(section_title + ":")
                    background = "background:#f3f7ed;" if field == "highlights" else ""
                    body.append('<div style="margin:15px 0;padding:12px 14px;border-left:3px solid ' + ("#9eb85a" if field == "highlights" else "#dfe6dc") + ';' + background + '"><h4 style="margin:0 0 7px;font-size:12px;color:#49624b">' + escape(section_title) + '</h4>')
                    for claim in claims:
                        kind = ("作者说明" if claim.get("kind") == "reported" else "分析推论") if is_chinese(language) else ("Author-reported" if claim.get("kind") == "reported" else "Interpretation")
                        qualifier = "" if "kind" not in claim else kind + ": "
                        lines.append("- " + qualifier + claim["text"] + f" [{number}]")
                        badge = '<span style="font-size:10px;color:#71806e">' + escape(qualifier) + '</span>' if qualifier else ""
                        body.append('<p style="margin:5px 0;font-size:14px;line-height:1.8;color:#293d30">' + badge + escape(claim["text"]) + _citation_html([{"ref": number}]) + '</p>')
                    body.append('</div>')
                if not has_claims and paper.abstract:
                    abstract = _excerpt(paper.abstract)
                    lines += [labels["abstract"] + ":", abstract]
                    body.append('<div style="margin:16px 0"><h4 style="margin:0 0 8px;color:#49624b;font-size:12px">' + escape(labels["abstract"]) + '</h4><p style="font-size:14px;line-height:1.8;color:#46534a;margin:0">' + escape(abstract) + '</p></div>')
                for figure in _figures(paper, config, meta.get("figure_delivery", "remote")):
                    caption = str(figure.get("caption") or labels["figure"])
                    heading = str(figure.get("id") or labels["figure"])
                    explanation = str(figure.get("explanation") or "")
                    lines += [labels["figure"] + ": " + heading, caption]
                    if explanation:
                        lines.append(explanation)
                    lines.append(figure["source_url"])
                    body.append('<div style="margin:20px 0 14px;border-top:1px solid #e6ebdf;padding-top:16px">')
                    if not figure["embed"] and not figure.get("caption") and not explanation:
                        body.append(_link(figure["source_url"], labels["figure_source"]) + '</div>')
                        continue
                    if figure["embed"]:
                        body.append('<img src="' + escape(figure["embed"], quote=True) + '" alt="' + escape(caption, quote=True) + '" width="640" style="display:block;max-width:100%;width:100%;height:auto;border:0" />')
                    body.append('<p style="margin:9px 0 5px;font-size:12px;line-height:1.6;color:#63705f"><strong>' + escape(heading) + '</strong>' + (' · ' + escape(explanation) if explanation else ' · ' + escape(caption)) + '</p>')
                    rights = []
                    for key in ("license", "attribution"):
                        if figure.get(key):
                            rights.append(labels[key] + ": " + str(figure[key]))
                    if rights:
                        lines.append(" · ".join(rights))
                        body.append('<p style="margin:5px 0;font-size:10px;color:#788071">' + escape(" · ".join(rights)) + '</p>')
                    if safe_link(figure.get("license_url", "")):
                        lines.append("License evidence: " + figure["license_url"])
                    body.append(_link(figure["source_url"], labels["figure_source"]) + '</div>')
                actions = []
                for url, label in ((paper.url, labels["read"]), (paper.full_text_url, labels["fulltext"])):
                    if safe_link(url):
                        lines.append(label + ": " + url)
                        actions.append(_link(url, label + " ↗"))
                if actions:
                    body.append('<p style="margin:20px 0 0;padding-top:14px;border-top:1px solid #edf0e8;font-size:12px">' + ' &nbsp; · &nbsp; '.join(actions) + '</p>')
                body.append('</td></tr></table></td></tr>')

    if papers and not meta.get("failure"):
        closing = checked_outlook(outlook, papers, language, allow_synthetic=bool(meta.get("demo")))
        if closing:
            closing_lines, closing_html = _outlook_blocks(closing, language)
            lines.extend(closing_lines)
            body.append(closing_html)
        lines += ["", labels["references"]]
        body.append('<tr><td style="padding:28px 36px 30px;background:#f7f9f3;border-top:1px solid #dfe6dc"><h2 style="margin:0 0 17px;font-size:18px;color:#173f35">' + escape(labels["references"]) + '</h2>')
        for paper in papers:
            number = numbers[paper.key]
            citation = _reference_text(number, paper)
            lines.append(citation)
            doi_url = safe_link("https://doi.org/" + paper.doi) if paper.doi else ""
            source_url = doi_url or safe_link(paper.url)
            plain_citation = citation[:-len(source_url)].rstrip() if source_url and citation.endswith(source_url) else citation
            body.append('<p id="ref-' + str(number) + '" style="margin:0 0 13px;font-size:12px;line-height:1.7;color:#526153">' + escape(plain_citation) + (' ' + _link(source_url, "doi:" + paper.doi if doi_url else labels["source"]) if source_url else "") + '</p>')
        body.append('</td></tr>')
    if papers and not meta.get("failure"):
        reference_lines, reference_html = _reference_downloads(meta, language)
        lines += [""] + reference_lines if reference_lines else []
        body.append(reference_html)
    lines += ["", labels["footer"], labels["audit"]]
    body.append('<tr><td style="padding:24px 36px 30px;background:#edf1e8;font-size:10px;line-height:1.8;color:#76816f">' + escape(labels["footer"]) + '<br />' + escape(labels["audit"]) + '</td></tr>')
    html = ('<!doctype html><html lang="' + escape(language, quote=True) + '"><head><meta charset="utf-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1" /><title>' + escape(labels["title"]) + '</title></head>'
            '<body style="margin:0;padding:0;background:#edf0e9;font-family:Arial,Helvetica,\'Microsoft YaHei\',sans-serif;color:#233a2c;overflow-wrap:anywhere;word-wrap:break-word">'
            '<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;overflow:hidden;opacity:0">' + escape(labels["title"] + " · " + date_line) + '</div>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#edf0e9"><tr><td align="center" style="padding:24px 8px">'
            '<table role="presentation" width="760" cellpadding="0" cellspacing="0" style="width:100%;max-width:760px;background:#ffffff;border-collapse:separate;table-layout:fixed">'
            '<tr><td style="padding:34px 36px 30px;background:#173f35;color:#ffffff;border-bottom:5px solid #b0c573">'
            '<p style="margin:0 0 13px;font-size:10px;letter-spacing:2.3px;color:#c9d8bd">' + labels["eyebrow"] + '</p>'
            '<h1 style="margin:0 0 12px;font-family:Georgia,\'Microsoft YaHei\',serif;font-size:31px;line-height:1.3;font-weight:500">' + escape(labels["title"]) + '</h1>'
            '<p style="margin:0 0 8px;color:#d5dfd0;font-size:12px">' + escape(date_line) + '</p>'
            '<p style="margin:0;color:#acc6b4;font-size:11px">' + escape(window) + '</p></td></tr>'
            + ''.join(body) + '</table></td></tr></table></body></html>')
    return "\n".join(lines), html
