from __future__ import annotations

from datetime import date, datetime, timezone
from html.parser import HTMLParser
import ipaddress
import re
import unicodedata
from urllib.parse import quote, urlencode, urlsplit
import xml.etree.ElementTree as ET

from .http import RetrievalError
from .models import Paper, clean, normalize_arxiv_id, normalize_doi, normalize_pmcid, parse_date_parts
from .relevance import BVOC_QUERIES, TREE_QUERIES

CROSSREF = "https://api.crossref.org/works"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
ARXIV = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
EPMC_QUERIES = {
    "bvoc": '(TITLE_ABS:BVOC OR TITLE_ABS:BVOCs OR TITLE_ABS:"biogenic volatile organic compounds" OR TITLE_ABS:"plant volatile organic compounds" OR ((TITLE_ABS:isoprene OR TITLE_ABS:monoterpene* OR TITLE_ABS:sesquiterpene* OR TITLE_ABS:"volatile organic compounds") AND (TITLE_ABS:emission* OR TITLE_ABS:flux* OR TITLE_ABS:volatile*) AND (TITLE_ABS:forest* OR TITLE_ABS:tree* OR TITLE_ABS:vegetation OR TITLE_ABS:plant* OR TITLE_ABS:soil OR TITLE_ABS:microbial OR TITLE_ABS:marine)))',
    "tree_species": '(TITLE_ABS:"tree species" OR TITLE_ABS:"forest species") AND (TITLE_ABS:"remote sensing" OR TITLE_ABS:hyperspectral OR TITLE_ABS:multispectral OR TITLE_ABS:LiDAR OR TITLE_ABS:"laser scanning" OR TITLE_ABS:UAV OR TITLE_ABS:satellite OR TITLE_ABS:SAR) AND (TITLE_ABS:classif* OR TITLE_ABS:identif* OR TITLE_ABS:map* OR TITLE_ABS:discriminat*)',
}



def _source_queries(config, source):
    """Configured values are literal search text, never provider query syntax."""
    topics = config.get("topics")
    if topics:
        return [(topic["id"], query) for topic in topics
                for query in topic.get("source_queries", {}).get(source, topic.get("queries", []))]
    if source == "europepmc":
        return list(EPMC_QUERIES.items())
    return [("bvoc", query) for query in BVOC_QUERIES] + [("tree_species", query) for query in TREE_QUERIES]


def _literal_query(value, field):
    # Removing syntax punctuation avoids relying on inconsistent escape handling
    # in provider query parsers. The full Unicode words remain a quoted phrase.
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value), re.UNICODE)
    if not words:
        raise ValueError("检索短语必须包含文字或数字")
    return field + ':"' + " ".join(words) + '"'


def _arxiv_query(value):
    """Require literal terms to co-occur, rather than one long exact phrase.

    Provider syntax in user text is never executable: punctuation is removed
    and even words such as OR remain quoted search terms. Separate configured
    queries supply the union of alternative word combinations.
    """
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value), re.UNICODE)
    if not words:
        raise ValueError("检索短语必须包含文字或数字")
    return " AND ".join('all:"' + word + '"' for word in dict.fromkeys(words))


def _date_window(start, end):
    left, right = date.fromisoformat(start), date.fromisoformat(end)
    if left > right:
        raise ValueError("检索起始日期不能晚于结束日期")
    return left, right


def _crossref_relations(value):
    relations, aliases = [], []
    for kind, items in (value or {}).items():
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            identifier, id_type = item.get("id", ""), item.get("id-type", "")
            if not identifier:
                continue
            if id_type.lower() == "doi":
                identifier = normalize_doi(identifier)
            relations.append({"type": kind, "id": identifier, "id_type": id_type, "source": "crossref"})
            if kind == "is-identical-to" and id_type.lower() == "doi":
                aliases.append("doi:" + identifier)
    return relations, aliases


def provenance(source, params, api_url):
    return {"source": source, "api_url": api_url, "query": params, "retrieved_at": datetime.now(timezone.utc).isoformat()}


def _source_report(source, papers, queries, config):
    truncated = any(query.get("truncated", False) for query in queries)
    report = {"source": source, "complete": all(query["complete"] for query in queries),
              "records_before_dedup": len(papers), "queries": queries,
              "retrieval_policy": config.get("retrieval_policy", "complete"), "truncated": truncated}
    if truncated:
        report["coverage_note"] = ("Bounded query retrieval: remaining source results were not fetched. "
                                   "Results are not an exhaustive literature review.")
    return report


