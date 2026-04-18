"""
本地宝可梦数据库 —— 从本地 api-data 目录读取，完全离线。

初始化数据源（只需一次）:
    git clone https://github.com/PokeAPI/api-data.git

设置路径（选其一）:
    环境变量:  set POKEAPI_DATA=C:/path/to/api-data
    或直接传参: PokeDB(api_data_path=Path("C:/path/to/api-data"))

用法:
    from pokepilot.data.pokedb import PokeDB
    db = PokeDB()
    db.build_all_pokemon()   # 首次运行，从 api-data 构建缓存
    db.pokemon_types("pelipper")   # → ["Water", "Flying"]
    db.move_type("hurricane")      # → "Flying"
"""

import json
import os
import unicodedata
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_CACHE_PATH = _DATA_DIR / "pokedb_cache.json"
_MANUAL_MAPPINGS_PATH = _DATA_DIR / "manual.json"

# api-data 根目录：优先用环境变量，否则默认在项目根目录下
_env_api_data = os.environ.get("POKEAPI_DATA", "")
_DEFAULT_API_DATA = Path(_env_api_data) if _env_api_data else \
                    Path(__file__).parent.parent.parent / "api-data"


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
    def __init__(self, cache_path: Path = _CACHE_PATH,
                 api_data_path: Path = _DEFAULT_API_DATA):
        self._path     = cache_path
        self._api_root = Path(api_data_path) / "data" / "api" / "v2"
        self._data: dict = {"pokemon": {}, "moves": {}, "items": {}, "abilities": {}}
        if cache_path.exists():
            self._data = json.loads(cache_path.read_text(encoding="utf-8"))
            self._data.setdefault("items", {})
            self._data.setdefault("abilities", {})

            # 从 _data 生成中文映射表
            self._move_mappings = {v['name_zh']: k for k, v in self._data.get('moves', {}).items() if v.get('name_zh')}
            self._item_mappings = {v['name_zh']: k for k, v in self._data.get('items', {}).items() if v.get('name_zh')}
            self._ability_mappings = {v['name_zh']: k for k, v in self._data.get('abilities', {}).items() if v.get('name_zh')}

            # 合并手动补充的映射
            manual = self._load_manual_mappings("moves")
            self._move_mappings.update(manual)
            manual = self._load_manual_mappings("items")
            self._item_mappings.update(manual)
            manual = self._load_manual_mappings("abilities")
            self._ability_mappings.update(manual)

    # ------------------------------------------------------------------
    # 本地文件读取
    # ------------------------------------------------------------------

    def _local(self, *parts: str) -> dict:
        """读取 api-data 本地 JSON，如 _local('pokemon', 'pikachu')"""
        path = self._api_root.joinpath(*parts) / "index.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _local_exists(self, *parts: str) -> bool:
        return (self._api_root.joinpath(*parts) / "index.json").exists()


    @staticmethod
    def _normalize_text(text: str) -> str:
        """规范化文本：将全宽字符转为半宽"""
        return unicodedata.normalize('NFKC', text).strip()

    def _load_manual_mappings(self, data_key: str) -> dict:
        """加载手动补充的映射（manual.json）"""
        if not _MANUAL_MAPPINGS_PATH.exists():
            return {}
        manual = json.loads(_MANUAL_MAPPINGS_PATH.read_text(encoding="utf-8"))
        return manual.get(data_key, {})

    def _translate_with_preloaded(self, zh_text: str, mapping: dict, fallback: str) -> str:
        """使用预加载的映射表进行转换"""
        if not mapping:
            return fallback

        zh_norm = self._normalize_text(zh_text)
        if zh_norm in mapping:
            return mapping[zh_norm]

        matched_key = _fuzzy_match(zh_norm, mapping)
        if matched_key != zh_norm:
            print(f"  [PokeDB] 中文名模糊匹配: '{zh_norm}' → '{matched_key}' → '{mapping[matched_key]}'")
            return mapping[matched_key]

        return fallback

    def move_zh_to_en(self, move_zh: str) -> str:
        """中文招式名 → 英文招式名"""
        return self._translate_with_preloaded(move_zh, self._move_mappings, move_zh)

    def item_zh_to_en(self, item_zh: str) -> str:
        """中文道具名 → 英文道具名"""
        return self._translate_with_preloaded(item_zh, self._item_mappings, item_zh)

    def ability_zh_to_en(self, ability_zh: str) -> str:
        """中文特性名 → 英文特性名"""
        return self._translate_with_preloaded(ability_zh, self._ability_mappings, ability_zh)

    # ------------------------------------------------------------------
    # 批量构建缓存（从 api-data 目录扫描）
    # ------------------------------------------------------------------


    def build_all_pokemon(self) -> None:
        """
        扫描 api-data/pokemon-species/ 下所有数字编号目录，
        构建全宝可梦属性 + 种族值缓存（含所有形态）。
        可断点续跑。
        """
        species_dir = self._api_root / "pokemon-species"
        ids = sorted(int(p.name) for p in species_dir.iterdir() if p.name.isdigit())
        total = len(ids)
        print(f"从 api-data 构建全部 {total} 只宝可梦缓存...")
        fetched = 0

        for i, idx in enumerate(ids, 1):
            try:
                species_data = self._local("pokemon-species", str(idx))
                species_name = species_data["name"]

                if species_name in self._data["pokemon"]:
                    continue

                varieties = species_data.get("varieties", [])
                default_pokemon_name = None

                for variety in varieties:
                    pokemon_name = variety["pokemon"]["name"]
                    if variety.get("is_default"):
                        default_pokemon_name = pokemon_name

                    if pokemon_name in self._data["pokemon"]:
                        continue

                    # api-data pokemon 目录是数字，从 URL 提取 ID
                    # variety["pokemon"]["url"] 如 "/api/v2/pokemon/1/"
                    pokemon_id = variety["pokemon"]["url"].rstrip("/").split("/")[-1]
                    if not self._local_exists("pokemon", pokemon_id):
                        continue

                    data = self._local("pokemon", pokemon_id)
                    self._data["pokemon"][pokemon_name] = self._parse_pokemon(data, species_data)

                # species_name 指向默认形态（方便不指定形态时查询）
                if default_pokemon_name and species_name not in self._data["pokemon"]:
                    self._data["pokemon"][species_name] = \
                        self._data["pokemon"].get(default_pokemon_name, {})

                fetched += 1
                if i % 100 == 0:
                    self._save()
                    print(f"  {i}/{total}，新增 {fetched} 条 ...")

            except Exception as e:
                print(f"  跳过 #{idx}: {e}")

        self._save()
        print(f"完成，缓存共 {len(self._data['pokemon'])} 条宝可梦数据")

    def _build_all_items(self, data_key: str, api_path: str, parse_fn, save_interval: int = 100) -> None:
        """通用的批量构建缓存函数"""
        item_dir = self._api_root / api_path
        ids = sorted(int(p.name) for p in item_dir.iterdir() if p.name.isdigit())
        total = len(ids)
        label = {"moves": "招式", "items": "道具", "abilities": "特性"}[data_key]
        api_name = api_path.rstrip("s")  # move, item, ability

        print(f"从 api-data 构建全部 {total} 个{label}缓存...")
        fetched = 0

        for i, idx in enumerate(ids, 1):
            try:
                data = self._local(api_name, str(idx))
                name = data["name"]
                if name not in self._data.get(data_key, {}):
                    self._data[data_key][name] = parse_fn(data)
                    fetched += 1
                if i % save_interval == 0:
                    self._save()
                    print(f"  {i}/{total}，新增 {fetched} 条 ...")
            except Exception as e:
                print(f"  跳过 {api_name} #{idx}: {e}")

        self._save()
        print(f"完成，缓存共 {len(self._data[data_key])} 个{label}")

    def build_all_moves(self) -> None:
        """扫描 api-data/move/ 构建全招式缓存"""
        self._build_all_items("moves", "move", self._parse_move, 200)

    def build_all_items(self) -> None:
        """扫描 api-data/item/ 构建全道具缓存"""
        self._build_all_items("items", "item", self._parse_item, 200)

    def build_all_abilities(self) -> None:
        """扫描 api-data/ability/ 构建全特性缓存"""
        self._build_all_items("abilities", "ability", self._parse_ability, 100)



    # ------------------------------------------------------------------
    # 内部：解析 + 按需获取单条数据
    # ------------------------------------------------------------------


    @staticmethod
    def _extract_zh_name(entries: list) -> str:
        """优先简体中文名，备选繁体"""
        for lang in ["hans", "hant"]:
            for entry in entries:
                if entry.get("language", {}).get("name") == f"zh-{lang}":
                    return entry.get("name", "")
        return ""

    @staticmethod
    def _extract_zh_text(entries: list, field: str = "flavor_text") -> str:
        """优先简体中文文本，备选繁体"""
        for lang in ["hans", "hant"]:
            for entry in entries:
                if entry.get("language", {}).get("name") == f"zh-{lang}":
                    return entry.get(field, "").replace("\n", " ")
        return ""

    @staticmethod
    def _parse_pokemon(data: dict, species_data: dict = None) -> dict:
        types = [t["type"]["name"].capitalize() for t in data["types"]]
        base_stats = {
            s["stat"]["name"].replace("special-attack", "sp_atk")
                             .replace("special-defense", "sp_def")
                             .replace("-", "_"): s["base_stat"]
            for s in data["stats"]
        }
        abilities = [a["ability"]["name"].capitalize() for a in data.get("abilities", [])]
        name_zh = PokeDB._extract_zh_name(species_data.get("names", [])) if species_data else ""

        return {
            "types": types,
            "base_stats": base_stats,
            "abilities": abilities,
            "name_zh": name_zh,
        }

    def _fetch_pokemon(self, key: str) -> None:
        """运行时按需加载单只宝可梦（缓存未命中时调用）"""
        try:
            # pokemon 目录是数字，查 species 找对应 ID
            species_data = None
            if self._local_exists("pokemon-species", key):
                species_data = self._local("pokemon-species", key)
                varieties = species_data.get("varieties", [])
                default = next((v for v in varieties if v.get("is_default")), None)
                if not default:
                    raise FileNotFoundError(key)
                pokemon_id = default["pokemon"]["url"].rstrip("/").split("/")[-1]
                data = self._local("pokemon", pokemon_id)
            else:
                raise FileNotFoundError(key)

            self._data["pokemon"][key] = self._parse_pokemon(data, species_data)
            self._save()
        except Exception as e:
            print(f"  [PokeDB] 获取 {key} 失败: {e}")
            self._data["pokemon"][key] = {"types": [], "base_stats": {}, "abilities": [], "name_zh": ""}

    @staticmethod
    def _parse_move(data: dict) -> dict:
        # 英文描述：优先 short_effect，否则从 flavor_text_entries 获取
        short_effect = next(
            (e.get("short_effect", "") for e in data.get("effect_entries", [])
             if e["language"]["name"] == "en"),
            None
        ) or next(
            (e.get("flavor_text", "").replace("\n", " ")
             for e in data.get("flavor_text_entries", [])
             if e.get("language", {}).get("name") == "en"),
            ""
        )

        meta = data.get("meta") or {}
        return {
            "type":           data["type"]["name"].capitalize(),
            "power":          data["power"],
            "category":       data["damage_class"]["name"],
            "accuracy":       data["accuracy"],
            "priority":       data["priority"],
            "ailment":        (meta.get("ailment") or {}).get("name", "none"),
            "ailment_chance": meta.get("ailment_chance", 0),
            "flinch_chance":  meta.get("flinch_chance", 0),
            "stat_changes":   [{"stat": sc["stat"]["name"], "change": sc["change"]}
                               for sc in data.get("stat_changes", [])],
            "short_effect":   short_effect,
            "name_zh":        PokeDB._extract_zh_name(data.get("names", [])),
            "short_effect_zh": PokeDB._extract_zh_text(data.get("flavor_text_entries", [])),
        }

    @staticmethod
    def _parse_item(data: dict) -> dict:
        short_effect = next(
            (e.get("short_effect", "") for e in data.get("effect_entries", [])
             if e["language"]["name"] == "en"),
            ""
        )

        return {
            "category":     data.get("category", {}).get("name", ""),
            "fling_power":  data.get("fling_power"),
            "attributes":   [a["name"] for a in data.get("attributes", [])],
            "short_effect": short_effect,
            "name_zh":      PokeDB._extract_zh_name(data.get("names", [])),
            "short_effect_zh": PokeDB._extract_zh_text(data.get("flavor_text_entries", []), "text"),
        }

    @staticmethod
    def _parse_ability(data: dict) -> dict:
        short_effect = next(
            (e.get("effect", "") for e in data.get("effect_entries", [])
             if e["language"]["name"] == "en"),
            ""
        )

        return {
            "effect":     short_effect,
            "name_zh":    PokeDB._extract_zh_name(data.get("names", [])),
            "effect_zh":  PokeDB._extract_zh_text(data.get("flavor_text_entries", [])),
        }

    def _fetch_move(self, key: str) -> None:
        try:
            self._data["moves"][key] = self._parse_move(self._local("move", key))
            self._save()
        except Exception as e:
            print(f"  [PokeDB] 获取招式 {key} 失败: {e}")
            self._data["moves"][key] = {
                "type": "", "power": 0, "category": "", "accuracy": 0,
                "priority": 0, "ailment": "none", "ailment_chance": 0,
                "flinch_chance": 0, "stat_changes": [], "short_effect": "",
                "name_zh": "", "short_effect_zh": "",
            }

    def _fetch_item(self, key: str) -> None:
        try:
            self._data["items"][key] = self._parse_item(self._local("item", key))
            self._save()
        except Exception as e:
            print(f"  [PokeDB] 获取道具 {key} 失败: {e}")
            self._data["items"][key] = {
                "category": "", "fling_power": None, "attributes": [],
                "short_effect": "", "name_zh": "", "short_effect_zh": "",
            }

    def _fetch_ability(self, key: str) -> None:
        try:
            self._data["abilities"][key] = self._parse_ability(self._local("ability", key))
            self._save()
        except Exception as e:
            print(f"  [PokeDB] 获取特性 {key} 失败: {e}")
            self._data["abilities"][key] = {
                "effect": "", "name_zh": "", "effect_zh": "",
            }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="从本地 api-data 构建 PokeDB 缓存")
    parser.add_argument("--all-pokemon",  action="store_true", help="构建全宝可梦属性+种族值缓存")
    parser.add_argument("--all-moves",    action="store_true", help="构建全招式缓存")
    parser.add_argument("--all-items",    action="store_true", help="构建全道具缓存")
    parser.add_argument("--all-abilities",action="store_true", help="构建全特性缓存")
    parser.add_argument("--all",          action="store_true", help="构建全部缓存（pokemon+moves+items+abilities）")
    parser.add_argument("--team",         default="",          help="从 my_team.json 按需补全缺失条目")
    parser.add_argument("--api-data",     default="",          help="api-data 根目录路径（覆盖环境变量）")
    args = parser.parse_args()

    kwargs = {"api_data_path": Path(args.api_data)} if args.api_data else {}
    db = PokeDB(**kwargs)

    if args.all or args.all_pokemon:
        db.build_all_pokemon()
    if args.all or args.all_moves:
        db.build_all_moves()
    if args.all or args.all_items:
        db.build_all_items()
    if args.all or args.all_abilities:
        db.build_all_abilities()
    if args.team:
        team = json.loads(Path(args.team).read_text(encoding="utf-8"))
        db.enrich_team(team)
        print("enrich 完成")

    print(f"\n缓存: {db._path}")
    print(f"  宝可梦: {len(db._data['pokemon'])} 条")
    print(f"  招式:   {len(db._data['moves'])} 条")
    print(f"  道具:   {len(db._data['items'])} 条")
