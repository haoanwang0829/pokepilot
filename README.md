# PokePilot 宝可梦冠军对战小助手

[English](README_EN.md) | **中文**

面向《宝可梦》冠军赛等对战场景的本地小工具：用浏览器配合**采集卡 / 摄像头画面**截取游戏 UI，通过 **OCR + 图像识别**生成己方与对方队伍数据，并在网页里做**队伍槽位管理**与**简化伤害区间估算**。

## 前置条件

- **Python 3.11** 及以上版本
- **Git**
- **Conda**（推荐，用于创建虚拟环境）
- **磁盘空间**：建议预留 **3GB+**（PokeAPI 数据与精灵图 + PyTorch / EasyOCR 依赖；首次 OCR 还会向 `~/.cache/torch` 下载预训练权重）

## 环境配置

### 1. 克隆仓库

```bash
git clone https://github.com/haoanwang0829/pokepilot.git
cd pokepilot
```

### 2. 创建Python虚拟环境

```bash
# 使用 Conda
conda create -n pokepilot python=3.11
conda activate pokepilot
```

或

```bash
# 使用 venv
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. 快速初始化（推荐）

使用自动化脚本进行初始化（包括安装依赖和下载数据）。

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File init.ps1
```

**macOS / Linux / WSL / Git Bash:**
```bash
bash init.sh
```

**网络问题？** 如果在线下载Sprites失败，脚本会提示你手动解压 `sprites.rar`（如有）。

---

### 4. 离线安装（如果网络下载失败）

如果你无法在线下载Sprites，可以使用离线包：

**前置条件：** 已获得 `sprites.rar` 文件

**步骤：**

1. 将 `sprites.rar` 放在**仓库根目录**（与 `init.sh`、`requirements.txt` 同级，即 `cd pokepilot` 后的当前目录）

2. **解压Sprites：**
   
   **Windows (PowerShell):**
   ```powershell
   Expand-Archive sprites.rar -DestinationPath sprites
   ```
   
   **macOS / Linux (需要unrar):**
   ```bash
   unrar x sprites.rar
   # 或使用其他解压工具：7z x sprites.rar
   ```

3. 继续运行初始化脚本或手动执行其他步骤

**自动处理：** 如果 `sprites.rar` 在项目根目录，初始化脚本会自动检测并提示解压。

---

### 5. 手动初始化（如果不使用脚本）

如果你需要逐步执行，请按以下步骤进行：

#### 5.1 安装 Python 依赖

```bash
pip install -r requirements.txt
```

#### 5.2 克隆 PokeAPI 数据

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/api-data.git
cd api-data
git sparse-checkout add data/api/v2
cd ..
```

#### 5.3 克隆宝可梦精灵图

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/sprites.git sprites
cd sprites
git sparse-checkout add sprites/types/generation-ix/scarlet-violet
cd ..
```

#### 5.4 下载和初始化数据

```bash
# 下载精灵图
python -m pokepilot.data.download_sprites

# 构建 Pikalytics 数据
python -m pokepilot.data.build_pikalytics

# 初始化数据库
python -m pokepilot.data.pokedb --all
```

## 使用

### 启动 Web UI 服务器

```bash
python -m pokepilot.ui.ui_server
```

默认监听 **`0.0.0.0`**（局域网内其他设备也可访问）。浏览器打开：**http://localhost:8765**

**可选参数：**

```bash
# 指定端口
python -m pokepilot.ui.ui_server --port 8080

# 启用调试模式
python -m pokepilot.ui.ui_server --debug
```

### 网页端能做什么

- **采集卡预览**：用浏览器 `getUserMedia` 打开摄像头，对准采集卡上的游戏画面。
- **截图入库**：将当前画面保存为 PNG（己方：`screenshots/team/` 下的 `moves.png`、`stats.png` 等；对方队伍：`screenshots/opp_team/team.png`）。
- **己方队伍**：对「技能页 + 能力页」截图 → **生成 OCR 草稿** → 在页面校对 → **构建**写入 `data/my_team/temp.json`，并可 **保存 / 加载 / 删除**多个队伍槽位（`data/my_team/*.json`）。
- **对方队伍**：上传对方队伍截图后 **生成**，结果写入 `data/opp_team/temp.json`。
- **伤害区间**：点击我方技能时，后端按简化公式（默认 **50 级**）估算对对方每只宝可梦的 **伤害与血量百分比区间**，并考虑 **双打扩散招式**、部分 **必中要害** 等简化修正（仅供参考，非完整对战模拟）。
- **布局校准**：可通过 API / 页面保存 `pokepilot/config/card_layout.json`（己方卡片）与 `pokepilot/config/opponent_team_layout.json`（对方队伍区域），适配不同分辨率或 UI 偏移。

## 项目结构

仓库根目录（克隆后的 `pokepilot/` 文件夹）主要包含：

