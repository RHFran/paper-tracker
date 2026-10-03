"""Model-free source tools for research directed by the calling agent.

``search`` runs exactly one agent-selected literal query in one configured source
and topic. It does not plan queries, screen papers, classify relevance or call a
model. ``fetch`` accepts a source URL as a lead, never supplied paper metadata.
It retrieves the corresponding record from fixed official APIs and verifies the
returned identity before exposing it as evidence.

Supported HTTPS leads (no credentials, explicit ports, query or fragment):
* arxiv.org, www.arxiv.org or export.arxiv.org /abs|pdf|html/<arxiv-id>
  (including versions, legacy IDs and the optional /pdf/<id>.pdf suffix);
* doi.org/<doi> or api.crossref.org/works/<doi>, for Crossref-registered DOIs;
* europepmc.org or www.europepmc.org /article/MED/<pmid>, /article/PPR/<pprid>,
  /article/PMC/<pmcid>, or /articles/<pmcid>;
* pmc.ncbi.nlm.nih.gov/articles/<pmcid> and
  www.ncbi.nlm.nih.gov/pmc/articles/<pmcid>.

DOI suffixes here support ASCII letters/digits and . _ ; ( ) / : + - only.
Percent encoding is decoded once for DOI URLs only. Other URL families are
rejected rather than scraped or followed. Redirects remain disabled by HttpClient.
If the arXiv API is rate-limited or unavailable, fetch may retrieve the official
/abs page once, requiring matching canonical/citation IDs, the cited version and
an explicit [v1] UTC submission-history timestamp. It never substitutes a revision
or citation_date for the first submission. Access denials, redirects and malformed
API evidence do not trigger this fallback.
API-supplied links are metadata, never fetch destinations. The caller is responsible
for assessing relevance, date-window membership and evidence limitations.
"""
from __future__ import annotations

import copy
from datetime import date, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import re
from urllib.parse import quote, unquote, urlsplit
import xml.etree.ElementTree as ET

from .config import DEFAULTS
from .http import HttpClient, RetrievalError
from .models import Paper, TRACKS, clean, normalize_arxiv_id, normalize_doi, normalize_pmcid
from .sources import (ARXIV, ATOM, CROSSREF, EPMC, arxiv_paper, crossref_paper,
                      enrich_full_text, epmc_paper, fetch_arxiv, fetch_crossref,
                      fetch_europepmc, provenance)

_FETCHERS = {"arxiv": fetch_arxiv, "crossref": fetch_crossref, "europepmc": fetch_europepmc}
_ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})(?:v[1-9]\d*)?"
_DOI = re.compile(r"10\.\d{4,9}/[A-Za-z0-9._;()/:+-]+\Z", re.ASCII)
_EPMC_IDS = {"MED": r"[1-9]\d*", "PPR": r"PPR[1-9]\d*", "PMC": r"PMC[1-9]\d*"}


def _settings(config):
    if not isinstance(config, dict):
        raise ValueError("config must be a configuration object")
    settings = copy.deepcopy(DEFAULTS)
    settings.update(copy.deepcopy(config))
    sources = settings["sources"]
    if (not isinstance(sources, list) or not sources
            or any(not isinstance(item, str) or item not in _FETCHERS for item in sources)
            or len(set(sources)) != len(sources)):
        raise ValueError("sources must be a nonempty allowlist of arxiv, crossref or europepmc")
    for key, maximum in (("page_size", 1000), ("max_pages_per_query", 1000),
                         ("http_timeout_seconds", 300), ("http_retries", 10)):
        if type(settings[key]) is not int or not 1 <= settings[key] <= maximum:
            raise ValueError(f"{key} must be an integer between 1 and {maximum}")
    if settings["retrieval_policy"] not in ("complete", "bounded"):
        raise ValueError("retrieval_policy must be complete or bounded")
    if type(settings["fetch_full_text"]) is not bool:
        raise ValueError("fetch_full_text must be true or false")
    return settings


