# PokePilot Pokémon Champions

**English** | [中文](README.md)

A local assistant for Pokémon Champions-style play: open the web UI with a **capture card / webcam** feed, grab in-game screenshots, run **OCR and image-based detection** to build **your team and the opponent’s team**, manage **multiple team slots**, and get **simplified damage range hints** in the browser.

## Prerequisites

- **Python 3.11** or higher
- **Git**
- **Conda** (recommended for virtual environments)
- **Disk space:** plan for **3GB+** (PokeAPI data and sprites + PyTorch / EasyOCR; first OCR run may download pretrained weights under `~/.cache/torch`)

## Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/haoanwang0829/pokepilot.git
cd pokepilot
```

### 2. Create a Python Virtual Environment

```bash
# Using Conda
conda create -n pokepilot python=3.11
conda activate pokepilot
```

or

```bash
# Using venv
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Quick Initialization (Recommended)

Use an automated script for initialization (includes installing dependencies and downloading data).

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File init.ps1
```

**macOS / Linux / WSL / Git Bash:**
```bash
bash init.sh
```

**Network Issues?** If online Sprite download fails, the script will prompt you to manually extract `sprites.rar` (if available).

---

### 4. Offline Installation (If Network Download Fails)

If you cannot download Sprites online, you can use an offline package:

**Prerequisite:** You have the `sprites.rar` file

**Steps:**

1. Place `sprites.rar` in the **repository root** (same folder as `init.sh` and `requirements.txt`, i.e. after `cd pokepilot`)

2. **Extract Sprites:**
   
   **Windows (PowerShell):**
   ```powershell
   Expand-Archive sprites.rar -DestinationPath sprites
   ```
   
   **macOS / Linux (requires unrar):**
   ```bash
   unrar x sprites.rar
   # Or use other tools: 7z x sprites.rar
   ```

3. Continue with the initialization script or perform manual steps

**Automatic Handling:** If `sprites.rar` is in the project root, the initialization script will automatically detect it and prompt you to extract.

---

### 5. Manual Initialization (Alternative)

If you prefer to perform steps manually:

#### 5.1 Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 5.2 Clone PokeAPI Data

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/api-data.git
cd api-data
git sparse-checkout add data/api/v2
cd ..
```

#### 5.3 Clone Pokémon Sprites

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/sprites.git sprites
cd sprites
git sparse-checkout add sprites/types/generation-ix/scarlet-violet
cd ..
```

#### 5.4 Download and Initialize Data

```bash
# Download sprites
python -m pokepilot.data.download_sprites

# Build Pikalytics data
python -m pokepilot.data.build_pikalytics

# Initialize database
python -m pokepilot.data.pokedb --all
```

## Usage

### Start the Web UI Server

```bash
python -m pokepilot.ui.ui_server
```

The server binds to **`0.0.0.0`** by default (reachable on your LAN). Open **http://localhost:8765** in a browser.

**Optional parameters:**

```bash
# Specify a port
python -m pokepilot.ui.ui_server --port 8080

