# PokePilot — 项目快速指南（供 AI 读取）

> 本文档是给 AI/新开发者的「速读卡」。改动代码前先读本文件，快速定位相关模块；更深的细节再读对应源码。

## 1. 项目是什么

**PokePilot** 是面向《宝可梦 冠军》（Pokémon Champions，Switch）对战场景的本地小工具：

- 浏览器 + 采集卡/摄像头画面 → 截图 → **OCR（EasyOCR）+ 图像识别（ResNet50 特征匹配）** → 自动构建己方/对方队伍 JSON。
- 网页（Flask 静态页）提供：摄像头预览、队伍槽位 CRUD、OCR 草稿校对、伤害估算（客户端 JS 引擎）、布局校准、宝可梦数据浏览。
- 全中文 UI，数据以简体中文为主（OCR 中文 → PokeDB 模糊匹配转英文）。

**语言习惯**：源码注释、错误信息、UI 均为中文；JSON key、函数名、API 字段为英文。遵守此惯例。

## 2. 技术栈

- Python 3.11+（实际 pycache 显示 3.14 也在用）、Flask + flask-cors（后端）
- opencv-python / numpy / pillow（图像）
- easyocr + torch / torchvision（OCR 与图像识别，ResNet50 预训练）
- requests + beautifulsoup4（数据爬取：Bulbapedia、Pikalytics、pokechamdb.com）
- 前端：原生 HTML/JS/CSS（`ui/` 内 index.html + script.js + team.js + type-effect.js + config.js），伤害计算引擎在 `ui/calc/production.min.js`（浏览器端）

## 3. 目录结构（重要文件）

```
pokepilot/                      # 仓库根目录
├── pokepilot/                  # Python 包
│   ├── common/
│   │   ├── pokemon.py          # 数据模型 dataclass：Pokemon / Move / Ability / HeldItem / EvoForm
│   │   ├── pokemon_builder.py  # 把 detect/OCR/usage 数据合成 Pokemon；EV/性格计算；克制矩阵
│   │   └── pokemon_detect.py   # ResNet50 特征最近邻识别宝可梦/形态；get_detector() 单例
│   ├── data/                   # 数据构建脚本（一次性/按需运行）
│   │   ├── pokedb.py           # PokeDB 访问层：从 db/db.db 实时读宝可梦/招式/道具/特性 + 中文→英文翻译（get_pokedb() 单例，见 §7）
│   │   ├── usage_db.py         # UsageDB 访问层：从 db/db.db 读各赛季/格式使用率（get_usage_db() 单例，默认 M-4/double，见 §7）
│   │   ├── build_usage_db.py   # data/raw/pokemon/*.json → db/db.db 使用率表（建表时翻译 en/zh）
│   │   ├── roster_db.py        # RosterDB：从 db/db.db 的 champions_roster 表读取参赛名单（运行时读侧唯一入口）
│   │   ├── build_roster.py     # Bulbapedia → data/champions_roster.json（参赛名单/形态，写源）
│   │   ├── download_sprites.py # Bulbagarden → sprites/champions{,_shiny}/*.png
│   │   ├── build_pikalytics.py # Pikalytics → data/pikalytics_cache.json
│   │   ├── build_pokechamdb.py # pokechamdb.com → data/pokechamdb_cache.json（主要 usage 源）
│   │   └── extract_pokecham_names.py # 解析 pokechamdb 前端 JS chunk → pokecham_names.json
│   ├── detect_team/
│   │   ├── my_team/            # layout_detect.py（自动找卡片矩形）+ parse_team.py（双页截图解析）
│   │   └── opponent_team/      # detect_opponents.py（对方队伍整屏识别）
│   ├── ui/                     # Flask 服务 + SPA 前端
│   │   ├── ui_server.py        # 主服务（唯一入口，8765 端口）；tools/ui_server.py 是另一份旧服务！
│   │   ├── index.html, script.js, team.js, type-effect.js, config.js, layout-overlay.js
│   │   └── data/（浏览页） calc/（伤害引擎） analysis/
│   ├── tools/                  # ocr_engine.py（EasyOCR 封装）、capture.py（DirectShow）、logger_util.py
│   ├── config/                 # card_layout.json、opponent_team_layout.json（可用 API 保存）
│   └── debug_tools/            # pick_coords、test_ocr、debug_card_layout 等调试脚本
├── data/                       # 运行时数据（JSON 缓存，见 §6）
├── screenshots/team|opp_team/  # 截图落盘目录
├── api-data/                   # git sparse：PokeAPI v2（**已无代码引用**，旧 pokedb 构建遗留）
├── sprites/                    # git sparse：第九世代 type 图标 + champions 精灵
├── db/  debug_output/          # 调试/本地产物
├── requirements.txt  init.ps1  init.sh  start_pokepilot.bat
└── README.md  README_EN.md  AGENTS.md（本文件）
```

