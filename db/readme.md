数据库是sqlite3.0
表清单
> 运行时读源说明：表 3（champions_roster）由 `roster_db.py` 的 `RosterDB` 读取（参赛名单）；表 4-9（pokemon/moves/items/abilities/pokemon_abilities/language_map）由 `pokedb.py` 的 `PokeDB` 读取（宝可梦/招式/道具/特性数据），输出与旧的 `data/pokedb_cache.json` 同构；表 10-16（champions_usage*）由 `usage_db.py` 的 `UsageDB` 读取（各赛季/格式使用率），由 `build_usage_db.py` 从 `data/raw/pokemon/*.json` 构建，输出与旧的 `data/pokechamdb_cache.json` 同构。**db/db.db 不在 git**，表缺失或为空会直接抛错，勿删。表 1/2（Team/team_detail）为队伍数据，暂无代码读取。
1、Team 队伍表，记录了宝可梦对战公开的队伍信息
字段如下
Team_ID|队伍ID
Team_Description | 队伍名称
Full_Name | 队伍全名
Item_1	| 3号位宝可梦道具
Item_2 | 2号位宝可梦道具
Item_3	| 3号位宝可梦道具
Item_4	| 4号位宝可梦道具
Item_5	| 5号位宝可梦道具
Item_6	| 6号位宝可梦道具
Pokepaste | 宝可梦paste网站链接，可以查看这个队伍的详细信息
EVs	|是否有ev数据
Extracted_paste | 队伍粘贴自己还是拓展？ 目前没啥实际意义	
Replica_Status	| 队伍码状态（Y有队伍码、N没有队伍码）
Replica_Code	| 队伍码
Date_Shared	 | 队伍分享日期
Tournament_Event	| 赛事名称，如果是赛季公开的队伍有数据
Rank	| 赛事排名
Link_to_Source	| 原文地址
Report_Video	| 原文视频
Other_Links	 | 其他来源
Owner	| 作者
Pokemon_1	| 宝可梦1
Pokemon_2	| 宝可梦2
Pokemon_3	| 宝可梦3
Pokemon_4	| 宝可梦4
Pokemon_5	| 宝可梦5
Pokemon_6   | 宝可梦6

2、team_detail 队伍详细信息
Team_ID | 队伍ID
form_ids | 宝可梦形态编码拼接数据，如0001,0002,0003,0004,0005,0006
paste_info | Pokepaste网站复制的队伍数据

3、champions_roster 冠军过签的宝可梦清单表
form_id |宝可梦形态id（dex_form 编码，如 0003-1）
id | 全国图鉴id，多形态id为同一个
name | 宝可梦名称
form | 形态语义（如 mega/alola/mega-x，base 形态为 NULL）
slug | 形态名称
type1 | 属性1
type2 | 属性2（单属性为 NULL）
sprite | 图标路径
sprite_shiny | 闪光图标路径
form_num | 形态编号（如 0003-001）关联pokemon表的form_num字段，用来获取宝可梦基础属性

4、pokemon 宝可梦列表
id | 数据id，pokeapi网站中数据id
form_num | 形态编号，唯一编码
name | 宝可梦名称（英文）
name_sch | 宝可梦中文名称
type1 | 宝可梦属性1
type2 | 宝可梦属性2
hp | HP种族值
attack | 攻击种族值
defense | 防御种族值
special_attack | 特攻种族值
special_defense | 特防种族值
speed | 速度种族值
weight | 体重
height | 身高
order | 排序

5、abilities 特性表
num | 主键序号
name | 名称中文
name_j | 日文名称
name_e | 英文名称
desc | 中文描述
gen | 引入世代

6、moves 技能表
num | 主键需要
name | 中文名称
name_j | 日文名称
name_e | 英文名称
type | 技能属性（存中文），对应18种属性
cat | 技能类型。物理、特殊、变化、极巨、超极巨（极巨/超极巨暂不参与分析，读取侧过滤）
power | 招式威力
acc | 招式命中率
pp | 招式PP数量
desc | 描述
gen | 引入世代
priority | 招式先制度（-7~5，数值越大越先出招，如守住=4、电光一闪=1），缺失默认 0

7、 items 道具表（携带物）
id | 主键id
name | 中文名称
name_j | 日文名称
name_e | 英文名称
desc | 描述
in_champions | 是否在宝冠军中过签

8、 pokemon_abilities 宝可梦-特性映射表
id | 自增主键
pokemon_name | 宝可梦名称（英文 slug，关联 pokemon.name）
form_num | 形态编号（关联 pokemon.form_num）
ability | 特性英文名称（关联 abilities.name_e）

说明：ability 按 abilities.name_e 关联，但 name_e 非唯一（As One/Embody Aspect 等形态特性共用英文名，按 num 区分）；部分第九世代特性在 abilities 表中缺失（如 Beads Of Ruin），读取侧缺失时降级保留原文。同一宝可梦多个特性存多行。

9、 language_map 语言翻译表
TYPE | 条目类型（name=宝可梦名；另有 move/item/ability 等）
NUM | 关联键（TYPE='name' 时为全国图鉴 id，即 pokemon.id）
JPN | 日文译名
USA | 英文译名
FRA / ITA / DEU / ESP / KOR | 法/意/德/西/韩译名
SCH | 简体中文译名
TCH | 繁体中文译名
说明：PokeDB 的 name_zh 与中文→英文映射优先从此表取（TYPE='name' 的 SCH 列），查不到再 fallback pokemon.name_sch（去形态后缀）。共 4526 行。

10、 champions_usage 使用率主表（每 宝可梦×赛季×格式 一行，由 build_usage_db.py 从 data/raw/pokemon/*.json 构建）
id | 自增主键
slug | 宝可梦 slug（UNIQUE(slug, season, format)）
season | 赛季（M-1 ~ M-4）
format | 格式（single / double）
rank | 该赛季/格式使用率排名
dex_no | 全国图鉴号
name_en / name_ja / name_zh | 名称（建表时由 pokecham_names.json 翻译，未命中保留日文）
updated_at | 数据更新时间（ISO）
说明：UsageDB 默认读取 M-4/double（DEFAULT_SEASON/DEFAULT_FORMAT），其余赛季/格式按需查询。

11、 champions_usage_move 招式使用率子表
id | 自增主键
usage_id | 关联 champions_usage.id
rank | 榜内名次
name_ja / name_en / name_zh | 招式名（建表时翻译）
pct | 使用率百分比
（11-15 结构相同：12=champions_usage_item 道具、13=champions_usage_ability 特性、14=champions_usage_nature 性格、15=champions_usage_partner 搭档宝可梦，读取侧 partner 输出字段名为 teammates）

16、 champions_usage_ev EV 分布子表
id | 自增主键
usage_id | 关联 champions_usage.id
rank | 榜内名次
pct | 使用率百分比
hp / atk / def / sp_atk / sp_def / speed | 六维 EV（读取侧输出为 spA/spD/spe 键）

附注：_champions_roster_old_20260803 为 champions_roster 改表结构（2026-08-03 增加 form 列）时的备份，字段不含 form，无代码读取，可删。