# Enable debug mode
python -m pokepilot.ui.ui_server --debug
```

### What the Web UI Does

- **Capture card preview:** Uses browser `getUserMedia` to show your webcam pointed at the capture card.
- **Save screenshots:** Writes PNGs to disk (player: `screenshots/team/` e.g. `moves.png`, `stats.png`; opponent: `screenshots/opp_team/team.png`).
- **Your team:** Capture moves + stats pages → **generate OCR draft** → edit in the page → **build** into `data/my_team/temp.json`, then **save / load / delete** slots under `data/my_team/*.json`.
- **Opponent team:** From one opponent-team screenshot → **generate** into `data/opp_team/temp.json`.
- **Damage ranges:** When you select your Pokémon’s move, the backend returns simplified damage and HP% ranges vs each opposing Pokémon (**level 50** baseline), with rough handling for **double spread moves** and some **guaranteed critical** moves (not a full battle simulator).
- **Layout tuning:** Persist `pokepilot/config/card_layout.json` and `pokepilot/config/opponent_team_layout.json` via the UI/API for different resolutions.

## Project Structure

Repository root after clone (`pokepilot/`):

```
pokepilot/                           # repo root
├── pokepilot/                       # Python package
│   ├── common/
│   │   ├── pokemon.py
│   │   ├── pokemon_builder.py
│   │   └── pokemon_detect.py
│   ├── config/                      # layout JSON (writable from web)
│   │   ├── card_layout.json
│   │   └── opponent_team_layout.json
│   ├── data/
│   │   ├── download_sprites.py
│   │   ├── build_roster.py
│   │   ├── build_pikalytics.py
│   │   └── pokedb.py
│   ├── detect_team/
│   │   ├── my_team/                 # layout_detect.py, parse_team.py
│   │   └── opponent_team/           # detect_opponents.py
│   ├── ui/
│   │   ├── ui_server.py             # Flask + REST API
│   │   ├── index.html, style.css, script.js, team.js, config.js
│   │   └── layout-overlay.js
│   ├── tools/                       # capture.py, ocr_engine.py, logger_util.py, …
│   └── debug_tools/
├── data/                            # runtime JSON + caches
│   ├── my_team/
│   ├── opp_team/
│   └── manual.json, type_effectiveness.json, …
├── screenshots/
│   ├── team/
│   └── opp_team/
├── api-data/
├── sprites/
├── requirements.txt
├── init.sh / init.ps1
└── README_EN.md
```

## Module Descriptions

### Common
- **pokemon.py**: Pokémon records (types, moves, stats)
- **pokemon_builder.py**: Merge OCR/card fields into full Pokémon objects
- **pokemon_detect.py**: Dex detect cards and name/form lookup (used by APIs)

### Detect Team
- **my_team**: Parse moves + stats screenshots (`layout_detect.py`, `parse_team.py`)
- **opponent_team**: Multi-Pokémon detection from one opponent screenshot (`detect_opponents.py`)

### UI (`pokepilot/ui/ui_server.py`)
- Serves static frontend and `/api/*`: screenshot upload, team CRUD, generate/build, generate-opponent, damage/range, layout read/write

### Tools
- **ocr_engine.py**: EasyOCR wrapper (may trigger PyTorch Hub downloads on first use)
- **capture.py**: Local capture helpers

### Debug Tools
- OCR/color/layout helpers (`pick_coords`, `debug_card_layout`, etc.)

## Features

**Core**
- Browser webcam preview and screenshot pipeline into fixed paths
- Player team: two-page OCR → draft → build → slot persistence
- Opponent team: one screenshot → `data/opp_team/temp.json`
- Simplified damage-range API (single/double, spread modifier, partial crit handling)
- Adjustable layouts under `pokepilot/config/`

**Data**
- PokeAPI v2 + local caches (`build_pikalytics`, `pokedb`)
- Gen IX sprites (sparse checkout + `download_sprites`)
- Type chart and move metadata for UI and damage hints

## Dependencies

See `requirements.txt`. Highlights:
- **opencv-python**, **numpy**, **pillow** — imaging
- **flask**, **flask-cors** — web server
- **requests**, **beautifulsoup4** — fetching/parsing for data builds
- **easyocr** — OCR
- **torch**, **torchvision**, **torchaudio** — EasyOCR backend (large install; first run may fetch ResNet etc. from PyTorch CDN)

## License

This project uses data from [PokeAPI](https://pokeapi.co/). Please respect their license terms.

## FAQ

**Q: The initialization script failed?**  
A: Confirm Python 3.11+ and Git. If sprite download fails, use the offline `sprites.rar` flow or a proxy, then retry manual steps.

**Q: How do I change the UI server port?**  
A: `python -m pokepilot.ui.ui_server --port 9000`. The app already listens on `0.0.0.0`; use your machine’s IP from other devices on the LAN.

**Q: First OCR run hangs or shows no download progress?**  
A: EasyOCR may download PyTorch Hub weights (e.g. ResNet). You often only see one `Downloading:` line; cache lives under `~/.cache/torch/`. If a `*.partial` file stays **0 bytes**, you likely cannot reach `download.pytorch.org`—use a proxy or place the full `.pth` in the expected `checkpoints` path.

**Q: torchvision warns that `pretrained` is deprecated?**  
A: Harmless warning from dependency APIs; upgrading call sites to `weights=` would silence it.

## Contributing

We welcome issues and pull requests! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Contact

For questions, please open an issue on GitHub.
