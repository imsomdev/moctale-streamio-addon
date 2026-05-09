import "dotenv/config";
import express from "express";
import cors from "cors";
import { buildManifest } from "./manifest.js";
import { getCatalog } from "./catalog.js";

const PORT = process.env.PORT || 7000;

const app = express();
app.use(cors());
app.set("trust proxy", true);

app.get("/manifest.json", (_req, res) => {
  res.json(buildManifest());
});

app.get("/catalog/:type/:id.json", async (req, res) => {
  const { type, id } = req.params;
  const genre = req.query.genre || "All";

  try {
    const metas = await getCatalog(type, genre);
    res.json({ metas });
  } catch (err) {
    console.error("Catalog error:", err);
    res.status(500).json({ error: "Failed to load catalog" });
  }
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, () => {
  console.log(`Moctale addon running on http://127.0.0.1:${PORT}`);
  console.log(`Manifest: http://127.0.0.1:${PORT}/manifest.json`);
});
