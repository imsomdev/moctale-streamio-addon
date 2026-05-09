from __future__ import annotations

import base64
import re

from config import AddonConfig
from moctale import ScrapedItem, scrape_moctale
from tmdb import get_tmdb_meta


def infer_type(name: str, year: str) -> str:
    if re.search(r"\b(season|episode|series|show)\b", name, re.I):
        return "series"
    if year and int(year) <= 2100:
        return "movie"
    return "movie"


def section_matches_filter(section: str, genre_filter: str) -> bool:
    section_lower = section.lower()
    filter_lower = (genre_filter or "All").lower()

    if filter_lower == "all":
        return True

    section_flat = re.sub(r"\s+", "", section_lower)
    filter_flat = re.sub(r"\s+", "", filter_lower)

    if filter_flat == "editorspick":
        return "editor" in section_lower

    return filter_flat in section_flat or section_flat in filter_flat


def generate_id(item: ScrapedItem) -> str:
    if item.link:
        slug = item.link.rstrip("/").split("/")[-1]
        if slug:
            return f"moctale-{slug}"

    raw = f"{item.name}|{item.section}".encode("utf-8")
    digest = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")[:16]
    return f"moctale-{digest}"


async def get_catalog(
    content_type: str,
    genre_filter: str,
    config: AddonConfig,
) -> tuple[list[dict], list[str]]:
    scrape = await scrape_moctale(config.moctale_cookie)
    metas: list[dict] = []

    for item in scrape["items"]:
        if not section_matches_filter(item.section, genre_filter):
            continue

        tmdb = await get_tmdb_meta(
            item.name,
            item.year,
            item.type,
            config.tmdb_api_key,
        )
        meta_type = item.type or (tmdb or {}).get("type") or infer_type(item.name, item.year)
        if meta_type != content_type:
            continue

        description_parts = [item.section]
        if item.year:
            description_parts.append(item.year)

        metas.append(
            {
                "id": (tmdb or {}).get("imdb_id") or generate_id(item),
                "type": meta_type,
                "name": item.name,
                "poster": (tmdb or {}).get("poster") or item.poster_url,
                "description": (tmdb or {}).get("description") or " - ".join(description_parts),
                "genres": (tmdb or {}).get("genres") or [],
                **({"year": item.year} if item.year else {}),
            }
        )

    return metas, scrape["notes"]
