# PokePilot 项目架构文档

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [图片识别模块](#3-图片识别模块)
4. [OCR文字识别模块](#4-ocr文字识别模块)
5. [计算逻辑模块](#5-计算逻辑模块)
6. [数据库模块](#6-数据库模块)
7. [UI服务端模块](#7-ui服务端模块)
8. [数据流向图](#8-数据流向图)
9. [核心数据模型](#9-核心数据模型)
10. [配置文件说明](#10-配置文件说明)

---

## 1. 项目概述

**PokePilot** 是一个宝可梦朱紫（Pokemon Scarlet/Violet）的队伍辅助工具，通过图像识别技术自动读取游戏中的队伍信息，并提供伤害计算等辅助功能。

### 主要功能

- **我方队伍识别**：从截图识别6只宝可梦的精灵图、属性、昵称、特性、道具、招式和属性值
- **对手队伍识别**：从队伍选择画面识别对手的6只宝可梦
- **伤害计算**：计算我方技能对对手全队的伤害范围
- **队伍管理**：保存和加载队伍数据

---

## 2. 整体架构

```
pokepilot/
├── common/                    # 公共模块
│   ├── pokemon.py             # 宝可梦数据模型
│   ├── pokemon_detect.py      # 宝可梦图像识别引擎
│   └── pokemon_builder.py     # 宝可梦构建器和计算逻辑
│
├── detect_team/               # 队伍检测模块
│   ├── my_team/               # 我方队伍检测
│   │   ├── parse_team.py      # 解析我方队伍（OCR+检测）
│   │   └── layout_detect.py   # 卡片布局自动检测
│   └── opponent_team/         # 对手队伍检测
│       └── detect_opponents.py
│
├── data/                      # 数据处理模块
│   ├── pokedb.py              # 宝可梦本地数据库
│   ├── build_roster.py        # 构建roster数据
│   ├── build_pikalytics.py    # 构建pikalytics缓存
│   └── download_sprites.py    # 精灵图下载工具
│
├── tools/                     # 工具模块
│   ├── ocr_engine.py           # OCR引擎封装
│   ├── capture.py             # 截图工具
│   ├── logger_util.py         # 日志工具
│   └── ui_assets/             # UI资源
│
├── ui/                        # Web UI模块
│   ├── ui_server.py           # Flask服务器（核心API）
│   ├── index.html             # 主页面
│   ├── script.js              # 前端逻辑
│   ├── team.js                # 队伍管理逻辑
│   └── style.css              # 样式
│
└── config/                    # 配置目录
    ├── card_layout.json       # 我方队伍卡片布局配置
    └── opponent_team_layout.json  # 对手队伍布局配置
```

### 模块依赖关系

```
ocr_engine.py          # 底层OCR引擎
       ↓
parse_team.py          # 使用OCR解析我方队伍
       ↓
pokemon_detect.py      # 图像识别宝可梦精灵
       ↓
pokemon_builder.py     # 构建完整Pokemon对象
       ↓
ui_server.py           # API层，提供前端接口
       ↓
index.html/script.js   # 前端展示层
```

---

## 3. 图片识别模块

### 3.1 宝可梦精灵识别 (`pokemon_detect.py`)

**核心类：`PokemonDetector`**

使用 **ResNet50** 预训练模型提取图像特征，通过余弦相似度匹配来识别宝可梦精灵图。

#### 识别流程

```
输入：sprite图片 + type1图标 + type2图标
    ↓
┌─────────────────────────────────────────────────────────┐
│ 1. 背景去除（可选）                                       │
│    - "multi": 多色背景去除（我方队伍）                     │
│    - "auto": 单色背景去除（对手队伍）                      │
│    - "none": 不去除背景                                   │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 2. 属性图标识别（_match_type）                            │
│    - 将图标与18种属性图标逐一比对                          │
│    - 使用绝对差均值计算相似度                              │
│    - 阈值: <60 分视为匹配                                 │
│    - 返回: type_id (1-18) 或 None                         │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 3. 候选过滤                                              │
│    - 根据识别到的属性过滤roster中的宝可梦                    │
│    - 排除mega形态                                        │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 4. 精灵图特征提取 (_extract_features)                    │
│    - 使用ResNet50提取224x224特征向量（2048维）             │
│    - 归一化处理                                          │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 5. 相似度匹配 (_match_sprite)                            │
│    - 与候选精灵图逐一比对                                  │
│    - 计算余弦距离（越接近0越相似）                          │
│    - 考虑普通版和闪光版                                     │
│    - 返回: (variant, score, is_shiny)                    │
└─────────────────────────────────────────────────────────┘
    ↓
输出: {"name", "slug", "types", "sprite_key", "score"}
```

#### 关键函数

| 函数 | 说明 |
|------|------|
| `_extract_features(img, model, device)` | ResNet50提取特征，返回2048维向量 |
| `_cosine_similarity(feat1, feat2)` | 计算余弦距离 |
| `_match_type(icon)` | 识别属性图标，返回type_id |
| `_match_sprite(sprite, candidates)` | 匹配精灵图 |
| `_remove_bg_multi(img, bg_colors)` | 多色背景去除 |

#### 参考数据

- **精灵图目录**：`sprites/champions/` 和 `sprites/champions_shiny/`
- **属性图标目录**：`sprites/sprites/types/generation-ix/scarlet-violet/small/`
- **roster数据**：`data/champions_roster.json`

---

### 3.2 卡片布局检测 (`layout_detect.py`)

自动检测6个宝可梦卡片的精确位置。

#### 检测流程

```
输入：队伍截图
    ↓
1. 颜色分割（HSV紫色区域）
    ↓
2. 形态学操作（闭运算+开运算）
    ↓
3. Canny边缘检测
    ↓
4. 轮廓检测和矩形近似
    ↓
5. 去重（合并接近的矩形）
    ↓
6. 布局分析（计算间距）
    ↓
输出：6个卡片坐标 + 布局参数
```

**失败时回退**：使用 `_FALLBACK_LAYOUT` 静态配置（1920x1080分辨率）

---

### 3.3 我方队伍解析 (`parse_team.py`)

整合OCR和图像识别，解析完整的队伍信息。

#### 三个页面的解析

##### 页面1：Pokemon页（`moves.png`）

```python
def _parse_moves_screen(image_path):
    # 1. 从6个卡片区域提取sprite + type1 + type2
    for slot_idx, card_info in enumerate(all_cards):
        regions = _extract_regions(img, card_info)
        
        # 2. 图像识别宝可梦
        pokemon_info = _identify_pokemon(img, card_info, slot_idx)
        
        # 3. OCR识别昵称/特性/道具/招式
        results = read_region(card)
        # 按y坐标分组（同一行的词汇合并）
        # 按x坐标排序后拼接
```

**OCR识别逻辑**：
- 将卡片分为左右两列
- 按y坐标分组（阈值20像素）
- 同组内按x坐标排序拼接

##### 页面2：Stats页（`stats.png`）

```python
def _parse_stats_screen(image_path):
    # 1. 识别性格箭头颜色
    for stat_key, (rx0, ry0, rx1, ry1) in arrow_map.items():
        color = _detect_stat_color(card, rx0, ry0, rx1, ry1)
        # "red" = 增加↑， "blue" = 减少↓， "neutral" = 无箭头
    
    # 2. OCR识别属性数值
    results = read_region(card)
    # 提取数字
```

**性格箭头检测**：
```python
def _detect_stat_color(card, rx0, ry0, rx1, ry1):
    # 去除背景色 (B=216, G=124.5, R=142.5, ±40)
    # 计算前景像素平均颜色
    # R>G,B → "red" (增加)
    # B>G,R → "blue" (减少)
    # 其他 → "neutral"
```

---

## 4. OCR文字识别模块

### 4.1 OCR引擎 (`ocr_engine.py`)

封装 **EasyOCR** 库，支持中文和英文识别。

#### 核心函数

```python
def get_reader(langs: list = ["ch_sim", "en"]) -> easyocr.Reader:
    """获取OCR Reader，单例模式缓存"""

def read_region(img, min_conf=0.25) -> list[tuple[box, text, conf]]:
    """对图像区域OCR，返回识别结果列表"""

def read_crop_text(img, x0, y0, x1, y1, min_conf=0.25, pad=8) -> str:
    """裁切区域并OCR，拼接文字返回"""
```

#### OCR流程

```
输入：图片区域
    ↓
1. 边缘扩展（pad=8像素，提供更多上下文）
    ↓
2. EasyOCR识别
    ↓
3. 过滤低置信度（conf < min_conf）
    ↓
4. 按x坐标排序
    ↓
5. 拼接为字符串
    ↓
输出：识别的文字
```

---

## 5. 计算逻辑模块

### 5.1 属性计算 (`pokemon_builder.py`)

#### HP计算公式

```python
def _calc_hp(base_stat, ev=0) -> int:
    return base_stat + 75 + ev
```

#### 其他属性计算公式

```python
def _calc_stat(base_stat, ev=0, nature=1.0) -> int:
    return int((base_stat + 20 + ev) * nature)

# nature: 1.0=无修正, 1.1=增加, 0.9=减少
```

#### 性格解析

```python
def parse_nature_string(nature_str) -> dict:
    # 输入: "sp_atk↑/attack↓"
    # 输出: {"hp": 1.0, "attack": 0.9, ..., "sp_atk": 1.1, ...}
```

#### EV反向计算

```python
def calc_ev_from_stats(pokemon) -> dict:
    """从实际属性值反推EV"""
    # HP: ev = actual - base - 75
    # 其他: ev = (actual / nature) - base - 20
```

#### 对手队伍属性范围

```python
def calc_opponent_stats_range(base_stats) -> dict:
    """
    计算对手队伍的属性范围（因为不知道EV和性格）
    - 下界: EV=0, Nature=0.9 (最低-10%)
    - 上界: EV=32, Nature=1.1 (最高+10%)
    """
```

#### 类型相克计算

```python
def cal_effectiveness(types) -> dict:
    """
    计算对该宝可梦的伤害倍数
    输入: ["ghost", "poison"]
    输出: {"fighting": 2.0, "ghost": 0.0, ...}
    """
```

---

### 5.2 伤害计算 (`ui_server.py`)

#### 伤害计算公式

```python
def _compute_damage_with_roll(power, atk, defense, stab, type_multiplier, roll):
    base = floor(floor((2 * LEVEL) / 5 + 2) * power * atk / defense / 50) + 2
    return max(1, floor(base * stab * type_multiplier * roll / 100))

# LEVEL = 50（固定等级）
# roll: 85-100（随机波动）
# stab: 1.0 或 1.5（同类技能加成）
```

#### 伤害范围计算

```python
def _compute_damage_range(attacker, defender, move):
    """
    计算技能对目标的极限伤害范围
    
    - 最低伤害：85roll + 对方最大防御
    - 最高伤害：100roll + 对方最小防御
    
    对手队伍属性为区间[min, max]，攻击方取max
    """
```

#### 特殊技能修正

| 技能类型 | 修正系数 | 识别方法 |
|----------|----------|----------|
| 必定要害 | ×1.5 | 技能名或效果描述 |
| 双打范围 | ×0.75 | 技能名或"全体"/"所有" |
| 多段攻击 | - | 效果含"2 to 5 times" |

**必定要害技能**：
- frost-breath, storm-throw, wicked-blow, surging-strikes, flower-trick
- 或效果描述含"always results in a critical hit"

**范围技能**：
- heat-wave, rock-slide, blizzard, earthquake, surf, discharge 等

---

## 6. 数据库模块

### 6.1 PokeDB (`data/pokedb.py`)

本地宝可梦数据库，从 **PokeAPI** 的 `api-data` 目录读取，完全离线。

#### 数据结构

```json
{
  "pokemon": {
    "bulbasaur": {
      "types": ["Grass", "Poison"],
      "base_stats": {"hp": 45, "attack": 49, ...},
      "abilities": ["Overgrow", "Chlorophyll"],
      "name_zh": "妙蛙种子"
    },
    ...
  },
  "moves": {
    "thunderbolt": {
      "type": "Electric",
      "power": 90,
      "category": "special",
      "accuracy": 100,
      "priority": 0,
      "ailment": "paralysis",
      "ailment_chance": 10,
      "name_zh": "十万伏特"
    },
    ...
  },
  "items": {...},
  "abilities": {...}
}
```

#### 中文转换

```python
def name_zh_to_en(name_zh) -> str      # 中文名→英文名
def move_zh_to_en(move_zh) -> str      # 中文招式名→英文
def item_zh_to_en(item_zh) -> str      # 中文道具名→英文
def ability_zh_to_en(ability_zh) -> str # 中文特性名→英文
```

**模糊匹配**：使用 Levenshtein 编辑距离，最大容忍2个字符差异

#### 缓存构建

```python
def build_all_pokemon()    # 构建全宝可梦缓存
def build_all_moves()      # 构建全招式缓存
def build_all_items()      # 构建全道具缓存
def build_all_abilities()  # 构建全特性缓存
```

---

### 6.2 Roster数据 (`data/champions_roster.json`)

包含所有宝可梦形态的精灵图信息。

```json
{
  "pokemon": [
    {
      "slug": "pikachu",
      "id": 25,
      "name": "Pikachu",
      "form": null,
      "types": ["Electric"],
      "sprite": "Menu CP 0025.png",
      "sprite_shiny": "Menu CP 0025-Shiny.png"
    },
    {
      "slug": "pikachu-alola",
      "id": 25,
      "name": "Pikachu-Alola",
      "form": "alola",
      "types": ["Electric"],
      "sprite": "Menu CP 0025-Alola.png",
      "sprite_shiny": null
    },
    ...
  ]
}
```

---

### 6.3 Pikalytics数据 (`data/pikalytics_cache.json`)

对手队伍预测数据（使用率统计）。

```json
{
  "pikachu": {
    "moves": [
      {"name": "thunderbolt", "pct": 82.4},
      {"name": "voltswitch", "pct": 65.2},
      ...
    ],
    "items": [
      {"name": "light-ball", "pct": 91.2},
      ...
    ],
    "abilities": [
      {"name": "lightning-rod", "pct": 97.8},
      ...
    ]
  }
}
```

---

### 6.4 类型相克表 (`data/type_effectiveness.json`)

18种属性间的克制关系。

```json
{
  "fire": {
    "grass": 2.0,
    "water": 0.5,
    ...
  },
  ...
}
```

---

## 7. UI服务端模块

### 7.1 Flask服务器 (`ui/ui_server.py`)

提供RESTful API接口。

#### 主要路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 返回主页面 |
| `/api/screenshot` | POST | 接收截图 |
| `/api/teams/generate` | POST | 从截图生成队伍草稿 |
| `/api/teams/build` | POST | 从草稿构建最终队伍 |
| `/api/teams/generate-opponent` | POST | 识别对手队伍 |
| `/api/damage/range` | POST | 计算伤害范围 |
| `/api/pokemon/by-name-zh/<name>` | GET | 按中文名查询宝可梦 |
| `/sprites/<path>` | GET | 提供精灵图 |
| `/api/get-layout-config` | GET | 获取布局配置 |
| `/api/save-layout-config` | POST | 保存布局配置 |

---

## 8. 数据流向图

### 我方队伍识别流程

```
┌─────────────────┐
│   moves.png     │ ← 截图（页面1）
└────────┬────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│                 parse_team.py                           │
│  ┌──────────────────┐    ┌──────────────────────────┐  │
│  │  _parse_moves    │    │  _parse_stats           │  │
│  │  (sprite检测)     │    │  (属性值+性格识别)        │  │
│  │  (OCR识别)        │    │                         │  │
│  └────────┬─────────┘    └────────────┬─────────────┘  │
│           ↓                           ↓                 │
│  detect_cards[]                   stat_cards[]          │
└────────────┬─────────────────────────┬────────────────┘
             ↓                          ↓
┌─────────────────────────────────────────────────────────┐
│               ui_server.py /api/teams/generate          │
│                                                         │
│  parse_team_init(moves_path, stats_path)               │
│         ↓                                               │
│  [detect_cards, move_cards, stat_cards]                │
│         ↓                                               │
│  保存到 draft.json                                     │
└─────────────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────┐
│               ui_server.py /api/teams/build             │
│                                                         │
│  for each card:                                        │
│      builder.build_pokemon(dc, mc, sc)                  │
│         ↓                                               │
│      Pokemon对象                                        │
│         ↓                                               │
│  保存到 temp.json                                       │
└─────────────────────────────────────────────────────────┘
```

### 伤害计算流程

```
┌─────────────────────────────────────────────────────────┐
│            前端点击技能 → /api/damage/range             │
└─────────────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────┐
│  ui_server.py _compute_damage_range()                   │
│                                                         │
│  1. 获取攻击方属性（我方取实际值，对手取max）              │
│  2. 获取防御方属性（我方取实际值，对手取min/max区间）       │
│  3. 计算type_multiplier                                  │
│  4. 计算damage_min = f(power, atk, def_max, roll=85)    │
│  5. 计算damage_max = f(power, atk, def_min, roll=100)  │
│  6. 应用必定要害/范围技能修正                            │
│  7. 计算hp百分比                                        │
└─────────────────────────────────────────────────────────┘
             ↓
返回: [{opp_name, range: {damage_min, damage_max, hp_pct_min, hp_pct_max}}]
```

---

## 9. 核心数据模型

### Pokemon类

```python
@dataclass
class Pokemon:
    name: str                    # 英文名
    name_zh: str                 # 中文名
    index: int                   # 图鉴号
    nickname: str                # 昵称
    
    types: list                  # 属性类型
    base_stats: dict             # 种族值
    stats: dict                  # 实际属性（我方）或区间[min,max]（对手）
    evs: dict                    # 努力值（仅我方）
    nature: str                  # 性格
    
    ability: Ability | list      # 特性（我方单/对手列表）
    held_item: HeldItem | list   # 持有物（我方单/对手列表）
    moves: list[Move]           # 招式列表
    
    type_effectiveness: dict      # 防守相克表
    sprite: str                  # 精灵图路径
    
    evoforms: list[EvoForm]     # 进化形态（Mega等）
```

### Move类

```python
@dataclass
class Move:
    name: str                   # 英文名
    name_zh: str                 # 中文名
    power: int | None            # 威力
    accuracy: int | None        # 命中
    category: str               # physical/special/status
    type: str                   # 属性
    priority: int               # 优先度
    
    ailment: str                # 附加状态
    ailment_chance: int         # 附加概率
    flinch_chance: int          # 畏缩概率
    stat_changes: list          # 属性变化
    
    pct: float | None           # 使用率（对手队伍）
```

### EvoForm类

```python
@dataclass
class EvoForm:
    slug_name: str               # slug
    form_name: str               # 英文名
    form_name_zh: str            # 中文名
    
    base_stats: dict             # 种族值
    stats: dict                 # 实际属性（区间或单值）
    
    ability: Ability | None      # 形态特性
    types: list                 # 形态属性
    
    type_effectiveness: dict     # 防守相克表
    sprite: str                 # 精灵图路径
```

---

## 10. 配置文件说明

### 10.1 card_layout.json

我方队伍卡片布局配置。

```json
{
  "layout": {
    "top_x": 191,           // 左上角X
    "top_y": 272,           // 左上角Y
    "rect_w": 738,          // 卡片宽度
    "rect_h": 186,          // 卡片高度
    "vertical_gap": 31,     // 垂直间距
    "horizontal_gap": 64   // 左右卡片间距
  },
  "regions": {
    "sprite": {"rx": 0.01, "ry": -0.11, "size": 66},   // 相对卡片的位置
    "type1": {"rx": 0.471, "ry": 0.05, "size": 30},
    "type2": {"rx": 0.528, "ry": 0.05, "size": 30}
  },
  "bg_colors_multi": [[221,237,245], [200,95,115]],  // 多色背景色(BGR)
  "stat_arrows": [...],    // 性格箭头位置
  "stat_boxes": {...}      // 属性数值框位置
}
```

### 10.2 opponent_team_layout.json

对手队伍布局配置。

```json
{
  "base_resolution": {"width": 1920, "height": 1080},
  "slot_layout": {
    "x0": 1554, "y0": 157,
    "width": 300, "height": 115,
    "gap": 11, "count": 6
  },
  "slot_regions": {
    "sprite": {"rx0": 0.2152, "ry0": 0.1466, "rx1": 0.5662, "ry1": 0.9914},
    "type1": {...},
    "type2": {...}
  }
}
```

---

## 附录：关键算法总结

### ResNet50特征提取

```
输入图像 → Resize(224x224) → Normalize → ResNet50(去掉分类层) → 2048维特征向量
```

### 余弦距离计算

```
cosine_distance = 1 - cosine_similarity
                = 1 - (A·B / |A|·|B|)
```

### 背景去除（多色）

```python
mask = Σ cv2.inRange(img, color-60, color+60)
result = img where mask==0 else 255
```

### OCR文字分组

```
按y坐标排序 → y差<20视为同行 → 同行按x排序 → 拼接
```