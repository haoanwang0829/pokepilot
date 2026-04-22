# PokePilot Pokémon Champions

**English** | [中文](README.md)

A comprehensive Pokémon team detection and data management tool. Automatically detect Pokémon teams from screenshots, manage team data, and interact through a web UI.

## Prerequisites

- **Python 3.11** or higher
- **Git**
- **Conda** (recommended for creating virtual environments)
- **2GB+** disk space (for Pokémon data and sprites)

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

---

### 4. Manual Initialization (Alternative)

If you prefer to perform steps manually:

#### 4.1 Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 4.2 Clone PokeAPI Data

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/api-data.git
cd api-data
git sparse-checkout add data/api/v2
cd ..
```

#### 4.3 Clone Pokémon Sprites

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/sprites.git sprites
cd sprites
git sparse-checkout add sprites/types/generation-ix/scarlet-violet
cd ..
```

#### 4.4 Download and Build Data

```bash
# Download sprites
python -m pokepilot.data.download_sprites

# Build Pokémon roster
python -m pokepilot.data.build_roster

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

After the server starts, access it through your browser: **http://localhost:8765**

**Optional Parameters:**
```bash
# Specify a port
python -m pokepilot.ui.ui_server --port 8080

# Enable debug mode
python -m pokepilot.ui.ui_server --debug
```

## Project Structure

```
pokepilot/
├── common/                          # Core data models and utilities
│   ├── pokemon.py                   # Pokémon data model
│   ├── pokemon_builder.py           # Pokémon object builder
│   └── pokemon_detect.py            # Pokémon detection tools
│
├── config/                          # Configuration files
│   └── regions.py                   # Region configuration
│
├── data/                            # Data processing and initialization modules
│   ├── download_sprites.py          # Sprite download script
│   ├── build_roster.py              # Build Pokémon roster
│   ├── build_pikalytics.py          # Build battle statistics database
│   └── pokedb.py                    # Database initialization
│
├── detect_team/                     # Team detection module
│   ├── my_team/                     # Player's team detection
│   │   ├── layout_detect.py         # Layout detection
│   │   └── parse_team.py            # Team parsing
│   └── opponent_team/               # Opponent team detection
│       ├── crop_slots.py            # Pokémon slot cropping
│       └── detect_opponents.py      # Opponent detection
│
├── ui/                              # Web UI module
│   ├── index.html                   # Main page
│   ├── style.css                    # Stylesheets
│   ├── script.js                    # Frontend logic
│   ├── team.js                      # Team management script
│   └── ui_server.py                 # Flask server
│
├── tools/                           # Utilities
│   ├── capture.py                   # Screenshot tool
│   ├── ocr_engine.py                # OCR engine
│   └── ui_server.py                 # UI server (alternative)
│
├── debug_tools/                     # Debugging tools
│   ├── debug_card_layout.py         # Card layout debugging
│   ├── debug_regions.py             # Region detection debugging
│   ├── pick_coords.py               # Coordinate picker tool
│   ├── test_color_ranges.py         # Color range testing
│   ├── test_ocr.py                  # OCR testing
│   └── test_pokemon_builder.py      # Pokémon builder testing
│
├── api-data/                        # PokeAPI data (sparse checkout)
│   └── data/api/v2/                 # Pokémon API data
│
├── sprites/                         # Pokémon sprites (sparse checkout)
│   └── sprites/types/generation-ix/
│
├── data/                            # Local data storage
│   ├── manual.json                  # Manual configuration data
│   ├── type_effectiveness.json      # Type effectiveness chart
│   ├── my_team/                     # Player's team data
│   └── opp_team/                    # Opponent team data
│
├── screenshots/                     # Screenshot storage
│   ├── team/                        # Player's team screenshots
│   └── opp_team/                    # Opponent team screenshots
│
├── requirements.txt                 # Python dependencies
├── init.sh                          # Linux/Mac initialization script
├── init.ps1                         # Windows initialization script
└── README_EN.md                     # This file
```

## Module Descriptions

### 📊 Common Module
- **pokemon.py**: Defines Pokémon data structure, including attributes, moves, and stats
- **pokemon_builder.py**: Builds Pokémon objects from raw data
- **pokemon_detect.py**: Detects Pokémon through image recognition

### 🎯 Detect Team Module
- **my_team**: Parses player's team screenshots, identifies Pokémon and move information
- **opponent_team**: Identifies opponent's Pokémon team

### 🌐 UI Module
- Web interface for:
  - Screenshot management (save battle screenshots)
  - Team management (create, edit, delete teams)
  - Sprite browsing
  - Team generation (auto-generate team data from screenshots)

### 🛠️ Tools Module
- **ocr_engine.py**: Optical character recognition for text (move names, types, etc.)
- **capture.py**: Screenshot capture tool

### 🐛 Debug Tools Module
Tools for development and debugging:
- Test OCR accuracy
- Adjust detection regions
- Validate Pokémon data building

## Features

✨ **Core Features**
- 📸 Automatically detect Pokémon teams from game screenshots
- 🗂️ Team data management (save, load, delete)
- 🎨 Web UI for interaction
- 🔍 Image-based Pokémon detection
- 📝 OCR text recognition

📦 **Data Support**
- Complete Pokémon attribute data
- Type effectiveness relationships
- Generation-specific sprites (Generation IX - Scarlet/Violet)
- Move and stat data

## Dependencies

See `requirements.txt` for details:
- **opencv-python** (≥4.9.0) - Image processing
- **numpy** (≥1.26.0) - Numerical computing
- **flask** (≥2.3.0) - Web framework
- **flask-cors** (≥4.0.0) - Cross-Origin Resource Sharing
- **pillow** (≥10.0.0) - Image processing
- **requests** - HTTP library
- **beautifulsoup4** - HTML parsing
- **easyocr** - Optical character recognition

## License

This project uses data from [PokeAPI](https://pokeapi.co/). Please respect their license terms.

## FAQ

**Q: The initialization script failed?**  
A: Make sure you have Python 3.11+, Git, and Conda installed. If issues persist, try executing steps manually.

**Q: How do I change the UI server port?**  
A: Use the `--port` parameter: `python -m pokepilot.ui.ui_server --port 9000`

**Q: How do I run this on a remote server?**  
A: Start with: `python -m pokepilot.ui.ui_server --host 0.0.0.0 --port 8765`

## Contributing

We welcome issues and pull requests! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Contact

For questions, please open an issue on GitHub.
