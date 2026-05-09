from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx


BASE_URL = "https://www.moctale.in"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

TITLE_KEYS = (
    "title",
    "name",
    "original_title",
    "original_name",
    "display_title",
    "display_name",
)
POSTER_KEYS = (
    "poster",
    "poster_url",
    "posterUrl",
    "poster_path",
    "posterPath",
    "image",
    "image_url",
    "imageUrl",
    "thumbnail",
    "thumbnail_url",
    "photo",
    "backdrop",
    "backdrop_url",
    "backdropPath",
)
LINK_KEYS = ("url", "link", "href", "path", "share_url", "shareUrl", "slug")
SECTION_KEYS = ("section", "heading", "category", "provider", "platform", "ott", "label")
YEAR_KEYS = (
    "year",
    "release_year",
    "releaseYear",
    "first_air_date",
    "firstAirDate",
    "release_date",
    "releaseDate",
    "premiere",
)
SHOW_KEYS = (
    "is_show",
    "isShow",
    "is_series",
    "isSeries",
    "media_type",
    "mediaType",
    "content_type",
    "contentType",
    "type",
)
ARRAY_KEYS = {
    "items",
    "results",
    "data",
    "movies",
    "shows",
    "contents",
    "content",
    "list",
    "cards",
    "rows",
}
EXCLUDED_SECTIONS = {"page"}
YEAR_RE = re.compile(r"-(\d{4})$")


@dataclass(frozen=True)
class ScrapedItem:
    section: str
    name: str
    link: str = ""
    poster_url: str = ""
    year: str = ""
    type: str = ""


_cache: dict[str, Any] = {"expires_at": 0, "items": [], "notes": []}
_cache_lock = asyncio.Lock()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def lower_keys(obj: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in obj.items()}


def first_value(
    obj: dict[str, Any], keys: tuple[str, ...], lowered: dict[str, Any] | None = None
) -> Any:
    if lowered is None:
        lowered = lower_keys(obj)

    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value

    return ""


