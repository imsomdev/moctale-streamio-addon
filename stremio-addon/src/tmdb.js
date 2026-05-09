import fs from "node:fs";
import path from "node:path";

const CACHE_FILE = path.resolve("tmdb_cache.json");
const TMDB_BASE = "https://api.themoviedb.org/3";
const API_KEY = process.env.TMDB_API_KEY;

let cache = {};
let cacheLoaded = false;

function loadCache() {
  if (cacheLoaded) return;
  try {
    cache = JSON.parse(fs.readFileSync(CACHE_FILE, "utf-8"));
  } catch {
    cache = {};
  }
  cacheLoaded = true;
}

function saveCache() {
  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
}

function cacheKey(title, year, type) {
  return `${title.toLowerCase().trim()}|${year}|${type || ""}`;
}

function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

let lastRequest = 0;
const RATE_LIMIT_MS = 300; // ~3 req/s, well under TMDB's 40/10s

async function tmdbRequest(endpoint) {
  if (!API_KEY) return null;
  const now = Date.now();
  const wait = RATE_LIMIT_MS - (now - lastRequest);
  if (wait > 0) await delay(wait);
  lastRequest = Date.now();

  const url = `${TMDB_BASE}${endpoint}${endpoint.includes("?") ? "&" : "?"}api_key=${API_KEY}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchImdbId(title, year, expectedType) {
  const params = new URLSearchParams({ query: title });
  if (year) params.set("year", year);
  const data = await tmdbRequest(`/search/multi?${params}`);
  if (!data?.results?.length) return null;

  let best;
  if (expectedType) {
    const targetMediaType = expectedType === "series" ? "tv" : "movie";
    best = data.results.find((r) => {
      const mt = r.media_type || (r.title ? "movie" : "tv");
      return mt === targetMediaType;
    });
    if (!best) best = data.results[0];
  } else {
    best = data.results[0];
  }

  const tmdbId = best.id;
  const mediaType = best.media_type || (best.title ? "movie" : "tv");
  const type = mediaType === "movie" ? "movie" : "tv";

  const ext = await tmdbRequest(`/${mediaType}/${tmdbId}/external_ids`);
  const imdbId = ext?.["imdb_id"];

  return {
    imdbId: imdbId || null,
    tmdbId: String(tmdbId),
    type,
    poster: best.poster_path ? `https://image.tmdb.org/t/p/w500${best.poster_path}` : null,
    description: best.overview || null,
    genres: best.genre_ids ? [] : null,
  };
}

export async function getTmdbMeta(title, year, expectedType) {
  loadCache();
  const key = cacheKey(title, year, expectedType);

  if (cache[key]) return cache[key];

  const result = await fetchImdbId(title, year, expectedType);
  if (result) {
    cache[key] = result;
    saveCache();
  } else {
    cache[key] = null;
    saveCache();
  }
  return result;
}

export function getCachedMeta(title, year) {
  loadCache();
  return cache[cacheKey(title, year)] || null;
}
