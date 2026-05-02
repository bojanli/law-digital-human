import html
import logging
import re
from dataclasses import dataclass
from urllib import parse, request


logger = logging.getLogger(__name__)
_OPENER = request.build_opener(request.ProxyHandler({}))


@dataclass
class WebSearchHit:
    title: str
    snippet: str
    url: str


def search_public_web(query: str, limit: int = 5, timeout_sec: int = 20) -> list[WebSearchHit]:
    text = (query or "").strip()
    if not text:
        return []

    endpoint = "https://html.duckduckgo.com/html/?q=" + parse.quote(text)
    req = request.Request(
        endpoint,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
        method="GET",
    )

    try:
        with _OPENER.open(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("public web search failed: %s", exc)
        return []

    hits: list[WebSearchHit] = []
    for block in re.findall(r"<div class=\"result__body\">(.*?)</div>\s*</div>", body, re.DOTALL):
        title_match = re.search(r'<a[^>]*class=\"result__a\"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not title_match:
            continue
        raw_url = html.unescape(title_match.group(1))
        url = _unwrap_duckduckgo_url(raw_url)
        title = _clean_html(title_match.group(2))
        snippet_match = re.search(r'<a[^>]*class=\"result__snippet\"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not snippet_match:
            snippet_match = re.search(r'<div[^>]*class=\"result__snippet\"[^>]*>(.*?)</div>', block, re.DOTALL)
        snippet = _clean_html(snippet_match.group(1)) if snippet_match else ""
        if not title or not url:
            continue
        hits.append(WebSearchHit(title=title, snippet=snippet[:180], url=url))
        if len(hits) >= limit:
            break
    return hits


def _unwrap_duckduckgo_url(raw_url: str) -> str:
    if "duckduckgo.com/l/?" not in raw_url:
        return raw_url
    parsed = parse.urlparse(raw_url)
    qs = parse.parse_qs(parsed.query)
    uddg = qs.get("uddg", [""])[0]
    return parse.unquote(uddg) if uddg else raw_url


def _clean_html(content: str) -> str:
    text = re.sub(r"<[^>]+>", " ", content or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
