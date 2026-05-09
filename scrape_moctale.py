from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load .env automatically (MOCTALE_COOKIE="session=abc123; other=val")
load_dotenv()

BASE_URL = "https://www.moctale.in"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE_URL}/explore",
}

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
LINK_KEYS = (
    "url",
    "link",
    "href",
    "path",
    "share_url",
    "shareUrl",
    "slug",
)
SECTION_KEYS = (
    "section",
    "heading",
    "category",
    "provider",
    "platform",
    "ott",
    "label",
)
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

ARRAY_KEYS = (
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
)


@dataclass(frozen=True)
class ScrapedItem:
    section: str
    name: str
    link: str = ""
    poster_url: str = ""
    year: str = ""
    type: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def parse_html_items(html: str, base_url: str) -> list[ScrapedItem]:
    """Extract image/link items from rendered HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    items: list[ScrapedItem] = []
    for img in soup.find_all("img"):
        poster = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-nimg")
            or (img.get("srcset", "").split(" ", 1)[0])
        )
        if not poster:
            continue
        name = img.get("alt") or img.get("title") or ""
        if not name or name.lower() in {"content poster", "poster", "image"}:
            name = ""
        parent_a = img.find_parent("a")
        link = (
            urljoin(base_url, parent_a["href"])
            if parent_a and parent_a.get("href")
            else ""
        )
        items.append(
            ScrapedItem(
                section="page",
                name=clean_text(name),
                link=link,
                poster_url=absolute_url(poster, base_url),
                year=extract_year_from_slug(link),
                type="movie",
            )
        )
    return items


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def absolute_url(value: Any, base_url: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if text.startswith("//"):
        return "https:" + text
    if text.startswith("/"):
        return urljoin(base_url, text)
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return urljoin(base_url, f"/content/{text}")


_YEAR_RE = re.compile(r"-(\d{4})$")


def extract_year_from_slug(slug: str) -> str:
    m = _YEAR_RE.search(slug)
    return m.group(1) if m else ""


def extract_year(value: Any, obj: dict[str, Any], link: str) -> str:
    from_api = first_value(obj, YEAR_KEYS)
    if from_api:
        year = clean_text(from_api)
        if len(year) == 4 and year.isdigit():
            return year

    from_slug = extract_year_from_slug(link)
    if from_slug:
        return from_slug

    for key in YEAR_KEYS:
        if key in obj and isinstance(obj[key], (int, float)):
            y = str(int(obj[key]))
            if 1888 <= int(y) <= 2100:
                return y
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

    # Fallback: check name/link for series hints
    series_patterns = re.compile(r"\bseason\s*\d|\bepisode\s*\d|\bss\d|part\s*\d+\s*:\s*|tv\s*show|web\s*series\b", re.IGNORECASE)
    if series_patterns.search(name) or series_patterns.search(link):
        return "series"
    return "movie"


def lower_keys(obj: dict[str, Any]) -> dict[str, Any]:
    return {str(k).lower(): v for k, v in obj.items()}


def first_value(obj: dict[str, Any], keys: tuple[str, ...], lowered: dict[str, Any] | None = None) -> Any:
    if lowered is None:
        lowered = lower_keys(obj)
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return ""


def normalize_possible_link(value: Any, obj: dict[str, Any], base_url: str) -> str:
    text = clean_text(value)
    if not text:
        content_id = first_value(
            obj, ("id", "tmdb_id", "content_id", "movie_id", "show_id")
        )
        if content_id:
            return f"{base_url}/title/{content_id}"
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return urljoin(base_url, text)
    if "/" in text:
        return urljoin(base_url, "/" + text.lstrip("/"))
    return text


def object_section_name(obj: dict[str, Any], lowered: dict[str, Any] | None = None) -> str:
    value = first_value(obj, SECTION_KEYS, lowered)
    if value:
        return clean_text(value)
    return clean_text(first_value(obj, TITLE_KEYS, lowered))


def item_from_object(
    obj: dict[str, Any], section: str, base_url: str, lowered: dict[str, Any] | None = None
) -> ScrapedItem | None:
    if lowered is None:
        lowered = lower_keys(obj)

    name_val = first_value(obj, TITLE_KEYS, lowered)
    poster_val = first_value(obj, POSTER_KEYS, lowered)

    if not name_val:
        return None
    if not poster_val:
        content_type = clean_text(
            first_value(obj, ("media_type", "content_type", "type"), lowered)
        ).lower()
        if content_type not in {"movie", "movies", "show", "shows", "tv", "series", "anime"}:
            return None

    name = clean_text(name_val)
    poster = absolute_url(poster_val, base_url)
    link = normalize_possible_link(first_value(obj, LINK_KEYS, lowered), obj, base_url)
    year = extract_year(obj, obj, link)
    media_type = extract_media_type(obj, link, name)

    return ScrapedItem(
        section=section or "unknown",
        name=name,
        link=link,
        poster_url=poster,
        year=year,
        type=media_type,
        raw=obj,
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
    """Parse 'key=val; key2=val2' cookie string into a dict."""
    cookies: dict[str, str] = {}
    for part in cookie.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def make_client(cookie: str) -> httpx.Client:
    return httpx.Client(
        headers=HEADERS,
        cookies=parse_cookie_str(cookie) if cookie else {},
        follow_redirects=True,
        timeout=30,
    )


def scrape_api(client: httpx.Client, base_url: str) -> tuple[list[ScrapedItem], str]:
    api_url = f"{base_url}/api/explore"
    try:
        resp = client.get(
            api_url, headers={"Accept": "application/json,text/plain,*/*"}
        )
    except httpx.RequestError as exc:
        return [], f"Request failed for {api_url}: {exc}"
    if resp.status_code >= 400:
        return [], f"{api_url} returned HTTP {resp.status_code}: {resp.text[:200]}"
    try:
        data = resp.json()
    except Exception:
        return (
            [],
            f"{api_url} did not return JSON. Content-Type: {resp.headers.get('content-type', '')}",
        )
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

    for match in re.finditer(
        r"self\.__next_f\.push\(\[(.*?)\]\)</script>", html, re.DOTALL
    ):
        try:
            blobs.append(json.loads("[" + match.group(1) + "]"))
        except json.JSONDecodeError:
            continue

    return blobs


def scrape_page(client: httpx.Client, base_url: str) -> tuple[list[ScrapedItem], str]:
    page_url = f"{base_url}/explore"
    try:
        resp = client.get(
            page_url, headers={"Accept": "text/html,application/xhtml+xml,*/*"}
        )
    except httpx.RequestError as exc:
        return [], f"Request failed for {page_url}: {exc}"
    if resp.status_code >= 400:
        return [], f"{page_url} returned HTTP {resp.status_code}: {resp.text[:200]}"
    if str(resp.url).rstrip("/") == f"{base_url}/login":
        return [], f"{page_url} redirected to login; provide an authenticated cookie"

    html = resp.text
    items: list[ScrapedItem] = []
    for blob in extract_next_json(html):
        items.extend(walk_json(blob, "page-data", base_url))
    items.extend(parse_html_items(html, base_url))

    hint = (
        "login page"
        if "/login" in html[:5000]
        else resp.headers.get("content-type", "")
    )
    return items, f"parsed {hint}"


def scrape_page_playwright(base_url: str, cookie: str) -> tuple[list[ScrapedItem], str]:
    """Render the explore page with headless Chromium via Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], (
            "playwright not installed; run: "
            "pip install playwright && playwright install chromium"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        if cookie:
            context.add_cookies(
                [
                    {"name": k, "value": v, "url": base_url}
                    for k, v in parse_cookie_str(cookie).items()
                ]
            )
        page = context.new_page()
        page.goto(f"{base_url}/explore", wait_until="networkidle")
        html = page.content()
        final_url = page.url
        browser.close()

    if final_url.rstrip("/") == f"{base_url.rstrip('/')}/login":
        return [], "playwright: redirected to login; check your cookie"

    items: list[ScrapedItem] = []
    for blob in extract_next_json(html):
        items.extend(walk_json(blob, "page-data", base_url))
    items.extend(parse_html_items(html, base_url))
    return items, "playwright render"


def write_json(items: list[ScrapedItem], output_path: str) -> None:
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in items:
        grouped.setdefault(item.section, []).append(
            {
                "name": item.name,
                "year": item.year,
                "type": item.type,
                "link": item.link,
                "poster_url": item.poster_url,
            }
        )

    payload = {
        "source": f"{BASE_URL}/explore",
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_items": len(items),
        "sections": grouped,
    }
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def write_csv(items: list[ScrapedItem], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file, fieldnames=["section", "name", "year", "type", "link", "poster_url"]
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "section": item.section,
                    "name": item.name,
                    "year": item.year,
                    "type": item.type,
                    "link": item.link,
                    "poster_url": item.poster_url,
                }
            )


