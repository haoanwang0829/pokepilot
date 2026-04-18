"""
实时对战监控 —— 连续抓取截图，OCR 识别，维护对战状态，输出推荐

流程：
  1. 启动监控（开始记录截图序列）
  2. 每帧：
     - 截图
     - OCR 识别（对手/我方/对话框）
     - 更新 BattleState
     - 查询 pikalytics 推荐
     - 输出到 UI（JSON / console）
  3. 对战结束时保存历史

用法:
    python -m pokepilot.battle.battle_monitor --source screenshot_dir
    python -m pokepilot.battle.battle_monitor --source screenshot_dir --output battle_log.json
    python -m pokepilot.battle.battle_monitor --live             # 实时截图模式（需要配置抓屏工具）
"""

import argparse
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from pokepilot.live_battle.battle_state import BattleState, BattleFrame, PokemonState
from pokepilot.live_battle.ocr_battle import extract_battle_info
from pokepilot.live_battle.battle_assistant import load_data, recommend_move, recommend_switch

_ROOT = Path(__file__).parent.parent.parent
_MY_TEAM_PATH = _ROOT / "data" / "my_team.json"


class BattleMonitor:
    """对战实时监控器"""

    def __init__(self):
        self.state = BattleState()
        self.state.battle_id = f"battle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.roster, self.pika, self.my_team_names = load_data()

        # 从 my_team.json 初始化我方队伍
        if _MY_TEAM_PATH.exists():
            my_team_data = json.loads(_MY_TEAM_PATH.read_text(encoding="utf-8"))
            self.state.my_team.roster = [p["name"] for p in my_team_data.get("roster", [])]

        self.last_opp_pokemon = None  # 用于检测对手换精灵
        self.last_my_pokemon = None

    def process_frame(self, screenshot_path: str) -> dict:
        """
        处理单张截图。
        返回 {
            "state_updated": bool,
            "my_pokemon": str,
            "opp_pokemon": str,
            "recommendations": {...},
            "battlefield": {...}
        }
        """
        try:
            # 1. OCR 识别
            battle_info = extract_battle_info(screenshot_path)
            my_pokemon = battle_info.get("my_pokemon")
            opp_pokemon = battle_info.get("opp_pokemon")
            dialog_text = battle_info.get("dialog_text")

            # 2. 更新对战状态
            if my_pokemon:
                self.state.update_my_active(my_pokemon)
                self.last_my_pokemon = my_pokemon

            if opp_pokemon:
                self.state.update_opp_active(opp_pokemon)
                self.last_opp_pokemon = opp_pokemon

            # 更新战场事件
            if dialog_text:
                self.state.battlefield.last_event = dialog_text
                # 简单的事件解析（可以后续扩展）
                if "rain" in dialog_text.lower():
                    self.state.battlefield.weather = "rain"
                elif "sunny" in dialog_text.lower() or "sun" in dialog_text.lower():
                    self.state.battlefield.weather = "sunny"

            # 3. 生成推荐
            recommendations = {}
            if opp_pokemon:
                recommendations["opp_moves"] = recommend_move(opp_pokemon, my_pokemon or "unknown", self.state.my_team.roster, self.roster, self.pika)
                recommendations["switch"] = recommend_switch(opp_pokemon, self.state.my_team.roster, self.pika)

            # 4. 记录快照
            frame = self.state.get_current_frame(screenshot_path)
            self.state.add_frame(frame)

            return {
                "state_updated": True,
                "my_pokemon": my_pokemon,
                "opp_pokemon": opp_pokemon,
                "dialog_text": dialog_text,
                "recommendations": recommendations,
                "battlefield": {
                    "weather": self.state.battlefield.weather,
                    "turn": self.state.battlefield.turn,
                },
                "battle_state": str(self.state),
            }

        except Exception as e:
            return {
                "state_updated": False,
                "error": str(e),
            }

    def process_directory(self, screenshot_dir: str, delay: float = 0.5, watch: bool = True):
        """
        从目录中读取截图。

        Args:
            screenshot_dir: 截图目录
            delay: 帧间隔（秒）
            watch:
              True  → watch 模式（持续监控，处理完后继续等待新截图）
              False → test 模式（处理完所有文件就退出）
        """
        screenshot_dir = Path(screenshot_dir)
        processed = set()

        print(f"📹 监控目录: {screenshot_dir}")
        print(f"⏱️  帧间隔: {delay}s")
        print(f"📋 模式: {'watch（持续）' if watch else 'test（处理完即退出）'}")
        print()

        try:
            idle_count = 0  # 连续无新文件的次数

            while True:
                # 找所有未处理的新截图
                all_files = sorted(screenshot_dir.glob("frame_*.png"))
                new_files = [f for f in all_files if f.name not in processed]

                if new_files:
                    idle_count = 0  # 重置
                    for screenshot in new_files:
                        result = self.process_frame(str(screenshot))

                        if result.get("state_updated"):
                            print(f"✓ {screenshot.name}")
                            print(f"  {result['battle_state']}")
                            if result.get("recommendations"):
                                for key, val in result["recommendations"].items():
                                    if val:
                                        print(f"  💡 {val}")
                            print()

                        processed.add(screenshot.name)
                        time.sleep(delay)

                else:
                    # 没有新截图
                    idle_count += 1

                    # test 模式：10 次检查都无新文件后退出
                    if not watch and idle_count >= 10:
                        print("✅ 所有文件已处理，退出（test 模式）")
                        break

                    # watch 模式：继续等待
                    time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\n⏹️  停止监控")
            self.save_battle_log()
        except Exception as e:
            print(f"\n\n❌ 错误: {e}")
            self.save_battle_log()

    def save_battle_log(self, output_path: Optional[str] = None):
        """保存对战日志"""
        if output_path is None:
            output_path = _ROOT / "data" / f"{self.state.battle_id}.json"
        else:
            output_path = Path(output_path)

        # 序列化（dataclass → dict）
        def serialize_state(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {
                    k: serialize_state(v)
                    for k, v in obj.__dict__.items()
                }
            elif isinstance(obj, list):
                return [serialize_state(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: serialize_state(v) for k, v in obj.items()}
            else:
                return obj

        data = {
            "battle_id": self.state.battle_id,
            "battle_format": self.state.battle_format,
            "timestamp": datetime.now().isoformat(),
            "my_team": serialize_state(self.state.my_team),
            "opp_team": serialize_state(self.state.opp_team),
            "battlefield": serialize_state(self.state.battlefield),
            "frame_count": len(self.state.history),
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 对战日志已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="实时对战监控")
    parser.add_argument("--source", help="截图目录")
    parser.add_argument("--output", help="输出日志路径")
    parser.add_argument("--delay", type=float, default=0.5, help="帧间隔（秒）")
    parser.add_argument("--watch", action="store_true", default=False, help="持续监控模式（默认为 test 模式）")
    args = parser.parse_args()

    monitor = BattleMonitor()

    if args.source:
        monitor.process_directory(args.source, delay=args.delay, watch=args.watch)
    else:
        print("用法:")
        print("  python -m pokepilot.battle.battle_monitor --source <dir>           # test 模式（处理完即退出）")
        print("  python -m pokepilot.battle.battle_monitor --source <dir> --watch  # watch 模式（持续监控）")


if __name__ == "__main__":
    main()
