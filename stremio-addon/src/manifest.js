const PORT = process.env.PORT || 7000;
const ADDON_URL = process.env.ADDON_URL || `http://127.0.0.1:${PORT}`;

export function buildManifest() {
  return {
    id: "org.moctale.catalog",
    version: "1.0.0",
    name: "Moctale Catalog",
    description: "Movies & shows curated from moctale.in",
    logo: "https://www.moctale.in/favicon.ico",
    resources: ["catalog"],
    types: ["movie", "series"],
    catalogs: [
      {
        id: "moctale-all",
        type: "movie",
        name: "Moctale - Movies",
        extra: [
          {
            name: "genre",
            options: [
              "Editors Pick",
              "Netflix",
              "JioHotstar",
              "Prime Video",
              "Hotstar",
            ],
          },
        ],
      },
      {
        id: "moctale-all",
        type: "series",
        name: "Moctale - Series",
        extra: [
          {
            name: "genre",
            options: [
              "All",
              "Talk Of The Town",
              "Watch It With District",
              "Editors Pick",
              "Netflix",
              "JioHotstar",
              "Prime Video",
              "Hotstar",
            ],
          },
        ],
      },
    ],
    behaviorHints: { adult: false },
    idPrefixes: ["moctale-"],
  };
}

export function handler({ type, id, extra }) {
  // Stremio SDK-compatible handler — returns Promise<{ metas }>
  const genre = extra?.genre || "All";
  return Promise.resolve({ metas: [] });
}
