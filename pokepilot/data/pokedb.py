"""
宝可梦数据访问层 —— 从 sqlite (db/db.db) 实时读取，替代旧的 pokedb_cache.json 一次性全量加载。

数据源: db/db.db 的 pokemon / moves / items / abilities / pokemon_abilities / language_map / champions_roster 表。

特点:
    - 每域独立读取函数（pokemon / moves / items / abilities），各查各表互不干扰
    - 惰性加载 + TTL 缓存：首次访问某域才读库，到期自动重读（默认 30 秒），clear_cache() 可立即刷新
    - 输出 dict 与旧 pokedb_cache.json 条目同构，消费方按字段名取值即可

用法:
    from pokepilot.data.pokedb import get_pokedb
    db = get_pokedb()
    db.get_pokemon("charizard-mega-x")   # → {types, base_stats, abilities, name_zh} | None
    db.get_move("protect")               # → {type, power, category, ...} | None（极巨/超极巨 → None）
    db.move_zh_to_en("守住")             # → "protect"

注意:
    - 本模块只读，不建表/写库。
    - DB 路径可用环境变量 POKEPILOT_DB_PATH 覆盖（默认 <项目根>/db/db.db）。
    - moves.cat 为中文；极巨/超极巨招式暂不参与分析，读取时直接过滤。
    - items 只读取 in_champions='Y'（宝可梦冠军过签道具），非冠军道具不参与校验/构建。
    - abilities.name_e 非唯一（As One/Embody Aspect），取 num 最小的一条。
"""

import json
import os
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_env_db_path = os.environ.get("POKEPILOT_DB_PATH", "")
_DEFAULT_DB_PATH = Path(_env_db_path) if _env_db_path else _ROOT / "db" / "db.db"
_MANUAL_MAPPINGS_PATH = _ROOT / "data" / "manual.json"

# 缓存 TTL（秒）：DB 外部改动后，最多 _CACHE_TTL 秒内自动重新读库
_CACHE_TTL = 300.0

# 中文属性名 → 英文（首字母大写，对齐旧缓存与前端 PIXILATE_TYPE_MAP）
_TYPE_ZH_TO_EN = {
    "一般": "Normal", "格斗": "Fighting", "飞行": "Flying", "毒": "Poison",
    "地面": "Ground", "岩石": "Rock", "虫": "Bug", "幽灵": "Ghost",
    "钢": "Steel", "火": "Fire", "水": "Water", "草": "Grass",
    "电": "Electric", "超能力": "Psychic", "冰": "Ice", "龙": "Dragon",
    "恶": "Dark", "妖精": "Fairy",
}
# 中文技能分类 → 英文（极巨/超极巨暂不参与分析，读取时过滤）
_CAT_ZH_TO_EN = {"物理": "physical", "特殊": "special", "变化": "status"}
_FILTERED_CATS = {"极巨", "超极巨"}


def _slugify(s: str) -> str:
    """英文名 → slug 键（与 ui_server 的 _slug 一致，并剥离重音符号）"""
    if not s:
        return ""
    text = unicodedata.normalize("NFKD", s)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower().replace(" ", "-").replace("'", "").replace(".", "")