def _bounded_query(config, details):
    return {**details, "complete": False, "truncated": True,
            "reason": "configured_max_pages_per_query", "page_limit": config["max_pages_per_query"]}


def crossref_paper(x, context) -> Paper:
    title = clean(" ".join(x.get("title", [])))
    doi = normalize_doi(x.get("DOI"))
    date_label, publication = "", ""
    for key in ("posted", "published-online", "published-print", "published", "issued"):
        if parse_date_parts(x.get(key, {})):
            date_label, publication = key, parse_date_parts(x[key])
            break
    item_type = x.get("type", "")
    relations, aliases = _crossref_relations(x.get("relation"))
    kind = "预印本/posted-content；未确认同行评审" if item_type == "posted-content" else "期刊记录；同行评审状态未由元数据核实" if item_type == "journal-article" else f"{item_type or '未知发表类型'}；同行评审状态未核实"
    return Paper(title=title, source_id=doi or x.get("URL", title), source="crossref", url=x.get("URL") or ("https://doi.org/" + quote(doi, safe="/") if doi else CROSSREF), doi=doi,
        abstract=clean(x.get("abstract")), authors=[clean(a.get("name") or " ".join([a.get("given") or "", a.get("family") or ""])) for a in (x.get("author") or []) if isinstance(a, dict)],
        author_details=[{"given": clean(a.get("given")), "family": clean(a.get("family")), "literal": clean(a.get("name"))} for a in (x.get("author") or []) if isinstance(a, dict)],
        journal=clean(" ".join(x.get("container-title", []))), publication_date=publication, publication_date_label=date_label,
        index_date=x.get("indexed", {}).get("date-time", ""), kind=kind, relations=relations, source_aliases=aliases,
        provenance=[{**context, "record_url": "https://api.crossref.org/works/" + quote(doi, safe=""), "type": item_type, "date_fields": {k: x[k] for k in ("posted", "published-online", "published-print", "published", "issued", "created", "deposited", "indexed") if k in x}, "licenses": x.get("license", []), "relations": x.get("relation", {})}])


def fetch_crossref(http, config, start, end, initial):
    _date_window(start, end)
    papers, queries = [], []
    date_type = "pub" if initial else "index"
    for track, query in _source_queries(config, "crossref"):
        cursor, count, total = "*", 0, None
        for page in range(config["max_pages_per_query"]):
            params = {"query": query, "filter": f"from-{date_type}-date:{start},until-{date_type}-date:{end}", "rows": config["page_size"], "cursor": cursor}
            if config.get("retrieval_policy") == "bounded":
                params.update(sort="score", order="desc")
            if config["contact_email"]:
                params["mailto"] = config["contact_email"]
            message = http.json(CROSSREF, params=params).get("message", {})
            if not isinstance(message, dict) or not isinstance(message.get("items"), list):
                raise RetrievalError("Crossref 响应缺少 items")
            items = message["items"]
            count += len(items)
            if isinstance(message.get("total-results"), int) and not isinstance(message["total-results"], bool):
                total = message["total-results"]
            context = {**provenance("crossref", params, CROSSREF), "topic_id": track}
            papers.extend(crossref_paper(x, context) for x in items if x.get("title"))
            if len(items) < config["page_size"] or count == total:
                queries.append({"track": track, "query": query, "pages": page + 1, "date_field": date_type, "complete": True,
                                "records_retrieved": count, "total_results": total})
                break
            next_cursor = message.get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                raise RetrievalError("Crossref 分页游标缺失/重复，检索不完整")
            cursor = next_cursor
        else:
            if config.get("retrieval_policy") != "bounded":
                raise RetrievalError(f"Crossref 查询达到分页上限，不能声称完整：{query}")
            queries.append(_bounded_query(config, {"track": track, "query": query,
                "pages": config["max_pages_per_query"], "date_field": date_type,
                "records_retrieved": count, "total_results": total, "order": "relevance score descending"}))
    return papers, _source_report("crossref", papers, queries, config)


