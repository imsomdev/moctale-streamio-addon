from __future__ import annotations


GENRES = [
    "All",
    "Talk Of The Town",
    "Watch It With District",
    "Editors Pick",
    "Netflix",
    "JioHotstar",
    "Prime",
    "Crunchyroll",
]


def _catalog(content_type: str, name: str) -> dict:
    return {
        "id": "moctale-all",
        "type": content_type,
        "name": name,
        "extra": [
            {
                "name": "genre",
                "options": GENRES,
                "isRequired": False,
            }
        ],
    }


def build_manifest(configured: bool = False) -> dict:
    return {
        "id": "org.moctale.catalog",
        "version": "1.0.0",
        "name": "Moctale Catalog",
        "description": "Movies and shows curated from moctale.in",
        "logo": "https://www.moctale.in/favicon.ico",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "catalogs": [
            _catalog("movie", "Moctale - Movies"),
            _catalog("series", "Moctale - Series"),
        ],
        "behaviorHints": {
            "adult": False,
            "configurable": True,
            "configurationRequired": not configured,
        },
        "idPrefixes": ["moctale-", "tt"],
    }
