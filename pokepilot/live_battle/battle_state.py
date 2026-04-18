"""
对战状态管理 —— 维护对战进程中的完整信息

数据结构：
  BattleState
    ├─ my_team: TeamState
    │    ├─ roster: list[PokemonInTeam]  # 6只队员
    │    └─ active: PokemonState         # 当前出场的
    ├─ opp_team: TeamState
    │    ├─ roster: list[str]            # 对手6只名字（可能不全知）
    │    └─ active: PokemonState         # 当前出场的
    ├─ battlefield: BattlefieldState
    │    ├─ weather: str                 # 天气
    │    ├─ terrain: str                 # 地形
    │    ├─ turn: int                    # 回合数
    │    └─ events: list[str]            # 本回合事件（日志）
    └─ history: list[BattleFrame]        # 历史快照（用于回放/分析）
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PokemonState:
    """单只宝可梦的实时状态"""
    name: str                          # 宝可梦名字（如 "raichu"）
    hp: Optional[int] = None           # 当前 HP（绝对值，可能无法精确识别）
    hp_percent: Optional[float] = None # 当前 HP 百分比（0-100）
    level: Optional[int] = None        # 等级
    status: str = "healthy"            # 状态：healthy, burn, poison, paralysis, sleep, freeze

    # 能力变化
    stat_changes: dict[str, int] = field(default_factory=lambda: {
        "attack": 0, "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0, "accuracy": 0, "evasion": 0
    })

    # 当前属性（type）
    types: list[str] = field(default_factory=list)  # ["water", "flying"]

    # 最后使用的招式
    last_move: Optional[str] = None
    last_move_result: str = ""  # "hit", "miss", "critical", "resisted", "weak", etc.


@dataclass
class TeamState:
    """整支队伍的状态"""
    roster: list[str] = field(default_factory=list)  # 6只名字列表
    active: Optional[PokemonState] = None            # 当前出场
    bench: list[str] = field(default_factory=list)   # 后备（未出场的名字）
    fainted: list[str] = field(default_factory=list) # 已晕倒的名字

    def active_pokemon_name(self) -> Optional[str]:
        return self.active.name if self.active else None

    def remaining_count(self) -> int:
        """剩余能出场的宝可梦数量"""
        return len(self.roster) - len(self.fainted)


@dataclass
class BattlefieldState:
    """战场环境状态"""
    weather: str = "none"           # 天气：sunny, rain, sandstorm, hail, none
    weather_turns: int = 0          # 天气剩余回合数

    terrain: str = "none"           # 地形：psychic, grassy, electric, misty, none
    terrain_turns: int = 0          # 地形剩余回合数

    screens: dict[str, int] = field(default_factory=dict)  # 场地效果：{"reflect": 2, "light_screen": 3}

    hazards: dict[str, int] = field(default_factory=dict)  # 危险招式：{"spikes": 1, "stealth_rock": 1}

    turn: int = 0                   # 当前回合数

    last_event: str = ""            # 最后一个战场事件（从对话框 OCR）


@dataclass
class BattleFrame:
    """单个时刻的战场快照（用于历史回放）"""
    timestamp: float                 # 时间戳
    turn: int                       # 回合数
    my_pokemon: PokemonState         # 我方出场
    opp_pokemon: PokemonState        # 对手出场
    battlefield: BattlefieldState    # 战场环境

    my_selected_move: Optional[str] = None   # 我方选中的招式（如果识别到）
    opp_last_move: Optional[str] = None      # 对手用过的最后一个招式

    screenshot_path: Optional[str] = None    # 对应的截图路径


@dataclass
class BattleState:
    """完整对战状态"""
    battle_id: str = ""              # 对战 ID（用于存档/回放）

    my_team: TeamState = field(default_factory=TeamState)
    opp_team: TeamState = field(default_factory=TeamState)

    battlefield: BattlefieldState = field(default_factory=BattlefieldState)

    # 历史快照
    history: list[BattleFrame] = field(default_factory=list)

    # 对战类型
    battle_format: str = "single"    # "single" 或 "double"
    battle_stage: str = "team_select" # "team_select", "battle", "finished"

    def get_current_frame(self, screenshot_path: Optional[str] = None) -> BattleFrame:
        """创建当前时刻的快照"""
        import time
        return BattleFrame(
            timestamp=time.time(),
            turn=self.battlefield.turn,
            my_pokemon=self.my_team.active or PokemonState(name="unknown"),
            opp_pokemon=self.opp_team.active or PokemonState(name="unknown"),
            battlefield=self.battlefield,
            screenshot_path=screenshot_path,
        )

    def add_frame(self, frame: BattleFrame):
        """记录历史快照"""
        self.history.append(frame)

    def update_my_active(self, name: str, hp_percent: Optional[float] = None, status: str = "healthy"):
        """更新我方出场宝可梦"""
        if self.my_team.active is None or self.my_team.active.name != name:
            # 换精灵
            self.my_team.active = PokemonState(name=name, hp_percent=hp_percent, status=status)
            if name in self.my_team.fainted:
                self.my_team.fainted.remove(name)
        else:
            # 更新状态
            if hp_percent is not None:
                self.my_team.active.hp_percent = hp_percent
            if status:
                self.my_team.active.status = status

    def update_opp_active(self, name: str, hp_percent: Optional[float] = None, status: str = "healthy"):
        """更新对手出场宝可梦"""
        if self.opp_team.active is None or self.opp_team.active.name != name:
            # 换精灵
            self.opp_team.active = PokemonState(name=name, hp_percent=hp_percent, status=status)
            if name in self.opp_team.fainted:
                self.opp_team.fainted.remove(name)
        else:
            # 更新状态
            if hp_percent is not None:
                self.opp_team.active.hp_percent = hp_percent
            if status:
                self.opp_team.active.status = status

    def mark_fainted(self, side: str, name: str):
        """标记宝可梦晕倒"""
        team = self.my_team if side == "my" else self.opp_team
        if name not in team.fainted:
            team.fainted.append(name)
        team.active = None

    def __str__(self) -> str:
        """简化显示"""
        my_active = self.my_team.active.name if self.my_team.active else "none"
        opp_active = self.opp_team.active.name if self.opp_team.active else "none"
        my_hp = f"{self.my_team.active.hp_percent:.0f}%" if (self.my_team.active and self.my_team.active.hp_percent) else "??"
        opp_hp = f"{self.opp_team.active.hp_percent:.0f}%" if (self.opp_team.active and self.opp_team.active.hp_percent) else "??"

        return (
            f"Turn {self.battlefield.turn} | "
            f"我方: {my_active}({my_hp}) vs "
            f"对手: {opp_active}({opp_hp}) | "
            f"天气: {self.battlefield.weather}"
        )
