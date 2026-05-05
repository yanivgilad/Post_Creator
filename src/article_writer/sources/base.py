from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from article_writer.config import Settings
from article_writer.models import SourceItem


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


class SourceAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def enabled(self, settings: Settings) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, since: datetime, settings: Settings) -> list[SourceItem]:
        raise NotImplementedError

    def _request_headers(self, settings: Settings, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "article-writer/0.1 (+http://localhost)",
        }
        if extra:
            headers.update(extra)
        return headers

    def _get_text(self, url: str, settings: Settings, headers: dict[str, str] | None = None) -> str:
        request = Request(url, headers=self._request_headers(settings, headers))
        try:
            with urlopen(request, timeout=20) as response:
                encoding = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(encoding, errors="replace")
        except HTTPError as exc:
            raise RuntimeError(f"{self.name} request failed with status {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.name} request failed: {exc.reason}") from exc

    def _get_json(self, url: str, settings: Settings, headers: dict[str, str] | None = None) -> Any:
        return json.loads(self._get_text(url, settings, headers))

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        settings: Settings,
        headers: dict[str, str] | None = None,
    ) -> Any:
        raw_payload = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = Request(url, data=raw_payload, headers=self._request_headers(settings, request_headers), method="POST")
        try:
            with urlopen(request, timeout=20) as response:
                encoding = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(encoding, errors="replace"))
        except HTTPError as exc:
            raise RuntimeError(f"{self.name} request failed with status {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.name} request failed: {exc.reason}") from exc


def parse_datetime(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    text = value.strip()
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    value = HTML_TAG_RE.sub(" ", value)
    return WHITESPACE_RE.sub(" ", value).strip()


def truncate_text(value: str, limit: int = 320) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit - 3].rsplit(" ", 1)[0]
    return f"{shortened}..."


def matches_keywords(text: str, keywords: list[str]) -> bool:
    haystack = text.lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def iter_xml_entries(xml_text: str) -> list[ElementTree.Element]:
    root = ElementTree.fromstring(xml_text)
    entries: list[ElementTree.Element] = []
    for element in root.iter():
        local_name = element.tag.split("}")[-1].lower()
        if local_name in {"item", "entry"}:
            entries.append(element)
    return entries


def child_text(element: ElementTree.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in element:
        local_name = child.tag.split("}")[-1].lower()
        if local_name in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return None


def encoded_query(value: str) -> str:
    return quote_plus(value)
