"""
采集卡视频预览服务器 —— 用浏览器 getUserMedia 打开摄像头 + API 服务

用法：
    python -m pokepilot.ui.ui_server --port 8765
"""

import argparse
import io
import json
import shutil
from math import floor
from pathlib import Path
from flask import Flask, send_file, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
from pokepilot.detect_team.my_team.parse_team import parse_team_init
from pokepilot.detect_team.opponent_team.detect_opponents import detect_opponents_team
from pokepilot.common.pokemon_detect import PokemonDetector
from pokepilot.common.pokemon_builder import PokemonBuilder

_ROOT = Path(__file__).parent
PROJECT_ROOT = _ROOT.parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots" / "team"
OPP_SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots" / "opp_team"
SPRITES_DIR = PROJECT_ROOT / "sprites"
TEAM_DIR = PROJECT_ROOT / "data" / "my_team"
OPP_TEAM_DIR = PROJECT_ROOT / "data" / "opp_team"

# 全局 PokemonDetector 实例
_pokemon_detector = None
_DAMAGE_LEVEL = 50


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stat_min_max(value):
    """将属性值统一为 (min, max) 区间。"""
    if isinstance(value, list) and value:
        values = [_to_int(v, 0) for v in value]
        return min(values), max(values)
    scalar = _to_int(value, 0)
    return scalar, scalar


def _attacker_stat_value(value):
    """攻击方属性取最大值，兼容对方队伍的区间属性。"""
    if isinstance(value, list) and value:
        return max(_to_int(v, 0) for v in value)
    return _to_int(value, 0)


def _compute_damage_with_roll(power, atk, defense, stab, type_multiplier, roll):
    if power <= 0 or atk <= 0 or defense <= 0 or type_multiplier <= 0:
        return 0
    base = floor(floor((2 * _DAMAGE_LEVEL) / 5 + 2) * power * atk / defense / 50) + 2
    return max(1, floor(base * stab * type_multiplier * roll / 100))


def _compute_damage_range(attacker, defender, move):
    """计算某技能对目标的极限伤害范围（对方属性取极限值）。"""
    power = _to_int(move.get("power"), 0)
    if power <= 0:
        return None

    category = (move.get("category") or "").lower()
    if category == "physical":
        atk_stat = _attacker_stat_value(attacker.get("stats", {}).get("attack"))
        def_min, def_max = _stat_min_max(defender.get("stats", {}).get("defense"))
    elif category == "special":
        atk_stat = _attacker_stat_value(attacker.get("stats", {}).get("sp_atk"))
        def_min, def_max = _stat_min_max(defender.get("stats", {}).get("sp_def"))
    else:
        return None

    if atk_stat <= 0 or def_max <= 0:
        return None

    hp_min, hp_max = _stat_min_max(defender.get("stats", {}).get("hp"))
    hp_min = max(hp_min, 1)
    hp_max = max(hp_max, 1)

    move_type = move.get("type", "")
    effectiveness = defender.get("type_effectiveness", {})
    type_multiplier = float(effectiveness.get(move_type.lower(), 1.0))
    if type_multiplier <= 0:
        return {
            "damage_min": 0,
            "damage_max": 0,
            "hp_pct_min": 0.0,
            "hp_pct_max": 0.0,
            "type_multiplier": type_multiplier,
        }

    stab = 1.5 if move_type in attacker.get("types", []) else 1.0
    # 最低伤害：最低 roll + 对方最大防御
    damage_min = _compute_damage_with_roll(power, atk_stat, def_max, stab, type_multiplier, 85)
    # 最高伤害：最高 roll + 对方最小防御
    damage_max = _compute_damage_with_roll(
        power, atk_stat, max(def_min, 1), stab, type_multiplier, 100
    )
    hp_pct_min = round(damage_min * 100 / hp_max, 2)
    hp_pct_max = round(damage_max * 100 / hp_min, 2)

    return {
        "damage_min": damage_min,
        "damage_max": damage_max,
        "hp_pct_min": hp_pct_min,
        "hp_pct_max": hp_pct_max,
        "type_multiplier": type_multiplier,
    }


def _is_guaranteed_critical_move(move):
    """识别“必定击中要害”技能（不含仅提高要害率）。"""
    move_name_raw = (move.get("name") or "").lower().strip()
    move_name = move_name_raw.replace(" ", "-").replace("_", "-")
    short_effect = (move.get("short_effect") or "").lower()
    short_effect_zh = move.get("short_effect_zh") or ""
    guaranteed_critical_move_names = {
        "frost-breath",
        "storm-throw",
        "wicked-blow",
        "surging-strikes",
        "flower-trick",
    }
    if move_name in guaranteed_critical_move_names:
        return True
    guaranteed_tokens_en = [
        "always results in a critical hit",
        "always scores a critical hit",
    ]
    if any(token in short_effect for token in guaranteed_tokens_en):
        return True
    return "必定会击中要害" in short_effect_zh