def epmc_paper(x, context) -> Paper:
    source, identifier = x.get("source", "UNKNOWN"), x.get("id", "")
    types = x.get("pubTypeList", {}).get("pubType", [])
    is_preprint = source == "PPR" or any("preprint" in t.lower() for t in types)
    doi = normalize_doi(x.get("doi"))
    return Paper(title=clean(x.get("title")), source_id=source + ":" + identifier, source="europepmc", url="https://europepmc.org/article/" + source + "/" + quote(identifier), doi=doi,
        abstract=clean(x.get("abstractText")), authors=[clean(a.get("fullName") or a.get("collectiveName") or " ".join([a.get("firstName") or "", a.get("lastName") or ""])) for a in ((x.get("authorList") or {}).get("author") or []) if isinstance(a, dict)],
        author_details=[{"given": clean(a.get("firstName")), "family": clean(a.get("lastName")), "literal": clean(a.get("collectiveName"))} for a in ((x.get("authorList") or {}).get("author") or []) if isinstance(a, dict)],
        journal=x.get("journalInfo", {}).get("journal", {}).get("title", ""), publication_date=x.get("electronicPublicationDate") or x.get("firstPublicationDate", ""), publication_date_label="electronicPublicationDate" if x.get("electronicPublicationDate") else "Europe PMC firstPublicationDate（部分日期可能经来源补齐）", index_date=x.get("firstIndexDate", ""),
        kind="预印本；未经同行评审核实" if is_preprint else "文献数据库收录；同行评审状态未核实", pmcid=normalize_pmcid(x.get("pmcid", "")), open_access=x.get("isOpenAccess") == "Y",
        provenance=[{**context, "record_url": EPMC + "/search?" + urlencode({"query": f"EXT_ID:{identifier} AND SRC:{source}", "format": "json", "resultType": "core"}), "publication_types": types, "licenses": x.get("license", ""), "date_fields": {k: x[k] for k in ("firstPublicationDate", "firstIndexDate", "electronicPublicationDate", "dateOfRevision") if k in x}}])


def fetch_europepmc(http, config, start, end, initial):
    _date_window(start, end)
    papers, queries = [], []
    field = "FIRST_PDATE" if initial else "FIRST_IDATE"
    for track, topic in _source_queries(config, "europepmc"):
        expression = _literal_query(topic, "TITLE_ABS") if config.get("topics") else topic
        query = f"({expression}) AND {field}:[{start} TO {end}]"
        cursor, count = "*", 0
        for page in range(config["max_pages_per_query"]):
            params = {"query": query, "format": "json", "resultType": "core", "pageSize": config["page_size"], "cursorMark": cursor}
            data = http.json(EPMC + "/search", params=params)
            if "hitCount" not in data or "resultList" not in data:
                raise RetrievalError("Europe PMC 响应缺少命中信息")
            items = data.get("resultList", {}).get("result", [])
            count += len(items)
            context = {**provenance("europepmc", params, EPMC + "/search"), "topic_id": track}
            papers.extend(epmc_paper(x, context) for x in items if x.get("title") and x.get("id"))
            if count >= int(data["hitCount"]):
                queries.append({"track": track, "query": query, "pages": page + 1, "complete": True,
                                "records_retrieved": count, "total_results": int(data["hitCount"])})
                break
            next_cursor = data.get("nextCursorMark")
            if not items or not next_cursor or next_cursor == cursor:
                raise RetrievalError("Europe PMC 分页提前结束，检索不完整")
            cursor = next_cursor
        else:
            if config.get("retrieval_policy") != "bounded":
                raise RetrievalError(f"Europe PMC 查询达到分页上限：{track}")
            queries.append(_bounded_query(config, {"track": track, "query": query,
                "pages": config["max_pages_per_query"], "date_field": field,
                "records_retrieved": count, "total_results": int(data["hitCount"]), "order": "source default relevance"}))
    return papers, _source_report("europepmc", papers, queries, config)



