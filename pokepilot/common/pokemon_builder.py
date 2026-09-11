"""
Pokemon 构建器和计算逻辑

负责：
  - 从各种源构建完整的 Pokemon 对象
  - 处理与数据库的交互
  - 计算 EV、性格倍率等
"""

import json
from pathlib import Path
from typing import Optional

from pokepilot.data.pokedb import PokeDB, _fuzzy_match
from pokepilot.data.roster_db import RosterDB
from pokepilot.data.usage_db import get_usage_db
from pokepilot.tools.logger_util import setup_logger
from .pokemon import Pokemon, Move, EvoForm, Ability, HeldItem

logger = setup_logger(__name__)

# 只有这些 form 才被视为 evoform（进化形态）
_EVOFORM_TYPES = {"mega", "mega-nium", "mega-x", "mega-y", "blade-forme", "hero"}


class PokemonBuilder:
    """Pokemon 构建器 - 处理复杂的构建和计算逻辑"""

    def __init__(self):
        """
        初始化构建器

        Args:
            db: PokeDB 实例
            pika_info: Pikalytics 数据（可选）
        """
        self.db = PokeDB()
        self.roster = {"pokemon": RosterDB().get_all()}  # 从数据库读取 roster（champions_roster 表）
        # 从数据库读取使用率数据（默认赛季/格式）
        self.pokechamdb_cache = get_usage_db().get_all()
        # 所有可用赛季（最新在前），供逐赛季回退查询
        self._seasons = sorted(get_usage_db().get_seasons(), reverse=True)
        # 回退查询缓存：slug/name -> usage entry（已跨赛季查找后的结果）
        self._fallback_cache: dict[str, dict] = {}

        # 加载类型相克表
        self.type_effectiveness = self._load_type_effectiveness()

    def _load_pikalytics_cache(self) -> dict:
        """加载 pikalytics 缓存"""
        cache_path = Path(__file__).parent.parent.parent / "data" / "pikalytics_cache.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        return {}

    # ------------------------------------------------------------------
    # OCR 草稿中文名模糊纠错（生成 draft.json 之前调用）
    # ------------------------------------------------------------------

    def _correct_zh_name(self, zh_text: str, mapping: dict,
                         known_exact: set | None = None) -> str:
        """
        对单个中文名做模糊匹配纠错，返回正确的标准中文名

        命中（精确或编辑距离≤2）→ 返回标准中文名；未命中 → 返回原文。
        已知真实名称（known_exact）但不在映射范围（如非冠军道具）→ 不做纠错，返回原文。
        """
        if not zh_text or not mapping:
            return zh_text

        zh_norm = self.db._normalize_text(zh_text)
        if zh_norm in mapping:
            return zh_norm

        if known_exact and zh_norm in known_exact:
            logger.warning(f"已知名称但不在冠军范围内（保留原文）: '{zh_norm}'")
            return zh_text

        matched_key = _fuzzy_match(zh_norm, mapping)
        if matched_key != zh_norm:
            logger.warning(f"中文名模糊匹配: '{zh_norm}' → '{matched_key}'")
            return matched_key

        logger.warning(f"中文名未匹配（保留原文）: '{zh_norm}'")
        return zh_text

    def correct_move_cards(self, move_cards: list[dict]) -> list[dict]:
        """
        对 OCR 草稿的 move_cards 逐槽做中文名模糊纠错（昵称除外）

        纠错字段：ability、held_item、moves[]。昵称为自由文本不纠错。
        返回纠错后的新列表，不影响传入参数。
        """
        corrected = []
        for mc in move_cards:
            mc = dict(mc)
            mc['ability'] = self._correct_zh_name(mc.get('ability', ''), self.db.get_ability_mappings())
            mc['held_item'] = self._correct_zh_name(
                mc.get('held_item', ''), self.db.get_item_mappings(),
                known_exact=self.db.get_all_item_zh_names())
            mc['moves'] = [
                self._correct_zh_name(m, self.db.get_move_mappings())
                for m in mc.get('moves', [])
            ]
            corrected.append(mc)
        return corrected

    def _fallback_usage(self, slug: str) -> dict:
        """
        默认赛季未找到时，逐赛季回退查询（最新→最旧），结果缓存。
        跳过已查过的 key，避免重复查询。
        """
        if slug in self._fallback_cache:
            return self._fallback_cache[slug]
        usage_db = get_usage_db()
        current_fmt = usage_db.DEFAULT_FORMAT
        for season in self._seasons:
            # 跳过已在默认缓存中的赛季（已确定无此 slug）
            if season == usage_db.DEFAULT_SEASON:
                continue
            entry = usage_db.get_pokemon_usage(slug, season, current_fmt)
            if entry:
                self._fallback_cache[slug] = entry
                return entry
        self._fallback_cache[slug] = {}
        return {}

    def read_pokechamdb(self, slug: str, name: str) -> dict:
        """从使用率数据库读取宝可梦数据，未找到则逐赛季回退"""
        info = self.pokechamdb_cache.get(slug) or self.pokechamdb_cache.get(name)
        if info:
            return info
        return self._fallback_usage(slug) or self._fallback_usage(name) or {}

    def _load_type_effectiveness(self) -> dict:
        """从 type_effectiveness.json 加载类型相克表"""
        try:
            type_file = Path(__file__).parent.parent.parent / "data" / "type_effectiveness.json"
            if type_file.exists():
                with open(type_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"警告: 无法加载 type_effectiveness.json: {e}")

        return {}

    def read_pikalytics(self, slug: str, name: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
        # 默认赛季缓存 → 逐赛季回退（新→旧）
        pika_info = self.pokechamdb_cache.get(slug) or self.pokechamdb_cache.get(name)
        if not pika_info:
            pika_info = self._fallback_usage(slug) or self._fallback_usage(name)

        # 处理招式 - 合并重复的
        moves_dict = {}
        for m in pika_info.get("moves", [])[:6]:
            key = m["name"].lower().replace(" ", "-")
            pct = m.get('pct', 0)
            moves_dict[key] = moves_dict.get(key, 0) + pct
        top_moves = [(k, f"{v:.1f}%") for k, v in moves_dict.items()]

        # 处理道具 - 合并重复的
        items_dict = {}
        for i in pika_info.get("items", [])[:3]:
            key = i["name"].lower().replace(" ", "-")
            pct = i.get('pct', 0)
            items_dict[key] = items_dict.get(key, 0) + pct
        top_items = [(k, f"{v:.1f}%") for k, v in items_dict.items()]

        # 处理特性 - 合并重复的
        abilities_dict = {}
        for a in pika_info.get("abilities", [])[:3]:
            key = a["name"].lower().replace(" ", "-")
            pct = a.get('pct', 0)
            abilities_dict[key] = abilities_dict.get(key, 0) + pct
        top_abilities = [(k, f"{v:.1f}%") for k, v in abilities_dict.items()]

        return top_moves, top_items, top_abilities

    def find_evo_forms(self, pokemon_name: str) -> list[dict]:
        """查找宝可梦的所有进化形态（只包含指定的形态类型：Mega、Blade-forme、Hero）"""
        evo_forms = []

        for poke in self.roster.get("pokemon", []):
            if poke.get("name") == pokemon_name:
                form = poke.get("form")
                # 只添加指定的形态类型
                if form and form in _EVOFORM_TYPES:
                    evo_forms.append(poke)

        return evo_forms

    def build_evo_form(self, evo_poke: dict, base_pokemon: Pokemon, is_opponent: bool = False) -> Optional[EvoForm]:
        """
        构建进化形态对象（支持我方队伍和对手队伍）

        Args:
            evo_poke: 从 roster 中获取的进化形态宝可梦数据
            base_pokemon: 基础宝可梦对象
            is_opponent: 是否为对手队伍（对方用范围值，我方用 EV/性格计算精确值）

        Returns:
            EvoForm 对象，如果构建失败返回 None
        """
        slug = evo_poke.get("slug", "")

        # 处理特殊情况：meganium-mega-nium → meganium-mega
        lookup_slug = slug if slug != "meganium-mega-nium" else "meganium-mega"

        # 从 pokedb 获取形态的属性
        evo_db = self.db.get_pokemon(lookup_slug) or {}
        evo_base_stats = evo_db.get("base_stats", {})
        evo_types = evo_db.get("types", [])
        evo_abilities = evo_db.get("abilities", [])
        evo_ability = evo_abilities[0] if evo_abilities else ""

        if not is_opponent:
            # 我方队伍：计算单个属性值（使用 EV 和性格）
            evo_stats = {}
            natures = self.parse_nature_string(base_pokemon.nature)

            for stat_key in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]:
                base = evo_base_stats.get(stat_key, 0)
                ev = base_pokemon.evs.get(stat_key, 0)
                nature = 1.0 if stat_key == "hp" else natures.get(stat_key, 1.0)
                is_hp = (stat_key == "hp")

                if is_hp:
                    evo_stats[stat_key] = self._calc_hp(base, ev)
                else:
                    evo_stats[stat_key] = self._calc_stat(base, ev, nature)
        else:
            # 对手队伍：计算属性范围 [min, max]
            evo_stats = self.calc_opponent_stats_range(evo_base_stats)

        # 构建进化形态的特性对象
        evo_ability_obj = [self.build_ability(evo_ability) if evo_ability else None]

        # 计算形态的类型相克
        evo_type_effectiveness = self.cal_effectiveness(evo_types)

        # 从 roster 中直接获取精灵图，转换为相对于项目根目录的完整路径
        sprite_filename = evo_poke.get("sprite")
        sprite = f"sprites/champions/{sprite_filename}" if sprite_filename else None

        return EvoForm(
            slug_name=slug,
            form_name=evo_poke.get("form", ""),
            form_name_zh=evo_db.get("name_zh", ""),
            base_stats=evo_base_stats,
            stats=evo_stats,
            ability=evo_ability_obj,
            types=evo_types,
            type_effectiveness=evo_type_effectiveness,
            sprite=sprite,
        )

    def cal_effectiveness(self, types: list[str]) -> dict:
        """
        计算对该宝可梦的伤害倍数矩阵

        Args:
            types: 防守方属性列表，如 ["ghost", "poison"]

        Returns:
            dict: 各进攻属性的伤害倍数，如 {"normal": 1, "fighting": 2, ...}
        """
        types = [t.lower() for t in types]
        effectiveness = {}

        # 遍历所有进攻属性
        for attack_type, defense_chart in self.type_effectiveness.items():
            multiplier = 1.0

            # 对防守方的每个属性，计算伤害倍数乘积
            for defend_type in types:
                dmg = defense_chart.get(defend_type, 1.0)
                multiplier *= dmg
            if multiplier != 1.0:
                effectiveness[attack_type] = multiplier

        return effectiveness

    def parse_nature_string(self, nature_str: str) -> dict[str, float]:
        """解析性格字符串，返回每个属性的倍率"""
        natures = {
            "hp": 1.0, "attack": 1.0, "defense": 1.0,
            "sp_atk": 1.0, "sp_def": 1.0, "speed": 1.0
        }

        if not nature_str:
            return natures

        # 解析 "attack↑/speed↓" 的格式
        if "↑" in nature_str:
            key = nature_str.split("↑")[0].strip()
            natures[key] = 1.1

        if "↓" in nature_str:
            key = nature_str.split("↓")[0].split("/")[-1].strip()
            natures[key] = 0.9

        return natures

    def calc_ev_from_stats(self, pokemon: Pokemon) -> dict[str, int]:
        """反向计算 Pokemon 的 EV，基于 stats 和 base_stats"""
        evs = {}
        natures = self.parse_nature_string(pokemon.nature)

        for stat_key in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]:
            if stat_key not in pokemon.stats or stat_key not in pokemon.base_stats:
                continue

            actual_stat = pokemon.stats[stat_key]
            base_stat = pokemon.base_stats[stat_key]

            # HP 不受性格影响
            nature = 1.0 if stat_key == "hp" else natures.get(stat_key, 1.0)
            is_hp = (stat_key == "hp")

            # 用公式反向算
            if is_hp:
                ev = actual_stat - base_stat - 75
            else:
                ev = int(actual_stat / nature) - base_stat - 20

            ev = max(0, ev)  # EV 不能为负

            # 用反算出来的 EV 正向算，检查是否一致
            if is_hp:
                calculated = self._calc_hp(base_stat, ev)
            else:
                calculated = self._calc_stat(base_stat, ev, nature)

            # 如果小于目标，EV+1 再算一遍
            if calculated < actual_stat:
                ev += 1
                if is_hp:
                    calculated = self._calc_hp(base_stat, ev)
                else:
                    calculated = self._calc_stat(base_stat, ev, nature)

            evs[stat_key] = min(ev, 32)  # EV 最多 32（Pokemon Champions 系统）

        return evs

    @staticmethod
    def _feasible_evs(base_stat: int, modifier: float, actual_stat: int) -> list[int]:
        """求使 floor((base + 20 + ev) * modifier) == actual 的所有 EV（0..32）
        用整数算术避免浮点截断偏差（如 int(130*0.9)==116 的坑）"""
        num = round(modifier * 100)
        return [ev for ev in range(33)
                if (base_stat + 20 + ev) * num // 100 == actual_stat]

    def infer_nature_and_evs(self, base_stats: dict, actual_stats: dict,
                             ev_reads: dict | None = None) -> tuple[str, dict, list]:
        """
        由「最终能力值 + 加点读数 + 种族值」按公式反推性格与完整 EV。

        公式：HP = base + 75 + ev；其它 int((base + 20 + ev) * 性格修正)，EV 上限 32。
        判定规则：
          - 某属性加点读数恰好落在唯一修正的可行 EV 集内 → 直接确定该修正；
          - 读数缺失/矛盾时收集候选修正，最后用「至多一升一降」全局约束消歧，
            候选含 1.0 时优先按无修正处理。

        Returns:
            (nature_str, evs, warnings)：nature_str 形如 "attack↑/speed↓"（可为空串），
            evs 为六项完整 EV，warnings 为人工校对提示列表
        """
        ev_reads = {k: int(v) for k, v in (ev_reads or {}).items() if v is not None}
        warnings: list[str] = []
        evs: dict[str, int] = {}
        up_key: str | None = None
        down_key: str | None = None
        candidates: dict[str, set[float]] = {}
        options_map: dict[str, dict[float, list[int]]] = {}

        # HP 无性格修正，直接反解并校验读数
        hp_actual = actual_stats.get("hp")
        hp_base = base_stats.get("hp")
        if hp_actual is not None and hp_base is not None:
            ev_hp = hp_actual - hp_base - 75
            read_hp = ev_reads.get("hp")
            if not 0 <= ev_hp <= 32:
                fallback = read_hp if read_hp is not None else max(ev_hp, 0)
                warnings.append(
                    f"HP 反推 EV={ev_hp} 越界（种族 {hp_base}/实际 {hp_actual}），按 {fallback} 兜底")
                ev_hp = min(max(int(fallback), 0), 32)
            elif read_hp is not None and read_hp != ev_hp:
                warnings.append(f"HP 加点读数 {read_hp} 与公式反推 {ev_hp} 不一致，以公式为准")
            evs["hp"] = int(ev_hp)

        # 逐非 HP 属性求可行修正集合
        for key in ("attack", "defense", "sp_atk", "sp_def", "speed"):
            actual = actual_stats.get(key)
            base = base_stats.get(key)
            if actual is None or base is None:
                continue
            options = {}
            for m in (1.1, 1.0, 0.9):
                ev_set = self._feasible_evs(base, m, actual)
                if ev_set:
                    options[m] = ev_set
            if not options:
                warnings.append(
                    f"{key}: 实际值 {actual} 无法匹配任何性格修正（数值可能误读），按无修正处理")
                evs[key] = min(max(actual - base - 20, 0), 32)
                continue
            options_map[key] = options

            read_ev = ev_reads.get(key)
            chosen = None
            if read_ev is not None:
                hits = {m for m in options if read_ev in options[m]}
                if len(hits) == 1:
                    chosen = next(iter(hits))
                elif not hits:
                    warnings.append(
                        f"{key}: 加点读数 {read_ev} 与公式矛盾（读数可能误读），改用约束消歧")
            if chosen is not None:
                evs[key] = self._pick_ev(options_map[key][chosen], read_ev)
                if chosen == 1.1:
                    up_key = up_key or key
                elif chosen == 0.9:
                    down_key = down_key or key
            else:
                candidates[key] = set(options)

        # 全局消歧：约束「至多一升一降」，候选含无修正时优先取无修正；
        # 若存在多种可行选择则按偏好取值并告警，供草稿校对页人工确认
        for key, cands in candidates.items():
            allowed = [m for m in (1.0, 1.1, 0.9) if m in cands]
            allowed = [m for m in allowed
                       if m == 1.0 or (m == 1.1 and up_key is None) or (m == 0.9 and down_key is None)]
            if not allowed:
                warnings.append(
                    f"{key}: 候选修正 {sorted(cands)} 与已确定的升/降冲突，强制按 {min(cands)} 处理")
                allowed = [min(cands)]
                chosen = allowed[0]
            else:
                chosen = allowed[0]
                if len(allowed) > 1:
                    pretty = {1.1: "↑", 0.9: "↓", 1.0: "无修正"}
                    alts = ", ".join(f"{pretty[m]}(EV {self._pick_ev(options_map[key][m], None)})"
                                     for m in allowed[1:])
                    warnings.append(
                        f"{key}: 性格修正存在歧义，按「{pretty[chosen]}」处理（其它可行: {alts}），请人工核对")
            evs[key] = self._pick_ev(options_map[key][chosen], ev_reads.get(key))
            if chosen == 1.1:
                up_key = key
            elif chosen == 0.9:
                down_key = key

        # 组装性格字符串（与旧格式一致："attack↑/speed↓"）
        nature = ""
        if up_key and down_key:
            nature = f"{up_key}↑/{down_key}↓"
        elif up_key:
            nature = f"{up_key}↑"
        elif down_key:
            nature = f"{down_key}↓"

        return nature, evs, warnings

    @staticmethod
    def _pick_ev(ev_set: list[int], read_ev: int | None) -> int:
        """从可行 EV 集合中取值：读数有效用读数，否则取集合中位数"""
        if read_ev is not None and read_ev in ev_set:
            return int(read_ev)
        return int(ev_set[len(ev_set) // 2])
    
    @staticmethod
    def _calc_hp(base_stat: int, ev: int = 0) -> int:
        """正向计算 HP"""
        return base_stat + 75 + ev

    @staticmethod
    def _calc_stat(base_stat: int, ev: int = 0, nature: float = 1.0) -> int:
        """正向计算其他属性"""
        return int((base_stat + 20 + ev) * nature)

    def calc_opponent_stats_range(self, base_stats: dict) -> dict[str, list[int]]:
        """
        计算对手队伍的属性范围

        Args:
            base_stats: 种族值 {"hp": 90, "attack": 85, ...}

        Returns:
            属性范围 {"hp": [100, 200], "attack": [50, 150], ...}
            下界：EV=0, Nature=0.9（-10%）
            上界：EV=32, Nature=1.1（+10%）
        """
        stats_range = {}

        for stat_key in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]:
            base = base_stats.get(stat_key, 0)
            is_hp = (stat_key == "hp")

            if is_hp:
                # HP 不受性格影响，只受 EV 影响
                min_stat = self._calc_hp(base, ev=0)
                max_stat = self._calc_hp(base, ev=32)
            else:
                # 其他属性受 EV 和性格影响
                min_stat = self._calc_stat(base, ev=0, nature=0.9)
                max_stat = self._calc_stat(base, ev=32, nature=1.1)

            stats_range[stat_key] = [min_stat, max_stat]

        return stats_range

    def build_move(self, name: str, pct: Optional[float] = None) -> Move:
        """
        构建单个 Move 对象

        Args:
            name: 招式名字
            pct: 使用率（可选）

        Returns:
            Move 对象
        """

        move_key = name.lower().replace(" ", "-")
        move_info = self.db.get_move(move_key) or {}

        return Move(
            name=move_info.get("name", name) or name,
            name_zh=move_info.get("name_zh", ""),
            power=move_info.get("power"),
            accuracy=move_info.get("accuracy"),
            category=move_info.get("category", ""),
            type=move_info.get("type", ""),
            priority=move_info.get("priority", 0),
            short_effect=move_info.get("short_effect", ""),
            short_effect_zh=move_info.get("short_effect_zh", ""),
            ailment=move_info.get("ailment", "none"),
            ailment_chance=move_info.get("ailment_chance", 0),
            flinch_chance=move_info.get("flinch_chance", 0),
            stat_changes=move_info.get("stat_changes", []),
            pct=pct,
        )

    def build_ability(self, name: str, pct: Optional[float] = None) -> Ability:
        """
        构建单个 Ability 对象

        Args:
            name: 特性名字（英文或中文）
            pct: 使用率（可选，对方队伍用）

        Returns:
            Ability 对象
        """
        ability_key = name.lower().replace(" ", "-")
        ability_info = self.db.get_ability(ability_key) or {}

        return Ability(
            name=ability_info.get("name", name) or name,
            name_zh=ability_info.get("name_zh", ""),
            description=ability_info.get("effect", ""),
            description_zh=ability_info.get("effect_zh", ""),
            pct=pct,
        )

    def build_held_item(self, name: str, pct: Optional[float] = None) -> HeldItem:
        """
        构建单个 HeldItem 对象

        Args:
            name: 持有物名字（英文或中文）
            pct: 使用率（可选，对方队伍用）

        Returns:
            HeldItem 对象
        """
        item_key = name.lower().replace(" ", "-")
        item_info = self.db.get_item(item_key) or {}

        return HeldItem(
            name=item_info.get("name", name) or name,
            name_zh=item_info.get("name_zh", ""),
            description=item_info.get("short_effect", ""),
            description_zh=item_info.get("short_effect_zh", ""),
            pct=pct,
        )

    def build_pokemon(self,
                      detect_data: dict,
                      moves_data: Optional[dict] = None,
                      stats_data: Optional[dict] = None,
                      language: str = 'zh') -> Pokemon:
        """
        构建完整的 Pokemon 对象（支持我方队伍和对手队伍）

        Args:
            detect_data: 宝可梦检测信息
                {'id': int, 'name': '宝可梦名', 'slug': 'pokemon-slug', 'sprite_key': 'sprite-key', 'types': ['type1', 'type2']}
            moves_data: 我方队伍信息（可选，None 时视为对手队伍）
                {'nickname': '昵称', 'ability': '特性', 'held_item': '持有物', 'moves': ['招式1', '招式2', ...]}
            stats_data: 属性和性格信息（可选，我方队伍用）
                {'stats': {'hp': 156, 'attack': 92, ...}, 'nature': 'sp_atk↑/attack↓'}
            language: 语言 ('zh' 或 'en')

        Returns:
            Pokemon 对象
        """
        is_zh_input = (language == 'zh')
        is_opponent = (moves_data is None)

        # 基本信息

        index = detect_data.get('id', 0)
        pokemon_name = detect_data.get('name', '')
        pokemon_slug = detect_data.get('slug', '')
        sprite = detect_data.get('sprite_key', '')
        types = detect_data.get('types', [])

        # 从数据库获取 Pokemon 信息（先用 slug，读不到用 name）
        # 先用 slug 查询
        slug_key = pokemon_slug.lower().replace(" ", "-") if pokemon_slug else ""
        pokemon_info = self.db.get_pokemon(slug_key) or {}

        # 如果 slug 查不到，尝试用 name 查询
        if not pokemon_info and pokemon_name:
            name_key = pokemon_name.lower().replace(" ", "-")
            pokemon_info = self.db.get_pokemon(name_key) or {}

        base_stats = pokemon_info.get("base_stats", {})
        name_zh = pokemon_info.get("name_zh", "")
        db_types = pokemon_info.get("types", [])
        if db_types:
            types = db_types

        # 计算类型相克
        type_effectiveness = self.cal_effectiveness(types)

        # 根据是否对手队伍分别构建
        nature_en = []
        evList = []
        evs = {}
        if is_opponent:
            top_moves, top_items, top_abilities = self.read_pikalytics(pokemon_slug, pokemon_name)
            # 构建招式列表（带使用率）
            moves = []
            for move_slug, pct_str in top_moves:
                pct = float(pct_str.rstrip('%')) / 100 if pct_str.endswith('%') else None
                move = self.build_move(move_slug, pct=pct)
                moves.append(move)

            # 构建特性列表（带使用率）
            abilities = [
                self.build_ability(ability_slug, pct=float(pct_str.rstrip('%')) / 100 if pct_str.endswith('%') else None)
                for ability_slug, pct_str in top_abilities
            ]

            # 构建持有物列表（带使用率）
            held_items = [
                self.build_held_item(item_slug, pct=float(pct_str.rstrip('%')) / 100 if pct_str.endswith('%') else None)
                for item_slug, pct_str in top_items
            ]

            ability = abilities if abilities else ""
            held_item = held_items if held_items else ""
            nickname = ""
            # 计算对手队伍的属性范围 [min, max]
            stats = self.calc_opponent_stats_range(base_stats)
            nature = ""

            # 从 pokechamdb 读取 natures 和 EVs（对手队伍专用）
            pokechamdb_info = self.read_pokechamdb(pokemon_slug, pokemon_name)
            nature_en = pokechamdb_info.get("natures", [])
            evList = pokechamdb_info.get("evs", [])
            if evList:
                first_ev = evList[0]
                stat_map = {"hp": "hp", "atk": "attack", "def": "defense",
                            "spA": "sp_atk", "spD": "sp_def", "spe": "speed"}
                evs = {}
                for k, v in first_ev.items():
                    if k in stat_map:
                        evs[stat_map[k]] = v

        else:  # 我方队伍
            nickname = moves_data.get('nickname', '')
            moves_list = moves_data.get('moves', [])
            ability_input = moves_data.get('ability', '')
            held_item_input = moves_data.get('held_item', '')

            # 从 stats_data 提取信息（evs 为截图直读的加点；性格一律由数值核算产出，不读传入值）
            stats = stats_data.get('stats', {}) if stats_data else {}
            ev_reads = stats_data.get('evs') or {}

            if stats and base_stats:
                nature, evs, nature_warnings = self.infer_nature_and_evs(
                    base_stats, stats, ev_reads)
                for w in nature_warnings:
                    logger.warning(f"[{pokemon_slug}] 性格/EV 核算: {w}")
            else:
                nature = ""
                evs = {k: int(v) for k, v in ev_reads.items() if isinstance(v, (int, float))}

            # 将输入转换为英文
            if is_zh_input:
                ability_input = self.db.ability_zh_to_en(ability_input)
                held_item_input = self.db.item_zh_to_en(held_item_input)

            # 构建招式列表
            moves = []
            for move_name in moves_list:
                move_en = self.db.move_zh_to_en(move_name) if is_zh_input else move_name
                move = self.build_move(move_en)
                moves.append(move)

            # 构建特性对象
            ability = [self.build_ability(ability_input)]

            # 构建持有物对象
            held_item = [self.build_held_item(held_item_input)]

        # 创建 Pokemon 对象
        pokemon = Pokemon(
            nickname=nickname,
            name=pokemon_name,
            name_zh=name_zh,
            index=index,
            slug=pokemon_slug,
            ability=ability,
            held_item=held_item,
            stats=stats,
            base_stats=base_stats,
            nature=nature,
            nature_en=nature_en,
            evs=evs,
            evList=evList,
            types=types,
            moves=moves,
            type_effectiveness=type_effectiveness,
            sprite=sprite,
        )

        # 构建进化形态（我方和对手队伍都支持）
        evo_forms_data = self.find_evo_forms(pokemon_name)
        for evo_poke in evo_forms_data:
            evo_form = self.build_evo_form(evo_poke, pokemon, is_opponent=is_opponent)
            if evo_form:
                pokemon.evoforms.append(evo_form)

        return pokemon
