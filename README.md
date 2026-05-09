# Moctale Scraper

Scrape movie/show names, links, and poster URLs from `https://www.moctale.in/explore`.

## Run

Create a `.env` file in this folder:

```env
MOCTALE_COOKIE="paste_browser_cookie_here"
```

Then run:

```powershell
python scrape_moctale.py
```

You can still override the `.env` value with `--cookie "..."` or the shell variable
`MOCTALE_COOKIE`.

The script writes:

- `moctale_items.json`

The JSON file groups items by section/provider when the API exposes headings such as Netflix,
Amazon, Hotstar, etc.