def absolute_url(value: Any, base_url: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if text.startswith("//"):
        return "https:" + text
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return urljoin(base_url, text)
    return text


def normalize_link(value: Any, obj: dict[str, Any], base_url: str) -> str:
    text = clean_text(value)
    if not text:
        content_id = first_value(obj, ("id", "tmdb_id", "content_id", "movie_id", "show_id"))
        return f"{base_url}/title/{content_id}" if content_id else ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return urljoin(base_url, text)
    if "/" in text:
        return urljoin(base_url, "/" + text.lstrip("/"))
    return urljoin(base_url, f"/content/{text}")


def extract_year_from_slug(value: str) -> str:
    match = YEAR_RE.search(clean_text(value))
    return match.group(1) if match else ""


def extract_year(obj: dict[str, Any], link: str) -> str:
    value = first_value(obj, YEAR_KEYS)
    if value:
        text = clean_text(value)
        if len(text) == 4 and text.isdigit():
            return text
        match = re.match(r"^(\d{4})-\d{2}-\d{2}", text)
        if match:
            return match.group(1)

    from_slug = extract_year_from_slug(link)
    if from_slug:
        return from_slug

    for key in YEAR_KEYS:
        if key in obj and isinstance(obj[key], int):
            year = obj[key]
            if 1888 <= year <= 2100:
                return str(year)

    return ""


def extract_media_type(obj: dict[str, Any], link: str, name: str) -> str:
    raw = first_value(obj, SHOW_KEYS)
    if isinstance(raw, bool):
        return "series" if raw else "movie"

    text = clean_text(raw).lower()
    if text in {"true", "show", "shows", "tv", "series", "anime", "tv show", "web series"}:
        return "series"
    if text in {"false", "movie", "movies", "film", "films"}:
        return "movie"

    if re.search(r"\bseason\s*\d|\bepisode\s*\d|\bss\d|tv\s*show|web\s*series\b", f"{name} {link}", re.I):
        return "series"

    return "movie"


def object_section_name(obj: dict[str, Any], lowered: dict[str, Any]) -> str:
    value = first_value(obj, SECTION_KEYS, lowered)
    if value:
        return clean_text(value)
    return clean_text(first_value(obj, TITLE_KEYS, lowered))


def item_from_object(
    obj: dict[str, Any], section: str, base_url: str, lowered: dict[str, Any]
) -> ScrapedItem | None:
    name_value = first_value(obj, TITLE_KEYS, lowered)
    poster_value = first_value(obj, POSTER_KEYS, lowered)

    if not name_value:
        return None
    if not poster_value:
        content_type = clean_text(first_value(obj, ("media_type", "content_type", "type"), lowered)).lower()
        if content_type not in {"movie", "movies", "show", "shows", "tv", "series", "anime"}:
            return None

    name = clean_text(name_value)
    link = normalize_link(first_value(obj, LINK_KEYS, lowered), obj, base_url)
    return ScrapedItem(
        section=section or "unknown",
        name=name,
        link=link,
        poster_url=absolute_url(poster_value, base_url),
        year=extract_year(obj, link),
        type=extract_media_type(obj, link, name),
    )


def walk_json(value: Any, section: str, base_url: str) -> list[ScrapedItem]:
    found: list[ScrapedItem] = []

    if isinstance(value, list):
        for item in value:
            found.extend(walk_json(item, section, base_url))
        return found

    if not isinstance(value, dict):
        return found

    lowered = lower_keys(value)
    item = item_from_object(value, section, base_url, lowered)
    if item:
        found.append(item)

    next_section = object_section_name(value, lowered) or section
    for key, child in value.items():
        child_section = next_section
        if isinstance(child, list) and str(key).lower() in ARRAY_KEYS:
            child_section = next_section or clean_text(key)
        found.extend(walk_json(child, child_section, base_url))

    return found


def dedupe_items(items: list[ScrapedItem]) -> list[ScrapedItem]:
    seen: set[tuple[str, str, str, str, str, str]] = set()
    unique: list[ScrapedItem] = []

    for item in items:
        if item.section.lower() in EXCLUDED_SECTIONS:
            continue
        if not (item.name or item.poster_url or item.link):
            continue

        key = (
            item.section.lower(),
            item.name.lower(),
            item.link.lower(),
            item.poster_url.lower(),
            item.year,
            item.type,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique


def parse_cookie_str(cookie: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in cookie.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def headers() -> dict[str, str]:
    return {
        "User-Agent": os.getenv("MOCTALE_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/json,text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{BASE_URL}/explore",
    }


def make_client(cookie: str) -> httpx.Client:
    return httpx.Client(
        headers=headers(),
        cookies=parse_cookie_str(cookie) if cookie else {},
        follow_redirects=True,
        timeout=30,
    )


def scrape_api(client: httpx.Client, base_url: str) -> tuple[list[ScrapedItem], str]:
    api_url = f"{base_url}/api/explore"
    try:
        response = client.get(api_url, headers={"Accept": "application/json,text/plain,*/*"})
    except httpx.RequestError as exc:
        return [], f"Request failed for {api_url}: {exc}"

    if response.status_code >= 400:
        return [], f"{api_url} returned HTTP {response.status_code}: {response.text[:200]}"

    try:
        data = response.json()
    except json.JSONDecodeError:
        return [], f"{api_url} did not return JSON. Content-Type: {response.headers.get('content-type', '')}"

    return walk_json(data, "", base_url), ""


def extract_next_json(html: str) -> list[Any]:
    blobs: list[Any] = []

    script_match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if script_match:
        try:
            blobs.append(json.loads(script_match.group(1)))
        except json.JSONDecodeError:
            pass

    for match in re.finditer(r"self\.__next_f\.push\(\[(.*?)\]\)</script>", html, re.DOTALL):
        try:
            blobs.append(json.loads("[" + match.group(1) + "]"))
        except json.JSONDecodeError:
            continue

    return blobs


def scrape_page(client: httpx.Client, base_url: str) -> tuple[list[ScrapedItem], str]:
    page_url = f"{base_url}/explore"
    try:
        response = client.get(page_url, headers={"Accept": "text/html,application/xhtml+xml,*/*"})
    except httpx.RequestError as exc:
        return [], f"Request failed for {page_url}: {exc}"

    if response.status_code >= 400:
        return [], f"{page_url} returned HTTP {response.status_code}: {response.text[:200]}"
    if str(response.url).rstrip("/") == f"{base_url}/login":
        return [], f"{page_url} redirected to login; provide an authenticated cookie"

    items: list[ScrapedItem] = []
    for blob in extract_next_json(response.text):
        items.extend(walk_json(blob, "page-data", base_url))

    return items, f"parsed {response.headers.get('content-type', '')}"


def scrape_moctale_sync(
    cookie: str,
    base_url: str = BASE_URL,
) -> tuple[list[ScrapedItem], list[str]]:
    normalized_base_url = base_url.rstrip("/")
    notes: list[str] = []
    items: list[ScrapedItem] = []

    if not cookie:
        notes.append("No MOCTALE_COOKIE provided; requests may redirect to login.")

    with make_client(cookie) as client:
        api_items, api_note = scrape_api(client, normalized_base_url)
        if api_note:
            notes.append(api_note)
        items.extend(api_items)

        page_items, page_note = scrape_page(client, normalized_base_url)
        if page_note:
            notes.append(page_note)
        items.extend(page_items)

    return dedupe_items(items), notes


async def scrape_moctale(
    cookie: str,
    base_url: str = BASE_URL,
    force: bool = False,
) -> dict[str, Any]:
    ttl = int(os.getenv("MOCTALE_CACHE_TTL_SECONDS", str(3 * 24 * 60 * 60)))

    async with _cache_lock:
        if not force and _cache["items"] and _cache["expires_at"] > time.time():
            return {
                "items": _cache["items"],
                "notes": _cache["notes"],
                "cached": True,
            }

        if not cookie and _cache["items"]:
            notes = [*_cache["notes"], "Serving stale shared cache; no cookie provided to refresh."]
            return {
                "items": _cache["items"],
                "notes": notes,
                "cached": True,
                "stale": True,
            }

        if not cookie:
            return {
                "items": [],
                "notes": ["Catalog cache is empty. Configure a Moctale cookie to refresh it."],
                "cached": False,
            }

        items, notes = await asyncio.to_thread(scrape_moctale_sync, cookie, base_url)
        if not items and _cache["items"]:
            return {
                "items": _cache["items"],
                "notes": [*notes, "Refresh failed; serving stale shared cache."],
                "cached": True,
                "stale": True,
            }

        _cache.update(
            {
                "expires_at": time.time() + ttl,
                "items": items,
                "notes": notes,
            }
        )
        return {"items": items, "notes": notes, "cached": False}


async def clear_moctale_cache() -> None:
    async with _cache_lock:
        _cache.update({"expires_at": 0, "items": [], "notes": []})


def item_to_dict(item: ScrapedItem) -> dict[str, str]:
    return {
        "section": item.section,
        "name": item.name,
        "year": item.year,
        "type": item.type,
        "link": item.link,
        "poster_url": item.poster_url,
    }
