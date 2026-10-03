"""Agent-selected original figures: evidence, bounded retrieval and MIME snapshots.

No image generation or scientific figure selection occurs here. The agent names
an actual paper figure and explains it; the program verifies source bytes and
rights anchors, then freezes approved raster assets for reliable inline email.
"""
from __future__ import annotations

import base64
import hashlib
import io
import warnings
import http.client
import ipaddress
import os
import re
import socket
import ssl
import struct
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, proxy_bypass
from urllib.error import HTTPError

from .models import clean, normalize_arxiv_id, normalize_pmcid
from .sources import safe_figure_url, _reuse_license

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_INLINE_IMAGES = 30
# Managed HTTPS proxies resolve DNS remotely. Keep that route restricted to
# exact institutional services, never a caller-controlled suffix or CDN.
PROXY_SOURCE_HOSTS = {"arxiv.org", "export.arxiv.org", "pmc.ncbi.nlm.nih.gov", "europepmc.org"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
MANIFEST_FIELDS = {"paper_key", "id", "caption", "explanation", "source_url", "url", "attribution", "license", "license_scope", "license_url", "license_evidence", "rights_basis", "original", "omission_reason"}


def _public_addresses(host):
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise ValueError("Figure host DNS lookup failed") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast for address in addresses):
        raise ValueError("Figure URL resolved to a private or non-public address")
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=40, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Pin the validated destination, but retain original SNI/hostname checks.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch_public(url, maximum):
    """Public HTTPS only, DNS pinning, revalidation on every redirect; no cookies."""
    for _ in range(4):
        if not safe_figure_url(url):
            raise ValueError("Figure retrieval requires a public HTTPS URL")
        parsed = urlsplit(url)
        if (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")) and not proxy_bypass(parsed.hostname):
            if parsed.hostname not in PROXY_SOURCE_HOSTS:
                raise ValueError("Proxy figure retrieval is restricted to exact official source hosts")
            request = Request(url, headers={"User-Agent": "SuperPaperRadar/3.1", "Accept-Encoding": "identity"})
            try:
                response = build_opener(_NoRedirect()).open(request, timeout=40)
            except HTTPError as exc:
                response = exc
            with response:
                if response.code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location", "")
                    if not location:
                        raise ValueError("Figure redirect omitted its destination")
                    url = urljoin(url, location)
                    continue
                if response.code != 200:
                    raise ValueError(f"Figure source returned HTTP {response.code}")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("Compressed figure transfer is unsupported")
                length = response.headers.get("Content-Length", "")
                if length and (not length.isdigit() or int(length) > maximum):
                    raise ValueError("Figure response exceeds byte limit")
                raw = response.read(maximum + 1)
                if len(raw) > maximum:
                    raise ValueError("Figure response exceeds byte limit")
                return raw, response.headers.get_content_type(), url
        addresses = _public_addresses(parsed.hostname)
        connection = _PinnedHTTPS(parsed.hostname, addresses[0])
        try:
            connection.request("GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                               headers={"User-Agent": "SuperPaperRadar/3.1", "Accept": "text/html,image/png,image/jpeg;q=0.9", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location", "")
                if not location:
                    raise ValueError("Figure redirect omitted its destination")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"Figure source returned HTTP {response.status}")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("Compressed figure transfer is unsupported")
            length = response.getheader("Content-Length", "")
            if length and (not length.isdigit() or int(length) > maximum):
                raise ValueError("Figure response exceeds byte limit")
            body = response.read(maximum + 1)
            if len(body) > maximum:
                raise ValueError("Figure response exceeds byte limit")
            return body, response.getheader("Content-Type", "").split(";", 1)[0].lower(), url
        finally:
            connection.close()
    raise ValueError("Too many figure redirects")


