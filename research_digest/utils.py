from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, Optional

USER_AGENT = "ResearchDigestBot/1.0 (+local-app)"


class HTTPError(Exception):
    pass


def http_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> bytes:
    if params:
        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status >= 400:
            raise HTTPError(f"HTTP {response.status}: {url}")
        return response.read()


def http_get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    body = http_get(url, params=params, timeout=timeout)
    return json.loads(body.decode("utf-8", errors="replace"))


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_date_parts(parts: Iterable[int]) -> Optional[date]:
    values = list(parts)
    if not values:
        return None
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_pub_date(value: str) -> Optional[date]:
    value = value.strip()
    # ISO-ish date
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.date()
        except ValueError:
            continue

    # RFC822-style dates often used in RSS.
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError):
        return None


def within_window(d: date, end: date, days: int) -> bool:
    start = end - timedelta(days=max(days - 1, 0))
    return start <= d <= end


def safe_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.lower()
    return doi or None