```
pokepilot/                           # 仓库根目录
├── pokepilot/                       # Python 包
│   ├── common/                      # 数据模型、构建器、图鉴/检测卡片查询
│   │   ├── pokemon.py
│   │   ├── pokemon_builder.py
│   │   └── pokemon_detect.py
│   ├── config/                      # 布局 JSON（可通过 Web 保存）
│   │   ├── card_layout.json         # 己方卡片 OCR 区域
│   │   └── opponent_team_layout.json # 对方队伍检测区域
│   ├── data/                        # 数据下载与库构建脚本
│   │   ├── download_sprites.py
│   │   ├── build_roster.py
│   │   ├── build_pikalytics.py
│   │   └── pokedb.py
│   ├── detect_team/
│   │   ├── my_team/                 # layout_detect.py, parse_team.py
│   │   └── opponent_team/           # detect_opponents.py
│   ├── ui/                          # Flask 静态页 + 前端脚本
│   │   ├── ui_server.py             # 采集卡预览 + REST API
│   │   ├── index.html, style.css, script.js, team.js, config.js
│   │   └── layout-overlay.js        # 布局叠加辅助
│   ├── tools/                       # capture.py, ocr_engine.py, logger_util.py 等
│   └── debug_tools/                 # 布局/OCR/色彩调试脚本
├── data/                            # 运行时数据（与包内脚本生成的缓存）
│   ├── my_team/                     # 己方队伍 JSON（含 temp.json）
│   ├── opp_team/                    # 对方队伍 JSON
│   ├── manual.json, type_effectiveness.json, *.json 缓存等
├── screenshots/
│   ├── team/                        # 己方截图（moves.png / stats.png 等）
│   └── opp_team/                    # 对方队伍截图 team.png
├── api-data/                        # git sparse：PokeAPI v2
├── sprites/                         # git sparse：第九世代精灵资源
├── requirements.txt
├── init.sh / init.ps1
└── README.md
```

## 模块说明

### Common
- **pokemon.py**：宝可梦数据结构（属性、技能、种族值等）
- **pokemon_builder.py**：把 OCR/卡片字段合并为完整宝可梦对象
- **pokemon_detect.py**：图鉴检测卡片与名称形态查询（供 API 使用）

### Detect Team
- **my_team**：从「技能页 + 能力页」截图解析卡片布局与文本（`layout_detect.py`、`parse_team.py`）
- **opponent_team**：从对方队伍整屏截图识别多只宝可梦（`detect_opponents.py`）

### UI（`pokepilot/ui/ui_server.py`）
- Flask 托管前端静态文件，并提供 `/api/*`：**截图上传**、**队伍 CRUD**、**generate / build**、**generate-opponent**、**damage/range**、**布局配置的读写**等

### Tools
- **ocr_engine.py**：EasyOCR 封装（首次使用可能下载 PyTorch Hub 权重）
- **capture.py**：本地采集相关工具

### Debug Tools
- 用于校对 OCR、色彩区间、`pick_coords` 选点、`debug_card_layout` 等开发调试

## 功能特性

**核心能力**
- 浏览器 **摄像头预览** + 将采集卡画面 **截图** 到本地固定路径
- **己方队伍**：双页截图 → OCR 草稿 → 网页校对 → 构建 `temp.json` → 多槽位持久化
- **对方队伍**：单张截图 → 识别写入 `data/opp_team/temp.json`
- **伤害区间**：选中技能后对对方全队给出简化伤害与血量百分比区间（单打/双打、扩散修正等）
- **布局可调**：`card_layout.json` / `opponent_team_layout.json` 持久化在 `pokepilot/config/`

**数据与资源**
- PokeAPI v2 数据 + 本地缓存（`build_pikalytics`、`pokedb`）
- 第九世代精灵资源（sparse checkout + `download_sprites`）
- 属性相克与技能效果字段（用于克制显示与伤害/API 中的简化逻辑）

## 依赖项

详见 `requirements.txt`，主要包括：
- **opencv-python**、**numpy**、**pillow** — 图像处理
- **flask**、**flask-cors** — Web 服务
- **requests**、**beautifulsoup4** — 联网与页面解析（数据构建）
- **easyocr** — OCR
- **torch**、**torchvision**、**torchaudio** — EasyOCR / 视觉后端（体积较大；首次推理可能从 PyTorch 官方 CDN 拉取 ResNet 等权重）

## 许可证

本项目使用的数据来自 [PokeAPI](https://pokeapi.co/)，请遵守其许可条款。

## 常见问题

**Q: 初始化脚本失败了？**  
A: 确认 Python 3.11+、Git 可用；网络不稳定时精灵下载失败可参考上文「离线安装」或检查代理。仍失败可按「手动初始化」逐步执行。

**Q: 如何修改 UI 端口？**  
A: `python -m pokepilot.ui.ui_server --port 9000`。监听地址默认为 `0.0.0.0`，局域网可直接访问本机 IP 对应端口。

**Q: 第一次 OCR / 截图识别时卡住或没有进度？**  
A: EasyOCR 可能通过 PyTorch Hub 下载预训练模型（如 ResNet 权重）。命令行往往只打印一行 `Downloading:`，耗时取决于网络；缓存目录为 `~/.cache/torch/`。若长期只有 `*.partial` 且大小为 0，多为无法访问 `download.pytorch.org`，需代理或手动将完整 `.pth` 放到对应 `checkpoints` 路径。

**Q: 如何在远程服务器上运行？**  
A: 启动时使用 `python -m pokepilot.ui.ui_server --host 0.0.0.0 --port 8765`

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

如有问题，请通过GitHub Issues联系。
