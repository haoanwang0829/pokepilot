"""
Pokemon 数据模型

包含：
  - AttributeOption: 游戏属性选项基类（特性、持有物）
  - Ability: 宝可梦特性
  - HeldItem: 宝可梦持有物
  - Move: 招式对象
  - EvoForm: 进化形态（Mega Evolution 等）
  - Pokemon: 宝可梦对象（代表队伍中的一只）
"""

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class AttributeOption:
    """游戏属性选项基类（特性、持有物等共用）"""
    name: str
    name_zh: str
    description: str = ""
    description_zh: str = ""
    pct: Optional[float] = None  # 使用率（对方队伍数据）

    def to_dict(self) -> dict:
        """转换为字典（JSON 序列化）"""
        result = {
            "name": self.name,
            "name_zh": self.name_zh,
            "description": self.description,
            "description_zh": self.description_zh,
        }
        if self.pct is not None:
            result["pct"] = self.pct
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "AttributeOption":
        """从字典加载对象（JSON 反序列化）"""
        return cls(
            name=data.get("name", ""),
            name_zh=data.get("name_zh", ""),
            description=data.get("description", ""),
            description_zh=data.get("description_zh", ""),
            pct=data.get("pct"),
        )


@dataclass
class Ability(AttributeOption):
    """宝可梦特性"""
    pass


@dataclass
class HeldItem(AttributeOption):
    """宝可梦持有物"""
    pass


@dataclass
class Move:
    """招式对象"""
    name: str
    name_zh: str
    power: Optional[int] = None
    accuracy: Optional[int] = None
    category: str = ""
    type: str = ""
    priority: int = 0
    short_effect: str = ""
    short_effect_zh: str = ""
    ailment: str = "none"
    ailment_chance: int = 0
    flinch_chance: int = 0
    stat_changes: list = field(default_factory=list)
    pct: Optional[float] = None  # 使用率（对方队伍数据）

    @classmethod
    def from_dict(cls, data: dict) -> "Move":
        """从字典加载 Move 对象（JSON 反序列化）"""
        return cls(
            name=data.get("name", ""),
            name_zh=data.get("name_zh", ""),
            power=data.get("power"),
            accuracy=data.get("accuracy"),
            category=data.get("category", ""),
            type=data.get("type", ""),
            priority=data.get("priority", 0),
            short_effect=data.get("short_effect", ""),
            short_effect_zh=data.get("short_effect_zh", ""),
            ailment=data.get("ailment", "none"),
            ailment_chance=data.get("ailment_chance", 0),
            flinch_chance=data.get("flinch_chance", 0),
            stat_changes=data.get("stat_changes", []),
            pct=data.get("pct"),
        )

    def to_dict(self) -> dict:
        """转换为字典（JSON 序列化）"""
        result = {
            "name": self.name,
            "name_zh": self.name_zh,
            "power": self.power,
            "accuracy": self.accuracy,
            "category": self.category,
            "type": self.type,
            "priority": self.priority,
            "short_effect": self.short_effect,
            "short_effect_zh": self.short_effect_zh,
            "ailment": self.ailment,
            "ailment_chance": self.ailment_chance,
            "flinch_chance": self.flinch_chance,
            "stat_changes": self.stat_changes,
        }
        if self.pct is not None:
            result["pct"] = self.pct
        return result


@dataclass
class EvoForm:
    """宝可梦进化形态（Mega Evolution 等）"""
    slug_name: str                    # "mega-charizard-x"
    form_name: str                  # 英文名 (e.g., "Mega Charizard X")
    form_name_zh: str               # 中文名 (e.g., "超级喷火龙 X")

    base_stats: dict = field(default_factory=lambda: {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_atk": 0, "sp_def": 0, "speed": 0
    })                              # 形态的种族值

    stats: dict = field(default_factory=lambda: {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_atk": 0, "sp_def": 0, "speed": 0
    })                              # 形态的实际属性值

    ability: Union[Ability, str, None] = None  # 形态特有的特性（Ability 对象或字符串）

    types: Optional[list] = None    # 形态的属性类型（如果改变）

    # 属性克制信息（防守倍率）
    type_effectiveness: dict = field(default_factory=dict)  # {"water": 2.0, "grass": 0.5, ...}

    sprite: Optional[str] = None    # 精灵图路径 (e.g., "champions/Menu CP 0006-Mega X.png")