## 4. 核心数据流

```
【己方队伍】screenshots/team/moves.png + stats.png
  → parse_team_init() 产生 draft（detect_cards + move_cards + stat_cards）→ 前端校对（中文输入）
  → POST /api/teams/build → PokemonBuilder.build_pokemon(detect_data, moves_data, stats_data, language="zh")
      └─ move_zh_to_en / item_zh_to_en / ability_zh_to_en：中文 → 英文（返回 slug key）
      └─ build_move / build_held_item / build_ability：按 slug 查 PokeDB → 输出规范英文名
  → data/my_team/temp.json（roster 的 ability/held_item/moves name 均为规范英文名）→ 槽位保存

【对方队伍】screenshots/opp_team/team.png
  → detect_opponents_team() → build_pokemon(detect_data)（对手模式：moves_data=None）
      └─ read_pikalytics()：usage 的 name_en（规范名）→ 内部转 slug key
      └─ build_* → PokeDB 反查 → 规范英文名
  → data/opp_team/temp.json

【伤害】前端 type-effect.js 的 calcDamage()（引擎 ./calc/production.min.js）：
  calcDamage 用 canonicalName() 把 ability/item 规范成引擎认可名（兼容 slug 与规范名），
  引擎对能力/道具做大小写敏感的精确字符串匹配（hasAbility("Huge Power")），
  服务端 /api/damage/range 已弃用（_compute_damage_range 标记「该方法已弃用」）
```

### 名称转换链路（重点，改名字相关代码前必读）

1. **源头（DB）**：`moves/items/abilities` 表的 `name_e` 列、usage 表的 `name_en` 列 = **规范英文名**（如 "Huge Power"、"Ice Beam"、"Leftovers"）；`pokemon` 表的 `name` 例外，是**小写 slug**（如 "starmie-mega"）。
2. **PokeDB 输出**：`_load_moves/_load_items/_load_abilities` 每条 dict 含 `"name"` = `name_e`（规范英文名）；key 仍是 slug（"huge-power"），仅作内部查询键。
3. **build_* 落盘**：`build_move/build_ability/build_held_item` 先用 `name.lower().replace(" ", "-")` 查库，再 `info.get("name", name)` 取规范英文名 → team JSON 的 `ability[].name / held_item[].name / moves[].name` 一律是规范英文名。
4. **前端 calcDamage**：`canonicalName('abilities'|'items', name)`（type-effect.js）用 `gen.abilities/items.get(window.calc.toID(name)).name` 反查规范名，**新旧数据（slug / 规范名）都能算对**；旧 `data/my_team/*.json` 里遗留的 slug 名无需迁移。

> 踩坑结论：引擎对能力/道具是**大小写敏感精确匹配**（`hasAbility("Huge Power","Pure Power")`），传 "Huge power"/"huge-power" 都算不出大力士（×2 攻击）。根因曾有两处：PokeDB dict 缺 `"name"` 键（已补）+ 前端 `capitalize()`（已删，换成 `canonicalName()`）。