class _Page(HTMLParser):
    def __init__(self, raw, url):
        super().__init__(convert_charrefs=True)
        self.url, self.parts, self.images, self.links, self.skip = url, [], set(), set(), 0
        self.rights_links, self.license_links, self.stack = set(), set(), []
        self.feed(raw.decode("utf-8", errors="replace"))
        self.text = re.sub(r"\s+", " ", " ".join(self.parts)).strip()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        rights_context = any(context for _, context in self.stack) or bool(re.search(r"copyright|licen[cs]e", attrs.get("id", "") + " " + attrs.get("class", ""), re.I))
        if tag not in {"img", "link", "meta", "br", "hr", "input", "source", "wbr"}:
            self.stack.append((tag, rights_context))
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "img":
            for field in ("src", "data-src", "data-original"):
                if attrs.get(field):
                    self.images.add(urljoin(self.url, attrs[field]))
        if tag in ("a", "link") and attrs.get("href"):
            link = urljoin(self.url, attrs["href"])
            self.links.add(link)
            if attrs.get("title", "").lower() == "rights to this article":
                self.rights_links.add(link)
            if rights_context:
                self.license_links.add(link)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def image_type(raw):
    """Fully decode bounded PNG/JPEG; reject malformed rasters and decompression bombs."""
    from PIL import Image, UnidentifiedImageError
    if not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ValueError("Figure image exceeds byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise ValueError("Only original PNG/JPEG figure assets are supported")
                width, height = image.size
                if not width or not height or width > 20000 or height > 20000 or width * height > 80_000_000:
                    raise ValueError("Figure raster dimensions are invalid or too large")
                kind = image.format
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
    except (OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Figure raster could not be decoded safely") from exc
    return ("image/png", "png") if kind == "PNG" else ("image/jpeg", "jpg")


def validate_inline_images(images):
    if not isinstance(images, list) or len(images) > MAX_INLINE_IMAGES:
        raise ValueError("Invalid inline image attachment list")
    names, cids, total = set(), set(), 0
    required = {"filename", "content_type", "content_base64", "content_id", "sha256", "size_bytes"}
    for item in images:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Invalid inline image attachment fields")
        name, cid = item["filename"], item["content_id"]
        if (not isinstance(name, str) or not re.fullmatch(r"figure-[a-f0-9]{64}\.(?:png|jpg)", name)
                or name in names or not isinstance(cid, str) or not re.fullmatch(r"figure-[a-f0-9]{64}@super-paper-radar", cid) or cid in cids):
            raise ValueError("Invalid or duplicate inline image filename/Content-ID")
        if not isinstance(item["content_base64"], str) or len(item["content_base64"]) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ValueError("Inline image exceeds byte limit")
        try:
            raw = base64.b64decode(item["content_base64"], validate=True)
        except (ValueError, TypeError):
            raise ValueError("Invalid inline image base64") from None
        digest = hashlib.sha256(raw).hexdigest()
        mime, extension = image_type(raw)
        if (not 0 < len(raw) <= MAX_IMAGE_BYTES or type(item["size_bytes"]) is not int or item["size_bytes"] != len(raw)
                or item["sha256"] != digest or item["content_type"] != mime
                or name != f"figure-{digest}.{extension}" or cid != f"figure-{digest}@super-paper-radar"):
            raise ValueError("Inline image integrity or MIME check failed")
        total += len(raw)
        names.add(name); cids.add(cid)
    if total > MAX_TOTAL_BYTES:
        raise ValueError("Inline images exceed total byte limit")
    return images


def _paper_page(paper, url):
    """Bind supported article pages to the ingested identifier, never bibliography text."""
    if not safe_figure_url(url):
        return False
    parsed = urlsplit(url)
    if parsed.query:
        return False
    if parsed.hostname in ("arxiv.org", "export.arxiv.org"):
        match = re.fullmatch(r"/(?:abs|html)/(\d{4}\.\d{4,5}(?:v\d+)?)/?", parsed.path)
        return bool(match and paper.arxiv_id and normalize_arxiv_id(match[1]) == normalize_arxiv_id(paper.arxiv_id))
    if parsed.hostname in ("pmc.ncbi.nlm.nih.gov", "europepmc.org"):
        match = re.fullmatch(r"/articles/(PMC\d+)/?", parsed.path, re.I)
        return bool(match and paper.pmcid and normalize_pmcid(match[1]) == normalize_pmcid(paper.pmcid))
    return False


def _license_code(value):
    value = clean(value).lower().strip().rstrip("/")
    if re.fullmatch(r"cc0(?: 1\.0)?", value) or value in ("https://creativecommons.org/publicdomain/zero/1.0", "http://creativecommons.org/publicdomain/zero/1.0"):
        return "zero/1.0"
    match = re.fullmatch(r"cc[ -](by(?:-nc-sa)?) (1\.0|2\.0|2\.5|3\.0|4\.0)", value)
    if not match:
        match = re.fullmatch(r"https?://creativecommons\.org/licenses/(by(?:-nc-sa)?)/(1\.0|2\.0|2\.5|3\.0|4\.0)", value)
    return "/".join(match.groups()) if match else ""


def register_figure(manifest, paper, mode, fetcher=None, reuse_context="general", evidence_dir=None):
    """Validate the agent's named original. Return metadata and optional frozen bytes.

    A permissive license is evidence-gated, never inferred from arXiv metadata
    CC0 or from open access. Semantics and third-party credits still need review.
    """
    fetcher = fetcher or fetch_public
    if not isinstance(manifest, dict) or set(manifest) - MANIFEST_FIELDS:
        raise ValueError("Unknown figure manifest fields")
    for key in ("paper_key", "source_url"):
        if not isinstance(manifest.get(key), str) or not 1 <= len(manifest[key].strip()) <= (4000 if key == "caption" else 2000):
            raise ValueError("Figure manifest requires bounded " + key)
    for key, value in manifest.items():
        if key != "original" and (not isinstance(value, str) or len(value) > 4000):
            raise ValueError("Figure manifest fields must be bounded text")
    if manifest.get("original") is not True or manifest["paper_key"] != paper.key:
        raise ValueError("Figure must be explicitly original and belong to the ingested paper")
    if not safe_figure_url(manifest["source_url"]):
        raise ValueError("Figure requires a safe source URL")
    if manifest.get("license_scope", "unknown") not in ("figure", "article", "unknown"):
        raise ValueError("Figure license scope is invalid")
    figure = {**manifest, "embed_allowed": False, "provenance": {"source": "agent_verified_original", "retrieved_at": datetime.now(timezone.utc).isoformat()}}
    for key in ("id", "caption", "explanation", "attribution"):
        figure.setdefault(key, "")
    figure.setdefault("omission_reason", "Reuse permission is not verified; see the original figure.")
    license_code = _license_code(manifest.get("license", ""))
    reusable = bool(license_code) and (not license_code.startswith("by-nc-sa/") or reuse_context == "personal_noncommercial")
    if mode != "embed" or not reusable or manifest.get("license_scope") not in ("figure", "article"):
        return figure, None
    required = ("id", "caption", "explanation", "attribution", "url", "license_url", "license_evidence", "rights_basis")
    if any(not manifest.get(key) for key in required) or not safe_figure_url(manifest["url"]) or not safe_figure_url(manifest["license_url"]):
        return figure, None
    if not 12 <= len(clean(manifest["license_evidence"])) <= 1000:
        raise ValueError("License evidence must be a short exact source quotation")
    # Explicitly reject metadata API terms as permission to redistribute figures.
    if re.search(r"(?:api|help|about|metadata)(?:[./_-]|$)", urlsplit(manifest["license_url"]).path.lower()):
        raise ValueError("Metadata/API terms cannot license paper figures")
    if not _paper_page(paper, manifest["source_url"]) or not _paper_page(paper, manifest["license_url"]):
        raise ValueError("Figure source and license must be exact ingested official article pages")
    source_id = urlsplit(manifest["source_url"]).path.rstrip("/").rsplit("/", 1)[-1]
    license_id = urlsplit(manifest["license_url"]).path.rstrip("/").rsplit("/", 1)[-1]
    if source_id != license_id:
        raise ValueError("Figure and license article versions must match exactly")
    source_raw, source_type, source_final = fetcher(manifest["source_url"], MAX_PAGE_BYTES)
    if source_type not in ("text/html", "application/xhtml+xml"):
        raise ValueError("Figure source must be the actual paper HTML page")
    source_page = _Page(source_raw, source_final)
    if not _paper_page(paper, source_final) or urlsplit(source_final).path.rstrip("/").rsplit("/", 1)[-1] != source_id:
        raise ValueError("Figure page does not identify the ingested paper")
    if manifest["url"] not in source_page.images:
        raise ValueError("Figure image URL is not present in the source paper HTML")
    if clean(manifest["caption"]) not in source_page.text:
        raise ValueError("Original figure caption is not an exact source quotation")
    if manifest["license_url"] == manifest["source_url"]:
        license_raw, license_type, license_final = source_raw, source_type, source_final
    else:
        license_raw, license_type, license_final = fetcher(manifest["license_url"], MAX_PAGE_BYTES)
    license_page = _Page(license_raw, license_final)
    if (license_type not in ("text/html", "application/xhtml+xml") or not _paper_page(paper, license_final)
            or urlsplit(license_final).path.rstrip("/").rsplit("/", 1)[-1] != license_id
            or clean(manifest["license_evidence"]) not in license_page.text
            or license_code not in {_license_code(link) for link in license_page.links}):
        raise ValueError("Paper-specific permissive license evidence could not be verified")
    bound_links = license_page.rights_links if urlsplit(manifest["license_url"]).hostname in ("arxiv.org", "export.arxiv.org") else license_page.license_links
    if license_code not in {_license_code(link) for link in bound_links}:
        raise ValueError("Figure reuse requires the matching article-specific rights link")
    raw, mime, final_url = fetcher(manifest["url"], MAX_IMAGE_BYTES)
    actual_type, extension = image_type(raw)
    if mime != actual_type or not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ValueError("Figure image MIME or byte limit failed")
    digest = hashlib.sha256(raw).hexdigest()
    asset = {"filename": f"figure-{digest}.{extension}", "content_id": f"figure-{digest}@super-paper-radar", "content_type": mime,
             "content_base64": base64.b64encode(raw).decode(), "sha256": digest, "size_bytes": len(raw)}
    validate_inline_images([asset])
    figure.update(embed_allowed=True, verified_original=True, reuse_context=reuse_context, omission_reason="", content_id=asset["content_id"], asset_sha256=digest)
    if evidence_dir is not None:
        directory = Path(evidence_dir)
        if directory.is_symlink():
            raise ValueError("Figure evidence directory cannot be a symlink")
        directory.mkdir(exist_ok=True)
        snapshots = []
        for label, content in (("source", source_raw), ("license", license_raw)):
            checksum = hashlib.sha256(content).hexdigest()
            path = directory / (checksum + ".html")
            if path.exists():
                if path.is_symlink() or path.read_bytes() != content:
                    raise ValueError("Figure evidence snapshot integrity failed")
            else:
                with path.open("xb") as handle:
                    handle.write(content)
                path.chmod(0o600)
            snapshots.append({"kind": label, "filename": path.name, "sha256": checksum})
        figure["provenance"]["snapshots"] = snapshots
    figure["provenance"].update(source_url=source_final, source_sha256=hashlib.sha256(source_raw).hexdigest(),
                                license_url=license_final, license_sha256=hashlib.sha256(license_raw).hexdigest(), asset_url=final_url,
                                license_evidence_verified=True, license_href=next(link for link in bound_links if _license_code(link) == license_code),
                                matched_license_evidence=clean(manifest["license_evidence"]), semantic_review_required=True)
    return figure, asset