@dataclass
class Pokemon:
    """Pokemon 对象 - 代表队伍中的一只宝可梦"""
    name: str                           # 英文名 (e.g., "pelipper")
    name_zh: str                        # 中文名（OCR 识别的原始名字）(e.g., "大嘴鸥")
    index: int                          # 图鉴编号 (e.g., 279)
    nickname: Optional[str] = ""                  # 昵称 (e.g., "rain setter")

    slug: str = ""                      # 地区形态 (e.g., "alola", "galar", "eternal-flower")

    # 特性：我方队伍为单个 Ability，对方队伍为列表
    ability: Union[Ability, list[Ability], str] = ""  # 兼容字符串（向后兼容）

    # 持有物：我方队伍为单个 HeldItem，对方队伍为列表
    held_item: Union[HeldItem, list[HeldItem], str] = ""  # 兼容字符串（向后兼容）
    # 属性相关
    stats: dict = field(default_factory=lambda: {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_atk": 0, "sp_def": 0, "speed": 0
    })                                  # 实际属性值
    base_stats: dict = field(default_factory=lambda: {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_atk": 0, "sp_def": 0, "speed": 0
    })                                  # 种族值
    evs: dict = field(default_factory=lambda: {})                                  # 努力值

    nature: str = ""                    # 性格 (e.g., "speed↑/attack↓")
    types: list = field(default_factory=list)  # 属性类型 (e.g., ["Water", "Flying"])

    moves: list = field(default_factory=list)  # 招式列表

    # 属性克制信息（防守倍率）
    type_effectiveness: dict = field(default_factory=dict)  # {"water": 2.0, "grass": 0.5, ...}

    # 精灵图路径
    sprite: Optional[str] = None        # 精灵图路径 (e.g., "champions/Menu CP 0006.png")

    # 进化形态（Mega Evolution 等）
    evoforms: list = field(default_factory=list)  # 可用的进化形态列表 (list of EvoForm)

    @classmethod
    def from_dict(cls, data: dict) -> "Pokemon":
        """从字典构造 Pokemon 对象"""
        name = data.get("name", "")
        name_zh = data.get("nickname", "")  # nickname 存的是中文名
        index = data.get("index", 0)

        # 构造招式列表
        moves_data = data.get("moves", [])
        moves = [
            Move.from_dict(m) if isinstance(m, dict) else m
            for m in moves_data
        ]

        # 处理特性：支持字符串（向后兼容）、字典或列表
        def deserialize_attribute(attr_data, attr_class):
            """反序列化特性或持有物"""
            if isinstance(attr_data, str):
                return attr_data
            elif isinstance(attr_data, dict):
                return attr_class.from_dict(attr_data)
            elif isinstance(attr_data, list):
                return [attr_class.from_dict(a) if isinstance(a, dict) else a for a in attr_data]
            else:
                return ""

        ability = deserialize_attribute(data.get("ability", ""), Ability)
        held_item = deserialize_attribute(data.get("held_item", ""), HeldItem)

        return cls(
            name=name,
            name_zh=name_zh,
            index=index,
            nickname=data.get("nickname", ""),  # 用户自定义昵称
            slug=data.get("slug", ""),  # 地区形态信息
            ability=ability,
            ability_zh=data.get("ability_zh", ""),
            ability_description=data.get("ability_description", ""),
            ability_description_zh=data.get("ability_description_zh", ""),
            held_item=held_item,
            held_item_zh=data.get("held_item_zh", ""),
            held_item_description=data.get("held_item_description", ""),
            held_item_description_zh=data.get("held_item_description_zh", ""),
            stats=data.get("stats", {}),
            base_stats=data.get("base_stats", {}),
            evs=data.get("evs", {}),
            nature=data.get("nature", ""),
            types=data.get("types", []),
            moves=moves,
            type_effectiveness=data.get("type_effectiveness", {}),
        )

    def to_dict(self) -> dict:
        """转换为字典（用于 JSON 序列化）"""
        def serialize_attribute(attr):
            """序列化特性或持有物（支持字符串、对象、列表）"""
            if isinstance(attr, (Ability, HeldItem)):
                return attr.to_dict()
            elif isinstance(attr, list):
                return [a.to_dict() if isinstance(a, (Ability, HeldItem)) else a for a in attr]
            else:
                return attr

        result = {
            "nickname": self.nickname,
            "name": self.name,
            "name_zh": self.name_zh,
            "slug": self.slug,
            "index": self.index,
            "ability": serialize_attribute(self.ability),
            "held_item": serialize_attribute(self.held_item),
            "stats": self.stats,
            "base_stats": self.base_stats,
            "evs": self.evs,
            "nature": self.nature,
            "types": self.types,
            "type_effectiveness": self.type_effectiveness,
            "moves": [
                m.to_dict() if isinstance(m, Move) else m  # 处理 Move 对象或字典
                for m in self.moves
            ],
        }

        # 仅当使用字符串模式时才添加这些字段（向后兼容）
        if isinstance(self.ability, str):
            result["ability_zh"] = self.ability_zh
            result["ability_description"] = self.ability_description
            result["ability_description_zh"] = self.ability_description_zh

        if isinstance(self.held_item, str):
            result["held_item_zh"] = self.held_item_zh
            result["held_item_description"] = self.held_item_description
            result["held_item_description_zh"] = self.held_item_description_zh

        if self.sprite:
            result["sprite"] = self.sprite
        if self.evoforms:
            result["evoforms"] = [
                {
                    "slug_name": f.slug_name,
                    "form_name": f.form_name,
                    "form_name_zh": f.form_name_zh,
                    "base_stats": f.base_stats,
                    "stats": f.stats,
                    "ability": f.ability.to_dict() if isinstance(f.ability, Ability) else f.ability,
                    "types": f.types,
                    "type_effectiveness": f.type_effectiveness,
                    "sprite": f.sprite,
                }
                for f in self.evoforms
            ]
        return result
