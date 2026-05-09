import fs from "node:fs";
import path from "node:path";
import { getTmdbMeta, getCachedMeta } from "./tmdb.js";

const SCRAPE_JSON = process.env.SCRAPE_JSON || "../moctale_items.json";

let lastMtime = 0;
let cachedItems = [];

function loadScrapedData() {
  const filePath = path.resolve(SCRAPE_JSON);
  try {
    const mtime = fs.statSync(filePath).mtimeMs;
    if (mtime === lastMtime && cachedItems.length) return cachedItems;

    const raw = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const items = [];

    for (const [section, entries] of Object.entries(raw.sections)) {
      for (const entry of entries) {
        if (!entry.name) continue;
        items.push({ ...entry, section });
      }
    }

    lastMtime = mtime;
    cachedItems = items;
    return items;
  } catch {
    return cachedItems.length ? cachedItems : [];
  }
}

function inferType(name, year) {
  const showIndicators = /\b(season|episode|series|show)\b/i;
  const seriesNames = /tv\s*show|web\s*series|anime\s*series/i;
  if (showIndicators.test(name) || seriesNames.test(name)) return "series";
  if (year && parseInt(year, 10) <= new Date().getFullYear()) return "movie";
  return "movie";
}

function generateId(item) {
  if (item.link) {
    const slug = item.link.replace(/^https?:\/\/[^/]+\//, "").replace(/\/$/, "");
    if (slug) return `moctale-${slug}`;
  }
  const hash = Buffer.from(`${item.name}|${item.section}`).toString("base64url").slice(0, 16);
  return `moctale-${hash}`;
}

export async function getCatalog(type, genreFilter) {
  const items = loadScrapedData();
  const results = [];
  const filterLower = (genreFilter || "All").toLowerCase();

  for (const item of items) {
    const sectionLower = item.section.toLowerCase();

    if (filterLower !== "all") {
      const sectionSpaceless = sectionLower.replace(/\s+/g, "");
      const filterSpaceless = filterLower.replace(/\s+/g, "");
      if (filterSpaceless === "editorspick") {
        if (!sectionLower.includes("editor")) continue;
      } else if (!sectionSpaceless.includes(filterSpaceless) && !filterSpaceless.includes(sectionSpaceless)) {
        continue;
      }
    }

    const tmdb = await getTmdbMeta(item.name, item.year, item.type);
    const metaType = item.type || tmdb?.type || inferType(item.name, item.year);
    if (type !== metaType) continue;

    const descParts = [item.section];
    if (item.year) descParts.push(item.year);

    results.push({
      id: tmdb?.imdbId || generateId(item),
      type: metaType,
      name: item.name,
      poster: tmdb?.poster || item.poster_url,
      description: tmdb?.description || descParts.join(" · "),
      genres: tmdb?.genres || [],
      year: item.year || undefined,
    });
  }

  return results;
}
