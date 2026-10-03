from __future__ import annotations

import json
import random
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class RetrievalError(RuntimeError):
    """A failed or incomplete source must never become 'no new papers'."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # API redirects are unexpected: never forward bearer tokens or downgrade TLS.
        raise RetrievalError("API 重定向已拒绝；请核对官方地址")


class HttpClient:
    def __init__(self, contact_email="", timeout=45, retries=3, opener=None, sleeper=time.sleep):
        self.timeout, self.retries = timeout, retries
        self.opener, self.sleeper = opener or build_opener(NoRedirect()).open, sleeper
        self.user_agent = "LiteratureDigest/2.0" + (f" (mailto:{contact_email})" if contact_email else "")
        self.last_request: dict[str, float] = {}

    def request(self, url, params=None, payload=None, headers=None, interval=1.0):
        if urlsplit(url).scheme != "https":
            raise RetrievalError("仅允许 HTTPS API 地址")
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        host = urlsplit(url).hostname
        for attempt in range(self.retries):
            delay = interval - (time.monotonic() - self.last_request.get(host, 0))
            if delay > 0:
                self.sleeper(delay)
            self.last_request[host] = time.monotonic()
            data = json.dumps(payload).encode() if payload is not None else None
            req = Request(url, data=data, headers={"User-Agent": self.user_agent, "Accept": "application/json", **({"Content-Type": "application/json"} if data else {}), **(headers or {})})
            try:
                with self.opener(req, timeout=self.timeout) as response:
                    # Resource bound prevents unexpected giant responses.
                    raw = response.read(20_000_001)
                    if len(raw) > 20_000_000:
                        raise RetrievalError(f"{host} 响应超过安全上限")
                    return raw
            except HTTPError as exc:
                if exc.code not in (408, 429, 500, 502, 503, 504) or attempt + 1 == self.retries:
                    raise RetrievalError(f"{host} HTTP {exc.code}") from None
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    wait = float(retry_after)
                except ValueError:
                    try:
                        wait = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError):
                        wait = 2 ** attempt + random.random()
                self.sleeper(min(120, max(0, wait)))
            except (URLError, OSError, TimeoutError) as exc:
                if attempt + 1 == self.retries:
                    raise RetrievalError(f"{host} 网络连接失败（{type(exc).__name__}）") from None
                self.sleeper(2 ** attempt + random.random())
        raise RetrievalError(f"{host} 请求失败")

    def json(self, *args, **kwargs):
        try:
            return json.loads(self.request(*args, **kwargs))
        except (ValueError, UnicodeError):
            raise RetrievalError("API 返回了无效 JSON") from None