def _allowed(config, source):
    if not isinstance(source, str) or source not in _FETCHERS:
        raise ValueError("Unsupported source; use arxiv, crossref or europepmc")
    if source not in config["sources"]:
        raise ValueError(f"Source {source} is not enabled in config.sources")


def _client(config, http):
    return _Requests(http if http is not None else HttpClient(
        config["contact_email"], config["http_timeout_seconds"], config["http_retries"]), config)


def _source_for_request(url):
    # Exact generated destinations, not a general public-host URL permission.
    if url == ARXIV or re.fullmatch(r"https://arxiv\.org/(?:html|abs)/" + _ARXIV_ID, url):
        return "arxiv"
    if url == CROSSREF or (url.startswith(CROSSREF + "/") and
                          _valid_doi(unquote(url[len(CROSSREF) + 1:]))):
        return "crossref"
    if url == EPMC + "/search" or re.fullmatch(re.escape(EPMC) + r"/PMC[1-9]\d*/fullTextXML", url):
        return "europepmc"
    raise RetrievalError("Refused a request outside the fixed official source endpoints")


class _Requests:
    """Record successful and failed requests, including optional full-text calls."""
    def __init__(self, http, config):
        self.http, self.config, self.records = http, config, []

    def _call(self, method, url, **kwargs):
        source = _source_for_request(url)
        _allowed(self.config, source)
        record = {**provenance(source, copy.deepcopy(kwargs.get("params", {})), url),
                  "method": "GET", "status": "pending"}
        self.records.append(record)
        try:
            result = getattr(self.http, method)(url, **kwargs)
            record["status"] = "ok"
            return result
        except RetrievalError as exc:
            record.update(status="error", error=str(exc))
            raise

    def json(self, url, **kwargs):
        result = self._call("json", url, **kwargs)
        if not isinstance(result, dict):
            raise RetrievalError("Source API response must be a JSON object")
        params = kwargs.get("params", {})
        if url == CROSSREF:
            items = result.get("message", {}).get("items") if isinstance(result.get("message"), dict) else None
            limit = params.get("rows")
        elif url == EPMC + "/search":
            items = result.get("resultList", {}).get("result") if isinstance(result.get("resultList"), dict) else None
            limit = params.get("pageSize")
        else:
            items, limit = None, None
        if isinstance(items, list) and type(limit) is int and len(items) > limit:
            raise RetrievalError("Source returned more records than the configured page size")
        return result

    def request(self, url, **kwargs):
        result = self._call("request", url, **kwargs)
        if url == ARXIV:
            try:
                entries = ET.fromstring(result).findall(ATOM + "entry")
            except ET.ParseError:
                return result  # The source parser supplies the detailed XML error.
            limit = kwargs.get("params", {}).get("max_results")
            if type(limit) is int and len(entries) > limit:
                raise RetrievalError("arXiv returned more records than the requested page size")
        elif url.startswith(EPMC + "/") and url.endswith("/fullTextXML"):
            try:
                root = ET.fromstring(result)
            except ET.ParseError:
                return result
            requested = url[len(EPMC) + 1:].split("/", 1)[0]
            for item in root.iter():
                if (item.tag.rsplit("}", 1)[-1] == "article-id"
                        and item.get("pub-id-type") in {"pmc", "pmcid"}):
                    actual = "".join(item.itertext()).strip().upper()
                    actual = actual if actual.startswith("PMC") else "PMC" + actual
                    if actual != requested:
                        raise RetrievalError("Europe PMC full-text XML identifies a different article")
        return result


def _finish(papers, config, http):
    for paper in papers:
        paper.evidence_level = "仅摘要" if paper.abstract else "仅元数据"
        if config["fetch_full_text"]:
            # Full text remains optional: enrich_full_text records its own failure
            # warning without converting an unavailable body into full evidence.
            enrich_full_text(paper, http, {**config, "fetch_full_text": "arxiv" in config["sources"]})


