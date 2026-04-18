"""
对战助手 —— 实时识别对战状态并推荐行动

1. 识别对方出场的宝可梦（OCR 对手名字 + 模糊匹配）
2. 识别自己出场的宝可梦（OCR 我方名字 + 模糊匹配）
3. 查询 pikalytics 数据推荐最佳招式、道具、搭档
4. 显示战场事件（对话框 OCR）

用法:
    python -m pokepilot.battle.battle_assistant <screenshot>
    python -m pokepilot.battle.battle_assistant <screenshot> --show-raw
"""

import sys
import json
from pathlib import Path

from pokepilot.live_battle.ocr_battle import extract_battle_info
from pokepilot.detect_team.opponent_team.detect_opponents import detect_opponents

_ROOT = Path(__file__).parent.parent.parent
_ROSTER_PATH = _ROOT / "data" / "champions_roster.json"
_PIKALYTICS_PATH = _ROOT / "data" / "pikalytics_cache.json"
_MY_TEAM_PATH = _ROOT / "data" / "my_team.json"


def load_data() -> tuple[dict, dict, list[str]]:
    """加载 roster、pikalytics、我的队伍名字列表"""
    roster_data = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
    roster = {p["name"]: p for p in roster_data.get("pokemon", [])}

    pika_data = {}
    if _PIKALYTICS_PATH.exists():
        pika_data = json.loads(_PIKALYTICS_PATH.read_text(encoding="utf-8"))

    my_team_names = []
    if _MY_TEAM_PATH.exists():
        my_team_data = json.loads(_MY_TEAM_PATH.read_text(encoding="utf-8"))
        my_team_names = [p["name"] for p in my_team_data.get("roster", [])]

    return roster, pika_data, my_team_names


def get_pokemon_info(name: str, roster: dict, pika: dict) -> dict:
    """查询单只宝可梦的完整信息（roster + pikalytics）"""
    info = {
        "name": name,
        "roster": roster.get(name),
        "pikalytics": pika.get(name),
    }
    return info


def recommend_move(opp_name: str, my_name: str, my_team: list[dict], roster: dict, pika: dict) -> str:
    """
    推荐招式。
    策略：
    1. 查询对手在 pikalytics 中的数据
    2. 返回对手最常用的招式（克制信息）
    """
    if opp_name not in pika:
        return f"⚠️  对手 {opp_name} 在 pikalytics 中无数据"

    opp_data = pika[opp_name]
    moves = opp_data.get("moves", [])
    if not moves:
        return f"⚠️  {opp_name} 无招式数据"

    # 显示对手最常用的 3 个招式
    top_moves = [f"{m['name']} ({m['pct']}%)" for m in moves[:3]]
    return f"对手 {opp_name} 常用: " + " | ".join(top_moves)


def recommend_switch(opp_name: str, my_team_names: list[str], pika: dict) -> str:
    """
    推荐换精灵。
    策略：
    1. 查询对手在 pikalytics 中的队友数据
    2. 推荐我方队伍中与对手搭档率高的宝可梦出场
    """
    if opp_name not in pika:
        return ""

    opp_data = pika[opp_name]
    teammates = opp_data.get("teammates", [])
    if not teammates:
        return ""

    # 对手的常见队友名字列表
    opp_teammate_names = {t["name"].lower(): t["pct"] for t in teammates}

    # 查询我方队伍中有没有跟对手高搭档率的
    my_matches = []
    for my_name in my_team_names:
        if my_name.lower() in opp_teammate_names:
            my_matches.append((my_name, opp_teammate_names[my_name.lower()]))

    if not my_matches:
        return ""

    my_matches.sort(key=lambda x: x[1], reverse=True)
    top_match = my_matches[0]
    return f"💡 考虑出场 {top_match[0].upper()}（与对手 {opp_name} 搭档率 {top_match[1]:.1f}%）"


def analyze_battle(screenshot: str, show_raw: bool = False) -> dict:
    """
    分析单张对战截图。
    返回完整的战场分析报告。
    """
    # 1. OCR 提取信息
    battle_info = extract_battle_info(screenshot)

    my_pokemon = battle_info.get("my_pokemon")
    opp_pokemon = battle_info.get("opp_pokemon")
    dialog_text = battle_info.get("dialog_text")

    # 2. 加载数据
    roster, pika, my_team = load_data()

    # 3. 构建分析报告
    report = {
        "screenshot": screenshot,
        "battle": {
            "my_pokemon": my_pokemon,
            "opp_pokemon": opp_pokemon,
            "dialog_text": dialog_text,
        },
        "recommendations": {}
    }

    if opp_pokemon:
        # 对手推荐
        report["recommendations"]["opp_moves"] = recommend_move(opp_pokemon, my_pokemon or "unknown", my_team, roster, pika)
        report["recommendations"]["switch"] = recommend_switch(opp_pokemon, my_team, pika)

    if show_raw:
        report["ocr_raw"] = battle_info.get("ocr_raw")

    return report


def main():
    if len(sys.argv) < 2:
        print("用法: python -m pokepilot.battle.battle_assistant <screenshot>")
        sys.exit(1)

    screenshot = sys.argv[1]
    show_raw = "--show-raw" in sys.argv

    report = analyze_battle(screenshot, show_raw)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
