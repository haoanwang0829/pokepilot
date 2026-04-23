# PokePilot 宝可梦冠军对战小助手

[English](README_EN.md) | **中文**

一个全面的宝可梦队伍检测与数据管理工具。支持从截图中自动识别宝可梦队伍、管理队伍数据，并通过Web UI进行交互操作。

## 前置条件

- **Python 3.11** 及以上版本
- **Git**
- **Conda** (推荐，用于创建虚拟环境)
- **2GB+** 磁盘空间（用于宝可梦数据和精灵图）

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

1. 将 `sprites.rar` 放在项目根目录（pokepilot文件夹同级）

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

#### 4.1 安装Python依赖

```bash
pip install -r requirements.txt
```

#### 4.2 克隆PokeAPI数据

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/api-data.git
cd api-data
git sparse-checkout add data/api/v2
cd ..
```

#### 4.3 克隆宝可梦精灵图

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/sprites.git sprites
cd sprites
git sparse-checkout add sprites/types/generation-ix/scarlet-violet
cd ..
```

#### 4.4 下载和初始化数据

```bash
# 下载精灵图
python -m pokepilot.data.download_sprites

# 构建Pikalytics数据
python -m pokepilot.data.build_pikalytics

# 初始化数据库
python -m pokepilot.data.pokedb --all
```

## 使用

### 启动Web UI服务器

```bash
python -m pokepilot.ui.ui_server
```

服务器启动后，通过浏览器访问：**http://localhost:8765**

**可选参数：**
```bash
# 指定端口
python -m pokepilot.ui.ui_server --port 8080

# 启用调试模式
python -m pokepilot.ui.ui_server --debug
```

## 项目结构

```
pokepilot/
├── common/                          # 核心数据模型和工具库
│   ├── pokemon.py                   # 宝可梦数据模型
│   ├── pokemon_builder.py           # 宝可梦对象构建器
│   └── pokemon_detect.py            # 宝可梦检测工具
│
├── config/                          # 配置文件
│   └── regions.py                   # 地区配置
│
├── data/                            # 数据处理和初始化模块
│   ├── download_sprites.py          # 下载精灵图脚本
│   ├── build_roster.py              # 构建宝可梦名册
│   ├── build_pikalytics.py          # 构建对战数据库
│   └── pokedb.py                    # 初始化数据库
│
├── detect_team/                     # 队伍检测模块
│   ├── my_team/                     # 己方队伍检测
│   │   ├── layout_detect.py         # 布局检测
│   │   └── parse_team.py            # 队伍解析
│   └── opponent_team/               # 对方队伍检测
│       ├── crop_slots.py            # 裁剪宝可梦框
│       └── detect_opponents.py      # 对手检测
│
├── ui/                              # Web UI模块
│   ├── index.html                   # 主页面
│   ├── style.css                    # 样式表
│   ├── script.js                    # 前端逻辑
│   ├── team.js                      # 队伍管理脚本
│   └── ui_server.py                 # Flask服务器
│
├── tools/                           # 工具集
│   ├── capture.py                   # 截图工具
│   ├── ocr_engine.py                # OCR引擎
│   └── ui_server.py                 # UI服务器 (备用)
│
├── debug_tools/                     # 调试工具
│   ├── debug_card_layout.py         # 卡片布局调试
│   ├── debug_regions.py             # 区域检测调试
│   ├── pick_coords.py               # 坐标选择工具
│   ├── test_color_ranges.py         # 色彩范围测试
│   ├── test_ocr.py                  # OCR测试
│   └── test_pokemon_builder.py      # 宝可梦构建器测试
│
├── api-data/                        # PokeAPI数据（稀疏检出）
│   └── data/api/v2/                 # 宝可梦API数据
│
├── sprites/                         # 宝可梦精灵图（稀疏检出）
│   └── sprites/types/generation-ix/
│
├── data/                            # 本地数据存储
│   ├── manual.json                  # 手动配置数据
│   ├── type_effectiveness.json      # 属性相克表
│   ├── my_team/                     # 己方队伍数据
│   └── opp_team/                    # 对方队伍数据
│
├── screenshots/                     # 截图存储
│   ├── team/                        # 己方队伍截图
│   └── opp_team/                    # 对方队伍截图
│
├── requirements.txt                 # Python依赖列表
├── init.sh                          # Linux/Mac初始化脚本
├── init.ps1                         # Windows初始化脚本
└── README.md                        # 本文件
```

## 模块说明

### 📊 Common 模块
- **pokemon.py**: 定义宝可梦数据结构，包含属性、技能、统计数据等
- **pokemon_builder.py**: 从原始数据构建宝可梦对象
- **pokemon_detect.py**: 通过图像识别检测宝可梦

### 🎯 Detect Team 模块
- **my_team**: 解析己方队伍截图，识别宝可梦和技能信息
- **opponent_team**: 识别对方队伍的宝可梦

### 🌐 UI 模块
- Web界面用于：
  - 截图管理（保存战斗截图）
  - 队伍管理（创建、编辑、删除队伍）
  - 精灵图浏览
  - 队伍生成（从截图自动生成队伍数据）

### 🛠️ Tools 模块
- **ocr_engine.py**: 用于文本识别（技能名、属性等）
- **capture.py**: 截图采集工具

### 🐛 Debug Tools 模块
用于开发和调试的工具集：
- 测试OCR准确性
- 调整检测区域
- 验证宝可梦数据构建

## 功能特性

✨ **核心功能**
- 📸 从游戏截图自动识别宝可梦队伍
- 🗂️ 队伍数据管理（保存、加载、删除）
- 🎨 Web UI交互界面
- 🔍 基于图像的宝可梦检测
- 📝 OCR文本识别

📦 **数据支持**
- 完整的宝可梦属性数据
- 属性相克关系
- 代数专属精灵图（第九代 - 猩红/紫罗兰）
- 技能和统计数据

## 依赖项

详见 `requirements.txt`：
- **opencv-python** (≥4.9.0) - 图像处理
- **numpy** (≥1.26.0) - 数值计算
- **flask** (≥2.3.0) - Web框架
- **flask-cors** (≥4.0.0) - 跨域资源共享
- **pillow** (≥10.0.0) - 图像处理
- **requests** - HTTP请求库
- **beautifulsoup4** - HTML解析
- **easyocr** - 光学字符识别

## 许可证

本项目使用的数据来自 [PokeAPI](https://pokeapi.co/)，请遵守其许可条款。

## 常见问题

**Q: 初始化脚本失败了？**  
A: 确保已安装Python 3.11+、Git和Conda。如果问题持续，尝试手动执行步骤。

**Q: 如何修改UI服务器端口？**  
A: 使用 `--port` 参数：`python -m pokepilot.ui.ui_server --port 9000`

**Q: 如何在远程服务器上运行？**  
A: 启动时使用 `python -m pokepilot.ui.ui_server --host 0.0.0.0 --port 8765`

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

如有问题，请通过GitHub Issues联系。
