"""
测试 PokemonBuilder.build_pokemon_myteam
"""

import json
from pathlib import Path

from pokepilot.detect_team.my_team.parse_team_old import parse_team, parse_team_init, _parse_moves_screen
from pokepilot.detect_team.opponent_team.detect_opponents import detect_opponents_team



def test_with_real_screenshots():
    """用真实截图测试"""

    moves_screenshot = Path("screenshots/team/moves.png")
    stats_screenshot = Path("screenshots/team/stats.png")

    detect_cards, moves_cards, stats_cards = parse_team_init(moves_screenshot, stats_screenshot, debug=True)
    # 保存结果
    # output_file = Path("debug_output/parse_team_test.json")
    # output_file.parent.mkdir(parents=True, exist_ok=True)
    # output_file.write_text(json.dumps([i.to_dict() for i in team['roster']], ensure_ascii=False, indent=2), encoding="utf-8")



def test_opponents_with_real_screenshot():
    """测试对手队伍识别"""

    team = detect_opponents_team("C:\\Users\\wangh\\test\\pokepilot\\screenshots\\opp_team\\team.png", debug=True)
    # print(team)
    output_file = Path("debug_output/parse_opp_team_test.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps([i.to_dict() for i in team['roster']], ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    # test_with_real_screenshots()
    # test_opponents_with_real_screenshot()
    from pokepilot.tools.logger_util import setup_logger
    setup_logger(debug=True)  # 先初始化 logger
    moves_screenshot = Path("screenshots/team/moves.png")
    # stats_screenshot = Path("screenshots/team/stats.png")

    detect_cards, moves_cards, layout = _parse_moves_screen(moves_screenshot, debug=True)
    # stats_cards = _parse_stats_screen(stats_screenshot, layout=layout, debug=False)
    # test_with_real_screenshots()
    # test_opponents_with_real_screenshot()