def _arxiv_timestamp(value):
    """Validate actual Atom timestamps: date-only or naive values are not evidence."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value or ""):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def arxiv_paper(entry, context) -> Paper:
    raw_id = entry.findtext(ATOM + "id", "")
    identifier = normalize_arxiv_id(raw_id)
    title = clean(entry.findtext(ATOM + "title", ""))
    if not identifier or not title:
        raise RetrievalError("arXiv 条目缺少有效标识符或标题（可能为 API 错误）")
    published = entry.findtext(ATOM + "published", "")
    updated = entry.findtext(ATOM + "updated", "")
    timestamp, update_timestamp = _arxiv_timestamp(published), _arxiv_timestamp(updated)
    warnings, dates = [], {"arxiv-published-raw": published, "arxiv-updated": updated}
    if timestamp is not None:
        dates["arxiv-published"] = timestamp.date().isoformat()
    else:
        warnings.append("arXiv 首次提交日期缺失或无效，不能据此确认发表窗口")
    if updated and (update_timestamp is None or (timestamp and update_timestamp < timestamp)):
        warnings.append("arXiv 版本更新日期无效或早于首次提交，未作为新发表日期使用")
    related_doi = normalize_doi(entry.findtext(ARXIV_NS + "doi", ""))
    relations = [{"type": "journal-doi", "id": related_doi, "id_type": "doi", "source": "arxiv"}] if related_doi else []
    version = re.search(r"v[1-9]\d*$", urlsplit(raw_id).path)
    source_id = identifier + (version.group(0) if version else "")
    # arxiv:doi usually identifies the journal article, not this preprint.
    return Paper(title=title, source_id=source_id, source="arxiv", arxiv_id=identifier,
        url="https://arxiv.org/abs/" + source_id, abstract=clean(entry.findtext(ATOM + "summary", "")),
        authors=[clean(author.findtext(ATOM + "name", "")) for author in entry.findall(ATOM + "author")],
        journal=clean(entry.findtext(ARXIV_NS + "journal_ref", "")),
        publication_date=timestamp.date().isoformat() if timestamp else "",
        publication_date_label="arXiv 首次提交/处理日期（UTC；不是期刊发表日期）", index_date="",
        kind="arXiv 预印本；未经同行评审核实", open_access=True, relations=relations, warnings=warnings,
        provenance=[{**context, "record_url": "https://arxiv.org/abs/" + source_id, "date_fields": dates,
                     "related_journal_doi": related_doi, "version_id": source_id}])


def fetch_arxiv(http, config, start, end, initial):
    left, right = _date_window(start, end)
    papers, queries = [], []
    # arXiv documents only submittedDate range filters; rolling retrieval is
    # deliberately based on first submission, never a revision as a new paper.
    field = "submittedDate"
    for track, topic in _source_queries(config, "arxiv"):
        query = f"({_arxiv_query(topic)}) AND {field}:[{left:%Y%m%d}0000 TO {right:%Y%m%d}2359]"
        seen_ids, count, expected_total = set(), 0, None
        for page in range(config["max_pages_per_query"]):
            params = {"search_query": query, "start": count, "max_results": min(config["page_size"], 2000),
                      "sortBy": field, "sortOrder": "descending"}
            raw = http.request(ARXIV, params=params, headers={"Accept": "application/atom+xml"}, interval=3.0)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                raise RetrievalError("arXiv 返回无效 Atom XML") from None
            if root.tag != ATOM + "feed":
                raise RetrievalError("arXiv 响应不是 Atom feed")
            try:
                total = int(root.findtext(OPENSEARCH + "totalResults", ""))
                offset = int(root.findtext(OPENSEARCH + "startIndex", ""))
            except ValueError:
                raise RetrievalError("arXiv 响应缺少有效分页信息") from None
            if total < 0 or offset != count or (expected_total is not None and total != expected_total):
                raise RetrievalError("arXiv 分页计数不一致，检索不完整")
            expected_total = total
            entries = root.findall(ATOM + "entry")
            context = {**provenance("arxiv", params, ARXIV), "topic_id": track}
            page_papers = [arxiv_paper(entry, context) for entry in entries]
            ids = [paper.source_id for paper in page_papers]
            if len(set(ids)) != len(ids) or any(value in seen_ids for value in ids):
                raise RetrievalError("arXiv 返回重复分页记录，检索不完整")
            seen_ids.update(ids)
            papers.extend(page_papers)
            count += len(entries)
            if count > total:
                raise RetrievalError("arXiv 记录数超过声明总数")
            if count == total:
                queries.append({"track": track, "query": query, "pages": page + 1, "date_field": field, "complete": True,
                                "records_retrieved": count, "total_results": total})
                break
            if not entries:
                raise RetrievalError("arXiv 分页提前结束，检索不完整")
        else:
            if config.get("retrieval_policy") != "bounded":
                raise RetrievalError(f"arXiv 查询达到分页上限：{track}")
            queries.append(_bounded_query(config, {"track": track, "query": query,
                "pages": config["max_pages_per_query"], "date_field": field,
                "records_retrieved": count, "total_results": total, "order": "first submission date descending"}))
    return papers, _source_report("arxiv", papers, queries, config)


def safe_figure_url(value):
    """Accept only public-looking HTTPS URLs; no files, scripts or local endpoints.

    This does not fetch/resolve an asset or guarantee host ownership. Figure
    metadata is never used as an HTTP fetch destination by this module.
    """
    if not isinstance(value, str) or not value or any(ord(c) < 33 for c in value):
        return ""
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or parsed.username or parsed.password or not host or parsed.port not in (None, 443):
            return ""
        if "\\" in value or "%" in host or "." not in host or not re.fullmatch(r"[a-z0-9.:-]+", host):
            return ""
        if host in {"localhost", "localhost.localdomain", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            # Reject alternate numeric IPv4 encodings (e.g. 127.1 or 0x7f.0.0.1).
            if all(re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", part) for part in host.split(".")):
                return ""
        return value
    except (ValueError, UnicodeError):
        return ""


def _reuse_license(license_value):
    value = clean(license_value).lower().strip().rstrip("/")
    if re.fullmatch(r"cc0(?: 1\.0)?|cc[ -]by(?: (?:1\.0|2\.0|2\.5|3\.0|4\.0))?", value):
        return True
    return bool(re.fullmatch(r"https?://creativecommons\.org/(?:publicdomain/zero/1\.0|licenses/by/(?:1\.0|2\.0|2\.5|3\.0|4\.0))", value))


def _figure_metadata(item, origin, mode):
    source_url = safe_figure_url(item.get("source_url", ""))
    asset_url = safe_figure_url(item.get("url", ""))
    if not source_url:
        return None
    license_value = clean(item.get("license", ""))
    attribution = clean(item.get("attribution", ""))
    # Only an explicit figure-level statement may grant reuse. Article-level
    # open access, a permissive title, or embed_allowed supplied by a caller do not.
    permitted = item.get("license_scope") == "figure" and _reuse_license(license_value) and bool(attribution) and bool(asset_url)
    return {"id": clean(item.get("id", "")), "caption": clean(item.get("caption", "")),
            "url": asset_url, "source_url": source_url, "license": license_value,
            "license_scope": item.get("license_scope", "unknown"), "attribution": attribution,
            "embed_allowed": mode == "embed" and permitted, "provenance": origin}


def attach_figures(paper, config):
    """Apply explicitly provided figure metadata; never download or invent images.

    figure_catalog maps paper.key (or a known alias) to dictionaries containing
    caption, url (optional actual HTTPS asset), source_url, license, attribution,
    license_scope='figure'. images.mode defaults to off; links is recommended.
    """
    settings = config.get("images", {})
    mode = settings.get("mode", "off")
    if mode == "off":
        paper.figures = []
        return
    limit = settings.get("max_per_paper", 3)
    catalog = config.get("figure_catalog", {})
    figures = []
    for item in paper.figures:
        normalized = _figure_metadata(item, item.get("provenance", {"source": "unknown"}), mode)
        if normalized:
            figures.append(normalized)
    for key in paper.aliases:
        for item in catalog.get(key, []):
            normalized = _figure_metadata(item, {"source": "configured_figure_catalog", "paper_key": key}, mode)
            if normalized:
                figures.append(normalized)
            else:
                paper.warnings.append("忽略缺少安全来源链接的配置图片")
    unique, seen = [], set()
    for figure in figures:
        identity = (figure["source_url"], figure["url"], figure["id"])
        if identity not in seen:
            unique.append(figure)
            seen.add(identity)
    paper.figures = unique[:limit]


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _elements(element, tag):
    return [node for node in element.iter() if _tag(node) == tag]


def _text(element):
    return clean(" ".join(element.itertext())) if element is not None else ""


def _jats_figures(paper, root, xml_url, config):
    mode = config.get("images", {}).get("mode", "off")
    if mode == "off":
        return
    pmcid = normalize_pmcid(paper.pmcid)
    if not pmcid:
        return
    article_url = "https://europepmc.org/articles/" + pmcid
    for figure in _elements(root, "fig"):
        identifier = figure.get("id", "")
        caption_nodes, label_nodes = _elements(figure, "caption"), _elements(figure, "label")
        caption = " ".join(filter(None, [_text(label_nodes[0]) if label_nodes else "", _text(caption_nodes[0]) if caption_nodes else ""]))
        assets = [node.get("{http://www.w3.org/1999/xlink}href", node.get("href", "")) for node in _elements(figure, "graphic")]
        # Relative JATS assets are not publicly resolvable URLs by themselves.
        # Link the actual figure anchor instead of fabricating an image address.
        asset = next((safe_figure_url(value) for value in assets if safe_figure_url(value)), "")
        permissions = _elements(figure, "permissions")
        licenses = _elements(permissions[0], "license") if permissions else []
        license_value = ""
        if licenses:
            license_value = licenses[0].get("{http://www.w3.org/1999/xlink}href", "") or _text(licenses[0])
            if not _reuse_license(license_value):
                ext_links = _elements(licenses[0], "ext-link")
                license_value = next((node.get("{http://www.w3.org/1999/xlink}href", "") for node in ext_links
                                      if _reuse_license(node.get("{http://www.w3.org/1999/xlink}href", ""))), license_value)
        credits = _elements(figure, "attrib") + (_elements(permissions[0], "copyright-holder") if permissions else [])
        attribution = "; ".join(filter(None, [_text(node) for node in credits]))
        # Source article authors provide attributable provenance, but no license.
        if not attribution and paper.authors:
            attribution = ", ".join(paper.authors) + " — " + paper.title
        item = {"id": identifier, "caption": caption, "url": asset,
                "source_url": article_url + ("#" + quote(identifier, safe="") if identifier else ""),
                "license": license_value, "license_scope": "figure" if licenses else "unknown", "attribution": attribution}
        normalized = _figure_metadata(item, {"source": "europepmc_jats", "api_url": xml_url,
                                            "retrieved_at": datetime.now(timezone.utc).isoformat()}, mode)
        if normalized:
            paper.figures.append(normalized)


def _arxiv_fulltext_id(paper):
    """Use a known arXiv identity, preserving an explicitly retrieved version.

    Never fetch a provider-supplied URL or a related journal DOI. After merging
    multiple metadata sources, prefer the highest observed version of this same
    preprint; do not guess a version or follow an arbitrary external link.
    """
    identifier = normalize_arxiv_id(paper.arxiv_id)
    if not identifier and paper.source.lower() == "arxiv":
        identifier = normalize_arxiv_id(paper.source_id)
    if not identifier:
        identifier = normalize_arxiv_id(paper.doi)
    if not identifier:
        return ""
    candidates = [paper.arxiv_id, paper.url]
    if paper.source.lower() == "arxiv":
        candidates.append(paper.source_id)
    candidates.extend(item.get("version_id", "") for item in paper.provenance
                      if item.get("source") == "arxiv")
    versions = []
    for candidate in candidates:
        if normalize_arxiv_id(candidate) != identifier:
            continue
        path = urlsplit(candidate).path if candidate.lower().startswith(("http://", "https://")) else candidate
        match = re.search(r"v([1-9]\d*)(?:\.pdf)?$", path, re.I)
        if match:
            versions.append(int(match.group(1)))
    return identifier + ("v" + str(max(versions)) if versions else "")


class _ArxivHTMLBody(HTMLParser):
    """Extract visible LaTeXML article content with no third-party dependency.

    Ordinary HTML/abstract pages, API XML, error pages, and large bibliographies
    are not a full-text body. Require the publisher's article marker and enough
    prose outside abstract/front matter, tables, captions, and references.
    """

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _SKIP_TAGS = {"head", "header", "footer", "nav", "script", "style", "noscript", "template", "form", "button", "select", "textarea", "svg", "annotation", "annotation-xml"}
    _SKIP_CLASSES = {"ltx_abstract", "ltx_authors", "ltx_creator", "ltx_date", "ltx_title_document",
                     "ltx_keywords", "ltx_classification", "ltx_bibliography", "ltx_acknowledgements",
                     "ltx_page_header", "ltx_page_footer", "ltx_page_navbar", "ltx_TOC", "ltx_toclist"}
    _BLOCKS = {"article", "main", "section", "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6",
               "blockquote", "pre", "table", "tr", "td", "th", "caption", "figure", "figcaption", "br", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts, self.prose = [], []
        self.documents, self.closed_documents = 0, 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        # Stack frames: tag, article, skip, prose, non-prose, root marker.
        parent = self.stack[-1] if self.stack else ("", False, False, False, False, False)
        root = tag in {"article", "div", "main", "body"} and "ltx_document" in classes and not parent[1]
        inside = parent[1] or root
        skip = (parent[2] or tag in self._SKIP_TAGS or bool(classes & self._SKIP_CLASSES)
                or "hidden" in attributes or (attributes.get("aria-hidden") or "").lower() == "true"
                or (attributes.get("role") or "").lower() in {"navigation", "contentinfo", "doc-abstract", "doc-bibliography"})
        non_prose = parent[4] or tag in {"table", "figure", "figcaption", "caption", "math"}
        prose = not non_prose and (parent[3] or tag == "p" or "ltx_para" in classes)
        if root and not skip:
            self.documents += 1
        if inside and not skip and tag in self._BLOCKS:
            self.parts.append(" ")
            if prose:
                self.prose.append(" ")
        if tag not in self._VOID:
            if len(self.stack) >= 2048:
                raise RetrievalError("arXiv HTML 嵌套层数过多")
            self.stack.append((tag, inside, skip, prose, non_prose, root and not skip))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            frame = self.stack[index]
            if frame[0] != tag:
                continue
            if frame[1] and not frame[2] and tag in self._BLOCKS:
                self.parts.append(" ")
                if frame[3]:
                    self.prose.append(" ")
            if frame[5]:
                self.closed_documents += 1
            del self.stack[index:]
            break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.parts.append(data)
            if self.stack[-1][3]:
                self.prose.append(data)

    def body_text(self):
        # Do not use models.clean: these strings have already been HTML-parsed,
        # and scientific text such as "p < 0.05" must not be stripped as a tag.
        text = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        prose = re.sub(r"\s+", " ", "".join(self.prose)).strip()
        if self.documents != 1 or self.closed_documents != 1:
            raise RetrievalError("arXiv HTML 缺少完整且唯一的论文正文")
        if len(text) < 500 or len(prose) < 300:
            raise RetrievalError("arXiv HTML 正文不足，保留摘要证据等级")
        return text


def _enrich_arxiv_full_text(paper, http, identifier):
    url = "https://arxiv.org/html/" + quote(identifier, safe="/")
    try:
        raw = http.request(url, headers={"Accept": "text/html"}, interval=3.0)
        parser = _ArxivHTMLBody()
        parser.feed(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        parser.close()
        text = parser.body_text()
        paper.full_text, paper.full_text_url = text, url
        paper.evidence_level = "全文正文（arXiv HTML 转换；不含图像像素、外部补充材料；公式/表格格式可能丢失）"
        paper.provenance.append({"source": "arxiv_fulltext", "api_url": url, "version_id": identifier,
                                 "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                 "format": "html", "extracted_characters": len(text),
                                 "extraction": "LaTeXML article body; excludes abstract, navigation, scripts and bibliography"})
        return True
    except (RetrievalError, UnicodeError) as exc:
        paper.warnings.append(f"arXiv 全文获取失败，保留已有正文或降级到摘要/元数据：{exc}")
        if not paper.full_text:
            paper.evidence_level = "仅摘要" if paper.abstract else "仅元数据"
        return False


def enrich_full_text(paper, http, config=None):
    config = config or {}
    identifier = _arxiv_fulltext_id(paper)
    if identifier and config.get("fetch_full_text", True):
        if _enrich_arxiv_full_text(paper, http, identifier):
            return
    if not normalize_pmcid(paper.pmcid) or not paper.open_access:
        return
    url = EPMC + "/" + quote(paper.pmcid, safe="") + "/fullTextXML"
    try:
        xml = http.request(url, headers={"Accept": "application/xml"})
        root = ET.fromstring(xml)
        _jats_figures(paper, root, url, config)
        attach_figures(paper, config)
        bodies = _elements(root, "body")
        if not bodies:
            raise RetrievalError("全文 XML 缺少正文 body")
        text = _text(bodies[0])
        if len(text) < 100:
            raise RetrievalError("全文正文过短，保留摘要证据等级")
        paper.full_text, paper.full_text_url = text, url
        paper.evidence_level = "全文正文（不含图像像素、外部补充材料；表格格式可能丢失）"
        licenses = _elements(root, "license")
        license_text = _text(licenses[0]) if licenses else "来源未提供许可文本"
        paper.provenance.append({"source": "europepmc_fulltext", "api_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "license_text": license_text})
    except (RetrievalError, ET.ParseError) as exc:
        paper.warnings.append(f"全文获取失败，降级到摘要/元数据：{exc}")
