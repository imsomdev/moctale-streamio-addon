from __future__ import annotations

from typing import Any

import httpx


TMDB_BASE = "https://api.themoviedb.org/3"
_cache: dict[str, dict[str, Any]] = {}


def _cache_key(title: str, year: str, content_type: str) -> str:
    return f"{title.lower().strip()}|{year}|{content_type}"


async def _tmdb_get(endpoint: str, api_key: str) -> dict[str, Any] | None:
    if not api_key:
        return None

    separator = "&" if "?" in endpoint else "?"
    url = f"{TMDB_BASE}{endpoint}{separator}api_key={api_key}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url)
    except httpx.RequestError:
        return None

    if response.status_code >= 400:
        return None

    return response.json()


async def get_tmdb_meta(
    title: str,
    year: str = "",
    expected_type: str = "",
    api_key: str = "",
) -> dict[str, Any] | None:
    key = _cache_key(title, year, expected_type)
    if key in _cache:
        return _cache[key]

    if not api_key:
        return None

    params = httpx.QueryParams({"query": title, **({"year": year} if year else {})})
    data = await _tmdb_get(f"/search/multi?{params}", api_key)
    if not data or not data.get("results"):
        return None

    target = "tv" if expected_type == "series" else "movie"
    best = next(
        (
            result
            for result in data["results"]
            if (result.get("media_type") or ("movie" if result.get("title") else "tv")) == target
        ),
        data["results"][0],
    )

    media_type = best.get("media_type") or ("movie" if best.get("title") else "tv")
    tmdb_type = "series" if media_type == "tv" else "movie"
    external_ids = await _tmdb_get(f"/{media_type}/{best['id']}/external_ids", api_key)

    result = {
        "imdb_id": (external_ids or {}).get("imdb_id"),
        "tmdb_id": str(best["id"]),
        "type": tmdb_type,
        "poster": f"https://image.tmdb.org/t/p/w500{best['poster_path']}" if best.get("poster_path") else None,
        "description": best.get("overview"),
        "genres": [],
    }
    _cache[key] = result
    return result
