# EET Mod Forge

**Master install order builder for Baldur's Gate: Enhanced Edition Trilogy**

Browse 498 mods and 3,500+ components. Build a WeiDU.log. Export for [mod_installer](https://github.com/dark0dave/mod_installer) or Project Infinity. Analyze debug logs. Check for updates.

> [**Launch the app →**](#) <!-- Replace with your GitHub Pages URL -->

## What it does

- **Browse the full EET mod catalog** — 498 mods organized by install order category (17 sections from Pre-EET through Post-SCS), with subcategories, search, and game phase filters (BG1/SoD/SoA/ToB).

- **Build a WeiDU.log** — Select components with checkboxes, then export a valid `WeiDU.log` and `WeiDU-BGEE.log` pair. The format is compatible with [mod_installer](https://github.com/dark0dave/mod_installer) (`eet --bg1-log-file WeiDU-BGEE.log --bg2-log-file WeiDU.log`).

- **Import your existing install** — Drag-and-drop a WeiDU.log onto the app. It matches entries against the catalog at 100% accuracy for known mods and auto-selects everything.

- **Start from presets** — Five curated starting points: Minimal Fixes (57 comps), Enhanced Vanilla (155), Story Expansion (229), Quest Megamod (1,269), SCS Tactical (241). Customize from there.

- **Analyze debug logs** — Upload a WSETUP.DEBUG file. The parser detects 13 error patterns, matches them against a known issues database, and tells you whether it's a documented problem with a workaround or something new to report.

- **Check for updates** — Scans GitHub releases for 320 mods to find version mismatches between what's installed and what's available. Cached weekly via GitHub Actions.

- **EET compatibility badges** — 84 mods show minimum version requirements from the official EET compatibility list.

- **Diff view** — See exactly what changed: additions, removals, and a component-level breakdown.

## Data sources

The catalog is built by merging four sources:

| Source | What it provides |
|---|---|
| [install-EET-4.txt](https://github.com/777087788) | 3,400+ component entries with install order, compatibility notes, and author commentary |
| [EET Mod Install Order Guide (Google Sheet)](https://docs.google.com/) | Mod-level metadata: authors, URLs, game phases, tags |
| WeiDU.log | Actual installed components with real tp2 paths and versions |
| [EET Compatibility List](https://k4thos.github.io/EET-Compatibility-List/) | Minimum versions and placement requirements |

## Repo structure

```
data/
  mods.json            # 498-mod catalog (762 KB)
  presets.json         # 5 curated install profiles
  known_issues.json    # Community-maintained issue database
  compat.json          # EET compatibility data
  pi_weidu_map.json    # PI label → WeiDU path mapping (640 KB)
  github_mods.json     # GitHub repo index for 320 mods
  version_cache.json   # Auto-updated by Actions

tools/
  build_data.py        # Full data pipeline (parse sources → JSON)
  scan_versions.py     # GitHub API scanner for Actions

.github/workflows/
  update-versions.yml  # Weekly scheduled version scan

index.html             # The app (35 KB, fetches data/ at startup)
```

## Running locally

Just serve the directory:

```sh
# Python
python3 -m http.server 8000

# Node
npx serve .

# Then open http://localhost:8000
```

Or push to GitHub and enable Pages — it works as-is.

## Contributing

### Adding a mod to the catalog

Edit `data/mods.json` and add an entry. The format:

```json
{
  "i": 999,
  "t": "MODNAME",
  "n": "Human-Readable Name",
  "c": "QUEST MODS BG2",
  "s": "BG2 quests by Author",
  "u": "https://github.com/author/mod",
  "a": "Author Name",
  "no": "Install notes...",
  "co": [
    {
      "n": "Main Component",
      "cn": 0,
      "wf": "MODNAME",
      "wp": "MODNAME\\MODNAME.TP2",
      "wc": 0,
      "wq": "exact"
    }
  ]
}
```

### Adding a known issue

Edit `data/known_issues.json`:

```json
{
  "pattern": "regex pattern to match in debug log",
  "mod": "MODNAME",
  "severity": "critical|warning|info",
  "known": true,
  "description": "What this error means",
  "workaround": "How to fix it"
}
```

### Rebuilding from source data

If you have updated source files (install order text, CSV, WeiDU logs):

```sh
cd tools
python3 build_data.py
```

This regenerates all `data/*.json` files.

## Credits

- **Install order guide**: [777087788's install-EET-4.txt](https://github.com/777087788) — the most comprehensive EET install order with 9,380 lines of component entries and compatibility notes
- **EET**: [K4thos](https://github.com/Gibberlings3/EET) and the Gibberlings Three community
- **mod_installer**: [dark0dave](https://github.com/dark0dave/mod_installer) — open source WeiDU log-based installer
- **Mod authors**: The hundreds of people who build and maintain BG mods across Gibberlings3, Spellhold Studios, Weaselmods, Artisan's Corner, Pocket Plane Group, and beyond

## License

MIT
=======
# eet-mod-forge
