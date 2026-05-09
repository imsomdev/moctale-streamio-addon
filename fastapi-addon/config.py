from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class AddonConfig:
    moctale_cookie: str = ""
    tmdb_api_key: str = ""


def encode_config(config: AddonConfig) -> str:
    payload = {
        "moctale_cookie": config.moctale_cookie,
        "tmdb_api_key": config.tmdb_api_key,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_config(value: str) -> AddonConfig:
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid addon configuration") from exc

    return AddonConfig(
        moctale_cookie=str(
            data.get("moctale_cookie") or data.get("moctaleCookie") or ""
        ),
        tmdb_api_key=str(data.get("tmdb_api_key") or data.get("tmdbApiKey") or ""),
    )