def _to_int_or_none(value):
    """DB 中的数值/中文串 → int 或 None（'—'/'变化'/空 → None）"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in ("—", "变化"):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _strip_form_suffix(name_sch: str) -> str:
    """去掉中文名中的形态后缀，如 '喷火龙-mega-x' → '喷火龙'"""
    if not name_sch:
        return ""
    return name_sch.split("-")[0] if "-" in name_sch else name_sch


def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串的 Levenshtein 距离（编辑距离）"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def _fuzzy_match(query: str, candidates: dict, max_distance: int = 2) -> str:
    """
    模糊匹配：在候选列表中找最接近的名字

    Args:
        query: 查询字符串（可能包含 OCR 错误）
        candidates: 候选字典 {key: value}
        max_distance: 最大编辑距离阈值

    Returns:
        最匹配的 key，如果找不到则返回原 query
    """
    query_lower = query.lower()
    best_match = None
    best_distance = max_distance + 1

    for key in candidates.keys():
        key_lower = key.lower()
        distance = _levenshtein_distance(query_lower, key_lower)
        if distance < best_distance:
            best_distance = distance
            best_match = key

    return best_match if best_match else query


class PokeDB:
    """从 sqlite 读取宝可梦数据的统一访问层（分域惰性加载 + TTL 缓存）"""

    def __init__(self, db_path: Path = _DEFAULT_DB_PATH, ttl: float = _CACHE_TTL):
        self._db_path = Path(db_path)
        self._ttl = ttl
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------

    def _cached(self, domain: str, loader):
        with self._lock:
            hit = self._cache.get(domain)
            if hit is not None and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
        value = loader()
        with self._lock:
            self._cache[domain] = (time.monotonic(), value)
        return value

    def clear_cache(self) -> None:
        """清空全部域缓存，下次访问立即重新读库"""
        with self._lock:
            self._cache.clear()

    def refresh(self) -> None:
        """同 clear_cache，供外部 DB 数据更新后手动刷新"""
        self.clear_cache()

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise RuntimeError(
                f"数据库不存在: {self._db_path}（缺少 db/db.db，宝可梦数据从该库读取）")
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # 分域读取（各自查询自己的表）
    # ------------------------------------------------------------------

    def _load_pokemon(self) -> dict:
        """pokemon 表 + pokemon_abilities + language_map → {slug: dict}"""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT id, form_num, name, name_sch, type1, type2, "
                "hp, attack, defense, special_attack, special_defense, speed "
                "FROM pokemon").fetchall()
            lang_zh = dict(conn.execute(
                "SELECT NUM, SCH FROM language_map "
                "WHERE TYPE='name' AND SCH IS NOT NULL AND SCH != ''").fetchall())
            roster = conn.execute(
                "SELECT slug, form_num FROM champions_roster").fetchall()
            ab_rows = conn.execute(
                "SELECT form_num, ability FROM pokemon_abilities ORDER BY id").fetchall()
        finally:
            conn.close()

        abilities_by_form: dict[str, list] = {}
        for form_num, ability in ab_rows:
            abilities_by_form.setdefault(form_num, []).append(_slugify(ability))

        form_to_id = {r["form_num"]: r["id"] for r in rows}
        by_form_num: dict[str, dict] = {}
        result: dict[str, dict] = {}

        for r in rows:
            types = [r["type1"].capitalize()] if r["type1"] else []
            if r["type2"]:
                types.append(r["type2"].capitalize())
            base_stats = {
                "hp": r["hp"], "attack": r["attack"], "defense": r["defense"],
                "sp_atk": r["special_attack"], "sp_def": r["special_defense"],
                "speed": r["speed"],
            }
            base_num = (r["form_num"] or "")[:4] + "-000"
            name_zh = lang_zh.get(form_to_id.get(base_num)) or _strip_form_suffix(r["name_sch"])
            item = {
                "types": types,
                "base_stats": base_stats,
                "abilities": abilities_by_form.get(r["form_num"], []),
                "name_zh": name_zh,
            }
            result[_slugify(r["name"])] = item
            by_form_num[r["form_num"]] = item

        # roster slug 别名（如 'maushold'/'meowstic' 等基础名不等于 pokemon.name，
        # 按 form_num 一对一关联到对应形态的种族值）
        for slug, form_num in roster:
            item = by_form_num.get(form_num)
            if item is not None:
                result[_slugify(slug)] = item

        return result

    def _load_moves(self) -> dict:
        """moves 表 → {slug: dict}（极巨/超极巨过滤）"""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT name, name_e, type, cat, power, acc, priority, desc AS description "
                "FROM moves ORDER BY num").fetchall()
        finally:
            conn.close()

        result: dict[str, dict] = {}
        for r in rows:
            if r["cat"] in _FILTERED_CATS:
                continue
            key = _slugify(r["name_e"])
            if key in result:
                continue
            result[key] = {
                "name": r["name_e"],
                "type": _TYPE_ZH_TO_EN.get(r["type"], r["type"]),
                "power": _to_int_or_none(r["power"]),
                "category": _CAT_ZH_TO_EN.get(r["cat"], r["cat"]),
                "accuracy": _to_int_or_none(r["acc"]),
                "priority": int(r["priority"] or 0),
                "ailment": "none",
                "ailment_chance": 0,
                "flinch_chance": 0,
                "stat_changes": [],
                "short_effect": "",
                "name_zh": r["name"],
                "short_effect_zh": r["description"] or "",
            }
        return result

    def _load_items(self) -> dict:
        """items 表 → {slug: dict}（只含宝可梦冠军过签道具 in_champions='Y'，供校验/构建用）"""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT name, name_e, desc AS description FROM items "
                "WHERE in_champions='Y'").fetchall()
        finally:
            conn.close()

        result: dict[str, dict] = {}
        for r in rows:
            key = _slugify(r["name_e"])
            if key in result:
                continue
            result[key] = {
                "name": r["name_e"],
                "category": "",
                "fling_power": None,
                "attributes": [],
                "short_effect": "",
                "name_zh": r["name"],
                "short_effect_zh": r["description"] or "",
            }
        return result

    def _load_all_item_zh_names(self) -> set:
        """items 表全部中文名（含 in_champions='N' 的非冠军道具）→ 已知真实名称集合"""
        conn = self._open()
        try:
            rows = conn.execute("SELECT name FROM items").fetchall()
        finally:
            conn.close()
        return {self._normalize_text(r["name"]) for r in rows if r["name"]}

    def _load_abilities(self) -> dict:
        """abilities 表 → {slug: dict}（name_e 重复取 num 最小的一条）"""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT num, name, name_e, desc AS description "
                "FROM abilities ORDER BY num").fetchall()
        finally:
            conn.close()

        result: dict[str, dict] = {}
        for r in rows:
            key = _slugify(r["name_e"])
            if key in result:
                continue
            result[key] = {
                "name": r["name_e"],
                "effect": "",
                "name_zh": r["name"],
                "effect_zh": r["description"] or "",
            }
        return result

    # ------------------------------------------------------------------
    # 对外：分域数据
    # ------------------------------------------------------------------

    def get_all_pokemon(self) -> dict:
        return self._cached("pokemon", self._load_pokemon)

    def get_all_moves(self) -> dict:
        return self._cached("moves", self._load_moves)

    def get_all_items(self) -> dict:
        return self._cached("items", self._load_items)

    def get_all_abilities(self) -> dict:
        return self._cached("abilities", self._load_abilities)

    def get_pokemon(self, slug: str) -> dict | None:
        """按 slug 查单只宝可梦（含 roster 别名），查不到返回 None"""
        return self.get_all_pokemon().get(_slugify(slug))

    def get_move(self, key: str) -> dict | None:
        """按 slug 查招式，极巨/超极巨或不存在返回 None"""
        return self.get_all_moves().get(_slugify(key))

    def get_item(self, key: str) -> dict | None:
        """按 slug 查道具，查不到返回 None"""
        return self.get_all_items().get(_slugify(key))

    def get_ability(self, key: str) -> dict | None:
        """按 slug 查特性，查不到返回 None"""
        return self.get_all_abilities().get(_slugify(key))

    def get_all_item_zh_names(self) -> set:
        """已知全部道具中文名（含非冠军道具），供不做模糊纠错的判断使用"""
        return self._cached("items_zh_all", self._load_all_item_zh_names)

    # ------------------------------------------------------------------
    # 中文 → 英文映射（惰性构建 + TTL 缓存）
    # ------------------------------------------------------------------

    def _load_pokemon_mappings(self) -> dict:
        """{中文名: 英文基础名}，基于 champions_roster 构建（与 detect 的 variants.name 匹配）"""
        conn = self._open()
        try:
            roster = conn.execute(
                "SELECT id, name, form_num FROM champions_roster").fetchall()
            lang_zh = dict(conn.execute(
                "SELECT NUM, SCH FROM language_map "
                "WHERE TYPE='name' AND SCH IS NOT NULL AND SCH != ''").fetchall())
            pokemon_names = dict(conn.execute(
                "SELECT form_num, name_sch FROM pokemon").fetchall())
        finally:
            conn.close()

        mapping: dict[str, str] = {}
        for r in roster:
            try:
                base_id = int(str(r["id"]))
            except (TypeError, ValueError):
                base_id = None
            name_zh = lang_zh.get(base_id) or _strip_form_suffix(pokemon_names.get(r["form_num"], ""))
            if name_zh:
                mapping[name_zh] = r["name"]
        return mapping

    def _load_move_mappings(self) -> dict:
        mapping = {v["name_zh"]: k for k, v in self.get_all_moves().items() if v.get("name_zh")}
        mapping.update(self._load_manual_mappings("moves"))
        return mapping

    def _load_item_mappings(self) -> dict:
        mapping = {v["name_zh"]: k for k, v in self.get_all_items().items() if v.get("name_zh")}
        mapping.update(self._load_manual_mappings("items"))
        return mapping

    def _load_ability_mappings(self) -> dict:
        mapping = {v["name_zh"]: k for k, v in self.get_all_abilities().items() if v.get("name_zh")}
        mapping.update(self._load_manual_mappings("abilities"))
        return mapping

    def get_pokemon_mappings(self) -> dict:
        return self._cached("map_pokemon", self._load_pokemon_mappings)

    def get_move_mappings(self) -> dict:
        return self._cached("map_moves", self._load_move_mappings)

    def get_item_mappings(self) -> dict:
        return self._cached("map_items", self._load_item_mappings)

    def get_ability_mappings(self) -> dict:
        return self._cached("map_abilities", self._load_ability_mappings)

    # ------------------------------------------------------------------
    # 中文名翻译
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_text(text: str) -> str:
        """规范化文本：将全宽字符转为半宽"""
        return unicodedata.normalize('NFKC', text).strip()

    def _load_manual_mappings(self, data_key: str) -> dict:
        """加载手动补充的映射（manual.json）"""
        if not _MANUAL_MAPPINGS_PATH.exists():
            return {}
        try:
            manual = json.loads(_MANUAL_MAPPINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return manual.get(data_key, {})

    def _translate_with_preloaded(self, zh_text: str, mapping: dict, fallback: str,
                                  known_exact: set | None = None) -> str:
        """
        使用预加载的映射表进行转换

        Args:
            known_exact: 已知真实名称集合。命中（精确）这些名称但不在 mapping
                范围时直接返回 fallback，不做模糊纠错（避免把范围外的
                真实名称强行纠成范围内道具，如非冠军道具『大师球』→『烟雾球』）。
        """
        if not mapping:
            return fallback

        zh_norm = self._normalize_text(zh_text)
        if zh_norm in mapping:
            return mapping[zh_norm]

        if known_exact and zh_norm in known_exact:
            print(f"  [PokeDB] '{zh_norm}' 为已知名称但不在冠军范围内（保留原文）")
            return fallback

        matched_key = _fuzzy_match(zh_norm, mapping)
        if matched_key != zh_norm:
            print(f"  [PokeDB] 中文名模糊匹配: '{zh_norm}' → '{matched_key}' → '{mapping[matched_key]}'")
            return mapping[matched_key]

        return fallback

    def name_zh_to_en(self, name_zh: str) -> str:
        """中文宝可梦名 → 英文基础名"""
        return self._translate_with_preloaded(name_zh, self.get_pokemon_mappings(), name_zh)

    def move_zh_to_en(self, move_zh: str) -> str:
        """中文招式名 → 英文招式 slug"""
        return self._translate_with_preloaded(move_zh, self.get_move_mappings(), move_zh)

    def item_zh_to_en(self, item_zh: str) -> str:
        """中文道具名 → 英文道具 slug（只含冠军道具；已知非冠军道具不做模糊纠错，返回原文）"""
        return self._translate_with_preloaded(
            item_zh, self.get_item_mappings(), item_zh,
            known_exact=self.get_all_item_zh_names())

    def ability_zh_to_en(self, ability_zh: str) -> str:
        """中文特性名 → 英文特性 slug"""
        return self._translate_with_preloaded(ability_zh, self.get_ability_mappings(), ability_zh)


# --------------------------------------------------------------------------
# 全局单例（避免每个消费方各自连库）
# --------------------------------------------------------------------------

_instance: PokeDB | None = None
_lock = threading.Lock()


def get_pokedb() -> PokeDB:
    """线程安全的 PokeDB 全局单例获取"""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = PokeDB()
    return _instance


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------

if __name__ == "__main__":
    print("pokedb 数据源已改为从 db/db.db 读取，不再生成/读取 pokedb_cache.json。")
    print("如需补充数据，请直接修改 db/db.db（pokemon/moves/items/abilities/pokemon_abilities/language_map 表）。")