def _apply_guaranteed_critical_modifier(range_info, is_guaranteed_critical):
    """必定要害修正：当前简化按 1.5 倍处理。"""
    if not is_guaranteed_critical:
        return range_info
    crit_modifier = 1.5
    return {
        "damage_min": 0 if range_info["damage_min"] <= 0 else max(1, floor(range_info["damage_min"] * crit_modifier)),
        "damage_max": 0 if range_info["damage_max"] <= 0 else max(1, floor(range_info["damage_max"] * crit_modifier)),
        "hp_pct_min": round(range_info["hp_pct_min"] * crit_modifier, 2),
        "hp_pct_max": round(range_info["hp_pct_max"] * crit_modifier, 2),
        "type_multiplier": range_info["type_multiplier"],
    }


def _is_spread_move(move):
    """轻量识别双打范围招式（命中多个目标时会有伤害修正）。"""
    move_name_raw = (move.get("name") or "").lower().strip()
    move_name = move_name_raw.replace(" ", "-").replace("_", "-")
    short_effect = (move.get("short_effect") or "").lower()
    short_effect_zh = move.get("short_effect_zh") or ""
    spread_move_names = {
        "heat-wave",
        "rock-slide",
        "blizzard",
        "earthquake",
        "surf",
        "discharge",
        "dazzling-gleam",
        "muddy-water",
        "snarl",
        "icy-wind",
        "electroweb",
        "eruption",
        "water-spout",
        "hyper-voice",
        "boomburst",
        "sludge-wave",
        "brutal-swing",
        "lava-plume",
        "bulldoze",
        "breaking-swipe",
    }
    if move_name in spread_move_names:
        return True
    spread_tokens_en = [
        "all adjacent foes",
        "all adjacent pokemon",
        "hits both opponents",
        "all other pokemon",
    ]
    spread_tokens_zh = ["全体", "所有", "双方", "除自己以外"]
    if any(token in short_effect for token in spread_tokens_en):
        return True
    if any(token in short_effect_zh for token in spread_tokens_zh):
        return True
    return False


def _apply_spread_modifier(range_info, battle_mode, is_spread_move):
    """双打下范围技能伤害修正。"""
    if battle_mode != "double" or not is_spread_move:
        return range_info
    modifier = 0.75
    damage_min = 0 if range_info["damage_min"] <= 0 else max(1, floor(range_info["damage_min"] * modifier))
    damage_max = 0 if range_info["damage_max"] <= 0 else max(1, floor(range_info["damage_max"] * modifier))
    return {
        "damage_min": damage_min,
        "damage_max": damage_max,
        "hp_pct_min": round(range_info["hp_pct_min"] * modifier, 2),
        "hp_pct_max": round(range_info["hp_pct_max"] * modifier, 2),
        "type_multiplier": range_info["type_multiplier"],
    }


def _is_multi_hit_move(move):
    """基于技能描述做轻量识别：是否可能为多段伤害技能。"""
    short_effect = (move.get("short_effect") or "").lower()
    short_effect_zh = move.get("short_effect_zh") or ""
    multi_hit_tokens = [
        "2 to 5 times",
        "hits 2 times",
        "hits twice",
        "two to five times",
    ]
    if any(token in short_effect for token in multi_hit_tokens):
        return True
    if "连续" in short_effect_zh and "攻击" in short_effect_zh:
        return True
    return False

def get_detector():
    """获取全局 PokemonDetector 实例（懒加载）"""
    global _pokemon_detector
    if _pokemon_detector is None:
        _pokemon_detector = PokemonDetector()
    return _pokemon_detector