## 5. API 一览（`ui/ui_server.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` `/data` `/data/<slug>` | SPA 页面（带 no-cache 头） |
| GET | `/api/data/pokemon-list` | 图鉴列表（rank 排序） |
| GET | `/api/data/pokemon-detail/<slug>` | 单只详情（usage 数据） |
| GET | `/api/data/pokemon-damage-rankings/<slug>?ev_hp=&ev_atk=&...&nature=` | 对全图鉴伤害排行（供前端 calcDamage） |
| POST | `/api/screenshot` | 截图落盘（multipart：`image` + `type`；opp_team → opp_team/team.png，否则 screenshots/team/{type}.png） |
| GET | `/api/teams` | 列槽位（跳过 temp.json） |
| POST | `/api/teams/load/<slot_id>` | 槽位 → temp.json |
| POST | `/api/teams/save` | temp.json → 槽位（body: slot_id/slot_name） |
| DELETE | `/api/teams/<slot_id>` | 删槽位 |
| POST | `/api/teams/generate` | 跑 OCR 草稿（需 moves.png+stats.png）→ draft.json |
| POST | `/api/teams/build` | 校对后构建 → temp.json |
| POST | `/api/teams/generate-opponent` | 对方队伍识别 → opp_team/temp.json |
| GET | `/api/pokemon/detect-card/<slug>` | 识别卡片 |
| GET | `/api/pokemon/by-name-zh/<name_zh>` | 中文名 → 形态变体 |
| GET | `/api/pokemon/detect-card-by-name-form/<name_zh>/<form>` | 按名称+形态取卡片（URL 里 `_none`=空） |
| POST | `/api/pokemon/rebuild` | 对手模式重建单只 |
| GET/POST | `/api/damage/range` | **已弃用**（勿依赖） |
| GET | `/api/get-layout-config` | 读 card_layout.json |
| POST | `/api/save-layout-config` / `/api/save-opponent-layout-config` | 写布局配置 |
| GET | `/sprites/<path>` | 精灵静态服务（PROJECT_ROOT/sprites） |
| GET | `/config/<filename>` | config 目录任意文件下载（无鉴权） |

## 6. 运行时数据文件（`data/`）与形状

- `db/db.db`（sqlite）— **唯一运行时数据源**，三套读入口：
  - **RosterDB**（`roster_db.py`，`get_roster_db()` 单例）：读 `champions_roster` 表参赛名单（337 条），字段 `form_id,id,name,form,slug,type1,type2,sprite,sprite_shiny,form_num`（`id` 转 int、`types` 由 type1/type2 拼装、`form` 读列）。
  - **PokeDB**（`pokedb.py`，`get_pokedb()` 单例）：读 `pokemon/moves/items/abilities/pokemon_abilities/language_map` 表，输出与旧 `pokedb_cache.json` 条目**同构**（`base_stats` 用 `sp_atk/sp_def`、`types` 首字母大写、`name_zh` 优先 language_map）。分域惰性加载 + 30s TTL 缓存，`clear_cache()`/`refresh()` 可立即重读。**`_load_moves/_load_items/_load_abilities` 每条 dict 含 `"name"` 键 = `name_e`（规范英文名）**，供 `build_*` 落盘时取规范名（见 §4 名称转换链路）。
  - **UsageDB**（`usage_db.py`，`get_usage_db()` 单例）：读 `champions_usage` + `champions_usage_{move,item,ability,nature,partner,ev}` 表（各赛季/格式使用率，见 db/readme 表 10-16），`get_all()`/`get_pokemon_usage()` 输出与旧 `pokechamdb_cache.json` 条目**同构**。默认生效赛季/格式 = `DEFAULT_SEASON`/`DEFAULT_FORMAT`（当前 M-4/double，暂固定）。30s TTL 缓存 + `clear_cache()`。
  - **db/ 不在 git**，表缺失/为空会直接报错（RosterDB/PokeDB 抛错、UsageDB 抛 RuntimeError），勿删。
