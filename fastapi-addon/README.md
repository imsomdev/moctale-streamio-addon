# Moctale FastAPI Stremio Addon

Deploy this folder to Beamup.

```powershell
cd fastapi-addon
beamup
```

Set secrets on Beamup:

```powershell
beamup secrets MOCTALE_COOKIE "auth_token=...; cf_clearance=..."
beamup secrets TMDB_API_KEY "optional_tmdb_key"
```

Local run:

```powershell
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 7000 --reload
```

Endpoints:

- `/manifest.json`
- `/catalog/movie/moctale-all.json?genre=All`
- `/catalog/series/moctale-all.json?genre=All`
- `/configure`
- `/debug/moctale`
