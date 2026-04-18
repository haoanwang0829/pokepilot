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

from pokepilot.data.pokedb import PokeDB
from .pokemon import Pokemon, Move, EvoForm, Ability, HeldItem

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
        self.roster = self._load_roster()  # 加载 champions_roster.json
        self.pika_cache = self._load_pikalytics_cache()

        # 加载 champions_roster.json 用于获取图鉴号

        # 加载类型相克表
        self.type_effectiveness = self._load_type_effectiveness()

    def _load_pikalytics_cache(self) -> dict:
        """加载 pikalytics 缓存"""
        cache_path = Path(__file__).parent.parent.parent / "data" / "pikalytics_cache.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        return {}
    
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

    def _load_roster(self) -> dict:
        """加载 champions_roster.json - 包含所有宝可梦形态信息"""
        try:
            roster_file = Path(__file__).parent.parent.parent / "data" / "champions_roster.json"
            if roster_file.exists():
                with open(roster_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"警告: 无法加载 champions_roster.json: {e}")

        return {"pokemon": []}

    def read_pikalytics(self, slug: str, name: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        pika_info = self.pika_cache.get(slug, {})
        pika_info = self.pika_cache.get(name, {}) if not pika_info else pika_info
        # 获取招式详细信息
        top_moves = []
        for m in pika_info.get("moves", [])[:8]:
            top_moves.append(
                (m["name"].lower().replace(" ", "-"), f"{m['pct']:.1f}%"))

        top_items = []
        for i in pika_info.get("items", [])[:3]:
            top_items.append(
                (i["name"].lower().replace(" ", "-"), f"{i['pct']:.1f}%"))
        
        top_abilities = []
        for a in pika_info.get("abilities", [])[:3]:
            top_abilities.append(
                (a["name"].lower().replace(" ", "-"), f"{a['pct']:.1f}%"))

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

    def build_evo_form(self, evo_poke: dict, base_pokemon: Pokemon) -> Optional[EvoForm]:
        """
        构建进化形态对象（支持我方队伍和对手队伍）

        Args:
            evo_poke: 从 roster 中获取的进化形态宝可梦数据
            base_pokemon: 基础宝可梦对象

        Returns:
            EvoForm 对象，如果构建失败返回 None
        """
        slug = evo_poke.get("slug", "")

        # 处理特殊情况：meganium-mega-nium → meganium-mega
        lookup_slug = slug if slug != "meganium-mega-nium" else "meganium-mega"

        # 从 pokedb 获取形态的属性
        evo_db = self.db._data.get("pokemon", {}).get(lookup_slug, {})
        evo_base_stats = evo_db.get("base_stats", {})
        evo_types = evo_db.get("types", [])
        evo_abilities = evo_db.get("abilities", [])
        evo_ability = evo_abilities[0] if evo_abilities else ""

        # 判断是我方队伍还是对手队伍：通过检查是否有 EV 值
        is_my_team = bool(base_pokemon.evs)

        if is_my_team:
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
        evo_ability_obj = self.build_ability(evo_ability) if evo_ability else None

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
        move_info = self.db._data.get("moves", {}).get(move_key, {})

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
        ability_info = self.db._data.get("abilities", {}).get(ability_key, {})

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
        item_info = self.db._data.get("items", {}).get(item_key, {})

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
        pokemon_db = self.db._data.get("pokemon", {})

        # 先用 slug 查询
        slug_key = pokemon_slug.lower().replace(" ", "-") if pokemon_slug else ""
        pokemon_info = pokemon_db.get(slug_key, {})

        # 如果 slug 查不到，尝试用 name 查询
        if not pokemon_info and pokemon_name:
            name_key = pokemon_name.lower().replace(" ", "-")
            pokemon_info = pokemon_db.get(name_key, {})

        base_stats = pokemon_info.get("base_stats", {})
        name_zh = pokemon_info.get("name_zh", "")
        db_types = pokemon_info.get("types", [])
        if db_types:
            types = db_types

        # 计算类型相克
        type_effectiveness = self.cal_effectiveness(types)

        # 根据是否对手队伍分别构建
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

        else:  # 我方队伍
            nickname = moves_data.get('nickname', '')
            moves_list = moves_data.get('moves', [])
            ability_input = moves_data.get('ability', '')
            held_item_input = moves_data.get('held_item', '')

            # 从 stats_data 提取信息
            stats = stats_data.get('stats', {}) if stats_data else {}
            nature = stats_data.get('nature', '') if stats_data else ''

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
            ability = self.build_ability(ability_input)

            # 构建持有物对象
            held_item = self.build_held_item(held_item_input)

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
            types=types,
            moves=[m.to_dict() if isinstance(m, Move) else m for m in moves],
            type_effectiveness=type_effectiveness,
            sprite=sprite,
        )

        # 计算 EV（仅我方队伍）
        if not is_opponent and stats:
            pokemon.evs = self.calc_ev_from_stats(pokemon)

        # 构建进化形态（我方和对手队伍都支持）
        evo_forms_data = self.find_evo_forms(pokemon_name)
        for evo_poke in evo_forms_data:
            evo_form = self.build_evo_form(evo_poke, pokemon)
            if evo_form:
                pokemon.evoforms.append(evo_form)

        return pokemon