- `champions_roster.json` — roster 的**写源/种子**（build_roster 爬虫产物），**运行时不再直接读取**；新形态需同步进 DB 才生效（`{pokemon:[{id,name,form,slug,types,available,version,sprite,sprite_shiny}]}`）。
- ~~`pokedb_cache.json`~~ — **已废弃**（损坏，不再被任何代码读取），数据已迁入 `db/db.db`，旧文件可删；补数据直接改库。
- ~~`pokechamdb_cache.json`~~ — **已废弃**（仅 build_pokechamdb 作为旧产物仍会写出，运行时不再读取），使用率数据已在 DB；raw 数据仍在 `data/raw/pokemon/*.json`。
- `pikalytics_cache.json` — 备用 usage（PokemonBuilder.read_pikalytics 其实**先查 pokechamdb 再查 pika**，名字有误导）。
- `pokecham_names.json` — 名称翻译表（en/ja/zh）。由 `extract_pokecham_names.py` 生成，但**需要仓库外的 data/mapping/*.js chunk**，所以已入库版本不要删。
- `manual.json` — PokeDB 翻译覆盖；`type_effectiveness.json` — 属性克制矩阵（key 小写）。
- `data/raw/pokemon/<slug>.json` — build_pokechamdb 的原始响应缓存。
- `data/my_team/*.json` — 队伍槽位（temp.json=当前工作缓冲，draft.json=OCR 草稿）；`data/opp_team/temp.json` — 对方队伍。

**关键形状**：
- detect-card：`{id,name,slug,sprite_key,types,score,candidates_searched}`
- move 卡片：`{slot,nickname,ability,held_item,moves[]}`；stat 卡片：`{slot,nickname,stats{},nature:"sp_atk↑/attack↓"}`
- team dict：`{trainer_name:"", roster:[Pokemon.to_dict()...]}`
- Pokemon.to_dict：`{nickname,name,name_zh,slug,index,ability,held_item,stats,base_stats,evs,nature,nature_en,evList,types,type_effectiveness,moves[],sprite?,evoforms?}`（ability/held_item 可能是 str/对象/列表三种形态）
- **名字规范**：`ability[]/held_item[]` 对象的 `name`、`moves[].name` 一律是**规范英文名**（"Huge Power"/"Choice Scarf"/"Ice Beam"），不是小写 slug；显示用 `name_zh`。

## 7. 核心逻辑要点（读代码前先看）

- **EV/属性公式（Champions 规则）**：`HP = base + 75 + EV`；其它 `int((base + 20 + EV) * 性格修正)`；**EV 上限 32**。见 `pokemon_builder.py` 的 `_calc_hp/_calc_stat/calc_ev_from_stats/calc_opponent_stats_range`。**反推/可行性判定必须用整数算术**（`_feasible_evs` 的 `(base+20+ev)*90//100`），直接 `int(x*0.9)` 有浮点截断坑（如 `int(130*0.9)==116`）。
- **性格解析与识别**：`parse_nature_string("attack↑/speed↓")` → `{stat: 1.1/0.9}`，用 Unicode 箭头 ↑↓。我方队伍性格**不再用箭头颜色检测**（stat_arrows 配置已删除），改为 `PokemonBuilder.infer_nature_and_evs(base_stats, actual_stats, ev_reads)` 数值反推：Stats 页同时 OCR 最终能力值（`text_regions.stat_numbers`）和加点数字（`text_regions.ev_numbers`，未加点的行不显示、缺读按可能无修正处理），加点读数唯一命中可行修正则直接确定，否则用「至多一升一降」全局约束消歧并输出 warnings（存入 stat_card 供人工核对）；歧义时偏好无修正。EV 直读+公式解出值落盘，人工在草稿页覆盖性格时走 `calc_ev_from_stats` 重算。
- **对手 vs 己方**：`build_pokemon(detect_data, moves_data=None, stats_data=None, language="zh")`，moves_data 为 None 即对手模式（stats 为范围 `[min,max]`，读 usage 列表）。
- **Roster 读取**：`RosterDB`（`pokepilot/data/roster_db.py`，`get_roster_db()` 单例）是参赛名单唯一读入口，返回与旧 JSON 同构的 dict（id 为 int、types 列表、form 语义字段）；表缺失/为空直接抛错，**不做 JSON 回退、不自动播种**。
- **PokeDB 读取**：`PokeDB`（`pokepilot/data/pokedb.py`，`get_pokedb()` 单例）是宝可梦/招式/道具/特性数据统一读入口。`get_pokemon/get_move/get_item/get_ability` 分域点查（`get_all_*` 惰性加载 + 30s TTL 缓存，`clear_cache()` 刷新）；`get_*_mappings()` 全表扫描供 OCR 模糊匹配；`name_zh_to_en/move_zh_to_en/item_zh_to_en/ability_zh_to_en` 中文→英文（NFKC 归一 + Levenshtein 模糊纠错，**返回 slug key**）。输出与旧 `pokedb_cache.json` 同构；`moves.cat` 为中文，**极巨/超极巨招式读取时直接过滤**（`get_move("max-flare")` → None）；**items 只读 `in_champions='Y'`（宝可梦冠军过签道具），非冠军道具不参与校验/构建**；`base_stats` 用 `sp_atk/sp_def`。
- **名称规范（canonical English name）**：队伍 JSON 里 `ability[].name / held_item[].name / moves[].name` 一律是**规范英文名**（"Huge Power"/"Choice Scarf"/"Ice Beam"），slug（"huge-power"）只作 DB 内部查询键。来源：DB `name_e`/usage `name_en` → PokeDB `"name"` 键 → `build_*` 落盘。**前端 `calcDamage` 必须先 `canonicalName()`（type-effect.js）再传给引擎**，引擎对能力/道具是大小写敏感的精确字符串匹配（`hasAbility("Huge Power")`）；**禁止用 `capitalize()`/首字母大写处理能力名**（会把 "Huge Power" 变 "Huge power"，大力士 ×2 失效，该函数已删除）。详见 §4 名称转换链路。
- **UsageDB 读取**：`UsageDB`（`pokepilot/data/usage_db.py`，`get_usage_db()` 单例）是各赛季/格式使用率数据统一读入口：`get_all(season, format)` 返回某 (赛季,格式) 全部 `{slug: entry}`（与旧 `pokechamdb_cache.json` 条目同构），`get_pokemon_usage(slug, ...)` 点查；season/format 缺省用 `DEFAULT_SEASON`/`DEFAULT_FORMAT`（M-4/double）。数据由 `build_usage_db.py` 从 `data/raw/pokemon/*.json` 平铺入库，名称建表时已翻译 en/zh（复用 build_pokechamdb 名称映射，未命中保留日文）。30s TTL 缓存 + `clear_cache()`；表缺失抛 RuntimeError。
- **图像识别**：`PokemonDetector.detect()` 用 ResNet50 全局池化特征 + 余弦最近邻，候选按「类型图标匹配」过滤（`-mega` 被排除）。首次 `get_detector()` 很慢（约 700 精灵特征预计算），`ui_server` 启动时用守护线程预热。
- **OCR**：EasyOCR `ch_sim+en`，`gpu=False`（慢）；`read_crop_text` 带 pad 便于中文。
- **布局配置**：`parse_team.py` / `detect_opponents.py` **每次调用**读 card_layout.json / opponent_team_layout.json（前端保存后立即生效，无需重启）。缺文件直接崩。

## 8. 已知坑 / 注意事项（改动时特别小心）

1. 服务端伤害接口 `/api/damage/range` 和 `_compute_damage_range` **已弃用**，真正的伤害是前端 calcDamage；修伤害相关 bug 看 `type-effect.js`/`team.js`。给前端的数据里 move/ability/item 名保持**规范英文名**（引擎对能力/道具是大小写敏感精确匹配；`canonicalName()` 可兼容遗留 slug，但不建议再产生新 slug）。
2. 启动入口**只有** `python -m pokepilot.ui.ui_server`（--port/--debug，host 固定 0.0.0.0，无 --host 参数，README 里的 --host 是文档错误）。`pokepilot/tools/ui_server.py` 是另一份旧服务，勿混淆。
3. CORS 全开、无鉴权、`/config/<filename>` 任意下载、`/api/screenshot` 的 type 参数未做路径清洗（有 `../` 穿越风险）。
4. `ui_server.py` 中 `_EVOFORM_TYPES` 在源码顺序上**晚于**使用它的路由定义——靠路由运行时才取值才成立，移动代码会炸。
5. 静态目录就是 `ui/` 根（`static_url_path=""`），`myteam.json/oppteam.json` 等会被直接下载。
6. `debug_tools/test_pokemon_builder.py` 引用了不存在的 `parse_team_old`（遗留，会 ImportError）。
7. `/api/teams/save` 依赖 temp.json 存在；`list_teams` 只跳过 temp.json，draft.json 也会被列出。
8. 伤害排行接口的 `ev_*` 参数是**全有或全无**：只要传了一个，缺省其余按 0 算，不与缓存 EV 合并。
9. OCR 调用硬编码 `debug=True`，会往 `debug_output/` 写调试产物。
10. `read_pikalytics` 名不副实（先读 pokechamdb）；`build_pokemon` 已改走 `PokeDB.get_*`（不再访问私有 `_data`，但 `self.db._data` 旧引用需留意）。
11. 运行时数据统一只从 `db/db.db` 读取：roster 经 `RosterDB`（`champions_roster` 表）、宝可梦/招式/道具/特性经 `PokeDB`（`pokemon/moves/items/abilities/pokemon_abilities/language_map` 表）、使用率经 `UsageDB`（`champions_usage*` 表），见 §7。**db/ 不在 git**：删库/新环境后表缺失或为空会直接抛错（RosterDB/PokeDB 抛错、UsageDB 抛 RuntimeError，均不做 JSON 回退、不自动播种）；`champions_roster.json` 仅是写源，改了它不跑同步 DB 不会生效；使用率表需跑 `build_usage_db.py` 才存在。

## 9. 常用命令

```bash
# 启动 UI（默认 0.0.0.0:8765）
python -m pokepilot.ui.ui_server [--port 8080] [--debug]

# 数据构建（按需）
python -m pokepilot.data.download_sprites      # 精灵图
python -m pokepilot.data.build_roster          # 参赛名单（爬 Bulbapedia）
python -m pokepilot.data.build_pikalytics --all # usage（Pikalytics）
python -m pokepilot.data.build_pokechamdb --all # usage+EV（pokechamdb.com）
python -m pokepilot.data.build_usage_db       # data/raw/pokemon/*.json → db/db.db 使用率表（幂等 upsert，--wipe 重建）
# 宝可梦/招式/道具/特性数据源 = db/db.db（无构建命令，补数据直接改库；旧 pokedb_cache.json 已废弃）

# 初始化（Windows / Unix）
powershell -ExecutionPolicy Bypass -File init.ps1   # 或 bash init.sh

# 打包免安装版（Windows）
build_portable.bat   # → pokepilot-release/（内嵌 Python 3.13.14 + CPU torch + 模型）

# 调试工具
python -m pokepilot.debug_tools.pick_coords  # 等等，见 debug_tools/ 各脚本
```

## 10. 调试

- `debug_output/` 存放识别/布局调试图（my_team/、pokemon_opp/）。
- `db/db.db` 现在是**唯一运行时读源**（roster + 宝可梦/招式/道具/特性数据 + 使用率），改动/删库前留意 git status 与 §7 的 RosterDB/PokeDB/UsageDB 报错行为；`debug_output/` 仍为本地产物。
- 数据构建脚本普遍「每只就写盘 + 可 `--resume`」，爬取有 sleep 限速。