def create_app():
    app = Flask(__name__, static_folder=str(_ROOT), static_url_path="")
    CORS(app)

    # 确保截图目录存在
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    @app.route("/", methods=["GET"])
    def index():
        html_file = _ROOT / "index.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/api/screenshot", methods=["POST"])
    def save_screenshot():
        """接收网页截图并保存到本地"""
        try:
            if "image" not in request.files:
                return jsonify({"success": False, "error": "未找到图片"}), 400

            image_file = request.files["image"]
            stage = request.form.get("type", "unknown")

            if not image_file:
                return jsonify({"success": False, "error": "图片为空"}), 400

            # 读取图片
            image = Image.open(io.BytesIO(image_file.read()))

            # 根据 stage 参数决定保存目录
            if stage == "opp_team":
                save_dir = PROJECT_ROOT / "screenshots" / "opp_team"
                filename = "team.png"
            else:
                save_dir = SCREENSHOTS_DIR
                filename = f"{stage}.png"

            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename

            image.save(save_path, "PNG")

            return jsonify({
                "success": True,
                "filename": filename,
                "path": str(save_path)
            })

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/sprites/<path:filename>")
    def sprites(filename):
        """提供精灵图静态文件"""
        return send_from_directory(SPRITES_DIR, filename)

    @app.route("/api/teams", methods=["GET"])
    def list_teams():
        teams = []
        for path in sorted(TEAM_DIR.glob("*.json")):
            if path.name == "temp.json":
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                teams.append({
                    "id": path.stem,
                    "slot_name": data.get("slot_name", path.stem)
                })
            except Exception:
                pass
        return jsonify({"success": True, "teams": teams})

    @app.route("/api/teams/load/<slot_id>", methods=["POST"])
    def load_team_slot(slot_id):
        src = TEAM_DIR / f"{slot_id}.json"
        dst = TEAM_DIR / "temp.json"
        try:
            shutil.copy2(src, dst)
            with open(dst, encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"success": True, "team": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/save", methods=["POST"])
    def save_team_slot():
        body = request.json or {}
        slot_id = body.get("slot_id")
        slot_name = body.get("slot_name", "")
        try:
            temp = TEAM_DIR / "temp.json"
            with open(temp, encoding="utf-8") as f:
                data = json.load(f)
            if slot_id:
                dst = TEAM_DIR / f"{slot_id}.json"
                with open(dst, encoding="utf-8") as f:
                    existing = json.load(f)
                data["slot_name"] = existing.get("slot_name", slot_id)
            else:
                nums = [int(p.stem) for p in TEAM_DIR.glob("*.json") if p.stem.isdigit()]
                new_id = max(nums, default=0) + 1
                slot_id = str(new_id)
                dst = TEAM_DIR / f"{slot_id}.json"
                data["slot_name"] = slot_name
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return jsonify({"success": True, "slot_id": slot_id, "slot_name": data["slot_name"]})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/<slot_id>", methods=["DELETE"])
    def delete_team_slot(slot_id):
        try:
            path = TEAM_DIR / f"{slot_id}.json"
            if not path.exists():
                return jsonify({"success": False, "error": "不存在"}), 404
            path.unlink()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/generate", methods=["POST"])
    def generate_team():
        """从截图提取 OCR 结果，保存到 draft.json，返回草稿供编辑"""
        try:
            moves_path = SCREENSHOTS_DIR / "moves.png"
            stats_path = SCREENSHOTS_DIR / "stats.png"

            if not moves_path.exists() or not stats_path.exists():
                return jsonify({"success": False, "error": "缺少截图。请先截取页面1（moves）和页面2（stats）"}), 400

            detect_cards, move_cards, stat_cards = parse_team_init(str(moves_path), str(stats_path), debug=True)

            draft = {
                "detect_cards": detect_cards,
                "move_cards": move_cards,
                "stat_cards": stat_cards
            }

            draft_path = TEAM_DIR / "draft.json"
            TEAM_DIR.mkdir(parents=True, exist_ok=True)
            with open(draft_path, "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "draft": draft
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/build", methods=["POST"])
    def build_team():
        """从编辑后的卡数据生成最终队伍，保存到 temp.json"""
        try:
            body = request.get_json() or {}
            detect_cards = body.get("detect_cards", [])
            move_cards = body.get("move_cards", [])
            stat_cards = body.get("stat_cards", [])

            if not (detect_cards and move_cards and stat_cards):
                return jsonify({"success": False, "error": "缺少卡数据"}), 400

            builder = PokemonBuilder()
            roster = []
            for dc, mc, sc in zip(detect_cards, move_cards, stat_cards):
                pokemon = builder.build_pokemon(
                    detect_data=dc,
                    moves_data=mc,
                    stats_data=sc,
                    language="zh"
                )
                roster.append(pokemon)

            team_data = {
                "trainer_name": "",
                "roster": [p.to_dict() if hasattr(p, 'to_dict') else p for p in roster]
            }

            output_path = TEAM_DIR / "temp.json"
            TEAM_DIR.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(team_data, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "team": team_data,
                "slot": "temp"
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/detect-card/<slug>")
    def pokemon_detect_card(slug):
        """根据 slug 查询宝可梦的 detect_card 数据"""
        try:
            detector = get_detector()
            card = detector.get_detect_card_by_slug(slug)
            if card:
                return jsonify({"success": True, "card": card})
            return jsonify({"success": False, "error": "slug 不存在"}), 404
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/by-name-zh/<name_zh>")
    def pokemon_by_name_zh(name_zh):
        """根据中文名查询宝可梦，返回所有匹配的variants（用于form下拉）"""
        try:
            detector = get_detector()
            db = detector.db
            name_en = db.name_zh_to_en(name_zh)
            if not name_en:
                return jsonify({"success": False, "error": f"中文名 '{name_zh}' 不存在"}), 404

            variants = detector.get_variants_by_name(name_en)
            if not variants:
                return jsonify({"success": False, "error": f"英文名 '{name_en}' 不存在"}), 404

            result = []
            for v in variants:
                sprite_filename = v.sprite_filename
                sprite_key = f"sprites/champions/{sprite_filename}" if sprite_filename else None
                result.append({
                    "id": v.id,
                    "name": v.name,
                    "slug": v.slug,
                    "form": v.form or "",
                    "sprite_key": sprite_key,
                    "types": v.types,
                })
            return jsonify({"success": True, "variants": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/detect-card-by-name-form/<name_zh>/<form>")
    def pokemon_detect_card_by_name_form(name_zh, form):
        """根据中文名和form查询 detect_card"""
        try:
            detector = get_detector()
            card = detector.get_detect_card_by_name_and_form(name_zh, form if form != "_none" else "")
            if card:
                return jsonify({"success": True, "card": card})
            return jsonify({"success": False, "error": f"未找到: {name_zh}/{form}"}), 404
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/generate-opponent", methods=["POST"])
    def generate_opponent_team():
        """从对方队伍截图生成队伍，保存到 data/opp_team/temp.json"""
        try:
            screenshot_path = OPP_SCREENSHOTS_DIR / "team.png"

            if not screenshot_path.exists():
                return jsonify({"success": False, "error": "缺少对方队伍截图。请先截取对方队伍"}), 400

            team = detect_opponents_team(str(screenshot_path))

            output_path = OPP_TEAM_DIR / "temp.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            team_data = {
                "trainer_name": team.get("trainer_name", ""),
                "roster": [p.to_dict() if hasattr(p, 'to_dict') else p for p in team.get("roster", [])]
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(team_data, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "team": team_data,
                "slot": "temp"
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/damage/range", methods=["GET", "POST"])
    def damage_range():
        """点击我方技能后，返回该技能对对方全队的伤害范围。"""
        try:
            body = request.get_json(silent=True) or {}
            if request.method == "GET" and not body:
                payload = request.args.get("payload", "")
                body = json.loads(payload) if payload else {}
            attacker = body.get("attacker") or {}
            move_index = _to_int(body.get("move_index"), -1)
            opp_team = body.get("opp_team") or []
            battle_mode = body.get("battle_mode") or "double"
            if battle_mode not in ("single", "double"):
                battle_mode = "double"

            moves = attacker.get("moves") or []
            if move_index < 0 or move_index >= len(moves):
                return jsonify({"success": False, "error": "无效的技能索引"}), 400

            move = moves[move_index]
            if not move or move.get("power") is None:
                return jsonify({"success": False, "error": "该技能非伤害技能"}), 400
            is_spread = _is_spread_move(move)
            is_guaranteed_critical = _is_guaranteed_critical_move(move)

            rows = []
            for opp in opp_team:
                range_info = _compute_damage_range(attacker, opp, move)
                if range_info is None:
                    continue
                range_info = _apply_guaranteed_critical_modifier(range_info, is_guaranteed_critical)
                range_info = _apply_spread_modifier(range_info, battle_mode, is_spread)
                hp_min, hp_max = _stat_min_max((opp.get("stats") or {}).get("hp"))
                rows.append({
                    "opp_name": opp.get("name", ""),
                    "opp_name_zh": opp.get("name_zh", ""),
                    "opp_types": opp.get("types", []),
                    "opp_hp_min": hp_min,
                    "opp_hp_max": hp_max,
                    "range": range_info,
                })

            rows.sort(
                key=lambda item: (
                    item["range"]["hp_pct_max"],
                    item["range"]["hp_pct_min"],
                ),
                reverse=True,
            )
            return jsonify({
                "success": True,
                "move_name": move.get("name", ""),
                "move_name_zh": move.get("name_zh", ""),
                "move_priority": _to_int(move.get("priority"), 0),
                "battle_mode": battle_mode,
                "is_spread_move": is_spread,
                "is_guaranteed_critical": is_guaranteed_critical,
                "is_multi_hit": _is_multi_hit_move(move),
                "rows": rows,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return app


def main():
    parser = argparse.ArgumentParser(description="采集卡视频预览服务器 + API")
    parser.add_argument("--port", type=int, default=8765, help="服务器端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    app = create_app()
    print(f"🎥 采集卡预览服务器启动: http://localhost:{args.port}")
    print(f"📁 截图保存位置: {SCREENSHOTS_DIR}")
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
