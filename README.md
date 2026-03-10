# EET Mod Forge

**Master install order builder for Baldur's Gate: Enhanced Edition Trilogy**

Browse 490+ mods and 3,500+ components. Build a WeiDU.log. Export for [mod_installer](https://github.com/dark0dave/mod_installer) or Project Infinity. Analyze debug logs. Check for updates.

> [**Launch the app →**](https://anprionsa.github.io/eet-mod-forge/)

## What it does

- **Browse the full EET mod catalog** — 490+ mods organized by install order category (20 sections from Pre-EET through EET Finalization), with search, game phase filters (BG1/SoD/SoA/ToB), and author filtering.

- **Build a WeiDU.log** — Select components with checkboxes, then export a valid `WeiDU.log` and `WeiDU-BGEE.log` pair. The format is compatible with [mod_installer](https://github.com/dark0dave/mod_installer) (`eet --bg1-log-file WeiDU-BGEE.log --bg2-log-file WeiDU.log`).

- **Import your existing install** — Drag-and-drop a WeiDU.log onto the app. It matches entries against the catalog and auto-selects everything.

- **Start from presets** — Five curated starting points: Minimal Fixes, Enhanced Vanilla, Story Expansion, Quest Megamod, SCS Tactical. Customize from there.

- **Essential auto-selection** — Selecting EET Core automatically selects all essential mods (DLC Merger, EE Fixpack, EET End). Dual-install mods like EE Fixpack are exported to both WeiDU logs.

- **Conflict detection** — Real-time alerts when selected mods conflict, with component-level detail where available.

- **Split mod navigation** — Mods that span multiple install positions show SPLIT badges with one-click navigation between parts.

- **Analyze debug logs** — Upload a WSETUP.DEBUG file. The parser detects 13 error patterns, matches them against a known issues database, and tells you whether it's a documented problem with a workaround or something new to report.

- **Check for updates** — Scans GitHub releases for 320 mods to find version mismatches. Cached weekly via GitHub Actions.

- **EET compatibility badges** — 84 mods show minimum version requirements from the official EET compatibility list.

- **Install Order Map** — Visual timeline of your install with essential mod validation warnings.

## Data sources

The catalog is built by merging four sources:

| Source | What it provides |
|---|---|
| [install-EET-4.txt](https://www.scribd.com/document/777087788/install-EET-4) | 3,400+ component entries with install order, compatibility notes, and author commentary |
| [EET Mod Install Order Guide (Google Sheet)](https://docs.google.com/spreadsheets/d/1tt4f-rKqkbk8ds694eJ1YcOjraZ2pISkkobqZ5yRcvI/edit?gid=676921267#gid=676921267) | Mod-level metadata: authors, URLs, game phases, tags |
| WeiDU.log | Actual installed components with real tp2 paths and versions |
| [EET Compatibility List](https://k4thos.github.io/EET-Compatibility-List/) | Minimum versions and placement requirements |

## Repo structure

```
data/
  mods.json            # Mod catalog with components, install order, and split groups
  presets.json         # 5 curated install profiles
  conflicts.json       # Mod/component conflicts, dependencies, essentials, meta-components
  known_issues.json    # Community-maintained issue database
  compat.json          # EET compatibility data
  pi_weidu_map.json    # PI label → WeiDU path mapping
  github_mods.json     # GitHub repo index for 320 mods
  version_cache.json   # Auto-updated by Actions

tools/
  build_data.py        # Full data pipeline (parse sources → JSON)
  scan_versions.py     # GitHub API scanner for Actions

.github/workflows/
  update-versions.yml  # Weekly scheduled version scan

index.html             # The app (single-file React 18, fetches data/ at startup)
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

Edit `data/mods.json` and add an entry to the array. Place it in the correct install order position.

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

**Field reference:**

| Field | Required | Description |
|-------|----------|-------------|
| `i` | Yes | Unique install order index |
| `t` | Yes | WeiDU tp2 name (folder name, case-sensitive) |
| `n` | Yes | Human-readable mod name |
| `c` | Yes | Install order category (must match one in `CL` object in index.html) |
| `s` | No | Subcategory description |
| `u` | No | URL to mod homepage or download |
| `a` | No | Author name(s) |
| `ph` | No | Game phases array: `["BG1","SoD","SoA","ToB"]` |
| `no` | No | Mod-level install notes |
| `sg` | No | Split group ID (see below) |
| `co` | Yes | Array of components |

**Component fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `n` | Yes | Component name |
| `cn` | Yes | Component number |
| `wf` | No | WeiDU folder name (defaults to mod `t`) |
| `wp` | No | WeiDU tp2 path (defaults to `WF\WF.TP2`) |
| `wc` | No | WeiDU component number (defaults to `cn`) |
| `wq` | No | Match quality: `"exact"` or `"fuzzy"` |
| `x` | No | Set to `1` for optional/choice components |
| `wb` | No | Set to `true` for BGEE-side components (dual-install mods) |
| `no` | No | Component-level notes. Prefix with `v ` for version comments |

### Split mods

Some mods have components that must be installed at different positions in the install order. These are tagged with a `sg` (split group) field so the app can link them with SPLIT badges and navigation.

To mark a mod as split, add `"sg": "group_id"` to each entry that belongs to the same logical mod. The `group_id` is a lowercase string shared by all entries of that mod.

Example — BuTcHeRy has components in two categories:
```json
{"i": 242, "t": "d9_butchery_tazok", "sg": "butchery", "c": "CREATURE MODS PRE SCS", ...}
{"i": 397, "t": "d9_butchery_irenicus_dungeon", "sg": "butchery", "c": "KIT MODS", ...}
```

Do **not** add `sg` to mods that share a tp2 prefix but are different mods (e.g., `A7` covers DLC Merger, Golem Construction, etc. — these are separate mods, not splits).

### Adding a conflict

Edit `data/conflicts.json` and add to the `conflicts` array:

```json
{
  "a": "modA_tp2",
  "b": "modB_tp2",
  "severity": "hard",
  "reason": "Why these conflict",
  "comp_a": "Component name in mod A",
  "comp_b": "Component name in mod B"
}
```

**Severity levels:**
- `hard` — Mods are mutually exclusive. "is incompatible with"
- `partial` — Specific components conflict. "may conflict with"
- `soft` — Possible issues. "may conflict with"

The `comp_a` and `comp_b` fields are optional. When present, the alert shows which specific components conflict instead of just mod names.

### Adding a dependency

Add to the `dependencies` array in `data/conflicts.json`:

```json
{
  "mod": "dependent_tp2",
  "requires": "required_tp2",
  "type": "hard",
  "reason": "Why this dependency exists"
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

### Design tokens

The app uses CSS custom properties defined in `:root`. To change colors or spacing globally, edit the variables at the top of `index.html`:

```css
:root {
  --bg: #0c0e14;      /* Main background */
  --bg2: #141620;     /* Card background */
  --gold: #d4a843;    /* Primary accent */
  --tx: #c8ccd8;      /* Main text */
  --grn: #4ade80;     /* Success/selected */
  --red: #f87171;     /* Error/conflict */
  --blu: #60a5fa;     /* Links/info */
  --bg-warn: #2a2010; /* Warning background */
  --bg-err: #2a1010;  /* Error background */
  /* ... see index.html for full list */
}
```

A `CONFIG` object near the top of the script holds app-level constants:

```javascript
const CONFIG = {
  EET_MOD_ID: 12,              // Mod ID that triggers essential auto-select
  DUAL_INSTALL: ['eefixpack'], // tp2s exported to both BGEE and BG2EE logs
  ITEM_HEIGHT: 50,             // Virtual list row height in px
  VL_OVERFLOW: 8               // Virtual list overscan rows
};
```

### Rebuilding from source data

If you have updated source files (install order text, CSV, WeiDU logs):

```sh
cd tools
python3 build_data.py
```

This regenerates all `data/*.json` files.

## Credits

- **Install order guide**: [install-EET-4.txt](https://www.scribd.com/document/777087788/install-EET-4) — the most comprehensive EET install order with 9,380 lines of component entries and compatibility notes
- **EET Mod Install Order Guide**: [Google Sheets](https://docs.google.com/spreadsheets/d/1tt4f-rKqkbk8ds694eJ1YcOjraZ2pISkkobqZ5yRcvI/edit?gid=676921267#gid=676921267) — the community-maintained spreadsheet that inspired this project and provided mod-level metadata
- **EET**: [K4thos](https://github.com/Gibberlings3/EET) and the Gibberlings Three community
- **mod_installer**: [dark0dave](https://github.com/dark0dave/mod_installer) — open source WeiDU log-based installer
- **Mod authors**: The hundreds of people who build and maintain BG mods across Gibberlings3, Spellhold Studios, Weaselmods, Artisan's Corner, Pocket Plane Group, and beyond

## License

MIT
