"""
宝可梦数据模型 —— 用于存储我方队伍配置和对战状态
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EVSpread:
    """
    Pokemon Champions 简化努力值系统
    每项最多 32，总计 66（如 32+32+2）
    全个体值默认 31
    """
    hp: int = 0
    attack: int = 0
    defense: int = 0
    sp_atk: int = 0
    sp_def: int = 0
    speed: int = 0

    def total(self) -> int:
        return self.hp + self.attack + self.defense + self.sp_atk + self.sp_def + self.speed


@dataclass
class Stats:
    """实际对战数值（直接从游戏 Stats 页面读取）"""
    hp: int = 0
    attack: int = 0
    defense: int = 0
    sp_atk: int = 0
    sp_def: int = 0
    speed: int = 0


@dataclass
class Move:
    name: str
    type: str = ""
    pp: int = 0
    pp_max: int = 0
    # 对当前对手的效果提示（从画面识别）
    effectiveness: str = ""   # "Effective" / "Not very effective" / "No effect"


@dataclass
class Pokemon:
    name: str                            # 英文名，用于查库
    nickname: str = ""                   # 昵称（如有）
    ability: str = ""
    held_item: str = ""
    types: list[str] = field(default_factory=list)

    # 实际数值（从游戏 Stats 页面读取，level 50）
    stats: Stats = field(default_factory=Stats)
    evs: EVSpread = field(default_factory=EVSpread)

    # 4 个招式配置
    moves: list[Move] = field(default_factory=list)

    # 对战中的实时状态
    current_hp: int = 0
    max_hp: int = 0
    hp_pct: float = 1.0       # 0.0 ~ 1.0，从血条颜色 / 百分比识别
    status: str = ""           # par / brn / frz / slp / psn / tox / ""
    is_fainted: bool = False
    is_active: bool = False    # 是否在场上


@dataclass
class Team:
    """我方队伍（6 只宝可梦完整配置）"""
    trainer_name: str = ""
    roster: list[Pokemon] = field(default_factory=list)  # 按队伍顺序排列

    def get(self, name: str) -> Optional[Pokemon]:
        """按英文名查找"""
        for p in self.roster:
            if p.name.lower() == name.lower():
                return p
        return None

    def active(self) -> list[Pokemon]:
        """返回当前在场上的宝可梦"""
        return [p for p in self.roster if p.is_active]