def search(config, source, topic_id, query, start, end, http=None) -> tuple[list[Paper], dict]:
    """Retrieve one chosen query; return papers and an auditable coverage report.

    Query text is literal, not executable provider syntax. New agent-chosen query
    text is allowed; topic_id must already exist. start/end are inclusive ISO days.
    Existing complete/bounded pagination policy and source limits are preserved.
    Invalid inputs raise ValueError; failed/incomplete source retrieval raises
    RetrievalError. No library, state, email or model operation is performed.
    """
    config = _settings(config)
    _allowed(config, source)
    topics = config.get("topics")
    if topics is not None and (not isinstance(topics, list) or any(not isinstance(t, dict) for t in topics)):
        raise ValueError("topics must be a list of configured topic objects")
    ids = [topic.get("id") for topic in topics] if topics is not None else list(TRACKS)
    if not isinstance(topic_id, str) or topic_id not in ids:
        raise ValueError("topic_id must identify an existing configured topic")
    if (not isinstance(query, str) or not query.strip() or len(query) > 500
            or any(ord(char) < 32 or ord(char) == 127 for char in query)):
        raise ValueError("query must be 1–500 characters of single-line literal text")
    for day in (start, end):
        try:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("start and end must be valid ISO dates (YYYY-MM-DD)") from None
    if start > end:
        raise ValueError("start must be on or before end")
    # Do not modify the saved topics or run their other queries/source overrides.
    selected = {**config, "topics": [{"id": topic_id, "queries": [query]}]}
    client = _client(config, http)
    try:
        papers, report = _FETCHERS[source](client, selected, start, end, True)
    except (TypeError, AttributeError, KeyError, IndexError) as exc:
        raise RetrievalError(f"Malformed {source} response ({type(exc).__name__})") from None
    for paper in papers:
        if paper.source != source:
            raise RetrievalError("Source search returned a different source identity")
        if source == "crossref":
            if not _valid_doi(paper.doi):
                raise RetrievalError("Crossref search record lacks a valid stable DOI")
            paper.url = "https://doi.org/" + quote(paper.doi, safe="/")
        elif source == "europepmc":
            record_source, separator, record_id = paper.source_id.partition(":")
            if (not separator or record_source not in _EPMC_IDS
                    or not re.fullmatch(_EPMC_IDS[record_source], record_id)):
                raise RetrievalError("Europe PMC search record lacks a supported stable identifier")
        for item in paper.provenance:
            item.update(agent_operation="search", agent_query=query, topic_id=topic_id)
    _finish(papers, config, client)
    report.update(operation="search", topic_id=topic_id, agent_query=query,
                  start=start, end=end, requests=client.records, model_calls=0,
                  full_text_requested=config["fetch_full_text"],
                  full_text_retrieved=sum(bool(paper.full_text) for paper in papers))
    return papers, report


def _valid_doi(identifier):
    return (bool(_DOI.fullmatch(identifier)) and len(identifier) <= 1000
            and not any(segment in (".", "..", "") for segment in identifier.split("/")))


def _lead(url):
    if (not isinstance(url, str) or not url or len(url) > 2048
            or any(ord(c) < 33 or ord(c) == 127 for c in url)
            or any(c in url for c in ("\\", "?", "#"))):
        raise ValueError("Lead must be an official HTTPS article URL without a query or fragment")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (parts.scheme != "https" or not host or parts.username is not None
                or parts.password is not None or parts.port is not None
                or parts.netloc.lower() != host):
            raise ValueError
    except ValueError:
        raise ValueError("Lead URLs must use HTTPS without credentials or explicit ports") from None
    path = parts.path
    if host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        match = re.fullmatch(r"/(abs|pdf|html)/(" + _ARXIV_ID + r")(\.pdf)?/?", path)
        if match and (not match[3] or match[1] == "pdf"):
            return "arxiv", match[2], "arxiv"
    if host in {"doi.org", "api.crossref.org"}:
        prefix = "/works/" if host == "api.crossref.org" else "/"
        if path.startswith(prefix):
            identifier = unquote(path[len(prefix):]).lower()
            if _valid_doi(identifier):
                return "crossref", identifier, "doi"
    if host in {"europepmc.org", "www.europepmc.org"}:
        match = re.fullmatch(r"/article/(MED|PPR|PMC)/([^/]+)/?", path)
        if match and re.fullmatch(_EPMC_IDS[match[1]], match[2]):
            return "europepmc", match[2], match[1]
        match = re.fullmatch(r"/articles/(PMC[1-9]\d*)/?", path)
        if match:
            return "europepmc", match[1], "PMC"
    for official, prefix in (("pmc.ncbi.nlm.nih.gov", "/articles/"),
                             ("www.ncbi.nlm.nih.gov", "/pmc/articles/")):
        if host == official:
            match = re.fullmatch(re.escape(prefix) + r"(PMC[1-9]\d*)/?", path)
            if match:
                return "europepmc", match[1], "PMC"
    raise ValueError("Unsupported official article URL or invalid identifier; see agent_sources supported URL families")