def get_cookie_default() -> str:
    # load_dotenv() already ran at module level; os.getenv is sufficient
    return os.getenv("MOCTALE_COOKIE", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape movie/show names, links, and poster URLs from Moctale explore."
    )
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--cookie", default=get_cookie_default())
    parser.add_argument("--json", default="moctale_items.json", dest="json_path")
    parser.add_argument("--csv", default="moctale_items.csv", dest="csv_path")
    parser.add_argument(
        "--page-only",
        action="store_true",
        help="Skip /api/explore and only parse the /explore HTML page.",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Use headless Chromium via Playwright instead of plain HTTP (handles JS-heavy pages).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cookie = clean_text(args.cookie)
    base_url = args.base_url.rstrip("/")
    errors: list[str] = []
    items: list[ScrapedItem] = []

    if not cookie:
        print(
            "No cookie provided. Public scraping may be redirected to login.",
            file=sys.stderr,
        )

    if args.playwright:
        pw_items, pw_msg = scrape_page_playwright(base_url, cookie)
        if pw_msg:
            errors.append(pw_msg)
        items.extend(pw_items)
    else:
        with make_client(cookie) as client:
            if not args.page_only:
                api_items, api_error = scrape_api(client, base_url)
                if api_error:
                    errors.append(api_error)
                items.extend(api_items)

            page_items, page_message = scrape_page(client, base_url)
            errors.append(page_message)
            items.extend(page_items)

    items = dedupe_items(
        [item for item in items if item.name or item.poster_url or item.link]
    )

    write_json(items, args.json_path)
    write_csv(items, args.csv_path)

    print(f"Scraped {len(items)} items")
    print(f"Wrote {args.json_path}")
    print(f"Wrote {args.csv_path}")
    if errors:
        print("\nNotes:")
        for error in errors:
            print(f"- {error}")

    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
