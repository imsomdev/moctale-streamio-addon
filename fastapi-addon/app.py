from __future__ import annotations

import os
from urllib.parse import parse_qs

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from catalog import get_catalog
from config import AddonConfig, decode_config
from manifest import build_manifest
from moctale import clear_moctale_cache, item_to_dict, scrape_moctale


load_dotenv()

app = FastAPI(title="Moctale Stremio Addon")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def env_config() -> AddonConfig:
    return AddonConfig(
        moctale_cookie=os.getenv("MOCTALE_COOKIE", ""),
        tmdb_api_key=os.getenv("TMDB_API_KEY", ""),
    )


def base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def genre_from_extra(extra: str) -> str:
    parsed = parse_qs(extra, keep_blank_values=True)
    return (parsed.get("genre") or ["All"])[0] or "All"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/manifest.json")
async def manifest() -> dict:
    return build_manifest(configured=bool(env_config().moctale_cookie))


@app.get("/{encoded_config}/manifest.json")
async def configured_manifest(encoded_config: str) -> dict:
    decode_config(encoded_config)
    return build_manifest(configured=True)


@app.get("/catalog/{content_type}/{catalog_id}.json")
async def catalog(content_type: str, catalog_id: str, genre: str = "All") -> JSONResponse:
    metas, notes = await get_catalog(content_type, genre, env_config())
    return JSONResponse({"metas": metas, "warnings": notes if not metas else []})


@app.get("/catalog/{content_type}/{catalog_id}/{extra}.json")
async def catalog_with_extra(
    content_type: str,
    catalog_id: str,
    extra: str,
) -> JSONResponse:
    metas, notes = await get_catalog(content_type, genre_from_extra(extra), env_config())
    return JSONResponse({"metas": metas, "warnings": notes if not metas else []})


@app.get("/{encoded_config}/catalog/{content_type}/{catalog_id}.json")
async def configured_catalog(
    encoded_config: str,
    content_type: str,
    catalog_id: str,
    genre: str = "All",
) -> JSONResponse:
    metas, notes = await get_catalog(content_type, genre, decode_config(encoded_config))
    return JSONResponse({"metas": metas, "warnings": notes if not metas else []})


@app.get("/{encoded_config}/catalog/{content_type}/{catalog_id}/{extra}.json")
async def configured_catalog_with_extra(
    encoded_config: str,
    content_type: str,
    catalog_id: str,
    extra: str,
) -> JSONResponse:
    metas, notes = await get_catalog(
        content_type,
        genre_from_extra(extra),
        decode_config(encoded_config),
    )
    return JSONResponse({"metas": metas, "warnings": notes if not metas else []})


@app.get("/debug/moctale")
async def debug_moctale() -> dict:
    result = await scrape_moctale(env_config().moctale_cookie, force=True)
    return {
        "count": len(result["items"]),
        "sections": sorted({item.section for item in result["items"]}),
        "items": [item_to_dict(item) for item in result["items"][:5]],
        "notes": result["notes"],
        "cached": result["cached"],
        "has_cookie": bool(env_config().moctale_cookie),
    }


@app.get("/{encoded_config}/debug/moctale")
async def configured_debug_moctale(encoded_config: str) -> dict:
    config = decode_config(encoded_config)
    result = await scrape_moctale(config.moctale_cookie, force=True)
    return {
        "count": len(result["items"]),
        "sections": sorted({item.section for item in result["items"]}),
        "items": [item_to_dict(item) for item in result["items"][:5]],
        "notes": result["notes"],
        "cached": result["cached"],
        "has_cookie": bool(config.moctale_cookie),
    }


@app.post("/debug/cache/clear")
async def clear_cache() -> dict[str, str]:
    await clear_moctale_cache()
    return {"status": "cleared"}


@app.get("/configure", response_class=HTMLResponse)
async def configure(request: Request) -> str:
    origin = base_url(request)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moctale Catalog Configure</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0b0d10; color: #f3f4f6; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 32px 20px; }}
    label {{ display: block; margin: 18px 0 8px; color: #cbd5e1; font-size: 14px; }}
    textarea, input {{ width: 100%; box-sizing: border-box; border: 1px solid #334155; border-radius: 8px; background: #111827; color: #f8fafc; padding: 12px; }}
    textarea {{ min-height: 140px; resize: vertical; }}
    button, a.button {{ display: inline-flex; margin-top: 18px; border: 0; border-radius: 8px; background: #22c55e; color: #052e16; padding: 12px 16px; font-weight: 700; text-decoration: none; cursor: pointer; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #111827; border: 1px solid #334155; border-radius: 8px; padding: 12px; }}
  </style>
</head>
<body>
  <main>
    <h1>Moctale Catalog</h1>
    <label for="cookie">Moctale Cookie</label>
    <textarea id="cookie" placeholder="auth_token=...; cf_clearance=..."></textarea>
    <label for="tmdb">TMDB API Key</label>
    <input id="tmdb" placeholder="optional">
    <button id="build" type="button">Build Install URL</button>
    <pre id="output"></pre>
    <a id="install" class="button" href="#" style="display:none">Install in Stremio</a>
  </main>
  <script>
    const origin = {origin!r};
    function base64url(value) {{
      const bytes = new TextEncoder().encode(value);
      let binary = "";
      bytes.forEach((byte) => binary += String.fromCharCode(byte));
      return btoa(binary).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
    }}
    document.getElementById("build").addEventListener("click", () => {{
      const config = {{
        moctale_cookie: document.getElementById("cookie").value.trim(),
        tmdb_api_key: document.getElementById("tmdb").value.trim()
      }};
      const encoded = base64url(JSON.stringify(config));
      const manifestUrl = `${{origin}}/${{encoded}}/manifest.json`;
      const manifest = new URL(manifestUrl);
      const stremioUrl = `stremio://${{manifest.host}}${{manifest.pathname}}`;
      document.getElementById("output").textContent = manifestUrl;
      const install = document.getElementById("install");
      install.href = stremioUrl;
      install.style.display = "inline-flex";
    }});
  </script>
</body>
</html>"""