def _arxiv(client, identifier, context):
    params = {"id_list": identifier, "start": 0, "max_results": 1}
    try:
        raw = client.request(ARXIV, params=params, headers={"Accept": "application/atom+xml"}, interval=3.0)
    except RetrievalError as exc:
        reason = str(exc)
        if not re.search(r"HTTP 429\b|网络连接失败|network (?:connection )?(?:failure|unavailable)|timed? ?out", reason, re.I):
            raise
        return _arxiv_abs(client, identifier, context, reason)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise RetrievalError("arXiv returned invalid Atom XML") from None
    entries = root.findall(ATOM + "entry")
    if root.tag != ATOM + "feed" or len(entries) != 1:
        raise RetrievalError("arXiv must return exactly one record for the requested identifier")
    paper = arxiv_paper(entries[0], {**provenance("arxiv", params, ARXIV), **context})
    explicit_version = re.search(r"v[1-9]\d*$", identifier)
    if (paper.arxiv_id != normalize_arxiv_id(identifier)
            or (explicit_version and paper.source_id != identifier)):
        raise RetrievalError("arXiv returned an identifier/version different from the requested article")
    return paper



class _ArxivAbsHTML(HTMLParser):
    """Read citation metadata and two source-marked visible evidence regions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metadata, self.canonicals, self.stack = {}, [], []
        self.history, self.citation = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name", "").startswith("citation_"):
            self.metadata.setdefault(attrs["name"], []).append(attrs.get("content", ""))
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonicals.append(attrs.get("href", ""))
        classes = set(attrs.get("class", "").split())
        parent = self.stack[-1] if self.stack else ("", False, False, False)
        frame = (tag, parent[1] or "submission-history" in classes,
                 parent[2] or bool(classes & {"arxivid", "arxividv"}),
                 parent[3] or tag in {"script", "style", "template", "noscript"} or "hidden" in attrs)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            if len(self.stack) >= 2048:
                raise RetrievalError("arXiv abstract HTML nesting exceeds the safety limit")
            self.stack.append(frame)
        elif tag == "br":
            self.handle_data(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        self.handle_data(" ")
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, value):
        if self.stack and not self.stack[-1][3]:
            if self.stack[-1][1]:
                self.history.append(value)
            if self.stack[-1][2]:
                self.citation.append(value)

    def single(self, name):
        values = self.metadata.get(name, [])
        if len(values) != 1 or not values[0].strip():
            raise RetrievalError(f"arXiv abstract page lacks unique {name} metadata")
        return values[0]


def _arxiv_abs(client, identifier, context, reason):
    url = "https://arxiv.org/abs/" + identifier
    raw = client.request(url, headers={"Accept": "text/html"}, interval=3.0)
    parser = _ArxivAbsHTML()
    try:
        parser.feed(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        parser.close()
    except UnicodeError:
        raise RetrievalError("arXiv abstract page is not valid UTF-8") from None
    base = normalize_arxiv_id(identifier)
    if len(parser.canonicals) != 1:
        raise RetrievalError("arXiv abstract page lacks a unique canonical identity")
    try:
        canonical_source, canonical_id, _ = _lead(parser.canonicals[0])
    except ValueError:
        raise RetrievalError("arXiv abstract page has an invalid canonical identity") from None
    if (canonical_source != "arxiv" or normalize_arxiv_id(canonical_id) != base
            or normalize_arxiv_id(parser.single("citation_arxiv_id")) != base):
        raise RetrievalError("arXiv abstract page returned a different article identity")
    citation = re.sub(r"\s+", " ", "".join(parser.citation)).strip()
    versions = re.findall(r"arXiv:(" + _ARXIV_ID + r")\s*(?:\[[^\]]*\]\s*)?for this version", citation)
    if len(versions) != 1 or not re.search(r"v[1-9]\d*$", versions[0]):
        raise RetrievalError("arXiv abstract page does not identify the retrieved version")
    version_id = versions[0]
    if normalize_arxiv_id(version_id) != base or (re.search(r"v[1-9]\d*$", identifier) and version_id != identifier):
        raise RetrievalError("arXiv abstract page returned a different requested version")
    history = re.sub(r"\s+", " ", "".join(parser.history)).strip()
    dates = re.findall(r"\[v1\]\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} UTC)\b", history)
    if len(dates) != 1:
        raise RetrievalError("arXiv abstract page lacks an explicit first-submission UTC timestamp")
    try:
        first = parsedate_to_datetime(dates[0])
        if first.tzinfo is None:
            raise ValueError
        first = first.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise RetrievalError("arXiv abstract page has an invalid first-submission timestamp") from None
    abstract = parser.metadata.get("citation_abstract", [])
    if len(abstract) > 1:
        raise RetrievalError("arXiv abstract page has ambiguous abstract metadata")
    title = clean(parser.single("citation_title"))
    if not title:
        raise RetrievalError("arXiv abstract page lacks a usable source title")
    return Paper(title=title, source="arxiv", source_id=version_id,
                 arxiv_id=base, url="https://arxiv.org/abs/" + version_id,
                 abstract=clean(abstract[0]) if abstract else "",
                 authors=[clean(author) for author in parser.metadata.get("citation_author", [])],
                 publication_date=first.date().isoformat(),
                 publication_date_label="arXiv 首次提交/处理日期（UTC；不是期刊发表日期）",
                 kind="arXiv 预印本；未经同行评审核实", open_access=True,
                 warnings=["arXiv API unavailable; verified official abstract-page metadata was used: " + reason],
                 provenance=[{**provenance("arxiv", {}, url), **context, "record_url": url,
                              "format": "arxiv_abstract_html", "version_id": version_id,
                              "retrieval_fallback": reason,
                              "date_fields": {"arxiv-published": first.date().isoformat(),
                                              "arxiv-published-raw": dates[0]}}])


def _crossref(client, identifier, context):
    url = CROSSREF + "/" + quote(identifier, safe="")
    params = {"mailto": client.config["contact_email"]} if client.config["contact_email"] else {}
    data = client.json(url, params=params)
    item = data.get("message")
    if (not isinstance(item, dict) or not isinstance(item.get("title"), list)
            or not item["title"] or not all(isinstance(title, str) for title in item["title"])
            or normalize_doi(item.get("DOI")) != identifier):
        raise RetrievalError("Crossref returned missing or mismatched DOI metadata")
    paper = crossref_paper(item, {**provenance("crossref", params, url), **context})
    paper.url = "https://doi.org/" + quote(identifier, safe="/")
    return paper


def _epmc(client, identifier, kind, context, optional=False):
    query = (f'DOI:"{identifier}"' if kind == "doi" else f"PMCID:{identifier}" if kind == "PMC"
             else f"EXT_ID:{identifier} AND SRC:{kind}")
    # Exact-identity lookups normally produce one result. Never silently choose
    # from a truncated set or turn an incomplete lookup into a negative result.
    params = {"query": query, "format": "json", "resultType": "core",
              "pageSize": min(client.config["page_size"], 25), "cursorMark": "*"}
    data = client.json(EPMC + "/search", params=params)
    total = data.get("hitCount")
    items = data.get("resultList", {}).get("result")
    if (type(total) is not int or total < 0 or not isinstance(items, list)
            or total != len(items) or len(items) > params["pageSize"]):
        raise RetrievalError("Europe PMC identity lookup was malformed or incomplete")
    if not items and not optional:
        raise RetrievalError("Europe PMC did not return the requested article")
    papers = []
    for item in items:
        if not isinstance(item, dict) or not item.get("title"):
            raise RetrievalError("Europe PMC returned invalid article metadata")
        source, record_id = item.get("source"), item.get("id")
        if (source not in _EPMC_IDS or not isinstance(record_id, str)
                or not re.fullmatch(_EPMC_IDS[source], record_id)):
            raise RetrievalError("Europe PMC returned an unsupported or invalid source identifier")
        matches = (normalize_doi(item.get("doi")) == identifier if kind == "doi"
                   else normalize_pmcid(item.get("pmcid")) == identifier if kind == "PMC"
                   else source == kind and record_id == identifier)
        if not matches:
            raise RetrievalError("Europe PMC returned a different identifier from the requested article")
        papers.append(epmc_paper(item, {**provenance("europepmc", params, EPMC + "/search"), **context}))
    return papers


def fetch(config, url, http=None) -> tuple[list[Paper], dict]:
    """Resolve an official article URL and retrieve source-authenticated evidence.

    Returns one or more source records (not prefiltered/deduplicated). A DOI
    lookup also retrieves Europe PMC abstract/body metadata when it is useful
    and that source is enabled. The caller can merge the returned stable IDs.
    Optional lookup/body failures are explicit report warnings; an identity
    mismatch always fails. Missing primary records and network failures raise
    RetrievalError. A successful lookup does not assert complete review coverage.
    """
    config = _settings(config)
    source, identifier, kind = _lead(url)
    _allowed(config, source)
    client = _client(config, http)
    context = {"agent_operation": "fetch", "requested_url": url,
               "requested_identifier": identifier}
    warnings, optional_lookup = [], "not_needed"
    try:
        if source == "arxiv":
            papers = [_arxiv(client, identifier, context)]
        elif source == "crossref":
            papers = [_crossref(client, identifier, context)]
            if not papers[0].abstract or config["fetch_full_text"]:
                if "europepmc" not in config["sources"]:
                    optional_lookup = "source_disabled"
                else:
                    # A mismatched response is unsafe evidence and must fail the
                    # operation. Transport errors alone permit a disclosed fallback.
                    try:
                        extra = _epmc(client, identifier, "doi", context, optional=True)
                    except RetrievalError as exc:
                        if not client.records or client.records[-1]["status"] != "error":
                            raise
                        optional_lookup = "failed"
                        warnings.append(f"Optional Europe PMC DOI lookup failed: {exc}")
                        papers[0].warnings.extend(warnings)
                    else:
                        papers.extend(extra)
                        optional_lookup = "found" if extra else "no_match"
        else:
            papers = _epmc(client, identifier, kind, context)
    except (TypeError, AttributeError, KeyError, IndexError) as exc:
        raise RetrievalError(f"Malformed {source} identity response ({type(exc).__name__})") from None
    _finish(papers, config, client)
    report = {"operation": "fetch", "source": source, "requested_url": url,
              "requested_identifier": identifier, "identity_verified": True,
              "records_before_dedup": len(papers), "complete": optional_lookup != "failed",
              "truncated": False, "retrieval_policy": config["retrieval_policy"],
              "optional_europepmc_lookup": optional_lookup, "warnings": warnings,
              "requests": client.records, "model_calls": 0,
              "full_text_requested": config["fetch_full_text"],
              "full_text_retrieved": sum(bool(paper.full_text) for paper in papers),
              "coverage_note": "Exact article lookup only; no exhaustive literature coverage is claimed."}
    return papers, report
