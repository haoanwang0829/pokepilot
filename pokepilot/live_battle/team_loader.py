"""
队伍配置加载器 —— 从 JSON 文件读取我方队伍数据
"""

import json
from pathlib import Path
from pokepilot.live_battle.models import Team, Pokemon, Stats, EVSpread, Move


_DEFAULT_PATH = Path(__file__).parent.parent.parent / "data" / "my_team.json"


def load_team(path: str | Path = _DEFAULT_PATH) -> Team:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    roster = []
    for p in raw["roster"]:
        stats = Stats(**p["stats"])
        evs   = EVSpread(**p.get("evs", {}))
        moves = [Move(**m) for m in p.get("moves", [])]
        roster.append(Pokemon(
            name       = p["name"],
            nickname   = p.get("nickname", ""),
            ability    = p.get("ability", ""),
            held_item  = p.get("held_item", ""),
            types      = p.get("types", []),
            stats      = stats,
            evs        = evs,
            moves      = moves,
            max_hp     = stats.hp,
            current_hp = stats.hp,
        ))

    return Team(trainer_name=raw.get("trainer_name", ""), roster=roster)


def validate_team(team: Team) -> list[str]:
    """检查 EV 分配是否合法，返回警告列表"""
    MAX_PER_STAT = 32
    MAX_TOTAL    = 66
    warnings = []
    for p in team.roster:
        ev = p.evs
        total = ev.total()
        if total != MAX_TOTAL:
            warnings.append(f"{p.name}: EV总计={total}，应为{MAX_TOTAL}")
        for stat_name in ("hp", "attack", "defense", "sp_atk", "sp_def", "speed"):
            val = getattr(ev, stat_name)
            if val > MAX_PER_STAT:
                warnings.append(f"{p.name}: {stat_name} EV={val} 超过上限 {MAX_PER_STAT}")
    return warnings


if __name__ == "__main__":
    team = load_team()
    print(f"队伍: {team.trainer_name}  ({len(team.roster)} 只)")
    print()
    for p in team.roster:
        ev = p.evs
        print(f"  {p.name}({p.nickname})")
        print(f"    特性: {p.ability}  道具: {p.held_item}")
        print(f"    招式: {[m.name for m in p.moves]}")
        print(f"    种族值: HP={p.stats.hp} Atk={p.stats.attack} Def={p.stats.defense} "
              f"SpA={p.stats.sp_atk} SpD={p.stats.sp_def} Spe={p.stats.speed}")
        print(f"    努力值: HP={ev.hp} Atk={ev.attack} Def={ev.defense} "
              f"SpA={ev.sp_atk} SpD={ev.sp_def} Spe={ev.speed}  合计={ev.total()}")

    warnings = validate_team(team)
    if warnings:
        print("\n[警告]")
        for w in warnings:
            print(f"  {w}")
    else:
        print("\n所有宝可梦 EV 分配合法 ✓")
