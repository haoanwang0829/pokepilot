"""
对战 UI 服务器 —— 提供实时数据给 OBS / 网页显示

提供 HTTP API：
  POST /generate-my-team      -> 生成我方队伍
  POST /detect-opponents      -> 识别对方队伍
  GET /my-team                -> 加载保存的队伍

用法:
    python -m pokepilot.tools.ui_server --port 8765
"""

import argparse
import json
import time
from pathlib import Path
from threading import Thread
import cv2
from flask import Flask, jsonify, request
from flask_cors import CORS

from pokepilot.detect_team.my_team.parse_team import parse_team
from pokepilot.detect_team.opponent_team.detect_opponents import detect_opponents_team
from pokepilot.tools.capture import ScreenCapture

_ROOT = Path(__file__).parent.parent.parent



class UIServer:
    """对战 UI 服务器"""

    def __init__(self, port: int = 8765):
        self.port = port

        self.app = Flask(__name__, static_folder=str(_ROOT / "sprites"), static_url_path="/sprites")
        CORS(self.app)
        self._setup_routes()


    def _setup_routes(self):
        """设置 HTTP 路由"""

        @self.app.route("/", methods=["GET"])
        def index():
            """返回 HTML UI"""
            ui_path = Path(__file__).parent / "ui_assets" / "battle.html"
            if ui_path.exists():
                return ui_path.read_text(encoding="utf-8")
            else:
                return jsonify({
                    "message": "Pokemon Battle Assistant",
                    "status": "running",
                    "api_endpoints": [
                        "GET /status",
                        "GET /recommendations",
                        "GET /health"
                    ]
                })


        @self.app.route("/my-team", methods=["GET"])
        def get_my_team():
            """加载我方队伍数据（支持指定槽位）"""
            try:
                # 迁移旧数据（只执行一次）
                old_path = Path(_ROOT) / "data" / "my_team.json"
                new_dir = Path(_ROOT) / "data" / "my_team"
                if old_path.exists():
                    new_dir.mkdir(parents=True, exist_ok=True)
                    old_path.replace(new_dir / "1.json")
                    print(f"[MIGRATION] Moved {old_path} to {new_dir / '1.json'}")

                # 支持 ?slot=temp（默认）或 ?slot=1, 2 等
                slot = request.args.get("slot", "temp")
                my_team_path = new_dir / f"{slot}.json"

                if not my_team_path.exists():
                    return jsonify({"error": f"Slot '{slot}' not found"}), 404

                team_data = json.loads(my_team_path.read_text(encoding="utf-8"))

                return jsonify({
                    "status": "loaded",
                    "team": team_data,
                    "slot": slot,
                    "slot_name": team_data.get("slot_name", f"槽位 {slot}")
                })
            except Exception as e:
                import traceback
                error_msg = f"{str(e)} | {traceback.format_exc()}"
                print(f"Error in get_my_team: {error_msg}")
                return jsonify({"error": error_msg}), 500

        @self.app.route("/detect-opponents", methods=["POST"])
        def detect_opp_team():
            """识别对方队伍（或使用 ?debug=1 直接用现有截图）"""
            try:
                debug_mode = request.args.get("debug", "0") == "1"

                if debug_mode:
                    # DEBUG 模式：直接用现有的截图
                    opp_dir = Path("screenshots/opp_team")
                    if not opp_dir.exists():
                        opp_dir = Path("screenshots/live")

                    png_files = sorted(opp_dir.glob("frame_*.png"))
                    if not png_files:
                        return jsonify({"error": "No screenshots found. Run in normal mode first or provide screenshots."}), 400

                    latest_screenshot = png_files[-1]
                    print(f"[DEBUG] 使用现有截图: {latest_screenshot}")
                else:
                    # 正常模式：启动截屏线程
                    # 清理之前的截图
                    opp_dir = Path("screenshots/opp_team")
                    if opp_dir.exists():
                        for f in opp_dir.glob("frame_*.png"):
                            f.unlink()
                        print(f"[detect-opponents] 清理旧截图")

                    opp_dir.mkdir(parents=True, exist_ok=True)
                    print(f"[detect-opponents] 启动截屏线程，保存到: {opp_dir.absolute()}")

                    # 启动截屏线程（对方队伍选择阶段）
                    self.is_monitoring = True
                    screenshot_thread = Thread(
                        target=self._screenshot_worker,
                        kwargs={"device_idx": 3, "output_dir": str(opp_dir)},
                        daemon=True
                    )
                    screenshot_thread.start()
                    print(f"[detect-opponents] 线程启动，等待2秒...")

                    # 等待几秒让截屏完成
                    time.sleep(2)
                    self.is_monitoring = False
                    print(f"[detect-opponents] 停止监控")
                    time.sleep(0.5)

                    # 获取最新的截图并识别
                    opp_dir = Path("screenshots/opp_team")
                    png_files = sorted(opp_dir.glob("frame_*.png"))
                    print(f"[detect-opponents] 查找截图，找到 {len(png_files)} 个文件: {[f.name for f in png_files]}")
                    if not png_files:
                        return jsonify({"error": "Failed to capture screenshot"}), 400

                    latest_screenshot = png_files[-1]
                    print(f"[detect-opponents] 使用最新截图: {latest_screenshot}")

                # 识别对方队伍
                team = detect_opponents_team(str(latest_screenshot))

                # 将 roster 转换为字典列表
                team_data = {
                    "trainer_name": team.get("trainer_name", ""),
                    "roster": [p.to_dict() for p in team.get("roster", [])]
                }

                return jsonify({
                    "status": "detected",
                    "debug_mode": debug_mode,
                    "screenshot": str(latest_screenshot),
                    "team": team_data
                })
            except Exception as e:
                if hasattr(self, 'is_monitoring'):
                    self.is_monitoring = False
                return jsonify({"error": str(e)}), 500

        @self.app.route("/team-assets-status", methods=["GET"])
        def team_assets_status():
            """检查截图和临时 JSON 文件是否存在"""
            moves_path = Path("screenshots/team/moves_latest.png")
            stats_path = Path("screenshots/team/stats_latest.png")
            json_path = Path(_ROOT) / "data" / "my_team" / "temp.json"

            return jsonify({
                "has_moves_screenshot": moves_path.exists(),
                "has_stats_screenshot": stats_path.exists(),
                "has_json": json_path.exists()
            })

        @self.app.route("/capture-team-screen", methods=["POST"])
        def capture_team_screen():
            """截取队伍截图（Moves 或 Stats 页）"""
            try:
                stage = request.args.get("stage", "moves")  # moves 或 stats
                if stage not in ("moves", "stats"):
                    return jsonify({"error": "Invalid stage"}), 400

                # 创建输出目录
                team_dir = Path("screenshots/team")
                team_dir.mkdir(parents=True, exist_ok=True)

                # 启动截屏线程
                self.is_monitoring = True
                output_file = team_dir / f"{stage}_latest.png"

                screenshot_thread = Thread(
                    target=self._screenshot_worker,
                    kwargs={"device_idx": 3, "output_dir": "screenshots/team"},
                    daemon=True
                )
                screenshot_thread.start()

                # 等待截屏完成
                time.sleep(2)
                self.is_monitoring = False
                time.sleep(0.5)

                # 检查是否成功
                png_files = sorted(team_dir.glob("frame_*.png"))
                if png_files:
                    latest = png_files[-1]
                    # 重命名为 {stage}_latest.png（使用 replace 以支持 Windows 文件覆盖）
                    latest.replace(output_file)
                    return jsonify({
                        "status": "captured",
                        "stage": stage,
                        "path": str(output_file)
                    })
                else:
                    return jsonify({"error": "Failed to capture screenshot"}), 400

            except Exception as e:
                self.is_monitoring = False
                return jsonify({"error": str(e)}), 500

        @self.app.route("/generate-my-team", methods=["POST"])
        def generate_my_team():
            """从截图生成队伍，保存到 temp.json"""
            try:
                moves_path = Path("screenshots/team/moves_latest.png")
                stats_path = Path("screenshots/team/stats_latest.png")

                if not moves_path.exists() or not stats_path.exists():
                    return jsonify({"error": "Missing screenshot files. Capture moves and stats first."}), 400

                # 从截图生成 team 数据
                team = parse_team(str(moves_path), str(stats_path))

                # 保存到 data/my_team/temp.json
                output_dir = Path(_ROOT) / "data" / "my_team"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / "temp.json"
                # roster 中是 Pokemon 对象，转换为字典后保存
                team_data = {
                    "trainer_name": team.get("trainer_name", ""),
                    "roster": [p.to_dict() for p in team.get("roster", [])]
                }
                output_path.write_text(json.dumps(team_data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[DEBUG] Saved to {output_path}")

                return jsonify({
                    "status": "generated",
                    "team": team_data,
                    "slot": "temp"
                })

            except Exception as e:
                import traceback
                error_msg = f"{str(e)} | {traceback.format_exc()}"
                print(f"[ERROR] Error in generate_my_team: {error_msg}")
                return jsonify({"error": error_msg}), 500

        @self.app.route("/my-team/slots", methods=["GET"])
        def get_my_team_slots():
            """列出所有保存的槽位（不含 temp）"""
            try:
                slots_dir = Path(_ROOT) / "data" / "my_team"
                result = []

                if slots_dir.exists():
                    for f in sorted(slots_dir.glob("*.json")):
                        if f.stem == "temp":
                            continue
                        try:
                            data = json.loads(f.read_text(encoding="utf-8"))
                            result.append({
                                "slot": f.stem,
                                "name": data.get("slot_name", f"槽位 {f.stem}")
                            })
                        except Exception as e:
                            print(f"[WARNING] Failed to read {f}: {e}")

                return jsonify({"slots": result})
            except Exception as e:
                import traceback
                error_msg = f"{str(e)} | {traceback.format_exc()}"
                print(f"Error in get_my_team_slots: {error_msg}")
                return jsonify({"error": error_msg}), 500

        @self.app.route("/my-team/save", methods=["POST"])
        def save_my_team_slot():
            """保存 temp.json 到指定槽位，或覆盖已有槽位"""
            try:
                slot = request.args.get("slot")
                if not slot:
                    return jsonify({"error": "Missing 'slot' parameter"}), 400

                # 从 POST body 获取 slot_name（仅在新建时使用）
                body = request.get_json() or {}
                new_name = body.get("name")

                # 读取 temp.json
                temp_path = Path(_ROOT) / "data" / "my_team" / "temp.json"
                if not temp_path.exists():
                    return jsonify({"error": "No team generated yet"}), 400

                data = json.loads(temp_path.read_text(encoding="utf-8"))

                # 检查目标槽位是否已存在
                target_path = Path(_ROOT) / "data" / "my_team" / f"{slot}.json"
                if target_path.exists():
                    # 覆盖已有槽位：保持原来的 slot_name
                    existing_data = json.loads(target_path.read_text(encoding="utf-8"))
                    original_name = existing_data.get("slot_name", f"槽位 {slot}")
                    data["slot_name"] = original_name
                    print(f"[DEBUG] Overwriting slot {slot}, keeping name: '{original_name}'")
                else:
                    # 新建槽位：使用新提供的 name 或默认值
                    name = new_name or f"槽位 {slot}"
                    data["slot_name"] = name
                    print(f"[DEBUG] Creating new slot {slot} with name: '{name}'")

                # 写入目标槽位
                target_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

                return jsonify({
                    "status": "saved",
                    "slot": slot,
                    "name": data.get("slot_name")
                })
            except Exception as e:
                import traceback
                error_msg = f"{str(e)} | {traceback.format_exc()}"
                print(f"Error in save_my_team_slot: {error_msg}")
                return jsonify({"error": error_msg}), 500

        @self.app.route("/my-team", methods=["DELETE"])
        def delete_my_team_slot():
            """删除指定槽位"""
            try:
                slot = request.args.get("slot")
                if not slot:
                    return jsonify({"error": "Missing 'slot' parameter"}), 400

                target_path = Path(_ROOT) / "data" / "my_team" / f"{slot}.json"
                if target_path.exists():
                    target_path.unlink()
                    print(f"[DEBUG] Deleted slot {slot}")

                return jsonify({"status": "deleted", "slot": slot})
            except Exception as e:
                import traceback
                error_msg = f"{str(e)} | {traceback.format_exc()}"
                print(f"Error in delete_my_team_slot: {error_msg}")
                return jsonify({"error": error_msg}), 500


    def _screenshot_worker(self, device_idx: int = None, output_dir: str = "screenshots/live"):
        """后台截屏线程 - 从虚拟摄像机读取"""
        from pathlib import Path
        from pokepilot.tools.capture import ScreenCapture, list_video_devices

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 如果没指定设备，自动扫描
        if device_idx is None:
            print("[UI Server] Scanning video devices...")
            devices = list_video_devices()
            if not devices:
                print("[UI Server] ERROR: No video devices found. Is OBS Virtual Camera running?")
                self.is_monitoring = False
                return

            # 尝试跳过摄像头（device 0），用第二个设备
            device_idx = devices[1] if len(devices) > 1 else devices[0]
            print(f"[UI Server] Available devices: {devices}, using: {device_idx}")
        else:
            print(f"[UI Server] Using specified device: {device_idx}")

        cap = ScreenCapture(device_idx)
        try:
            cap.start()
            frame_count = 0

            while self.is_monitoring:
                frame = cap.read()
                if frame is None:
                    time.sleep(0.1)
                    continue

                path = output_path / f"frame_{frame_count:06d}.png"
                cv2.imwrite(str(path), frame)
                frame_count += 1
                time.sleep(0.5)

        except Exception as e:
            print(f"[UI Server] Screenshot error: {e}")
            self.is_monitoring = False
        finally:
            cap.stop()


    def run(self, debug: bool = False):
        """启动服务器"""

        print(f"🚀 UI 服务器启动: http://localhost:{self.port}")
        print(f"   GET /status           -> 当前对战状态")
        print(f"   GET /recommendations  -> 推荐信息")
        print(f"   POST /screenshot      -> 处理截图")
        print(f"   GET /health           -> 健康检查")
        print()

        self.app.run(host="0.0.0.0", port=self.port, debug=debug, use_reloader=False)



def main():
    parser = argparse.ArgumentParser(description="队伍识别 UI 服务器")
    parser.add_argument("--port", type=int, default=8765, help="服务器端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    server = UIServer(port=args.port)
    server.run(debug=args.debug)


if __name__ == "__main__":
    main()
